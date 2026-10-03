---
kind: IMPLEMENTATION_DIFF
feature: F-001
status: draft
---

# F-001 実装差分レポート

実装後に AI が記入する。設計（30-detailed-design.md）と実装の差分、設計に無い副作用（ファイル書き込み・ネットワーク・外部プロセス起動）、追加した依存を列挙する。差分が設計変更に当たる場合は設計書を同じ commit で更新し、H4 の承認対象とする。

| 設計項目 | 差分 | 理由 | 設計書更新 |
|---|---|---|---|
| ソース構成 | `hub/app.py`・`car/app.py`（配線）と `__main__.py`（起動）に分けた。I/O 層用に `clock.py` を追加 | 試験と読みやすさ | 30（ソース構成） |
| DD-0002 | `Registry` クラスを追加し、`validate_extensions()` を公開。hub・car_ctrl に `--extra-topic` を追加 | 試験用の拡張 topic を起動時に登録するため（IT-0004、ST-0013） | 30（DD-0002） |
| DD-0002 / DD-0009 | `sys/state` に `dropped`（car_ctrl の UDP in 破棄件数）を追加し、hub の `/status.dropped` に合算 | 破棄は car_ctrl で起きるため、そのままでは `/status` に出ない（IT-0004・ST-0013） | 30（DD-0002、DD-0009） |
| DD-0005 | `ControlCore.on_link_up()` を追加（ラッチ中なら S3 確立時に `sys/estop` を再送） | ラッチ中に S3 が張り直されると車載が ESTOP でなくなるため（安全機構の強化方向。DD-0005〜0007 の判断は変えていない） | 30（DD-0005） |
| DD-0006 | `on_link_down(now=None)`、`update(now)`、`pop_state_changed()`、属性 `state`・`since`・`reason` を公開 IF とした | 設計が「フラグを立てる」とだけ書いていたため IF を具体化 | なし（設計の範囲内） |
| DD-0008 / DD-0011 | 置き換えた旧接続を close code 4001 で閉じ、ブラウザはそのコードでは再接続しない | 同じ role の画面が2つあると互いを追い出し続けることを開発機で確認したため | 30（DD-0008、DD-0011） |
| DD-0009 | `/status` に `telemetry` キー、CLI に `--s1-device-label --web-dir --log-dir --extra-topic` を追加。ブラウザ由来 `env` の `src` を接続 role で上書き | booth 表示・試験・起動場所の自由度。src の偽装防止 | 30（DD-0009） |
| DD-0010 | car_ctrl に CLI（`--udp-out --udp-in --insecure --log-dir --extra-topic --ack-delay-ms`）を追加。状態変化時に UDP out を即時送信 | 試験で別ポートを使うため。停止の反映を 50 ms 周期待ちにしないため | 30（DD-0010） |
| DD-0011 | offerer はセッション作成時に `restart_req` を送る | メディア取得中に `restart` を取りこぼす競合を開発機で確認したため | 30（DD-0011） |
| DD-0014 | 流用元の XR ビューアが生 WebGL だったため three.js を使わず、`web/vendor/` は空 | 既存コードの流用（本人確認済み） | 30（DD-0014、ソース構成） |
| DD-0015 | `scripts/dump_effective.py` と `run_car.sh` の `FAKE_MEDIA=1` を追加 | ST-0006・0008 の確認と開発機での確認用 | 30（DD-0015） |
| DD-0003 | RateLimiter を「前回許可からの最小間隔」から GCRA（20 % の早着を許容）に変更 | 宣言レートちょうどの送信元が揺らぎで 15 件中 10〜12 件に間引かれた（IT-0004 で検出） | 30（DD-0003） |
| DD-0005 / DD-0010 | 入力途絶で停止値に変わったら hub は即時に cmd を送り、car_ctrl は drive が 0/0 に変わったら即時に UDP out を送る | 300＋33＋50 ms で最大約 383 ms かかり、IT-0007 の 350 ms を満たさなかった（IT-0007 で検出） | 30（DD-0005、DD-0010） |
| DD-0009 | S3 確立し直しで RTT を null に戻す | 再接続後に古い RTT が約 1 秒残った（IT-0006 の実施中に観察） | 30（DD-0009） |
| DD-0002 / DD-0009 | `/status.dropped` の car_ctrl 分と hub 分を、同じキーで上書きしていたのを合算に修正 | 設計（合算）との不一致（E2E の REQ-0013 試験で検出） | なし（設計どおりに修正） |
| DD-0008 | hub の WebSocket ping を 10 秒周期（pong 待ち 5 秒）にした | 5 秒周期では負荷時にブラウザの pong が遅れ、3ページが同時に切断された（E2E 全体実行で検出）。安全系は S3 の heartbeat で担保しており WS の ping は画面の消失検出だけに使う | なし（設計に周期の定めなし） |
| DD-0010 | car_ctrl は SIGTERM で正常終了する（メインタスクを cancel） | systemd の停止や試験終了時にログと Coverage を書き出すため | なし |
| DD-0006 | heartbeat timeout を 500 ms → 1,200 ms（REQ-0010 を 1.5 秒以内、AD-0007・UT-0008・IT-0002・ST-0008 も更新） | 本人の指示（DEV-0005）。500 ms では要件 500 ms に検出遅れの余裕が無く 0.506 秒の FAIL が出た | 10、20、30、40、50、60 |
| AD-0010 / DD-0015 | subnet router をやめ、Quest 3S も tailnet に参加させる構成に変更（コード変更なし） | 会場ごとにブースLAN の CIDR が変わり、subnet route の設定・承認が手間（本人が Quest を tailnet に参加済み、2026-10-02）。REQ-0001 の「追加アプリを入れず」との整合は本人に確認中 | 20（AD-0002、AD-0004、AD-0010、R-1）、30（DD-0015）、60（事前条件） |
| DD-0002 / DD-0004 / DD-0005 / DD-0006 / DD-0007 | デッドマン（左グリップ）を廃止。`cmd/drive` から `deadman` を削除し、走行・ステージは常にスティック・ボタンどおりに出す。Quest 入力途絶（300 ms）での停止は残す | 本人の決定（2026-10-02、要件変更 REQ-0012） | 10、20、30、40、50、60 |
| DD-0002 / DD-0004 / DD-0005 / DD-0006 / DD-0007 | Quest によるアーム操作（右コントローラ追従・クラッチ・右トリガー把持）を F-001 から削除。`cmd/arm` topic と `out/effective` の `arm` を削除。UT-0006 を廃止 | 本人の決定（2026-10-02）。アームは SO-101 Leader で操作し、別Feature とする（要件変更 REQ-0006） | 00、10、20、30、40、60 |
| DD-0014 | `xr-view.js` の球面の頂点式を修正し、正距円筒の中央（u = 0.5）を正面（-z）に、u の増加を右（+x）に対応させた | 流用元のビューアは左右が鏡像で、画像の継ぎ目が正面に来ていた（2026-10-02、X4 実機の映像を Quest で見て、左右がバラバラに見えることを本人が観察） | 30（DD-0014） |
| DD-0014 | quest ページに URL パラメータ `layout` を追加（`tb`・`bt`：上下に重なった2本の帯を前後に並べて球に貼る。省略時は正距円筒） | X4 の Webcam Mode の映像が、2:1 の正距円筒ではなく、180° ずつの帯2本を上下に重ねたフレームだった（2026-10-02、Quest の平面表示の写真で確認）。どちらの帯が正面かは取り付けによるため URL で選ぶ | 30（DD-0014） |
| DD-0001 | `decode` は bytes も受ける。`src` は空でない文字列であれば受理し、値の集合は検査しない | UDP in の送信元（ローカルモジュール）は任意名で、src は `car_local` に上書きするため | なし（設計の範囲内） |
| DD-0014 / DD-0009（暫定） | Quest を使わずに PC の画面とゲームコントローラーで操縦する pilot ページ（`web/pilot/`）を追加した。hub には `/pilot/` の配信ルートだけを追加した。pilot ページは quest role で接続し、Gamepad API の入力を Quest と同じ形式の `in/quest` で送る（右スティック左右は視点操作に使うので、`right.axes[0]` は 0 で送る）。E-STOP は両スティック押し込み・画面ボタン・`Space`・`Esc` | 本人の指示（2026-10-03）。移動の多い試験で、Quest 無しでも操縦できるようにするため。設計・試験仕様・承認を経ていない（逸脱記録を参照） | 未（暫定のため。正式化する場合は別 Feature として設計する） |

## 設計に無い副作用

- hub：`--tls-self-signed` 指定時に `openssl` を起動し `.certs/` に鍵と証明書を書く（DD-0009 に追記済み）。
- hub・car_ctrl：`logs/` への JSON Lines 書き込み（DD-0016 のとおり）。

## 追加した依存

- 実行時：`aiohttp`、`aiortc`（30 の「依存」どおり）。
- 開発時：`pytest`、`pytest-asyncio`、`pytest-cov`、`ruff`、`mypy`。

## 試験の作り方

- UT（`tests/unit/`）は、実装より前に 30・40 と公開 IF の決定だけから作成し、実装前に commit した（commit `2674e15`）。
- IT（`tests/integration/`）は、実装を読まない別コンテキスト（サブエージェント）で 20・30・50 と CLI の help だけから作成した。
