---
kind: AD
feature: F-002
status: draft
---

# F-002 Architecture

## System Context

```text
Quest controller -> hub -> S3 -> car_ctrl -> UDP out/effective
                                                |
                                                v
                                      ros2_drive_adapter
                                                |
                          sensor_msgs/msg/Joy /nasura/drive_joy
                                                |
                                                v
                          joy_motor_controller (joy remapped)
                                                |
                          geometry_msgs/msg/Vector3 /motor_pwm
                                                |
                                                v
                                        Pico motor node

Insta360 X4 -> car_media ============================> Quest
```

F-001の安全状態機械を上流の唯一の命令決定者とし、本Featureは実効命令の検証・形式変換・途絶時の中立化に限定する。

### AD-0011: 車載UDP-to-ROS 2アダプタ構成

covers: REQ-0020, REQ-0022, REQ-0023
verify: test

`ros2_drive_adapter` を `car_ctrl` と `joy_motor_controller` の間に置く。入力はF-001の公開I/Fである
UDP `127.0.0.1:47001`、出力はROS 2 topic `/nasura/drive_joy` とする。`joy_motor_controller`は
`joy:=/nasura/drive_joy` をリマップして起動する。`car_media` は別プロセスのままとし、映像のデータ経路は変更しない。

### AD-0012: out/effectiveからJoyへのデータ契約

covers: REQ-0020, REQ-0021, REQ-0022
verify: test

`out/effective` の `state == "RUN"` のときだけ、正規化値 `w` を `Joy.axes[0]`、`v` を
`Joy.axes[1]` へ写像する。この対応は `joy_motor_controller` の `axis_x=axes[0]`、
`axis_y=axes[1]` とF-001の `w` 正方向に一致する。`stage`は対象外としてROS 2へ渡さない。

`Joy.axes` は `[w, v]`、`Joy.buttons` は空配列、`header.stamp` は発行時のROS clockとする。
`state != "RUN"` のときは `v` と `w` の値にかかわらず `[0.0, 0.0]` を発行する。

### AD-0013: 停止と障害時の安全境界

covers: REQ-0021, REQ-0024
verify: test

アダプタは起動直後から中立走行入力を発行し、最後の有効データグラム受信から200 ms以上経過した場合も
20 Hzで中立走行入力を継続する。不正なデータグラムは有効受信時刻を更新しない。通常終了時は中立走行入力を発行してからROS 2ノードを終了する。

`ros2_drive_adapter` 自体が強制終了した場合は、既存 `joy_motor_controller` のwatchdogが停止PWMを出す。
ただし現行watchdogの最悪停止時間は約0.8秒であり、アダプタ稼働中の200 ms保証とは分けて扱う。

### AD-0014: 車載同時起動と運用境界

covers: REQ-0022, REQ-0023, REQ-0024
verify: review

新規の車載起動スクリプトがROS 2 Humbleと `roarm_ws_em0` をsourceし、次を同時管理する。

- `ros2 run joy_motor_controller joy_motor_controller --ros-args -r joy:=/nasura/drive_joy`
- ROS 2走行アダプタ
- 既存 `scripts/run_car.sh`による `car_ctrl` と `car_media`

終了シグナルは子プロセス全体へ伝搬させる。運用手順は `/joy` に発行する `joy_node` や
`socket_cmd_publisher` を同時起動しない。専用 topicの発行元数を起動時と稼働中に監視し、
自分以外の発行元を検出したら中立走行入力のみに切り替えてエラーを継続表示する。
