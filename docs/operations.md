# NASURA 通信系 運用手順書（実機構成）

2026-10-04 の実機試験で使う手順である。開発機での確認手順は [README](../README.md) を参照する。

- 対象：F-001 NASURA 通信系 PoC（commit は当日の `git log -1` で記録する）
- 試験項目と合否基準：[60-system-e2e-spec.md](features/F-001_nasura-comm/60-system-e2e-spec.md)（ST-0001〜ST-0013）
- 「要確認」と書いた箇所は、当日までに実機で確かめて埋める。

---

## 1. マシンごとの役割

| マシン | 置き場所 | 動かすもの | 開くページ | OS | 必要なもの |
|---|---|---|---|---|---|
| 中間サーバ | 操縦ブース | hub（`python -m nasura_comm.hub`） | booth（`/booth/`） | 要確認 | Python 3.10 以上（uv が用意する）、uv、Git、Tailscale、Chromium または Chrome、パイロット用カメラ・マイク（機種は要確認） |
| 車載 Ubuntu PC | NASURA | car_ctrl（`python -m nasura_comm.car`） | car（`/car/`、Chromium のキオスク表示） | Ubuntu（バージョン要確認） | Python 3.10 以上（uv が用意する）、uv、Git、Tailscale、Chromium、Insta360 X4、車載マイク・スピーカー・モニタ |
| Quest 3S | 操縦ブース | なし（ブラウザのみ） | quest（`/quest/`） | Meta Horizon OS（バージョン要確認） | Quest Browser（追加アプリ不要）。ブースLAN の Wi-Fi に接続する |

### ネットワーク

| 項目 | 値 |
|---|---|
| hub の URL | `https://<hub のホスト名>.<tailnet 名>.ts.net/`（ホスト名・tailnet 名は要確認） |
| ブースLAN の CIDR | 要確認（中間サーバの subnet route として広告する） |
| hub の待ち受け | `127.0.0.1:8080`（`tailscale serve` で HTTPS 化） |
| 車載のローカル出力 | UDP `127.0.0.1:47001`（`out/effective`、20 Hz） |
| 車載のテレメトリ入力 | UDP `127.0.0.1:47002` |

Quest は tailnet に参加しない。中間サーバを subnet router にして、車載PC からブースLAN 上の Quest へ届くようにする（AD-0010）。

以下、`<HUB>` は `<hub のホスト名>.<tailnet 名>.ts.net` を表す。

---

## 2. 事前準備（各マシンで1回だけ）

設定ファイルは無い。設定はすべて起動時のオプションで与える（DD-0009）。

### 2.1 中間サーバ

1. uv と Git を入れる（uv の公式手順：`curl -LsSf https://astral.sh/uv/install.sh | sh`）。
2. リポジトリを取得し、依存を入れる。

   ```bash
   git clone https://github.com/ruri-sayo/nasu_tuusinn_10_4.git
   ```

   ```bash
   cd nasu_tuusinn_10_4 && uv sync
   ```

3. Tailscale に参加し、ブースLAN を subnet route として広告する。

   ```bash
   sudo tailscale up --advertise-routes=<ブースLAN の CIDR>
   ```

   - Tailscale の管理画面で、このマシンの subnet route を承認する。
   - 中間サーバが Linux の場合は、subnet router として IP フォワーディングを有効にする必要がある（Tailscale の subnet router の手順に従う）。OS が macOS・Windows の場合の扱いは要確認。

4. hub を HTTPS で公開する（設定は Tailscale 側に残る）。

   ```bash
   tailscale serve --bg 8080
   ```

5. Tailscale の管理画面で、tailnet の HTTPS 証明書（MagicDNS・HTTPS）が有効であることを確認する（要確認）。

### 2.2 車載 Ubuntu PC

1. uv・Git・Chromium を入れる（Chromium の入れ方は Ubuntu のバージョンによる。要確認）。
2. リポジトリを取得し、依存を入れる（中間サーバと同じ手順）。
3. Tailscale に参加し、subnet route を受け入れる。

   ```bash
   sudo tailscale up --accept-routes
   ```

4. 中間サーバへ届くことを確かめる。

   ```bash
   tailscale ping <hub のホスト名>
   ```

5. Chromium のカメラ・マイク・自動再生は `scripts/run_car.sh` が起動オプションで許可するので、事前の設定は不要。

### 2.3 Quest 3S

1. ブースLAN の Wi-Fi に接続する。
2. Quest Browser で `https://<HUB>/quest/` を開けるか確かめる。開けない場合は 5.2 の R-1 を参照。
3. 初回はマイクの許可を求められるので許可する（音声は送らない。接続のために必要）。
4. ブックマークに登録しておく。

### 2.4 Insta360 X4

1. X4 を車載PC に USB で接続し、X4 本体の USB モードで **Webcam Mode** を選ぶ（充電・ファイル転送ではない）。
2. 車載PC で X4 がカメラとして見えるか確かめる。Linux でのデバイス名（ラベル）に `Insta360` が含まれるかは要確認。含まれない場合は、hub を `--s1-device-label <ラベルの一部>` で起動する。
3. 1920×960 で取れるかは要確認。car ページ右上の `camera:` 表示が黄色なら、設定と違う解像度になっている（3.3）。

---

## 3. 当日の起動手順

各ノードは自動で再接続するので、順番を間違えても、待てばつながる。ただし確認しやすいように次の順で起動する。

### 3.1 中間サーバ：hub を起動する

```bash
cd nasu_tuusinn_10_4 && scripts/run_hub.sh
```

- `[hint] HTTPS is not served yet` と出たら、2.1 の手順 4 を実行する。
- S1 の上限を変えるときは、オプションを付ける（例：`scripts/run_hub.sh --s1-codec H264 --s1-max-bitrate 2000000`）。

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

1. Quest Browser で `https://<HUB>/quest/` を開く。
2. 「S1: connected」になり、ボタンが「VR で見る」に変わるまで待つ。
3. 「VR で見る」を押す。360°映像が表示され、車載音声が聞こえる。

### 3.5 起動後の確認

booth ページで次を確かめる（4 章の操作に入る前）。

- 接続：quest・booth・car_media・car_ctrl がすべて「接続」、S1・S2・S3 がすべて `connected`。
- 車載状態：`RUN`。
- 映像：「S1 上り」が予算（3000 kbps）以下、「S2 送信」が 400 kbps 以下。

---

## 4. 操作手順

### 4.1 操縦者（Quest 3S）

| 操作 | 入力 |
|---|---|
| デッドマン（走行・ステージの有効化） | 左グリップを握り続ける。離すと停止する |
| 走行 | 左スティック（上で前進、左右で旋回） |
| アーム | 右グリップを握っている間、右コントローラの動きに追従（握った時点が基準） |
| 把持 | 右トリガー |
| ステージ（横） | A（＋）／B（−） |
| ステージ（前後） | 右スティック上下 |
| **E-STOP** | **左右のスティックを同時に押し込む** |

- Quest からは E-STOP を**解除できない**。解除はブース担当に頼む。
- ヘッドセットを外す（VR が終わる）と入力が途絶し、約 0.3 秒で停止命令が出る。

### 4.2 ブース担当（booth ページ）

| 操作 | 方法 |
|---|---|
| **E-STOP** | 赤い **E-STOP** ボタンを押す、または `Esc` キー |
| **E-STOP の解除** | 「E-STOP 解除」ボタンを **2 秒以内に 2 回**押す |

- E-STOP 中は「車載状態」が赤の `ESTOP`、「hub で E-STOP ラッチ中」と表示される。
- 解除すると、車載は `STOP` を経て `RUN` に戻る。操縦者がデッドマンを握り直すまで動かない。
- 解除は、介添人と操縦者に安全を確認してから行う。
- 「WS: 切断」と表示されているときは E-STOP を送れない。そのとき車載は、通信途絶として約 1.2 秒後に停止する（補助機能）。

### 4.3 介添人

- 暴走時に**物理的に止めるのは介添人の責任**である。通信による停止は補助機能に過ぎない（DEV-0005）。
- 物理的な止め方（車体の非常停止スイッチ、電源の遮断、押さえ方など）は要確認。
- 異常に気づいたら、まず物理的に止め、同時にブース担当へ E-STOP を依頼する。
- E-STOP の解除はブース担当だけができる。介添人が安全を確認するまで解除しないよう、事前に取り決めておく。

### 4.4 停止に関わる時間（参考）

| 事象 | 停止までの時間 |
|---|---|
| E-STOP（Quest・booth） | 届きしだい（通常は即時） |
| デッドマン解放・Quest 入力の途絶 | 約 0.3 秒（REQ-0012） |
| 中間サーバ↔車載の通信途絶 | 1.5 秒以内（heartbeat 途絶 1.2 秒、REQ-0010） |

本 PoC の範囲は、車載PC の UDP `127.0.0.1:47001` に実効命令を出すところまでである。この出力を Drive・アームにつなぐか（別 Feature）は要確認。

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
| Quest で `https://<HUB>/quest/` が開けない | Quest が `*.ts.net` を名前解決できない（R-1） | hub を `scripts/run_hub.sh --bind 0.0.0.0 --tls-self-signed` で起動し、Quest で `https://<中間サーバの LAN IP>:8080/quest/` を開いて証明書の警告を1回許可する。車載側は `run_car.sh` を使わず、5.2.1 の手順で起動する |
| S1 が `connected` にならない（Quest に映像が来ない） | Quest のマイク許可が無い（mDNS で候補が隠れる） | quest ページを再読み込みし、マイクを許可する |
| 同上 | subnet route が未承認、または車載で `--accept-routes` が無い | Tailscale 管理画面で route を承認する。車載で `sudo tailscale up --accept-routes` |
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
| 中間サーバの OS とバージョン | 中間サーバ |
| 車載PC の Ubuntu のバージョンと Chromium の入れ方 | 車載PC |
| Quest 3S の OS のバージョン | Quest |
| hub のホスト名・tailnet 名（`<HUB>`） | Tailscale 管理画面 |
| ブースLAN の CIDR | 会場 |
| tailnet の HTTPS 証明書が有効か | Tailscale 管理画面 |
| 中間サーバの subnet router 設定（OS ごとの手順） | 中間サーバ |
| パイロット用カメラ・マイクの機種 | ブース |
| X4 の Linux 上のデバイス名、1920×960 で取れるか | 車載PC |
| 介添人の物理的な止め方 | 機体担当 |
| UDP 出力を Drive・アームにつなぐか | 機体担当 |
