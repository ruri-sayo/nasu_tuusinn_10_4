---
kind: REQ
feature: F-002
status: draft
---

# F-002 Requirements

## Preconditions and Constraints

- F-001の `car_ctrl` は `127.0.0.1:47001` へ `out/effective` を20 Hzで出力する。
- 対象のROS 2実行コマンドは `ros2 run joy_motor_controller joy_motor_controller`である。
- `joy_motor_controller` は `sensor_msgs/msg/Joy` の `axes[0]`を旋回、`axes[1]`を前後進として受け取る。
- 車両をリフトアップするか駆動輪を浮かせ、介添人が即時に物理停止できる状態でなければ実機STを行わない。

### REQ-0020: 安全判定済み走行命令をROS 2へ中継する

covers: -
verify: test

`car_ctrl` が出力した `out/effective.payload.drive.v` と `.w` を、車載PC上のROS 2走行入力へ
20 Hzで中継できること。`v` は前後進、`w` は反時計回りを正とする旋回である。

### REQ-0021: 停止状態と入力途絶をROS 2へ反映する

covers: -
verify: test

`out/effective.payload.state` が `RUN` 以外の場合は中立走行入力を出力すること。また、
有効な `out/effective` が200 ms途絶した場合、アダプタが稼働している限り200 ms以内に中立走行入力へ
移行し、有効な `RUN` を再受信するまで中立出力を継続すること。

### REQ-0022: 既存のjoy_motor_controllerを利用する

covers: -
verify: test

ROS 2 Humbleに導入済みの `joy_motor_controller` パッケージと実行ファイルを使用し、その
`joy` 購読先をNASURA専用 topicへリマップすること。`joy_motor_controller` 自体のソースコードは
本Featureで変更しない。

### REQ-0023: 映像伝送とROS 2走行制御を同時稼働する

covers: -
verify: test

Insta360 X4の `car_media` と制御系の `car_ctrl`、ROS 2走行アダプタ、
`joy_motor_controller` を同一車載PC上で同時に起動できること。映像セッションの切断・輻輳は
ROS 2への停止判定を妨げないこと。

### REQ-0024: ROS 2走行入力の競合を防止する

covers: -
verify: test

`joy_motor_controller` が購読するNASURA専用 topicの発行元はROS 2走行アダプタ1つだけとし、
別のjoystickノードや遠隔入力ノードとの入力競合を運用上分離すること。
