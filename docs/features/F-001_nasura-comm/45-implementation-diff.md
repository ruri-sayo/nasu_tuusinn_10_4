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
| DD-0001 | `decode` は bytes も受ける。`src` は空でない文字列であれば受理し、値の集合は検査しない | UDP in の送信元（ローカルモジュール）は任意名で、src は `car_local` に上書きするため | なし（設計の範囲内） |

## 設計に無い副作用

- hub：`--tls-self-signed` 指定時に `openssl` を起動し `.certs/` に鍵と証明書を書く（DD-0009 に追記済み）。
- hub・car_ctrl：`logs/` への JSON Lines 書き込み（DD-0016 のとおり）。

## 追加した依存

- 実行時：`aiohttp`、`aiortc`（30 の「依存」どおり）。
- 開発時：`pytest`、`pytest-asyncio`、`pytest-cov`、`ruff`、`mypy`。

## 試験の作り方

- UT（`tests/unit/`）は、実装より前に 30・40 と公開 IF の決定だけから作成し、実装前に commit した（commit `2674e15`）。
- IT（`tests/integration/`）は、実装を読まない別コンテキスト（サブエージェント）で 20・30・50 と CLI の help だけから作成した。
