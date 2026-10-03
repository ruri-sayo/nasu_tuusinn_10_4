---
kind: IMPLEMENTATION_DIFF
feature: F-002
status: draft
---

# Implementation Diff

## Implemented but not designed

- Tailscale Serveの追加設定にroot権限が必要だったため、既存の自己署名TLSフォールバックで車載側が接続できる `INSECURE_TLS=1` を `scripts/run_car.sh` に追加した。このフラグは `car_ctrl --insecure` とChromiumの自己署名証明書許容を同時に有効化する。
- ROS 2のsetupスクリプトが未定義変数を参照するため、source中だけshellの `nounset` を無効化した。

## Designed but not implemented

- なし

## Verification Notes

- 純粋変換・途絶・競合ラッチの新規単体試験9件はPASS。
- 模擬UDP `v=0.5, w=0.2` を実ROS 2ノードへ入力し、`/nasura/drive_joy` の `axes=[0.2, 0.5]` を確認。
- 既存結合試験7件はPASS。
- 実機起動で `car_media=true`, `car_ctrl=true`, `S3=connected`, `car_state=RUN` を確認。X4の `/dev/video0` はChromeのvideo capture processが使用中。Quest未接続のためS1は未成立。
