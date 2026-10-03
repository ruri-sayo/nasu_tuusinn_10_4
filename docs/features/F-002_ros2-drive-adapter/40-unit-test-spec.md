---
kind: UT
feature: F-002
status: draft
---

# Unit Test Spec

### UT-0014: out/effectiveを検証して受理する

covers: DD-0017, MD-0001
verify: test

公開I/F `decode_effective()` に正常な `out/effective` を与えて値が取得できること。topic、ver、src、state、
drive型・範囲、seqが契約外の場合は `None` となること。

### UT-0015: RUN命令をJoy軸へ変換する

covers: DD-0018, MD-0001
verify: test

`state=RUN, v=0.6, w=-0.25` を与えたとき、`to_joy_axes()` が `(-0.25, 0.6)` を返すこと。

### UT-0016: 非RUN状態を中立入力へ変換する

covers: DD-0018, MD-0001
verify: test

`INIT`, `STOP`, `ESTOP` の各状態で、非零の `v`, `w` を含めても `(0.0, 0.0)` を返すこと。

### UT-0017: 入力途絶で中立入力へ移行する

covers: DD-0017, DD-0019, MD-0001
verify: test

起動時と有効入力の200 ms途絶後は中立出力を選び、途絶後の低いseqを新世代として受理すること。
不正データグラムと重複seqは有効受信時刻を更新しないこと。

### UT-0018: publisher競合をラッチする

covers: DD-0020, MD-0001
verify: test

自ノード以外のpublisher検出で競合状態がラッチされ、publisherが消失しても自動解除されず中立出力を続けること。

### UT-0019: ログ状態遷移を抑制する

covers: DD-0022, MD-0001
verify: test

受信、途絶、復帰、状態変化の通知は遷移したときだけ発生し、20 Hzの入力ごとに同じ通知を繰り返さないこと。
