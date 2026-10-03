---
kind: AD
feature: F-003
status: draft
---

# Architecture

### AD-0015: 既存系とアーム制御を分離する

covers: REQ-0027, REQ-0028, REQ-0029
verify: test

SO-101はLeRobotのローカルシリアル経路で直接制御し、F-001のhub、S3、`out/effective`、および
F-002のROS 2走行経路には接続しない。左右は独立した `lerobot-teleoperate` プロセスとし、
片側のID・較正・ポートを反対側へ渡せない構造にする。

### AD-0016: ハードウェア情報の参照境界

covers: REQ-0025, REQ-0026
verify: test

ハードウェアcheckoutを外部入力として読み取り専用で参照し、指定commitとの一致を確認する。
checkout内の `so101/scripts/verify.sh` を用いて、追跡済みudevルール、実USB個体、較正ファイルの
存在を検証する。起動側は較正JSONを複製・加工せず、`HF_LEROBOT_CALIBRATION` で参照する。

### AD-0017: プロセス構成とライフサイクル

covers: REQ-0027, REQ-0028, REQ-0030
verify: test

車載アーム・配信起動スクリプトを親プロセスとし、左アーム、右アーム、既存 `run_car.sh` の3子プロセスを
所有する。事前検査完了後に左右アームを起動し、両方が初期安定時間を越えて生存した場合だけ配信を起動する。
親への終了シグナルまたはいずれかの子の終了を全体停止へ伝播する。

### AD-0018: 安全境界と停止責務

covers: REQ-0026, REQ-0028
verify: review

ソフトウェア停止は補助機能であり、安全の最終境界は追従側アームの電源である。起動前に介添人、
電源遮断手段、可動域内の無人・無障害、無負荷を人が確認し、明示的な起動確認オプションを与える。
SO-101の制御プロセスには相対目標制限と切断時トルク無効を明示する。稼働中のUSB抜去試験は、
先に対象Followerの電源を切ってから行う。

### AD-0019: 映像配信との同時稼働

covers: REQ-0029, REQ-0030
verify: test

映像・音声・S3は既存 `scripts/run_car.sh` へ委譲し、F-001の設定と通信契約を変更しない。
アームにカメラを登録せず、Insta360 X4は `car_media` だけが取得する。親プロセスは各子のログを分離し、
終了時に全子を回収する。

## Data and Process Flow

```text
left leader  --USB serial--> LeRobot left process  --USB serial--> left follower
right leader --USB serial--> LeRobot right process --USB serial--> right follower
                                      |
                       supervisor owns lifecycle
                                      |
                              scripts/run_car.sh
                                      |
                         existing S1/S2/S3 pathways
```
