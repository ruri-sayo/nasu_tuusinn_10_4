# NASURA 通信系 運用手順書（実機構成）

2026-10-04 の実機試験で使う手順である。開発機での確認手順は [README](../README.md) を参照する。

- 対象：F-001 NASURA 通信系 PoC（commit は当日の `git log -1` で記録する）
- 試験項目と合否基準：[60-system-e2e-spec.md](features/F-001_nasura-comm/60-system-e2e-spec.md)（ST-0001〜ST-0013）
- 「要確認」と書いた箇所は、当日までに実機で確かめて埋める。

---

## 00. 2026-10-09 散楽フェスタの構成（中間サーバ＋Quest＋ブース）

本来の構成（1章）で動かす。2026-10-05 の変更で、次の点が 10-04 までと違う。

| 項目 | 10-04 まで | 2026-10-05 以降 |
|---|---|---|
| 360°映像（S1）の経路 | 車載PC → Quest（直結） | 車載PC → **booth ページ（中間サーバ）** → Quest（S4）。booth でもロボ側の映像が見える。車載PCの上りは1本のまま |
| S1 の送信設定 | 起動引数だけ（既定 2.5 Mbps） | 既定は「制限」（2880×1440 を ÷1.5 = 1920×960、上限 3.6 Mbps）。booth のボタンで「フルスペック」（2880×1440、上限 12 Mbps）に**その場で**切り替えられる |
| 正面の合わせ方 | なし | Quest の**左 Y ボタン**で、今向いている方向を正面にする。取付のずれは `--yaw-offset-deg` で固定値を与える |
| ログ | 状態変化と映像統計 | 加えて2秒ごとに CPU 使用率・メモリ・CPU 温度（Linux のみ）を記録し、ディスクへ確実に書き出す（fsync） |

### 00.1 起動（この順に行う）

1. 中間サーバ（Windows 11、PowerShell）：hub を起動する。`tailscale serve --bg 8080` は設定済みであること（2.1）。

   ```powershell
   cd nasu_tuusinn_10_4; uv run python -m nasura_comm.hub --port 8080
   ```

   - 取付のずれを補正するときは `--yaw-offset-deg <度>` を付ける（ロボ正面が 360°画像の中央から右へ何度にあるか。左なら負）。
2. 中間サーバ：Chrome で `https://<HUB>/booth/` を開き、カメラとマイクを許可する。**booth のウィンドウは閉じない・最小化しない**（booth が Quest へ映像を送り直しているため、閉じると Quest の映像も止まる）。
3. 車載PC：`HUB_HOST=<HUB> scripts/run_car.sh`（3.3）。
4. Quest 3S：`https://<HUB>/quest/` を開き、「VR で見る」（3.4）。

### 00.2 確認

- booth：接続がすべて「接続」、S1・S2・S3・**S4** が `connected`、車載状態が `RUN`。
- booth の左上にロボ側の 360°映像（正距円筒のまま）が出る。
- booth の「映像」表：「S1 上り」が 4000 kbps 以下（「制限」のとき）、「S1 エンコーダ（車載）」がハードかソフトか、「S1 ロス」が 2 % 以下。

### 00.3 本番中の操作

| 操作 | 方法 |
|---|---|
| 送信設定を下げる／上げる | booth の「S1 送信」で「制限」／「フルスペック」を押す。再接続なしで数秒以内に変わる。会場の回線が細いときは「制限」のまま使う |
| 正面を合わせる | 操縦者が正面にしたい方向を向いて、**左コントローラの Y** を押す（ヨーのみ。上下・傾きは変えない） |
| Quest の表示がずれたとき | Meta ボタンの長押し（システムの再センタリング）でもよい。そのときは左 Y で合わせた値も初期化される |
| booth で車載音声を聞く | booth の「車載音声」ボタン（既定は消音。ブースのマイクに回り込むので、普段は消音にしておく） |
| **Quest なしでブースから操縦する** | booth の「操縦」欄にパスワード（初期値 `Admin`）を入れて「ブースで操縦（Quest なし）」を押す。ロボ側映像が見回せる表示に変わり、中間サーバにつないだゲームコントローラー（Xbox 配列）で操縦する（操作は 4.1.1 の pilot ページと同じ。E-STOP は L3＋R3・`Esc`・赤ボタン）。戻すときは同じくパスワードを入れて「Quest で操縦」 |

- 操縦の切替は誤操作を防ぐためパスワードが要る。hub の起動時に `--admin-password <新しいパスワード>`（または環境変数 `NASURA_ADMIN_PASSWORD`）で変えられる。間違えると1秒間は受け付けない。
- 切り替えた瞬間、それまでの操縦者の入力は無視されるので、約 0.3 秒で一旦停止する（入力途絶 L1）。新しい操縦者が入力すると動く。
- ブースで操縦中も、Quest は映像を見られる（操作は無効。Quest の画面に「ブースで操縦中」と出る）。

### 00.4 うまく動かないとき

- **リレーをやめて従来の直結に戻す**：hub を `--s1-route direct` を付けて起動し直し、全ページを再読み込みする。booth ではロボ映像が見えなくなるが、10-04 までと同じ経路になる。
- Quest の映像だけ止まる：booth のウィンドウが開いているか、最小化されていないかを確かめる。booth の「S4」の状態を見る。
- 車載PCの「S1 エンコーダ」が「ソフト」で、「制約」が `cpu`：車載PCの CPU が足りていない。「制限」にする。

### 00.5 PC が落ちたときに調べること

ログは各マシンの `logs/` にある（hub は `hub-*.jsonl`、車載PCは `car_ctrl-*.jsonl`）。

- `"event": "sys"`：2秒ごとの `cpu_pct`（CPU 使用率 %）、`mem_pct`（メモリ %）、`temp_c`（CPU 温度 ℃、Linux のみ。Windows は `null`）、`load1`。落ちる直前の値を見る。
- `"event": "stats"`（hub）・`"event": "media_stats"`（車載PC）：2秒ごとの映像統計。`send_kbps`・`recv_kbps`・`fps`・`loss_pct`・`remote_loss_pct`・`rtt_ms`・`encoder`・`hw_encoder`・`quality_limit`。
- 車載PC（Ubuntu）では、再起動後に次も確認する。

  ```bash
  journalctl -b -1 -p warning --no-pager | tail -n 100
  ```

  ```bash
  last -x | head
  ```

  - 前回の起動のログが途中で切れていて、シャットダウンの記録も無ければ、電源断か強制リセットの可能性が高い。`thermal`・`throttl`・`Out of memory` などの語が出ていないかを見る。

### 00.6 実機での確認手順（2026-10-05 の変更）

開発機ではヘッドレス Chrome（偽カメラ）で、リレー（車載→booth→quest）と直結の両方が `connected` になり、映像が流れることを確認済み。次は実機でしか確認できない。

| # | 確認すること | 手順 | 合格 |
|---|---|---|---|
| 1 | booth でロボ映像が見える | 00.1 の順に起動する | booth にロボ側映像が出る。S1・S4 が `connected` |
| 2 | Quest に映像が届く（リレー経由） | Quest で「VR で見る」 | 360°映像が見え、頭の向きに追従する。遅延が 10-04 と比べて大きく悪化していない（booth の「S4 受信」の RTT を記録する） |
| 3 | 送信設定の切替 | booth で「フルスペック」→「制限」の順に押す | 車載ページ右上（`h` で表示）の `camera:` 行が `[full ÷1 ≤12.0Mbps]`／`[limited ÷1.5 ≤3.6Mbps]` に変わる。booth の「S1 上り」と「S1 解像度」が数秒〜数十秒で追従する |
| 4 | 「制限」の上り | 「制限」で 5 分間動かす | 「S1 上り」が 4000 kbps 以下（ST-0007） |
| 5 | 正面補正 | Quest で右を向いて左 Y を押す | 押した瞬間に向いていた方向に、映像の正面（ロボ正面）が来る。上下・傾きは変わらない |
| 6 | 取付オフセット | `--yaw-offset-deg 30` で hub を起動し、Quest と pilot を開く | ロボ正面が、画像中央から右に 30° の位置にある場合に正面に来る（向きが逆なら符号を反対にする） |
| 7 | 負荷ログ | 10 分動かし、両マシンの `logs/` を見る | `sys` が2秒ごとに出ている。車載PCに `temp_c` が数値で入る。車載PCに `media_stats` が出ている |
| 8 | 直結への戻し | `--s1-route direct` で hub を起動し直す | Quest に映像が出る（booth にはロボ映像が出ない） |

---

## 0. 2026-10-04 の構成（暫定：中間サーバの代わりにラップトップ）

10-04 だけは、中間サーバと Quest を使わず、次の構成にする。2026-10-04 未明に、コントローラー以外の全機能をこの構成で確認した。1章以降の手順とは、hub の置き場所が違う。

| マシン | 動かすもの |
|---|---|
| 車載PC（nasc） | hub（`https://nasc.tailffb95c.ts.net`）、car_ctrl と car ページ（X4）、アームの Follower 2台 |
| ラップトップ（laptop-dynabook） | booth ページ（パイロットのカメラ・マイク、E-STOP の解除）、pilot ページ（360°映像、コントローラー操縦）、アームの Leader 2台 |

### 0.1 起動（この順に行う）

1. 車載PC：hub を起動する（`tailscale serve` は 5324 番で設定済み）。

   ```bash
   cd ~/nasu_tuusinn_10_4 && PORT=5324 scripts/run_hub.sh --s1-route direct --s1-preset full

   （2026-10-05 以降のコードで 10-04 と同じ動きにする場合。中間サーバを使う構成では 00 章に従う）
   ```

2. 車載PC：X4 を Webcam Mode で接続し、映像と car_ctrl を起動する。

   ```bash
   cd ~/nasu_tuusinn_10_4 && HUB_HOST=nasc.tailffb95c.ts.net scripts/run_car.sh
   ```

3. ラップトップ：コントローラーと Leader 2台を接続し、Leader を Follower と近い姿勢にしてから、PowerShell で起動する。booth と pilot のウィンドウが開き、Leader の送信が左右それぞれのウィンドウで始まる。

   ```powershell
   cd $env:USERPROFILE\Downloads\nasu_tuusinn_10_4; powershell -ExecutionPolicy Bypass -File scripts\start_pilot_station.ps1
   ```

   - booth：カメラとマイクを許可する。
   - pilot：マイクを許可し、「クリックして開始」を押してから、コントローラーのボタンを1回押す。上部の「コントローラー」に機種名が緑で出れば認識している。操縦中は pilot のウィンドウを選択（フォーカス）しておく。
   - X4 は 2880×1440 で使う（正距円筒）。1920×1080 は前後2画面の「デュアル表示」で 360° ではなく、上下・前後が入れ替わって見える（2026-10-04 に発生）。pilot・quest の URL に `?layout=` は付けない。

4. 車載PC：介添人の配置・可動域・無負荷を確認してから、アームの Follower を起動する（3.4.0.1）。

   ```bash
   cd ~/nasu_tuusinn_10_4 && LEADER_HOST=laptop-dynabook scripts/run_car_so101_remote.sh --confirm-safe-workspace
   ```

### 0.2 確認

- `https://nasc.tailffb95c.ts.net/status` で、roles がすべて `true`、S1・S2・S3 が `connected`、`car_state` が `RUN`。
- S1 の解像度は、接続直後は低く、数十秒で上がる。
- アーム：車載PCの `logs/so101-follower-*.log` に `stream fresh: following leader`。

### 0.3 操作と停止

- 操縦は 4.1.1（pilot ページ）、E-STOP の解除は 4.2（booth ページ）。
- アームの Follower を止める（車載PCで Ctrl+C）と脱力する。腕を支えてから止める。
- 終了は、アームの Follower → Leader（各ウィンドウを閉じる）→ run_car.sh → hub の順に止め、booth と pilot のウィンドウを閉じる（booth はカメラを開いたままになるため）。

### 0.4 この構成での注意

- pilot ページは quest role として接続するので、Quest は使えない（つなぐと pilot が置き換えられる）。
- ラップトップで hub を起動しない。hub が2つあると、両側が別の hub につながり、映像がつながらない（2026-10-04 に発生）。
- コントローラーでの操縦は、偽のコントローラーでしか確認していない（実機のコントローラーは 10-04 当日に初めて接続する）。

---

## 1. マシンごとの役割

| マシン | 置き場所 | 動かすもの | 開くページ | OS | 必要なもの |
|---|---|---|---|---|---|
| 中間サーバ | 操縦ブース | hub（`python -m nasura_comm.hub`） | booth（`/booth/`） | Windows 11 または Ubuntu（未定） | Python 3.10 以上（uv が用意する）、uv、Git、Tailscale、Chromium または Chrome、パイロット用カメラ・マイク（機種は未定） |
| 車載 Ubuntu PC | NASURA | car_ctrl（`python -m nasura_comm.car`） | car（`/car/`、Chromium のキオスク表示） | Ubuntu（バージョン要確認） | Python 3.10 以上（uv が用意する）、uv、Git、Tailscale、Chromium、Insta360 X4、車載マイク・スピーカー・モニタ |
| Quest 3S | 操縦ブース | なし（ブラウザのみ） | quest（`/quest/`） | Meta Horizon OS（バージョン要確認） | Quest Browser、Tailscale（Android 版をサイドロード済み）。インターネットにつながる Wi-Fi に接続する |

### ネットワーク

| 項目 | 値 |
|---|---|
| hub の URL | `https://<hub のホスト名>.<tailnet 名>.ts.net/`（ホスト名・tailnet 名は要確認） |
| hub の待ち受け | `127.0.0.1:8080`（`tailscale serve` で HTTPS 化） |
| 車載のローカル出力 | UDP `127.0.0.1:47001`（`out/effective`、20 Hz） |
| 車載のテレメトリ入力 | UDP `127.0.0.1:47002` |

中間サーバ・車載PC・Quest 3S の3台とも tailnet に参加する（AD-0010）。subnet router は使わないので、会場のブースLAN のアドレス帯を設定する必要は無い。

以下、`<HUB>` は `<hub のホスト名>.<tailnet 名>.ts.net` を表す。

---

## 2. 事前準備（各マシンで1回だけ）

設定ファイルは無い。設定はすべて起動時のオプションで与える（DD-0009）。

### 2.1 中間サーバ

1. uv と Git を入れる（uv の公式手順：Ubuntu は `curl -LsSf https://astral.sh/uv/install.sh | sh`、Windows 11 は PowerShell で `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`）。
2. リポジトリを取得し、依存を入れる。

   ```bash
   git clone https://github.com/ruri-sayo/nasu_tuusinn_10_4.git
   ```

   ```bash
   cd nasu_tuusinn_10_4 && uv sync
   ```

3. Tailscale に参加する（Ubuntu は `sudo tailscale up`、Windows 11 はタスクトレイの Tailscale からログイン）。

4. hub を HTTPS で公開する（設定は Tailscale 側に残る）。

   ```bash
   tailscale serve --bg 8080
   ```

5. tailnet の HTTPS 証明書（MagicDNS・HTTPS）は有効にしてある（確認済み）。

### 2.2 車載 Ubuntu PC

1. uv・Git・Chromium を入れる（Chromium の入れ方は Ubuntu のバージョンによる。要確認）。
2. リポジトリを取得し、依存を入れる（中間サーバと同じ手順）。
3. Tailscale に参加する。

   ```bash
   sudo tailscale up
   ```

4. 中間サーバへ届くことを確かめる。

   ```bash
   tailscale ping <hub のホスト名>
   ```

5. Chromium のカメラ・マイク・自動再生は `scripts/run_car.sh` が起動オプションで許可するので、事前の設定は不要。

### 2.3 Quest 3S

1. インターネットにつながる Wi-Fi に接続する。
2. Tailscale アプリで tailnet に接続する（VPN を有効にする）。本人が設定済み。
3. Quest Browser で `https://<HUB>/quest/` を開けるか確かめる。開けない場合は 5.2 の R-1 を参照。
4. 初回はマイクの許可を求められるので許可する（音声は送らない。接続のために必要）。
5. ブックマークに登録しておく。

### 2.4 Insta360 X4

1. X4 を車載PC に USB で接続し、X4 本体の USB モードで **Webcam Mode** を選ぶ（充電・ファイル転送ではない）。
2. 車載PC で X4 がカメラとして見えるか確かめる。Linux でのデバイス名（ラベル）に `Insta360` が含まれるかは要確認。含まれない場合は、hub を `--s1-device-label <ラベルの一部>` で起動する。
3. 1920×960 で取れるかは要確認。car ページ右上の `camera:` 表示が黄色なら、設定と違う解像度になっている（3.3）。

---

## 3. 当日の起動手順

各ノードは自動で再接続するので、順番を間違えても、待てばつながる。ただし確認しやすいように次の順で起動する。

### 3.1 中間サーバ：hub を起動する

Ubuntu：

```bash
cd nasu_tuusinn_10_4 && scripts/run_hub.sh
```

Windows 11（PowerShell。`run_hub.sh` は bash 用なので使えない）：

```powershell
cd nasu_tuusinn_10_4; uv run python -m nasura_comm.hub --port 8080
```

- `[hint] HTTPS is not served yet` と出たら、2.1 の手順 4 を実行する。
- S1 の上限を変えるときは、オプションを付ける（例：`scripts/run_hub.sh --s1-codec H264 --s1-max-bitrate 2000000`）。`--s1-max-bitrate` は「制限」の上限、`--s1-full-max-bitrate` は「フルスペック」の上限、`--s1-limited-scale` は「制限」の解像度の縮小率、`--s1-preset` は起動時の設定。サブカメラは `--sub-*`、パイロット映像は `--s2-*`、音声は `--audio-max-bitrate`。一覧は `uv run python -m nasura_comm.hub --help`。

### 3.2 中間サーバ：booth ページを開く

Chromium で `https://<HUB>/booth/` を開き、カメラとマイクを許可する。

- 「WS: 接続」と出て、右側に「車載状態」が表示されれば hub とつながっている。

### 3.3 車載PC：X4 を接続し、car_ctrl と car ページを起動する

1. X4 を USB で接続し、Webcam Mode にする（2.4）。
2. 起動する。

   ```bash
   cd nasu_tuusinn_10_4 && HUB_HOST=<HUB> scripts/run_car.sh
   ```

   - car_ctrl がバックグラウンドで起動し、続けて Chromium がキオスク表示で `https://<HUB>/car/` を開く。
   - Chromium のパスが自動で見つからない場合は、`CHROMIUM=<パス>` を付ける。
3. 確認する。
   - 右上の表示：S1 と S2 の点が緑、`camera:` に X4 のラベル・解像度・fps が出る。`h` キーで表示を隠せる。
   - 左下に赤字で「カメラ「Insta360」が見つかりません」と出たら、X4 の接続と USB モードを確かめる（既定カメラで続行している）。

### 3.4 Quest 3S：quest ページを開く

1. Tailscale アプリで VPN が有効になっていることを確かめる（スリープ明けなどで切れていることがある。要確認）。
2. Quest Browser で `https://<HUB>/quest/` を開く。
3. 「S1: connected」になり、ボタンが「VR で見る」に変わるまで待つ。
4. 「VR で見る」を押す。360°映像が表示され、車載音声が聞こえる。

### 3.4.0 Quest を使わない場合（pilot ページ・暫定）

Quest の代わりに、PC の画面とゲームコントローラーで操縦する（暫定機能。逸脱記録あり）。hub と車載側の手順は変わらない。

1. Xbox 配列のコントローラーを PC に USB または Bluetooth で接続する。
2. Chrome で `https://<HUB>/pilot/` を開き、マイクを許可する（音声は送らない。接続のために必要）。X4 の2本帯の映像は `?layout=tb`（または `bt`）を付ける。
3. 「クリックして開始」を押す（車載音声の再生を有効にする）。
4. コントローラーのボタンを1回押す。上部の「コントローラー」に機種名が緑で出れば認識している。
5. booth ページを同じ PC で開く場合は、別のウィンドウで開く。**操縦中は pilot のウィンドウを選択（フォーカス）しておく。**

- pilot ページは quest と同じ接続（role）を使うので、**Quest と同時には使えない**。後から開いた方が有効になり、先の画面には「置き換えられました」と出る。
- タブを隠す、最小化する、コントローラーが外れると入力が途絶し、約 0.3 秒で停止命令が出る。

### 3.4.0.1 SO-101 アーム（Leader はラップトップ、Follower は車載PC・暫定）

前提：介添人が Follower の電源をすぐに切れる位置にいる。可動域に人と物が無い。アームに負荷が無い。

1. 車載PC：ハードウェア情報を `/home/nasc/hardware` に置き、commit `8ec5487` にする。Follower 2台を USB で接続する。
2. 車載PC：Follower を起動する（ラップトップより先に起動する）。

   ```bash
   LEADER_HOST=laptop-dynabook scripts/run_car_so101_remote.sh --confirm-safe-workspace
   ```

3. ラップトップ：Leader 2台を USB で接続し、Leader を Follower と同じくらいの姿勢にしてから起動する（左右それぞれ別のウィンドウが開く）。

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_leader_so101.ps1 -FollowerHost nasc
   ```

- Follower は、1周期あたり最大 5° ずつ Leader の姿勢へ近づく。
- Leader 側を止める、または通信が 0.5 秒途絶えると、Follower はその位置で**保持**する（脱力しない）。
- Follower 側を止める（Ctrl+C）と、トルクが切れて**脱力する**。アームを支えてから止める。
- 最終的な停止手段は、Follower の電源を切ること。

### 3.4.1 ROS 2走行制御を同時起動する場合

駆動輪を浮かせ、物理E-stopを有効にしてから、3.3の `run_car.sh` の代わりに次を実行する。

```bash
HUB_HOST=<HUB> scripts/run_car_ros2.sh
```

これは `joy_motor_controller` の購読先を `/nasura/drive_joy` へリマップし、UDP実効命令アダプタ、
`car_ctrl`、`car_media` を同時起動する。`joy_node` や `socket_cmd_publisher` は同時起動しない。

Tailscale Serveを設定できず、hubを `--bind 0.0.0.0 --tls-self-signed` で起動した場合の車載側は次を使う。

```bash
HUB_HOST=<hubのTailscale IP>:8080 INSECURE_TLS=1 scripts/run_car_ros2.sh
```

Quest Browserは `https://<hubのTailscale IP>:8080/quest/` を開き、初回の証明書警告を許可する。

### 3.5 起動後の確認

booth ページで次を確かめる（4 章の操作に入る前）。

- 接続：quest・booth・car_media・car_ctrl がすべて「接続」、S1・S2・S3・S4 がすべて `connected`（`--s1-route direct` のときは S4 は `-`）。
- 車載状態：`RUN`。
- 映像：「S1 上り」が予算（4000 kbps）以下（送信設定が「制限」のとき）、「S2 送信」が 400 kbps 以下。

---

## 4. 操作手順

### 4.1 操縦者（Quest 3S）

| 操作 | 入力 |
|---|---|
| 走行 | 左スティック（上で前進、左右で旋回） |
| ステージ（横） | A（＋）／B（−） |
| ステージ（前後） | 右スティック上下 |
| 正面を合わせる | 左 Y（今向いている方向を正面にする） |
| **E-STOP** | **左右のスティックを同時に押し込む** |

- アームは SO-101 の Leader で操作する（本システム F-001 の対象外。手順は別途）。
- Quest からは E-STOP を**解除できない**。解除はブース担当に頼む。
- ヘッドセットを外す（VR が終わる）と入力が途絶し、約 0.3 秒で停止命令が出る。

### 4.1.1 操縦者（pilot ページ・暫定）

| 操作 | 入力 |
|---|---|
| 走行 | 左スティック（Quest と同じ） |
| ステージ（横） | A（＋）／B（−） |
| ステージ（前後） | 右スティック上下 |
| 視点 | 右スティック左右、十字キー上下、マウスのドラッグ。ホイールでズーム |
| 視点のリセット | View（Back）ボタン、ダブルクリック、`R` キー |
| 全画面 | `F` キー |
| **E-STOP** | **左右のスティックを同時に押し込む**、画面右上の E-STOP ボタン、`Space` キー、`Esc` キー（全画面中の `Esc` は全画面の解除に使われることがあるので、`Space` を使う） |

- pilot ページからは E-STOP を**解除できない**。解除は booth ページで行う。

### 4.2 ブース担当（booth ページ）

| 操作 | 方法 |
|---|---|
| **E-STOP** | 赤い **E-STOP** ボタンを押す、または `Esc` キー |
| **E-STOP の解除** | 「E-STOP 解除」ボタンを **2 秒以内に 2 回**押す |
| S1 の送信設定 | 「S1 送信」の「制限」／「フルスペック」（00.3） |

- E-STOP 中は「車載状態」が赤の `ESTOP`、「hub で E-STOP ラッチ中」と表示される。
- 解除すると、車載は `STOP` を経て `RUN` に戻る。**解除した時点の Quest の入力どおりにすぐ動き出す**（デッドマンは無い）ので、解除する前に操縦者へ声をかけ、スティックから手を離してもらう。
- 解除は、介添人と操縦者に安全を確認してから行う。
- 「WS: 切断」と表示されているときは E-STOP を送れない。そのとき車載は、通信途絶として約 1.2 秒後に停止する（補助機能）。

### 4.3 介添人

- 暴走時に**物理的に止めるのは介添人の責任**である。通信による停止は補助機能に過ぎない（DEV-0005）。
- 物理的に止めるときは、**車体の緊急停止ボタンを押す**。
- 異常に気づいたら、まず物理的に止め、同時にブース担当へ E-STOP を依頼する。
- E-STOP の解除はブース担当だけができる。介添人が安全を確認するまで解除しないよう、事前に取り決めておく。

### 4.4 停止に関わる時間（参考）

| 事象 | 停止までの時間 |
|---|---|
| E-STOP（Quest・booth） | 届きしだい（通常は即時） |
| Quest 入力の途絶（ヘッドセットを外した場合など） | 約 0.3 秒（REQ-0012） |
| 中間サーバ↔車載の通信途絶 | 1.5 秒以内（heartbeat 途絶 1.2 秒、REQ-0010） |

本 PoC の範囲は、車載PC の UDP `127.0.0.1:47001` に実効命令を出すところまでである。この出力を Drive につなぐか（別 Feature）は要確認。アームは SO-101 Leader で別経路から操作する（別 Feature）。

---

## 5. 動作確認とトラブル時

### 5.1 正常に動いているかの確認

**booth ページ**（1 秒ごとに更新）で確認する。

| 表示 | 正常 | 異常のとき |
|---|---|---|
| 車載状態 | `RUN`（緑） | `STOP`＝通信途絶など、`ESTOP`＝E-STOP 中、`不明`＝S3 未接続 |
| 接続（quest〜car_ctrl） | すべて「接続」 | 「未接続」のノードを確認する |
| S1・S2・S3 | `connected` | 5.2 を参照 |
| RTT（最新・EWMA） | 数十 ms 程度 | 200 ms を超えると黄色 |
| Quest 入力の経過 | 300 ms 以下（操縦中） | 300 ms を超えると停止命令になる |
| S1 上り | 3000 kbps 以下 | 予算超過で赤 |
| S2 送信 | 400 kbps 以下 | 超過で赤 |
| S1 候補 | `host ↔ host` など | — |
| 破棄件数 | 空 | 件数が増えるなら、テレメトリの topic 登録を確認する |

**`/status`**（JSON）：`https://<HUB>/status` を開くと、booth と同じ内容を JSON で見られる。

| キー | 意味 |
|---|---|
| `roles` | 各ノードの WebSocket 接続 |
| `sessions` | S1・S2・S3 の接続状態 |
| `control.rtt_ms` / `rtt_ewma_ms` | 制御リンクの RTT（最新・平均） |
| `control.car_state` | 車載の安全状態（INIT／RUN／STOP／ESTOP） |
| `control.latched` | hub で E-STOP がラッチ中か |
| `control.last_input_age_ms` | 最後の Quest 入力からの経過 |
| `stats.S1` / `stats.S2` | 各ページが報告した送受信 kbps・fps・解像度など |
| `dropped` | 破棄したメッセージの件数 |
| `telemetry` | テレメトリの最新値 |

**車載PC の UDP 出力**：別の端末で次を実行すると、実効命令が 1 行ずつ表示される（200 ms を超える間隔は `GAP` と出る）。

```bash
uv run python scripts/dump_effective.py
```

下流（Drive など）が 47001 を使っている場合は、ポートが重なるので実行しない。

**ネットワーク経路**（車載PC）：

```bash
tailscale ping <hub のホスト名>
```

`via DERP` と出たら中継経由で、遅延・帯域が悪化する（R-3）。対処はしないが、記録する（ST-0011）。

### 5.2 よくある不具合と対処

| 症状 | 原因の候補 | 対処 |
|---|---|---|
| Quest で `https://<HUB>/quest/` が開けない | Quest の Tailscale が切れている | Tailscale アプリで VPN を有効にしてから再読み込みする |
| 同上（Tailscale は有効） | `*.ts.net` を名前解決できない（R-1） | hub を `scripts/run_hub.sh --bind 0.0.0.0 --tls-self-signed` で起動し、Quest で `https://<中間サーバの LAN IP>:8080/quest/` を開いて証明書の警告を1回許可する。車載側は `run_car.sh` を使わず、5.2.1 の手順で起動する |
| S1 が `connected` にならない（Quest に映像が来ない） | Quest のマイク許可が無い（mDNS で候補が隠れる） | quest ページを再読み込みし、マイクを許可する |
| 同上 | Quest または車載PC の Tailscale が切れている | 両方で Tailscale が接続中か確かめる。車載PC で `tailscale ping <Quest のホスト名>` |
| 画面上部に赤帯で「別の画面に置き換えられました」 | 同じ役割のページを別の場所で開いた | 不要なほうを閉じる。使うほうを再読み込みする |
| car ページに「カメラ「Insta360」が見つかりません」 | X4 が Webcam Mode でない、USB 未接続、ラベルが違う | 接続と USB モードを確認する。ラベルが違う場合は hub を `--s1-device-label` 付きで起動し直す |
| car ページの `camera:` が黄色 | X4 が 1920×960 を出していない | 表示された解像度を記録する（要確認事項）。必要なら `--s1-width` `--s1-height` で合わせる |
| S1 の fps が低い・フレームが落ちる | 車載PC の CPU 不足（R-2）、回線 | `top` で CPU を確認する。hub を `--s1-codec H264`（または `VP8`）や解像度を下げて起動し直す |
| 車載状態が `STOP` のまま | S3 が切れている、hub が止まっている | booth の S3 と car_ctrl の接続を確認する。car_ctrl は 2 秒ごとに自動で再接続する |
| 車載状態が `ESTOP` のまま | E-STOP 中 | 安全を確認してから、booth の解除ボタンを 2 秒以内に 2 回押す |
| Quest で音が出ない | 自動再生の制限 | 「VR で見る」を押す（その操作で再生が始まる） |
| 車載で音・映像が出ない | 自動再生の制限 | `run_car.sh` で起動しているか確認する（自動再生を許可するオプションが付く） |

#### 5.2.1 自己署名証明書で動かすときの車載側（R-1）

車載PC から見た中間サーバのアドレス（tailnet IP など、要確認）を `<ADDR>` とする。

```bash
uv run python -m nasura_comm.car --hub wss://<ADDR>:8080/ws --insecure
```

別の端末で Chromium を起動する。キオスク表示では証明書の警告を操作できないので、警告を無視するオプションを付ける。

```bash
chromium --kiosk --ignore-certificate-errors --autoplay-policy=no-user-gesture-required --use-fake-ui-for-media-stream --user-data-dir=$HOME/.cache/nasura-car-chromium https://<ADDR>:8080/car/
```

どのノードも、再起動（ページは再読み込み）すれば 15 秒以内に元に戻る。他のノードを再起動する必要は無い（REQ-0018）。

### 5.3 ログ

- hub・car_ctrl のログは、それぞれのマシンの `logs/<ノード名>-<起動時刻>.jsonl` に残る（接続・切断、E-STOP、状態遷移、1 秒ごとの RTT など）。
- 試験後、ST の記録と一緒に保存する。

### 5.4 終了手順

1. 操縦者が VR を終了し、ブース担当が E-STOP を押す（車両を止めた状態で終える）。
2. 車載PC：キオスク表示の Chromium を閉じる（`Alt+F4`）。`run_car.sh` が car_ctrl も止める。止まらない場合は、`run_car.sh` の端末で `Ctrl+C`。
3. 中間サーバ：booth ページを閉じ、hub の端末で `Ctrl+C`。
4. 必要なら HTTPS 公開を止める。

   ```bash
   tailscale serve reset
   ```

5. `logs/` を回収し、`60-system-e2e-spec.md` に結果（`result`・`commit`・`executed_by`・`executed_at`）を記入する。

---

## 要確認の一覧

| 項目 | 確認先 |
|---|---|
| 中間サーバの OS（Windows 11 か Ubuntu か） | 中間サーバ |
| 車載PC の Ubuntu のバージョンと Chromium の入れ方 | 車載PC |
| Quest 3S の OS のバージョン | Quest |
| hub のホスト名・tailnet 名（`<HUB>`） | Tailscale 管理画面 |
| Quest のスリープ明けに Tailscale の VPN が切れないか | Quest |
| パイロット用カメラ・マイクの機種（未定） | ブース |
| X4 の Linux 上のデバイス名、1920×960 で取れるか | 車載PC |
| UDP 出力を Drive につなぐか | 機体担当 |
