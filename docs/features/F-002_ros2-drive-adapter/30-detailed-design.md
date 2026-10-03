---
kind: DD
feature: F-002
status: draft
---

# F-002 Detailed Design

## Constants

| 名称 | 値 | 意味 |
|---|---:|---|
| `UDP_ADDR` | `127.0.0.1:47001` | F-001の実効命令受信先 |
| `JOY_TOPIC` | `/nasura/drive_joy` | NASURA専用ROS 2走行入力 |
| `INPUT_TIMEOUT_MS` | `200` | 有効入力途絶判定 |
| `PUBLISH_PERIOD_MS` | `50` | 中立入力の継続発行周期 |

### DD-0017: UDP受信とエンベロープ検証

covers: AD-0011, AD-0012, AD-0013
verify: test

`decode_effective(data: bytes) -> EffectiveDrive | None` はF-001の公開エンベロープ検証を通した後、
次の条件をすべて満たす場合だけ値を返す。

- `topic == "out/effective"`、`ver == 1`、`src == "car_ctrl"`
- `payload.state` が `INIT | RUN | STOP | ESTOP` のいずれか
- `payload.drive.v` と `.w` がboolでない有限の数値で、`[-1.0, 1.0]` の範囲内
- `seq` が同一世代で直前より大きい

不正入力と重複・逆行seqは破棄し、有効受信時刻を更新しない。200 ms以上の途絶後は
seq世代をリセットし、再起動した `car_ctrl` のseqを受け入れる。

### DD-0018: 実効命令からJoyメッセージへの変換

covers: AD-0012
verify: test

`to_joy_axes(effective: EffectiveDrive) -> tuple[float, float]` は、`state == "RUN"` の場合に
`(w, v)`、それ以外の場合に `(0.0, 0.0)` を返す。ROS 2ノードはこれを
`Joy.axes = [axis_x, axis_y]` とし、`buttons = []` で発行する。入力値の符号反転やPWMスケーリングは行わない。

### DD-0019: 入力途絶監視と停止出力

covers: AD-0013
verify: test

`DriveInputState` は単調時計で最後の有効受信時刻を保持する。起動時、最後の有効受信から
200 ms以上、または競合publisher検出中のいずれかで中立出力を選ぶ。50 ms timerで必ず発行し、
正常入力受信時はデータグラムごとに発行する。通常終了ハンドラでも中立入力を1回発行する。

### DD-0020: ROS 2 publisherと競合検出

covers: AD-0013, AD-0014
verify: test

ROS 2ノード名は `ros2_drive_adapter`、publisherは `/nasura/drive_joy`、QoS depthは10とする。
1秒ごとに `get_publishers_info_by_topic()` を確認し、自ノード以外のpublisherを1つ以上検出した場合は
`conflict` をラッチして中立入力だけを発行する。競合解消後も自動で走行入力へ復帰せず、
プロセスの再起動を必要とする。

### DD-0021: プロセス起動と終了処理

covers: AD-0011, AD-0014
verify: test

`scripts/run_car_ros2.sh` は `HUB_HOST` を必須とし、`ROS_DISTRO_SETUP`と `ROS_WORKSPACE_SETUP` でsource先を
上書きできる。既定値は `/opt/ros/humble/setup.bash` と `/home/nasc/roarm_ws_em0/install/setup.bash` とする。
両ファイルと `joy_motor_controller` 実行ファイルの存在を、モータ系プロセスの起動前に検証する。

起動順序は `joy_motor_controller` → `ros2_drive_adapter` → `scripts/run_car.sh` とする。
`EXIT`, `INT`, `TERM` でアダプタ、モータコントローラの順に終了シグナルを送り、子プロセスを回収する。

### DD-0022: ログと診断

covers: AD-0013, AD-0014
verify: test

最初の正常受信、状態変化、途絶への遷移と復帰、不正データグラムの初回破棄、競合publisher検出をログに記録する。
20 Hzの各メッセージは通常時にログ出力しない。破棄件数は理由別に保持し、終了時に要約を表示する。
