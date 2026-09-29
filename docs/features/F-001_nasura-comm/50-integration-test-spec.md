---
kind: IT
feature: F-001
status: draft
---

# F-001 結合試験仕様

1台のマシン上で、hub と car_ctrl を実プロセス（または同一イベントループ内の実インスタンス）として起動し、aiortc の実 DataChannel・実 WebSocket・実 UDP で結合する。ブラウザは使わず、quest/booth の役は WebSocket の試験クライアントが担う。タイムアウト系の試験は実時間で行い、許容誤差を ±50 ms とする。

### IT-0001: 命令が車載の UDP out まで届く

covers: AD-0005, AD-0008

1. hub・car_ctrl を起動し、S3 が connected になるまで待つ（上限 10 秒）。
2. 試験クライアント（role=quest）が deadman=true、left.y=-1 の `in/quest` を 30 Hz で送る。
3. `127.0.0.1:47001` で受信する。

合格：1秒以内に `state=RUN` かつ `drive.v ≈ 1.0` の `out/effective` を受信する。受信間隔の平均が 50±10 ms。

### IT-0002: heartbeat 途絶で停止する

covers: AD-0007

1. IT-0001 の状態から、hub プロセスを強制終了（SIGKILL）する。

合格：強制終了から 550 ms 以内に `state=STOP` かつ drive 0/0 の `out/effective` を受信し、以後も 20 Hz で停止値が出続ける。hub 再起動後、S3 が自動で再接続し（上限 15 秒）、入力再開で RUN に戻る。

### IT-0003: E-STOP のラッチと解除

covers: AD-0007

1. IT-0001 の状態で、試験クライアント（quest）が `in/estop` を送る。
2. quest から `in/estop_release` を送る。
3. 試験クライアント（role=booth）から `in/estop_release` を送る。

合格：1 の後 200 ms 以内に `state=ESTOP`、drive 0/0。2 では ESTOP のまま。3 の後 RUN に戻り、入力どおりの命令が出る。hub の `/status` の car_state が各段階で一致する。

### IT-0004: テレメトリの投入と破棄

covers: AD-0006, AD-0008

試験用に拡張 topic `tlm/test_value`（up, ctrl, 5 Hz）を登録した状態で起動する。

1. `127.0.0.1:47002` に `tlm/test_value` を 5 Hz で 3 秒投げる。
2. 未登録の `tlm/unknown` を投げる。
3. `tlm/test_value` を 50 Hz で 2 秒投げる。

合格：1 は booth 役の試験クライアントに WebSocket の `env` として届く（件数 15±2）。2 は届かず、`/status` の dropped に計上される。3 は届く件数が 10±2 に制限される。いずれの間も car_ctrl・hub は停止しない。

### IT-0005: シグナリングの中継と再接続

covers: AD-0002, AD-0004

試験クライアント4つ（quest・booth・car_media 役の WebSocket、car_ctrl は実プロセス）。

1. car_media 役、quest 役の順に接続する。
2. car_media 役が S1 の sdp、quest 役が S1 の candidate を送る。
3. quest 役を切断し、再接続する。

合格：1 で car_media 役が `restart(S1)` を受ける。2 はそれぞれ相手にだけ届き、booth 役には届かない。3 の切断で car_media 役が `peer down(S1)`、再接続で `restart(S1)` を受ける。

### IT-0006: RTT と状態が /status に出る

covers: AD-0009

1. IT-0001 の状態で `/status` を取得する。
2. car_ctrl 側に 100 ms の人工遅延（ack 送信前に sleep する試験用フラグ）を入れて再取得する。

合格：1 で roles.car_ctrl=true、sessions.S3=connected、rtt_ms が数値、car_state=RUN。2 で rtt_ms が 100 ms 以上増える。

### IT-0007: 入力途絶で停止命令が出る

covers: AD-0005, AD-0007

1. IT-0001 の状態で、試験クライアント（quest）の送信を止める（接続は維持）。
2. deadman=false の入力を再開する。

合格：1 の停止から 350 ms 以内に drive 0/0 の `out/effective`（state は RUN のまま）。2 の間も drive 0/0。
