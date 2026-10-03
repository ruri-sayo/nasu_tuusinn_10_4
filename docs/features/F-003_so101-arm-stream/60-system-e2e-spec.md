---
kind: ST
feature: F-003
status: draft
---

# System E2E Spec

### ST-0019: 左右SO-101の追従動作を確認する

covers: REQ-0025, REQ-0027
verify: test

method: manual

両Followerを無負荷とし、電源遮断担当を配置して起動する。左右Leaderの各6関節を可動範囲中央付近で
小さく個別操作し、同じ側のFollowerだけが対応して追従すること。その後、左右を同時に5分間操作し、
プロセスが継続すること。実施commit、ハードウェア情報commit、LeRobot commitを結果へ記録する。

### ST-0020: 片側切断時の停止を確認する

covers: REQ-0028
verify: test

method: manual

先に片側Followerの電源を切り、その後USBを抜く。対象LeRobotプロセスの終了を起点に、反対側LeRobotと
配信プロセスも停止すること。再接続時に自動再起動しないこと。介添人が電源遮断できることも確認する。

### ST-0021: アーム稼働中の映像配信を確認する

covers: REQ-0029
verify: test

method: manual

F-001のS1〜S3が接続済みの状態で左右アームを5分間同時操作する。QuestでX4映像が継続し、boothで
S1〜S3と車載状態が正常であり、アーム操作によって走行・ステージ命令が変化しないこと。

### ST-0022: 未接続状態では起動を拒否する

covers: REQ-0026
verify: test

method: automated

SO-101を接続しない状態で公開起動コマンドを実行し、4個のデバイス欠落を列挙して非0終了し、
LeRobot、`run_car.sh`、Chromiumが起動しないこと。

### ST-0023: 試験ログを確認する

covers: REQ-0030
verify: test

method: manual

正常起動とST-0020の異常停止後に、supervisor・left arm・right armのログが存在し、指定した両commit、
検査結果、各子PID、開始・停止理由、終了コードを時刻付きで追跡できること。認証情報が含まれないこと。
