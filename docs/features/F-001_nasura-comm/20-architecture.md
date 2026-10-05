---
kind: AD
feature: F-001
status: draft
---

# F-001 基本設計

## 全体図

```
┌──────────── 操縦ブース ────────────┐              ┌──────────── NASURA ────────────┐
│                                    │              │                                 │
│  [Quest 3S]                        │              │  [車載 Ubuntu PC]               │
│   quest page (WebXR)               │              │   car_media (Chromium kiosk)    │
│     ▲ S1: 360映像+車載音声 ────────┼──────────────┼──── X4 / 車載マイク             │
│     │ WS: 入力 30Hz                │              │     ▼ S2: パイロット映像+音声   │
│     ▼                              │   tailnet    │       → モニタ全画面・スピーカ │
│  [中間サーバ]                      │══════════════│                                 │
│   hub (Python)                     │              │   car_ctrl (Python)             │
│     ├ HTTPS配信 / WS シグナリング  │              │     ├ 安全状態機械              │
│     ├ 入力→High-level命令          │── S3 (DC) ───┼──   ├ UDP out 127.0.0.1:47001   │
│     └ heartbeat / RTT              │              │     └ UDP in  127.0.0.1:47002   │
│   booth page (Chromium)            │              │            ▲ テレメトリ投入     │
│     └ パイロットカメラ・マイク ── S2 ┼──────────────┼──→ car_media                    │
└────────────────────────────────────┘              └─────────────────────────────────┘
```

## 設計項目

### AD-0001: ノード配置と責務分担

covers: REQ-0001, REQ-0017
verify: review

5つのノードで構成する。

| ノード | 場所 | 実装 | 責務 |
|---|---|---|---|
| hub | 中間サーバ | Python (aiohttp + aiortc) | ページ配信、シグナリング、入力→命令変換、heartbeat、監視集約 |
| booth | 中間サーバ | ブラウザ | パイロットのカメラ・マイク送信、E-STOP UI、監視表示、S1 の受信・表示と quest への再送（S4、既定のリレー経路）、S1 の送信設定の切替 |
| quest | Quest 3S | WebXR | 360°映像・車載音声の受信と描画、コントローラ入力の送信 |
| car_media | 車載PC | Chromium (kiosk) | X4・車載マイク送信、パイロット映像・音声の表示再生 |
| car_ctrl | 車載PC | Python (aiortc) | 制御受信、安全状態機械、ローカルUDP入出力 |

Quest には映像再生・頭部追従・入力生成だけをさせる。車載PCは映像の再エンコード・視野切り出しを行わない（ブラウザのエンコーダのみ使用）。

### AD-0002: セッションを3本に分割する

covers: REQ-0002, REQ-0003, REQ-0004, REQ-0005, REQ-0006, REQ-0015
verify: test

| ID | 経路 | 中身 | offerer / answerer |
|---|---|---|---|
| S1 | car_media → quest | 360°映像＋車載音声 | car_media / quest |
| S2 | booth → car_media | パイロット映像＋音声 | booth / car_media |
| S3 | car_ctrl ⇄ hub | DataChannel（制御・テレメトリ） | car_ctrl / hub |
| S4 | booth → quest | 360°映像＋車載音声（S1 の再送） | booth / quest |

既定（`--s1-route relay`、2026-10-05）では S1 の受け手を booth とし、booth が受けた映像・音声をそのまま S4 で quest へ送り直す。ブースでもロボ側の映像を見られ、車載PCの上りは1本のままである。`--s1-route direct` では S1 の受け手を quest とし、S4 は使わない（10-04 までの構成）。

メディアの送信側を offerer とする。S3 は車載側から張る。セッションを分けることで、映像の輻輳・再接続が制御の配送に影響しない。

### AD-0003: メディアはブラウザの WebRTC に任せる

covers: REQ-0007, REQ-0008, REQ-0009
verify: review

- 圧縮・レート適応はブラウザ（WebRTC）の責任とし、アプリは生のカメラ映像と上限値を渡すだけにする。
- 上限は `RTCRtpSender.setParameters`（maxBitrate / maxFramerate）で与え、優先方針は `MediaStreamTrack.contentHint` で与える。
  - S1：`motion`（フレームレート維持）。X4 を 2880×1440 で取り込み、送信設定を2つ持つ。booth から切り替える（再接続なし、`maxBitrate` と `scaleResolutionDownBy` を変える）。
    - 制限（既定）：解像度 ÷1.5（1920×960）、上限 3.6 Mbps
    - フルスペック：解像度そのまま、上限 12 Mbps（会場の上りに余裕があるときだけ使う）
  - S2：`detail`（解像度維持）、640×480・15 fps・上限 400 kbps
- 音声は Opus、上限 32 kbps。エコーキャンセルはブラウザ標準を有効にする。
- メディアの中継は hub（Python）では行わない。既定のリレー経路では、中間サーバの booth ページ（ブラウザ）が S1 を受けて S4 で再エンコードして送る（ブースLAN 内、上限 15 Mbps）。再エンコード1回分の画質低下と遅延の増加、booth ページが閉じると Quest の映像も止まることを許容する（本人の指示、2026-10-05：ブースでロボ側映像を見る、上りを増やさない）。再エンコードしない SFU は依存とインフラの追加が大きいので、11 月の本番に向けて別途検討する。
- 直結経路（`--s1-route direct`）では、S1 は車載PC と Quest の間を tailnet で直接流れる。

上り帯域予算：

| 項目 | 上限 |
|---|---|
| S1 映像（制限） | 3,600 kbps |
| S1 音声 | 32 kbps |
| S3 上り（ack・state・テレメトリ） | 100 kbps |
| 余裕（RTP/ICE オーバーヘッド） | 約 270 kbps |
| **合計** | **4,000 kbps 以内** |

フルスペックに切り替えている間は、この予算を超える（REQ-0007 の対象外）。

### AD-0004: シグナリングは hub の WebSocket に集約する

covers: REQ-0017, REQ-0018
verify: test

- 全ノードは hub の `wss://<hub>/ws` に接続し、自分の role を名乗る（hello）。
- hub は role ごとに接続を1本だけ保持する（同じ role が再接続したら古い接続を閉じる）。
- セッションの両端が揃った時点で、hub は offerer に `restart` を送り、offerer は新しい PeerConnection を作って offer する。片端が切れたら、残った側に `peer down` を通知する。
- ICE は trickle。STUN/TURN サーバは使わず（`iceServers: []`）、tailnet 上の host 候補（`100.x` のアドレス）だけで接続する。
- 各ページは ICE の失敗・3秒以上の切断を検出したら hub に `restart_req` を送る。WebSocket 自体は指数バックオフ（1→2→4→5秒上限）で再接続する。

### AD-0005: 制御プレーン

covers: REQ-0006, REQ-0015
verify: test

- Quest → hub：シグナリングと同じ WebSocket（tailnet 経由）で、入力を 30 Hz で送る。
- hub：入力を High-level 命令（`cmd/drive`・`cmd/stage`）に変換する。変換規則は差し替え可能な純粋関数に閉じ込める。
- hub → car_ctrl：S3 の DataChannel 2本で送る。
  - `ctrl`：順序保証なし・再送なし。最新値だけに意味があるもの（命令・heartbeat）
  - `rel`：順序保証・確実配送。取りこぼしが許されないもの（E-STOP・状態・拡張の一部）

### AD-0006: 共通エンベロープと topic 登録表

covers: REQ-0013, REQ-0014
verify: test

- 全メッセージを共通エンベロープ `{topic, ver, seq, ts, src, payload}`（JSON）で包む。
- topic は2種類。
  - **固定 topic**（`sys/*`・`cmd/*`・`in/*`・`out/*`）：安全に関わるため処理をコードに直書きし、登録表で上書きできない。
  - **拡張 topic**（`tlm/*` など）：登録表に「方向・チャネル（ctrl/rel）・最大レート」を宣言して追加する。
- 受信側は未登録 topic を捨て、topic ごとに件数を数え、初回だけログに出す。
- 登録表の正本は Python（`topics.py`）に1つだけ置き、ブラウザには hub が `/topics.json` として配る。人が JSON/YAML を手書きしない。

### AD-0007: 安全機構を多層にする

covers: REQ-0010, REQ-0011, REQ-0012
verify: test

| 層 | 場所 | 条件 | 動作 |
|---|---|---|---|
| L1 | hub | Quest 入力が 300 ms 途絶（ヘッドセットを外した場合など） | 停止命令を送る |
| L2 | car_ctrl | heartbeat が 1,200 ms 途絶、または S3 切断 | 状態 STOP、実効命令を停止 |
| L3 | car_ctrl | 命令が 300 ms 更新されない | その命令を停止値にする |
| L4 | car_ctrl | `sys/estop` 受信 | 状態 ESTOP にラッチ。`sys/estop_release` までは全命令無視 |
| L5 | 下流（範囲外） | UDP out が 200 ms 途絶、または state ≠ RUN | 停止（I/F 契約として規定） |

heartbeat だけ届いて命令が古い、という状況を L1 と L3 で潰す。

競技中の暴走を物理的に止める責任は介添人が負う。通信途絶による停止（L2）は補助機能と位置づけ、回線の瞬断で誤停止しないよう timeout を長めに取る（DEV-0005）。E-STOP の解除はブースからだけ受け付ける。

### AD-0008: 車載のローカル I/F

covers: REQ-0014, REQ-0016
verify: test

- **UDP out**（`127.0.0.1:47001`）：car_ctrl が 20 Hz で `out/effective`（安全判定後の実効命令と状態）を1データグラムで送る。受け手（将来の Drive/Arm アダプタ）はこれだけを見ればよい。
- **UDP in**（`127.0.0.1:47002`）：車載のローカルモジュールがエンベロープ形式のテレメトリを投げ込む。car_ctrl は登録表で検証・レート制限し、S3 で hub へ送る。hub は quest・booth に配る。

### AD-0009: 監視

covers: REQ-0019
verify: test

- car_ctrl は heartbeat に即 ack を返し、hub が RTT を計算する（最新値と EWMA）。
- 各ページは 2 秒ごとに `getStats()` の要約（ビットレート・fps・フレーム落ち・選択された候補ペアの種別・RTT）を WebSocket で hub に送る。
- hub は `/status`（JSON）で接続状態・セッション状態・RTT・車載の安全状態・stats・破棄件数を返す。booth ページが 1 Hz で取得して表示する。

### AD-0010: ネットワーク構成

covers: REQ-0017
verify: review

- hub は `127.0.0.1:8080` で待ち受け、`tailscale serve` で HTTPS 化して `https://<hub>.<tailnet>.ts.net/` として公開する。
- Quest 3S にも Tailscale を入れて tailnet に参加させる（本人が設定済み）。全ノードが tailnet 上にあるので、subnet router は使わない。会場ごとに変わるブースLAN の CIDR に依存しない。
- Quest ページは起動時にマイク権限を取得してすぐ解放する。Chromium は権限が無いと自分の host 候補を mDNS 名（`.local`）で隠すため、車載から Quest の実IPが見えず S1 が張れなくなるのを防ぐ。
- S1 は車載PC と Quest の tailnet アドレス同士で張る。Quest の Tailscale が切れている（VPN が無効）と、S1 も quest ページの表示もできない。

## リスク

| ID | リスク | 影響 | 対処 |
|---|---|---|---|
| R-1 | Quest の Tailscale が無効、または `*.ts.net` を名前解決できない | quest ページが開けない、S1 が張れない | Quest を tailnet に参加させ、MagicDNS を有効にする（本人が設定済み）。どうしても使えない場合は hub を `--bind 0.0.0.0 --tls-self-signed` で出し、Quest で証明書警告を一度許可する（この場合 S1 の経路は別途確認が要る） |
| R-2 | 車載 Chromium の映像エンコードがソフトウェアになり CPU が足りない | S1 のフレーム落ち | `--s1-codec` で H264/VP8 を切替、解像度を下げる。ST-0012 で CPU を測る |
| R-3 | 主催者回線で UDP が通らず Tailscale が DERP 中継になる | 遅延・帯域の悪化 | 現地で `tailscale ping` を確認（ST-0011）。本Featureでは対処しない |
| R-4 | 認証が無い | tailnet 内の誰でも操作できる | tailnet の ACL で担保。PoC では許容 |
| R-5 | 下り帯域が不明 | S2 が劣化 | S2 は 400 kbps に抑えてあり、ブラウザのレート適応に任せる |
