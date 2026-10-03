---
kind: ST
feature: F-002
status: draft
---

# System E2E Spec

### ST-0014: Quest走行入力がmotor_pwmへ到達する

covers: REQ-0020
verify: test

method: manual

駆動輪を浮かせ、Questの左スティックを前後左右へ操作する。`/motor_pwm` の左右値と車輪の回転方向が操作に一致すること。

### ST-0015: 停止状態と途絶でmotor_pwmがゼロになる

covers: REQ-0021
verify: test

method: manual

STOP、E-STOP、`car_ctrl` 停止の各条件を与え、`/motor_pwm` の左右値がゼロになり車輪が停止すること。

### ST-0016: 既存joy_motor_controllerを利用して起動する

covers: REQ-0022
verify: test

method: automated

`ros2 node info /joy_motor_controller` で `/nasura/drive_joy` の購読と `/motor_pwm` の発行が確認できること。

### ST-0017: X4配信と走行制御を同時稼働する

covers: REQ-0023
verify: test

method: manual

X4の映像をQuestで表示した状態で走行入力を5分間操作し、映像とROS 2走行出力が同時に継続すること。

### ST-0018: 走行入力publisherを単一化する

covers: REQ-0024
verify: test

method: automated

`ros2 topic info /nasura/drive_joy --verbose` でpublisherが `ros2_drive_adapter` 1つだけであること。試験用の競合publisherを起動した場合は、アダプタが中立出力へラッチすること。
