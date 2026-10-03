---
kind: UT
feature: F-003
status: draft
---

# Unit Test Spec

### UT-0020: 設定とファイル検査

covers: DD-0023, MD-0003
verify: test

公開I/F `validate_config()` に一時checkoutと実行ファイルを与え、commitと必須ファイルが一致すれば
エラーが空になること。不一致commit、欠落ファイル、実行不可ファイル、0以下・5超・数値でない設定を
それぞれ拒否し、検出した全エラーを返すこと。

### UT-0021: デバイス名と較正IDの対応

covers: DD-0024, MD-0003
verify: test

公開I/F `arm_command()` が左には `left_follower` と `left_leader`、右には `right_follower` と
`right_leader` のポート・IDだけを含むこと。較正root、型、切断時トルク無効、相対目標制限を明示し、
未知のsideを拒否すること。

### UT-0022: LeRobot起動引数の生成

covers: DD-0024, DD-0025, MD-0003
verify: test

同じ設定から生成した引数配列が決定的で、shell展開を含まず、左右で共通する安全引数と個別のID・ポートを
正しく分離すること。既定の相対目標制限が文字列 `5.0` として両方へ渡ること。

### UT-0023: 子プロセス終了の伝播

covers: DD-0026, MD-0004
verify: test

テスト用の子プロセス3個を起動スクリプトへ注入し、INT、TERM、各子の予定外終了について、残る全子へ
TERMが送られ、回収不能な子だけが5秒後にKILLされ、全PIDがwaitされること。

### UT-0024: ログ分離と診断情報

covers: DD-0027, MD-0004
verify: test

模擬子プロセスの標準出力・標準エラーがleft、right、supervisorの各ログへ混線せず保存されること。
supervisorログに固定した両commit、PID、開始・停止理由、終了コードが含まれ、環境変数全体は含まれないこと。

### UT-0025: 既存配信起動への委譲

covers: DD-0028, MD-0004
verify: test

左右の模擬アームが初期安定時間を越えるまで `run_car.sh` を呼ばず、その後1回だけ呼ぶこと。
既存の `HUB_HOST`、`CHROMIUM`、`INSECURE_TLS`、`FAKE_MEDIA` を変更せず子へ継承すること。
