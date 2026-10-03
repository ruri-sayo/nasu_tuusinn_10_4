---
kind: IT
feature: F-002
status: draft
---

# Integration Test Spec

### IT-0008: UDP実効命令をROS 2 Joyへ中継する

covers: AD-0011, AD-0012
verify: test

localhost UDPへ `state=RUN, v=0.5, w=0.2` の `out/effective` を送り、`/nasura/drive_joy` で
`axes=[0.2, 0.5]` の `sensor_msgs/msg/Joy` を受信できること。

### IT-0009: 途絶と異常入力で中立出力を維持する

covers: AD-0012, AD-0013
verify: test

`state=STOP`、不正JSON、有効入力200 ms途絶の各条件で、アダプタが `axes=[0.0, 0.0]` を20 Hzで継続発行すること。

### IT-0010: 専用topicと起動構成を分離する

covers: AD-0011, AD-0014
verify: test

起動スクリプトの公開コマンドが `joy:=/nasura/drive_joy` を使用し、既存 `run_car.sh` とROS 2プロセスを同時管理すること。
