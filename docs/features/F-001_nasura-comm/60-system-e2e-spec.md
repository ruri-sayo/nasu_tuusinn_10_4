---
kind: ST
feature: F-001
status: draft
---

# F-001 システム／E2E 試験仕様

実機（車載PC＋X4、中間サーバ＋カメラ・マイク、Quest 3S）で人間が実施する（H5）。回線は、可能なら 5G モバイルルータ経由で本番に近づける。各項目の `result:`（PASS/FAIL）・`commit:`（実施した commit のフル hash）・`executed_by:`・`executed_at:` を埋め、メモは「結果：」欄に書く。開発機で自動化できる部分は `tests/e2e/` にある（REQ-0001・0002・0003・0005・0008・0017 は実機でのみ判定できる。DEV-0004）。

事前条件：中間サーバ・車載PC・Quest 3S が tailnet に参加済み、hub・car_ctrl・car_media・booth が起動済み、Quest で `https://<hub>/quest/` を開いて Enter VR 済み。

### ST-0001: Quest のブラウザだけで操縦席が成立する

covers: REQ-0001, REQ-0017
method: manual
result:
commit:
executed_by:
executed_at:

手順：Quest Browser で quest ページを開き、マイク許可→Enter VR。
合格：Tailscale 以外のアプリ追加なしで VR 表示に入れる。証明書エラーが出ない（R-1 の fallback を使った場合はメモに記載）。

結果：

### ST-0002: 360°映像が全天球で見える

covers: REQ-0002, REQ-0008
method: manual
result:
commit:
executed_by:
executed_at:

手順：頭を 360° 回す。カメラの前で手を振る。
合格：頭の向きに追従して全周が見える。booth の stats で S1 の fps が 20 以上、手の動きの遅れが体感 0.5 秒以内（ストップウォッチを映して Quest 画面と比較し、差をメモ）。

結果：

### ST-0003: 車載音声が聞こえる

covers: REQ-0003
method: manual
result:
commit:
executed_by:
executed_at:

手順：車載マイクの近くで話す。
合格：Quest で聞き取れる。会話のテンポが崩れない。

結果：

### ST-0004: パイロット映像が車載モニタに出る

covers: REQ-0004, REQ-0009
method: manual
result:
commit:
executed_by:
executed_at:

手順：booth カメラの前に座る。
合格：車載モニタに全画面で表示される。booth の stats で S2 の送信ビットレートが 400 kbps 以下。

結果：

### ST-0005: パイロット音声が車載で聞こえる、エコーが実用範囲

covers: REQ-0005
method: manual
result:
commit:
executed_by:
executed_at:

手順：booth マイクで話し、同時に車載側でも話す。
合格：双方で聞き取れる。Quest 側に自分の声が大きく返ってこない。

結果：

### ST-0006: 操作命令が車載に届く

covers: REQ-0006
method: manual
result:
commit:
executed_by:
executed_at:

手順：車載PCで `nc -ul 127.0.0.1 47001`（または付属のダンプツール）を実行し、Quest で左スティックを倒す。A・B と右スティックを操作する。
合格：drive・stage の値が操作に追従する。スティックとボタンを離すと 0 になる。

結果：

### ST-0007: 上り帯域が 3.0 Mbps 以内

covers: REQ-0007
method: manual
result:
commit:
executed_by:
executed_at:

手順：全系統を 5 分間動かし、booth の表示と車載PCの `nload`（または `ifstat`）で tailscale0 の送信量を記録する。
合格：5 分間の平均が 3.0 Mbps 以下、10 秒平均の最大が 3.5 Mbps 以下。

結果：

### ST-0008: 通信途絶で停止する

covers: REQ-0010, REQ-0015
method: manual
result:
commit:
executed_by:
executed_at:

手順：ST-0006 の状態で、(a) 中間サーバの LAN ケーブルを抜く／Wi-Fi を切る、(b) S1 だけを切る（car_media のタブをリロード）。
合格：(a) UDP out が 1.5 秒以内に state=STOP・停止値になる（ダンプのタイムスタンプで確認）。(b) の間、UDP out は RUN のまま命令が継続する。

結果：

### ST-0009: E-STOP

covers: REQ-0011
method: manual
result:
commit:
executed_by:
executed_at:

手順：Quest で両スティック押し込み。booth の E-STOP ボタン。Quest からの解除を試みる。booth の解除ボタンを2回押す。
合格：どちらの E-STOP でも state=ESTOP。Quest からは解除できない。booth の2回押しで解除され、操作で RUN に戻る。

結果：

### ST-0010: 入力途絶

covers: REQ-0012
method: manual
result:
commit:
executed_by:
executed_at:

手順：左スティックで走行させている途中でヘッドセットを外す（XR セッション終了）。
合格：drive が 0.5 秒以内に 0 になる。

結果：

### ST-0011: 自動復帰とネットワーク経路

covers: REQ-0018, REQ-0017
method: manual
result:
commit:
executed_by:
executed_at:

手順：hub、car_ctrl、car_media、quest ページをそれぞれ1回ずつ再起動（リロード）する。車載PCで `tailscale ping <hub>` を実行する。
合格：どれを再起動しても 15 秒以内に全系統が戻り、他ノードの操作は不要。`tailscale ping` が direct（DERP relay でない）。relay の場合は FAIL ではなくメモに記録する（R-3）。

結果：

### ST-0012: 監視表示と車載負荷

covers: REQ-0019
method: manual
result:
commit:
executed_by:
executed_at:

手順：booth ページを見ながら ST-0007 を実施。車載PCで `top` を確認する。
合格：RTT・S1/S2 のビットレートと fps・接続状態・車載状態が 1 秒ごとに更新される。車載 CPU 使用率（全体）を記録する（合否ではなく R-2 の判断材料）。

結果：

### ST-0013: テレメトリ経路

covers: REQ-0013, REQ-0014, REQ-0016
method: manual
result:
commit:
executed_by:
executed_at:

手順：車載PCで `scripts/fake_telemetry.py` を使い、試験用に登録した `tlm/test_value` と未登録の `tlm/unknown` を送る。
合格：`tlm/test_value` が booth の表示（または /status）に届く。`tlm/unknown` は dropped に計上され、他の系統に影響しない。

結果：
