---
kind: MD
feature: F-002
status: draft
---

# F-002 Module Design

### MD-0001: ROS 2走行アダプタモジュール

covers: DD-0017, DD-0018, DD-0019, DD-0020, DD-0022
verify: test

`src/nasura_comm/ros2_drive.py`はROS 2に依存しない変換・状態管理を所有する。

- `EffectiveDrive`: `state`, `v`, `w`, `seq` を保持する不変データ。
- `decode_effective(data)`: エンベロープとpayloadを検証する純粋関数。
- `to_joy_axes(effective)`: `state`を反映した `(axis_x, axis_y)` を返す純粋関数。
- `DriveInputState`: seq世代、有効受信時刻、最新命令、途絶、publisher競合ラッチを管理する。

`src/nasura_comm/ros2_drive_node.py` はUDP socket、ROS 2 timer、`Joy` publisher、ROS graph監視とログのみを所有する。
UDP受信はROS 2 executorと競合しないよう非ブロッキングsocketをtimerからdrainする。

ResponsibilitiesはUDP→ROS 2変換、途絶と競合の中立化。Non-responsibilitiesはPWM計算、モータ駆動、F-001の安全状態決定である。

### MD-0002: 車載ROS 2起動スクリプト

covers: DD-0021
verify: review

`scripts/run_car_ros2.sh` はROS 2環境の検証、`joy_motor_controller` の専用 topicリマップ起動、
ROS 2走行アダプタ起動、既存 `run_car.sh` の呼び出し、シグナル時の後始末だけを担う。
各子プロセスのビジネスロジックやROS 2メッセージ生成は担わない。
