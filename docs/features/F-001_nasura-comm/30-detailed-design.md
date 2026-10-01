---
kind: DD
feature: F-001
status: draft
---

# F-001 詳細設計

## ソース構成

```
src/nasura_comm/
  __init__.py
  envelope.py        # DD-0001
  topics.py          # DD-0002
  filters.py         # DD-0003  SeqFilter / RateLimiter
  mapping.py         # DD-0004
  control.py         # DD-0005  ControlCore (hub side, pure)
  safety.py          # DD-0006  SafetyCore (car side, pure)
  local_io.py        # DD-0007  effective-command builder + UDP transport
  signaling.py       # DD-0008  SignalRouter (pure)
  config.py          # DD-0009  defaults + CLI overrides
  datachannel.py     # DD-0010  channel option builder + aiortc glue
  log.py             # DD-0016
  clock.py           # monotonic / epoch ms (I/O layer only)
  hub/app.py         # aiohttp app wiring (DD-0009)
  hub/__main__.py    # entry point
  car/app.py         # car_ctrl wiring (DD-0010)
  car/__main__.py    # entry point
web/
  common/signaling.js, rtc.js, stats.js   # DD-0011
  car/index.html, car.js                  # DD-0012
  booth/index.html, booth.js              # DD-0013
  quest/index.html, quest.js, input.js, xr-view.js   # DD-0014
  vendor/                                 # vendored libraries if needed (no CDN)
scripts/
  run_hub.sh, run_car.sh, fake_telemetry.py, dump_effective.py   # DD-0015
tests/unit, tests/integration, tests/e2e
```

依存：Python 3.10 以上、`aiohttp`、`aiortc`。純粋ロジック（envelope / topics / filters / mapping / control / safety / signaling）は時刻を引数で受け取り、I/O を持たない。I/O は `hub/`・`car/`・`local_io.py`・`datachannel.py` に閉じ込める。

時刻は全て **ミリ秒の整数**。`ts` は送信側の UNIX epoch ms、タイムアウト判定は受信側の monotonic ms で行う（送受信間の時計ずれに依存しない）。

---

## 設計項目

### DD-0001: エンベロープ（envelope.py）

covers: AD-0006
verify: test

```json
{"topic": "cmd/drive", "ver": 1, "seq": 1234, "ts": 1790000000000, "src": "hub", "payload": {}}
```

| キー | 型 | 規則 |
|---|---|---|
| topic | str | `^[a-z0-9_]+(/[a-z0-9_]+)+$`、64文字以内 |
| ver | int | ≥ 1。受信側は知っている ver 以下のみ処理、超えていれば破棄 |
| seq | int | ≥ 0。送信元×topic ごとに単調増加 |
| ts | int | 送信時の epoch ms |
| src | str | `hub` / `quest` / `booth` / `car_ctrl` / `car_local` |
| payload | object | topic ごとの定義に従う |

- `make(topic, payload, src, seq, ts, ver=1) -> dict`
- `encode(env) -> str`（JSON、区切りは `(",", ":")`）
- `decode(text) -> Envelope | None`：JSON不正・キー欠落・型不正・topic 形式違反のいずれでも例外を投げず `None` を返す。
- 1メッセージの上限は 16 KiB。超えたものは `None`。

### DD-0002: topic 登録表（topics.py）

covers: AD-0006
verify: test

```python
@dataclass(frozen=True)
class TopicSpec:
    name: str
    direction: Literal["down", "up"]   # down: hub->car, up: car->hub
    channel: Literal["ctrl", "rel"]
    max_rate_hz: float | None          # None = no limit
    fixed: bool                        # True = safety/core topic, handled in code
    ver: int = 1
```

初期登録（固定 topic）：

| topic | 方向 | ch | 最大Hz | payload |
|---|---|---|---|---|
| sys/heartbeat | down | ctrl | 10 | `{hb:int, t_hub:int}` |
| sys/heartbeat_ack | up | ctrl | 10 | `{hb:int, t_hub:int, state:str}` |
| sys/estop | down | rel | — | `{source:"quest"\|"booth"\|"hub", reason:str}` |
| sys/estop_release | down | rel | — | `{source:"booth"}` |
| sys/state | up | rel | 5 | `{state:"INIT"\|"RUN"\|"STOP"\|"ESTOP", since:int, reason:str, dropped:{key:int}}` |
| cmd/drive | down | ctrl | 30 | `{v:float, w:float, deadman:bool}` |
| cmd/arm | down | ctrl | 30 | `{enable:bool, clutch_id:int, p:[x,y,z], q:[x,y,z,w], grip:float}` |
| cmd/stage | down | ctrl | 30 | `{x:float, z:float}` |

`in/*`（ブラウザ→hub、WebSocket のみ）と `out/*`（car_ctrl→ローカルUDP のみ）も固定扱いだが、S3 には流れない。

拡張 topic は `EXTENSIONS: list[TopicSpec]` に追記する。初期は空。記入例をコメントで残す：

```python
# TopicSpec("tlm/battery_voltage", "up", "ctrl", 2.0, fixed=False)
```

- `sys/state` の `dropped` は car_ctrl の UDP in で破棄した件数（DD-0007 の分類キーごとの累計）。hub はこれを `/status` の `dropped` に合算する。
- `lookup(name) -> TopicSpec | None`
- `EXTENSIONS` に固定 topic と同名、または `sys/`・`cmd/`・`in/`・`out/` で始まる名前があれば、import 時に `ValueError`。
- `to_json() -> dict`：ブラウザ配布用。
- 登録表の実体は `Registry(extensions)`（固定 topic＋検証済みの拡張）。モジュール関数 `lookup` / `to_json` は既定の登録表（`EXTENSIONS`）に委譲する。
- 試験用に、hub と car_ctrl は CLI `--extra-topic NAME:DIR:CHANNEL:HZ` で拡張 topic を起動時に追加できる（IT-0004・ST-0013 用。人が設定ファイルを書かない方針は変えない）。

意味：
- `v`・`w`・`x`・`z` は正規化値 [-1, 1]。物理単位への換算は下流で行う。`w` は正で反時計回り（左旋回）、ROS REP-103 に合わせる。
- `cmd/arm` の `p`（m）・`q`（四元数 xyzw）は、クラッチ開始時の右コントローラ姿勢からの相対姿勢。座標系は WebXR `local-floor`（右手系、y 上、-z 前）。`grip` は [0, 1]。

### DD-0003: SeqFilter と RateLimiter（filters.py）

covers: AD-0006
verify: test

- `SeqFilter.accept(src, topic, seq) -> bool`：`ctrl` チャネルは順序保証が無いので、同じ (src, topic) で過去に受けた最大 seq 以下のものを捨てる。送信元の再起動で seq が戻ることに備え、`seq < last - 1000` のときはリセットとみなして受け入れる。
- `RateLimiter.allow(topic, now_ms) -> bool`：`max_rate_hz` から間隔 `1000 / hz` ms を求め、仮想的な予定時刻（許可するたびに間隔ぶん進める）より間隔の 20 % 以上早く来たものを拒否する（GCRA）。宣言どおりのレートで送る送信元が時刻の揺らぎで間引かれないようにし、長期のレートは `max_rate_hz` に保つ。`None` は常に許可。

### DD-0004: Quest 入力 → 命令変換（mapping.py）

covers: AD-0005
verify: test

入力 `in/quest` の payload：

```json
{"left":  {"axes": [x, y], "trigger": 0.0, "grip": 0.0, "x": false, "y": false, "thumb": false, "pose": null},
 "right": {"axes": [x, y], "trigger": 0.0, "grip": 0.0, "a": false, "b": false, "thumb": false,
           "pose": {"p": [x, y, z], "q": [x, y, z, w]}}}
```

`axes` は Gamepad API の thumbstick（上が y<0）。`pose` は `local-floor` の grip 姿勢で、取れなければ null。

`Mapper`（状態：クラッチ基準姿勢、clutch_id）。`map(inp) -> (drive, arm, stage)`：

| 出力 | 規則（初期値。差し替え可） |
|---|---|
| deadman | `left.grip > 0.5` |
| drive | デッドゾーン 0.15（放射状、外側は 0〜1 に再スケール）後、`v = -left.y`、`w = -left.x`。deadman が false なら v = w = 0 |
| arm.enable | `right.grip > 0.5` かつ `right.pose` あり |
| arm クラッチ | enable の立ち上がりで基準姿勢を保存し `clutch_id += 1`。`p = pose.p - ref.p`、`q = ref.q⁻¹ ⊗ pose.q`（正規化） |
| arm（非enable） | `enable=false, p=[0,0,0], q=[0,0,0,1]`、clutch_id は据え置き |
| arm.grip | `right.trigger` |
| stage.x | `a` 押下で +1、`b` 押下で -1、両方・無しで 0。deadman が false なら 0 |
| stage.z | デッドゾーン後の `-right.y`。deadman が false なら 0 |
| E-STOP | `left.thumb and right.thumb`（両スティック押し込み）→ Quest ページ側で `in/estop` を送る（DD-0014） |

### DD-0005: hub 制御コア（control.py）

covers: AD-0005, AD-0007
verify: test

`ControlCore(mapper, input_timeout_ms=300, hb_period_ms=100, cmd_period_ms=33)`。I/O を持たず、送るべきエンベロープの列を返す。

- `on_input(env, now)`：`in/quest` を保存し受信時刻を記録。`in/estop` → 直ちに `sys/estop`（rel）を返し、`latched = True`。`in/estop_release` は `src == "booth"` のときだけ `sys/estop_release` を返し `latched = False`。それ以外の src からの release は無視してログ。
- `on_car(env, now)`：`sys/heartbeat_ack` → `rtt_ms = now - t_hub` を更新（最新値と EWMA α=0.2）。`sys/state` → 車載状態を保存。
- `tick(now) -> list[env]`：
  - `cmd_period_ms` ごとに `cmd/drive`・`cmd/arm`・`cmd/stage` を出す。入力が `input_timeout_ms` より古い、入力が一度も無い、または `latched` のときは停止値（drive 0/0/false、arm enable=false、stage 0/0）。入力途絶で停止値に切り替わった時点では、周期を待たずにすぐ出す。
  - `hb_period_ms` ごとに `sys/heartbeat`（hb は連番、t_hub = now）。
- seq は topic ごとに ControlCore が採番する。
- `on_link_up(now)`：S3 が（再）確立したとき、`latched` なら `sys/estop` を再送する（ラッチ中に S3 が張り直された場合も車載を ESTOP に揃えるため）。

※ tick の now は monotonic ms を使い、heartbeat の t_hub も同じ monotonic ms にする（RTT は hub 内で閉じるため）。エンベロープの `ts` は epoch ms を別に入れる。

### DD-0006: 車載安全状態機械（safety.py）

covers: AD-0007
verify: test

`SafetyCore(hb_timeout_ms=1200, cmd_timeout_ms=300)`。heartbeat timeout の根拠は AD-0007 と DEV-0005。

状態遷移：

| 現状態 | イベント | 次状態 |
|---|---|---|
| INIT | heartbeat 受信 | RUN |
| RUN | heartbeat が hb_timeout_ms 途絶 / `on_link_down()` | STOP |
| STOP | heartbeat 受信 | RUN |
| 任意 | `sys/estop` 受信 | ESTOP |
| ESTOP | `sys/estop_release` 受信 | STOP |
| ESTOP | heartbeat・命令 | ESTOP のまま（無視） |

- STOP・ESTOP へ入るときは保持している最新命令を全て破棄する（復帰直後に古い命令で動かないため）。
- `on_envelope(env, now)`：cmd/* は最新値と受信時刻を保存（RUN のときだけ）。
- `effective(now) -> dict`：
  - RUN かつ命令が cmd_timeout_ms 以内：その命令。ただし drive は `deadman == false` なら 0/0。
  - それ以外：停止値。
- 状態が変わったら `sys/state` を1回出すためのフラグを立てる。変化が無くても 1 Hz で出す（car 側ループが担当）。

### DD-0007: 車載ローカル I/O（local_io.py）

covers: AD-0008
verify: test

**UDP out**：`build_effective(state, eff, seq, ts) -> dict`。

```json
{"topic": "out/effective", "ver": 1, "seq": 42, "ts": 1790000000000, "src": "car_ctrl",
 "payload": {"state": "RUN",
             "drive": {"v": 0.0, "w": 0.0},
             "arm":   {"enable": false, "clutch_id": 3, "p": [0,0,0], "q": [0,0,0,1], "grip": 0.0},
             "stage": {"x": 0.0, "z": 0.0}}}
```

- 20 Hz（50 ms）で `127.0.0.1:47001` へ送る。状態に関係なく送り続ける。
- **下流との I/F 契約**：受け手は、最後の受信から 200 ms 経過、または `state != "RUN"` のとき停止すること。（本Featureの範囲外だが、I/F 契約としてここに固定する）

**UDP in**：`127.0.0.1:47002` で待ち受け。データグラム＝エンベロープ1個（`src` は `car_local` に上書き）。

1. `decode` 失敗 → 破棄（`dropped["invalid"]`）
2. `lookup(topic)` が None、または direction ≠ up、または fixed → 破棄（`dropped[topic]`、初回だけログ）
3. RateLimiter 拒否 → 破棄（`dropped["rate:"+topic]`）
4. 登録どおりのチャネルで hub へ送る

### DD-0008: シグナリングプロトコル（signaling.py）

covers: AD-0004
verify: test

WebSocket 上の JSON メッセージ（エンベロープとは別の層）：

| 方向 | type | 内容 |
|---|---|---|
| C→H | `hello` | `{role}` |
| H→C | `welcome` | `{config, topics}` |
| C→H / H→C | `signal` | `{session, data}`。data は `{sdp:{type,sdp}}` または `{candidate:{...}\|null}` |
| H→C | `restart` | `{session}`：offerer に新しい offer を要求 |
| C→H | `restart_req` | `{session}`：ICE 失敗時にページから要求 |
| H→C | `peer` | `{session, state:"down"}`：相手が切れた |
| C→H | `env` | `{env}`：`in/quest`・`in/estop`・`in/estop_release` |
| H→C | `env` | `{env}`：`sys/state`・`tlm/*` を quest・booth へ配信 |
| C→H | `stats` | `{session, data}`：DD-0011 の要約 |

`SignalRouter`（純粋。接続オブジェクトは不透明なハンドルとして扱う）：

- セッション表 `S1: car_media→quest`、`S2: booth→car_media`、`S3: car_ctrl→hub`（hub は内部ピア）。
- `on_hello(role, handle) -> actions`：同じ role の旧ハンドルがあれば `close(old)`。その role を含む各セッションで両端が揃えば offerer に `restart`。
- `on_signal(from_role, session, data) -> actions`：from_role がそのセッションの端でなければ破棄。相手へ転送（S3 の相手が hub なら内部ピアへ渡す）。
- `on_restart_req(from_role, session)`：両端が揃っていれば offerer に `restart`。
- 旧ハンドルの `close` は WebSocket の close code 4001（replaced）で行う。ブラウザはこのコードで閉じられたら再接続しない（同じ role の画面が2つあるときに互いを追い出し続けるのを防ぐ）。
- `on_close(role, handle)`：ハンドルが現行のものでなければ無視（置き換え済みの旧接続）。現行なら削除し、その role を含むセッションの相手に `peer down`。
- 不明な role・session・type は破棄してログ。
- 認証は行わない（R-4）。

### DD-0009: hub サーバと設定（hub/__main__.py, config.py）

covers: AD-0004, AD-0009
verify: test

ルート（aiohttp、既定 `127.0.0.1:8080`）：

| パス | 内容 |
|---|---|
| `/` | 各ページへのリンク |
| `/quest/` `/booth/` `/car/` `/common/` `/vendor/` | `web/` の静的配信 |
| `/config.json` | メディア設定（下表） |
| `/topics.json` | `topics.to_json()` |
| `/status` | 監視 JSON（下記） |
| `/ws` | WebSocket（DD-0008） |

メディア設定の既定値（`config.py` の dataclass。CLI で上書き可）：

| キー | S1 | S2 |
|---|---|---|
| width × height | 1920 × 960 | 640 × 480 |
| fps | 30 | 15 |
| max_bitrate (bps) | 2,500,000 | 400,000 |
| content_hint | motion | detail |
| codec | auto | auto |
| audio_max_bitrate | 32,000 | 32,000 |
| device_label | `Insta360` | （既定カメラ） |

その他：`up_budget_bps = 3,000,000`。CLI：`--port --bind --s1-width --s1-height --s1-fps --s1-max-bitrate --s1-codec --s1-device-label --s2-max-bitrate --tls-self-signed --web-dir --log-dir --extra-topic`。人が設定ファイルを手書きしない。`--tls-self-signed` は `openssl` で `.certs/` に自己署名証明書を1回だけ作る。

`build_config_json(cfg) -> dict` と `build_status(state) -> dict` は純粋関数にする。`/status` の形：

```json
{"roles": {"quest": true, "booth": true, "car_media": true, "car_ctrl": true},
 "sessions": {"S1": "connected", "S2": "connecting", "S3": "connected"},
 "control": {"rtt_ms": 42, "rtt_ewma_ms": 45, "car_state": "RUN", "latched": false,
             "last_input_age_ms": 20},
 "stats": {"S1": {...}, "S2": {...}},
 "dropped": {"tlm/unknown": 3},
 "telemetry": {"tlm/battery_voltage": {...}},
 "up_budget_bps": 3000000}
```

セッション状態は、S1・S2 は各ページの stats 報告（`data.state` に `connectionState`）から、S3 は hub 側 aiortc の状態から得る。`telemetry` は拡張 topic ごとの最新 payload。S3 が確立し直したら RTT を null に戻す（前の接続の値を表示しない）。hub はブラウザから来た `env` の `src` を接続の role で上書きする（申告された src を信用しない）。

### DD-0010: S3 DataChannel（datachannel.py）

covers: AD-0005
verify: test

- `channel_options(name) -> dict`：`ctrl` → `{"ordered": False, "maxRetransmits": 0}`、`rel` → `{"ordered": True}`。
- car_ctrl（offerer）が `RTCPeerConnection(RTCConfiguration(iceServers=[]))` を作り、2本のチャネルを作成して offer する。hub は answer し、`ondatachannel` でラベルから振り分ける。
- 受信処理：`decode` → `ctrl` なら SeqFilter → ControlCore / SafetyCore へ。
- car_ctrl は hub の WebSocket が切れた、または PC が `failed`/`closed` になったら `SafetyCore.on_link_down()` を呼び、2秒後に再接続する。
- car_ctrl の周期処理：20 Hz で UDP out、1 Hz と状態変化時に `sys/state`、heartbeat 受信時に即 `sys/heartbeat_ack`。状態が変わったとき、および実効命令の drive が動作中から 0/0 に変わったときは、周期を待たずに UDP out を1回送る（IT-0007 の 350 ms を満たすため）。
- car_ctrl の CLI：`--hub URL --insecure --udp-out HOST:PORT --udp-in HOST:PORT --log-dir --extra-topic`、試験用の `--ack-delay-ms`（IT-0006 の人工遅延）。

### DD-0011: ブラウザ共通部（web/common）

covers: AD-0003, AD-0004
verify: review

- `signaling.js`：`wss://${location.host}/ws` に接続して hello。切断時は 1→2→4→5 秒上限で再接続。`on(type, fn)` / `send(type, body)`。
- `rtc.js`：`createSession({session, role, stream, cfg, sig, onTrack})`
  - `new RTCPeerConnection({iceServers: []})`
  - 送信側：トラックに `contentHint` を設定して addTrack。codec が auto 以外なら `transceiver.setCodecPreferences` で先頭に並べる。接続後に `sender.setParameters` で `maxBitrate`・`maxFramerate` を適用（映像・音声それぞれ）。
  - `restart` 受信で古い PC を閉じて作り直し、offer。
  - `iceConnectionState` が `failed`、または `disconnected` が 3 秒続いたら `restart_req`。
  - offerer は、セッションを作った時点で WebSocket が接続済みなら `restart_req` を送る（メディア取得を待つ間に hub の `restart` を取りこぼした場合の補償）。
- `signaling.js` は close code 4001（replaced）で閉じられたら再接続せず、画面に「置き換えられた」と表示する。
- `stats.js`：2 秒ごとに `getStats()` を要約して `stats` 送信：送受信 kbps、fps、framesDropped、jitter、選択候補ペアの `currentRoundTripTime`・local/remote の candidateType。

### DD-0012: car_media ページ（web/car）

covers: AD-0002, AD-0003
verify: review

- 起動時に `getUserMedia({audio:true, video:true})` で権限を取ってから `enumerateDevices`、ラベルに `device_label` を含む videoinput を選び、S1 の解像度・fps で取り直す。見つからなければ画面に赤字で表示し、既定カメラで続行する。
- 音声：`echoCancellation: true, noiseSuppression: true, autoGainControl: true`。パイロット音声を同じページで再生するのでエコーキャンセルが効く。
- S1 offerer（→quest）、S2 answerer（←booth）。
- パイロット映像を `<video autoplay playsinline>` で全画面（`object-fit: contain`、背景は黒。車載モニタが高輝度なため白を避ける）。
- 右上に小さく接続状態（S1/S2 の状態）を表示。`h` キーで表示切替。

### DD-0013: booth ページ（web/booth）

covers: AD-0002, AD-0007, AD-0009
verify: review

- `getUserMedia` で S2 設定の映像＋マイク。ローカルプレビュー。S2 offerer（→car_media）。
- **E-STOP ボタン**（大きく赤）と `Escape` キー → `in/estop`（source=booth）。
- **解除ボタン**：2秒以内に2回押すと `in/estop_release`（`confirm()` 等のブラウザダイアログは使わない）。
- 1 Hz で `/status` を取得し表示：各 role の接続、S1〜S3 の状態、RTT（最新・EWMA）、車載状態（ESTOP/STOP は赤）、S1/S2 のビットレートと fps、S1 上り合計が `up_budget_bps` を超えたら赤、破棄件数。

### DD-0014: quest ページ（web/quest）

covers: AD-0002, AD-0005, AD-0010
verify: review

- 起動時に `getUserMedia({audio:true})` を1回取り、すぐ全トラックを stop する（AD-0010 の mDNS 回避。Quest の音声は送らない）。
- S1 answerer（←car_media）。
- 描画：Mac→Quest テストで動いた既存の XR ビューア（mac-camera-vr の `createWebXR360Renderer`、生 WebGL）を `xr-view.js` として流用する。three.js は使わない。参照空間は `local-floor`（取れなければ `local`）とし、コントローラ姿勢も同じ空間で読む。
- 車載音声は `<audio autoplay>` で再生。Enter VR のクリックでユーザー操作要件を満たす。
- `input.js`：XR フレームループで `inputSources` の gamepad と grip 姿勢（`local-floor`）を読み、30 Hz に間引いて `env`（`in/quest`）を送る。XR セッション外では送らない（hub 側で入力途絶→停止になる）。
- 両スティック押し込みで `in/estop`（source=quest）。押しっぱなしでも 1 秒に1回まで。
- （任意・10/4 必須ではない）車載状態と RTT を視界の隅にテキスト表示。

### DD-0015: 起動スクリプトとネットワーク設定（scripts/）

covers: AD-0001, AD-0010
verify: review

- `run_hub.sh`：venv を有効化して `python -m nasura_comm.hub --port 8080`。初回だけ `tailscale serve --bg 8080` を案内表示。
- `run_car.sh`：`python -m nasura_comm.car --hub wss://<hub>.<tailnet>.ts.net/ws` をバックグラウンド起動し、続けて Chromium を起動：
  ```
  chromium --kiosk --autoplay-policy=no-user-gesture-required \
           --use-fake-ui-for-media-stream https://<hub>.<tailnet>.ts.net/car/
  ```
  （`--use-fake-ui-for-media-stream` は権限ダイアログを自動許可するだけで、実デバイスを使う）
- `fake_telemetry.py`：UDP in に任意 topic を任意レートで投げる検証用ツール。
- `dump_effective.py`：UDP out を受けて1行ずつ表示する検証用ツール（ST-0006・ST-0008。200 ms を超える間隔を GAP と表示）。
- `run_car.sh` は `FAKE_MEDIA=1` で Chromium の fake device を使う（開発機での確認用）。
- README に Tailscale 設定を記載：中間サーバ `tailscale up --advertise-routes=<ブースLAN CIDR>` と管理画面での承認、車載 `tailscale up --accept-routes`。
- 開発機での確認用に、Chromium の `--use-fake-device-for-media-stream` でカメラ無しでも S1/S2 を張れることを README に記載。

### DD-0016: ログ（log.py）

covers: AD-0009
verify: review

- JSON Lines、`logs/<node>-<起動時刻>.jsonl`。
- hub：接続・切断、セッション restart、E-STOP 発行・解除、1 Hz の RTT と車載状態、stats。
- car_ctrl：状態遷移（理由付き）、E-STOP、破棄件数（10秒ごとに差分）。
- 命令本体は毎回は記録しない（量が多い）。状態遷移の前後だけ記録する。
