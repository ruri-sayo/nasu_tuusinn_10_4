---
kind: FEATURE
feature: F-003
status: draft
tier: L
---

# F-003 SO-101双腕稼働試験・映像配信

## Overview

NASURAの左右SO-101を、それぞれの操作側アームから追従側アームへ直接テレオペレーションし、
既存の車載映像配信と同時に稼働させる。ハードウェア固有情報は
`ruri-sayo/NASURA2026_LeRobot_info` の指定commitを正本とし、誤接続や不完全な構成では
実機駆動を開始しない。

## Tier Decision

**L**。外部のLeRobot実行環境、4台のUSBシリアル機器、左右12個のサーボ、既存の映像配信、
実機停止手順に影響する。誤った較正値またはデバイス対応は予期しない実機動作につながるため、
REQ・AD・DD・MDとUT・IT・STを必須とする。

## Scope

| 区分 | 内容 |
|---|---|
| 対象 | 左右SO-101の事前検査、2組のLeader/Followerテレオペレーション、子プロセス監視、既存X4映像配信との同時起動、試験ログ |
| 対象外 | LeRobot本体の変更、較正値の生成・変更、学習・推論・データ収集、Questからのアーム操作、既存WebRTCプロトコルの変更、SO-101電源回路の変更 |

## External Constraints

- ハードウェア情報の正本は `https://github.com/ruri-sayo/NASURA2026_LeRobot_info` の commit
  `8ec5487568089dcf3d5ebf2140b46acd12a02bc2` とする。
- LeRobotは既存checkout `/home/nasc/lebot/lerobot` の commit
  `5aa74557`（package version `0.6.2`）と、その既存仮想環境を利用する。
- 追従側アームの電源を即時遮断できる介添人、十分な可動空間、無負荷状態を実機起動の前提とする。
- 外部リポジトリ参照、既存LeRobot依存の利用、ログ書き込み、実機駆動は、REQ・AD・DD・MDの
  人間承認をH4承認として扱う。
- 2026-10-03の調査時点では、この端末に4台のSO-101 USBシリアル機器と映像カメラは接続されておらず、
  Tailscaleも停止している。接続されるまで実機STと配信開始は行えない。
