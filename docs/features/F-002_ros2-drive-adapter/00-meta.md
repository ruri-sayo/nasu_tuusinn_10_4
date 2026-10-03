---
kind: FEATURE
feature: F-002
status: draft
tier: L
---

# F-002 ROS 2走行制御アダプタ

## Overview

F-001の車載制御プロセスが出力する安全判定済みの `out/effective` を、既存のROS 2
`joy_motor_controller` が購読する `sensor_msgs/msg/Joy` に変換する。Insta360 X4の映像伝送と
走行制御を同じ車載PC上で同時に稼働させる。

## Tier Decision

**L**。ROS 2との外部I/F、別リポジトリの既存ノード、車載モータの実機駆動経路に影響する。
入力競合やプロセス停止が予期しない走行につながるため、基本設計・詳細設計・モジュール設計と
UT・IT・STを必須とする。

## Scope

| 区分 | 内容 |
|---|---|
| 対象 | localhost UDP受信、`out/effective` 検証、`Joy` 変換、途絶時の中立出力、ROS 2ノードと映像系の同時起動 |
| 対象外 | `joy_motor_controller` のPWM変換式の変更、Picoファームウェア、モータドライバ、アーム制御 |

## External Constraints

- ROS 2 Humbleと `/home/nasc/roarm_ws_em0`にビルド済みの `joy_motor_controller` を利用する。
- モータ出力の最終的な物理停止は介添人が担う。
- 実機駆動と新たな外部I/Fは、本Featureの設計承認をH4承認として扱う。
