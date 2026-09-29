---
kind: UT
feature: F-001
status: draft
---

# F-001 単体試験仕様

対象は純粋ロジックのモジュール。時刻は引数で与え、実時間・ネットワークを使わない。試験は本仕様と上流文書（DD）から作成し、実装を参照しない（Specification-derived）。

### UT-0001: エンベロープの生成と検証

covers: DD-0001

- `make`→`encode`→`decode` で元と同じ内容に戻る。
- JSON 不正、キー欠落（6キーそれぞれ）、型不正（seq が文字列、payload が配列 等）で `None`。例外が出ないこと。
- topic 形式違反（`Cmd/drive`、`cmd`、`cmd//x`、65文字）で `None`。
- 16 KiB を超える文字列で `None`。

### UT-0002: topic 登録表

covers: DD-0002

- 固定 topic 8件が表どおりの方向・チャネル・最大Hzで引ける。
- 未登録名で `lookup` が `None`。
- `EXTENSIONS` に固定 topic と同名、または予約接頭辞（`sys/` `cmd/` `in/` `out/`）の項目を入れると `ValueError`（テストでは登録表を検証する関数を直接呼ぶ）。
- `to_json()` に全登録 topic が含まれる。

### UT-0003: SeqFilter

covers: DD-0003

- 同じ (src, topic) で seq 5 の後に 4・5 は拒否、6 は受理。
- src または topic が違えば独立に判定される。
- 最大 seq 5000 の後に seq 3 は受理（リセット扱い）、seq 4500 は拒否。

### UT-0004: RateLimiter

covers: DD-0003

- 10 Hz の topic：t=0 受理、t=50 拒否、t=100 受理。
- `max_rate_hz=None` は連続で全て受理。

### UT-0005: 走行・ステージの変換

covers: DD-0004

- deadman（left.grip）0.4 → drive 0/0、stage 0/0。0.6 → 有効。
- デッドゾーン：|stick| = 0.1 → 0。スティック上いっぱい（y=-1）→ v=1。右いっぱい（x=1）→ w=-1。
- デッドゾーン外の再スケール：|stick| = 0.15 の直後がほぼ 0、1.0 で 1.0 になり、単調増加。
- a のみ → stage.x=+1、b のみ → -1、両方 → 0。

### UT-0006: アームのクラッチ

covers: DD-0004

- right.grip 立ち上がりで clutch_id が 1 増え、その瞬間の p=[0,0,0]、q≈[0,0,0,1]。
- 基準から +0.1 m（x）動かすと p≈[0.1,0,0]。基準から y 軸 90° 回すと q が y 軸 90° の四元数。
- grip を離すと enable=false、p/q が恒等、clutch_id は据え置き。再度握ると +1。
- right.pose が null のときは enable=false。

### UT-0007: hub 制御コア

covers: DD-0005

- 入力が一度も無い状態で tick → 停止値の cmd と heartbeat が出る。
- 入力を t=0 に与え、t=200 の tick → 入力に基づく cmd。t=301 の tick → 停止値。
- heartbeat は 100 ms ごと、cmd は 33 ms ごとに出る（t=0〜1000 の tick を 1 ms 刻みで回して個数を数える：hb 10±1、各 cmd 30±1）。
- `in/estop` → 戻り値に `sys/estop` が含まれ、以後の cmd は入力があっても停止値。
- booth 以外からの `in/estop_release` では解除されない。booth からなら `sys/estop_release` が出て、入力に基づく cmd に戻る。
- `sys/heartbeat_ack`（t_hub=1000）を now=1040 で受けると rtt_ms=40。

### UT-0008: 安全状態機械の遷移

covers: DD-0006

- 初期は INIT、effective は停止値。
- heartbeat → RUN。新しい cmd/drive（deadman=true, v=0.5）→ effective の v=0.5。
- heartbeat 最終受信から 499 ms で RUN、501 ms で STOP、effective は停止値。
- STOP 中に heartbeat → RUN になるが、新しい cmd が来るまで effective は停止値（古い命令が破棄されている）。
- `on_link_down()` → 即 STOP。
- RUN 中、cmd/drive の受信から 301 ms 経過で drive だけ停止値（heartbeat は継続）。
- deadman=false の cmd/drive は v・w が 0。

### UT-0009: E-STOP ラッチ

covers: DD-0006

- RUN / STOP / INIT のいずれからでも `sys/estop` で ESTOP。
- ESTOP 中の heartbeat・cmd は無視され、effective は停止値のまま。
- `sys/estop_release` → STOP。その後の heartbeat で RUN。
- 状態が変わるたびに sys/state 送信フラグが立つ。

### UT-0010: 実効命令の組み立て

covers: DD-0007

- `build_effective` の出力が DD-0007 の形（topic=out/effective、payload に state/drive/arm/stage）で、`decode` を通る。
- 停止値のとき drive 0/0、arm.enable=false、stage 0/0。

### UT-0011: テレメトリ投入の判定

covers: DD-0007

- UDP in の判定関数（I/O と分離した部分）について：
  - 不正 JSON → invalid で破棄
  - 未登録 topic → 破棄、dropped にその topic が計上される
  - 固定 topic（例：cmd/drive）や direction=down の topic → 破棄
  - 登録済み拡張 topic（テスト用に登録）→ 登録どおりのチャネルで転送対象になり、src が `car_local` に置き換わる
  - 最大レート超過 → 破棄

### UT-0012: シグナリングルータ

covers: DD-0008

- car_media → quest の順に hello → 2件目の時点で car_media に `restart(S1)`。
- booth と car_media が揃う → booth に `restart(S2)`。car_ctrl の hello → car_ctrl に `restart(S3)`（hub は常在）。
- quest から S1 の signal → car_media へ転送。booth から S1 の signal → 破棄。
- 同じ role の2回目の hello → 旧ハンドルの close と、揃っていれば restart。
- 旧ハンドルの close は無視される。現行ハンドルの close → 相手に `peer down`。
- `restart_req` は両端が揃っているときだけ offerer に restart。

### UT-0013: 設定・状態 JSON とチャネル設定

covers: DD-0009, DD-0010

- `build_config_json` に S1/S2 の全キーと既定値、`up_budget_bps` が含まれる。CLI 上書き（`--s1-max-bitrate 2000000`）が反映される。
- `build_status` が DD-0009 の形のキーを全て持つ（値が未取得なら null）。
- `channel_options("ctrl")` が順序なし・再送 0、`channel_options("rel")` が順序あり・再送制限なし。未知名は `ValueError`。
