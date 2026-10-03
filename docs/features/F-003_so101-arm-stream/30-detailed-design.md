---
kind: DD
feature: F-003
status: draft
---

# Detailed Design

### DD-0023: 設定値と起動時検証

covers: AD-0016, AD-0018
verify: test

公開起動コマンドは `scripts/run_car_so101.sh --confirm-safe-workspace` とする。`HUB_HOST` は既存仕様に従う。
次を環境変数で上書き可能とし、既定値を固定する。

| 変数 | 既定値 | 用途 |
|---|---|---|
| `NASURA_HARDWARE_DIR` | `/home/nasc/hardware` | ハードウェア情報checkout |
| `LEROBOT_DIR` | `/home/nasc/lebot/lerobot` | LeRobot checkout |
| `SO101_MAX_RELATIVE_TARGET` | `5.0` | 1周期の関節位置変化上限（度） |
| `SO101_STARTUP_GRACE_S` | `3` | アーム初期安定時間（秒） |

事前検査は確認オプション、両checkoutのcommit、LeRobot実行ファイル、ハードウェア側 `verify.sh` の成功、
値が正の相対目標制限と初期安定時間を確認する。失敗中は子プロセスを1つも起動しない。

### DD-0024: 左右アームのLeRobot起動引数

covers: AD-0015, AD-0016
verify: test

左右は別々の `lerobot-teleoperate` とし、次の固定対応で起動する。

| 側 | `robot.port` | `robot.id` | `teleop.port` | `teleop.id` |
|---|---|---|---|---|
| 左 | `/dev/left_follower` | `left_follower` | `/dev/left_leader` | `left_leader` |
| 右 | `/dev/right_follower` | `right_follower` | `/dev/right_leader` | `right_leader` |

各プロセスは `robot.type=so101_follower`、`teleop.type=so101_leader`、
`robot.disable_torque_on_disconnect=true`、`robot.max_relative_target=SO101_MAX_RELATIVE_TARGET` を明示する。
`HF_LEROBOT_CALIBRATION` はハードウェアcheckoutの `so101/calibration` とする。

### DD-0025: 相対目標制限

covers: AD-0018
verify: test

既定値5度の `max_relative_target` を左右Followerへ個別に設定し、1周期の指令差分をLeRobotに制限させる。
0以下、数値でない値、5度を超える値は事前検査で拒否する。上限値を変更する場合は、本DDの改訂と
再承認を必要とし、起動時だけの任意変更で安全境界を広げない。

### DD-0026: 子プロセス監視と終了処理

covers: AD-0017, AD-0018
verify: test

親は子PIDを保持し、INT・TERM・EXITを処理する。正常停止では全子へTERMを送り、最大5秒回収を待つ。
残存子だけへKILLを送り、全子をwaitする。いずれか1子が予定外に終了した場合は、その終了コードを記録し、
同じ停止処理を実行して親も非0で終了する。配信は左右アームが初期安定時間を越えるまで起動しない。

### DD-0027: ログと診断出力

covers: AD-0017, AD-0019
verify: test

`logs/` に起動時刻を含む supervisor、left arm、right arm のログを作り、標準出力と標準エラーを保存する。
supervisorログには両checkoutのcommit、検査結果、子PID、開始・停止理由、終了コードを記録する。
USBデバイスのシリアル番号と較正ファイル名は記録してよいが、環境変数全体は記録しない。

### DD-0028: 映像配信起動の委譲

covers: AD-0019
verify: test

既存 `scripts/run_car.sh` を変更せず子プロセスとして呼ぶ。`HUB_HOST`、`CHROMIUM`、`INSECURE_TLS`、
`FAKE_MEDIA` は既存の意味のまま引き継ぐ。アーム起動側は新たな外部通信を開かず、配信URLやWebRTC設定を
生成しない。
