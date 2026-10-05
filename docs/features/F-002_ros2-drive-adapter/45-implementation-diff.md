---
kind: IMPLEMENTATION_DIFF
feature: F-002
status: draft
---

# Implementation Diff

## Implemented but not designed

- Tailscale Serveの追加設定にroot権限が必要だったため、既存の自己署名TLSフォールバックで車載側が接続できる `INSECURE_TLS=1` を `scripts/run_car.sh` に追加した。このフラグは `car_ctrl --insecure` とChromiumの自己署名証明書許容を同時に有効化する。
- ROS 2のsetupスクリプトが未定義変数を参照するため、source中だけshellの `nounset` を無効化した。
- 2026-10-05：`scripts/run_car_ros2.sh` が Pico と通信する micro-ROS エージェント（`ros2 run micro_ros_agent micro_ros_agent serial --dev ...`）を起動していなかったため、同時に起動するようにした（それまでは手で `--dev /dev/ttyACM0` を指定して起動していた）。デバイスは `PICO_DEV`、なければ `/dev/nasura_pico`（`scripts/udev/99-nasura-pico.rules`、Pico のシリアル番号で固定）、なければ唯一の `/dev/serial/by-id/*Raspberry_Pi_Pico*` を使う。`/dev/ttyACM*` は SO-101 の基板と番号が入れ替わるので推測しない。本人の指示（Pico を登録して ttyACM0 以外で起動）。AD-0011 の構成図にエージェントは無い（設計書は未更新）。

## Designed but not implemented

- なし

## Verification Notes

- 純粋変換・途絶・競合ラッチの新規単体試験9件はPASS。
- 模擬UDP `v=0.5, w=0.2` を実ROS 2ノードへ入力し、`/nasura/drive_joy` の `axes=[0.2, 0.5]` を確認。
- 既存結合試験7件はPASS。
- 実機起動で `car_media=true`, `car_ctrl=true`, `S3=connected`, `car_state=RUN` を確認。X4の `/dev/video0` はChromeのvideo capture processが使用中。Quest未接続のためS1は未成立。
