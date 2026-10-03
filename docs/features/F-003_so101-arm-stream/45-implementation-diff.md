---
kind: IMPLEMENTATION_DIFF
feature: F-003
status: draft
---

# Implementation Diff

2026-10-04、本人の指示により、設計承認前に暫定実装した（逸脱記録を参照）。本人の決定で、Leader を操縦側ラップトップ（Windows）に、Follower を車載PC（Linux）に接続する構成とした。設計（全4台を車載PCに直結し、`lerobot-teleoperate` で動かす）とは機器の配置が異なる。

## Implemented but not designed

| 設計項目 | 差分 | 理由 |
|---|---|---|
| AD-0015 / DD-0024 | `lerobot-teleoperate` を使わない。Leader 側 `scripts/so101_leader_stream.py`（ラップトップ）が関節位置を 30 Hz で読み、tailnet 上の UDP（左 47110・右 47111）で車載PCへ送る。Follower 側 `scripts/so101_follower_sink.py`（車載PC）が受信して `send_action` する。左右は別プロセス・別ポートで、フレームにも side を入れて不一致を破棄する | Leader と Follower が別のPCにあるため（本人の決定） |
| AD-0015 | アーム制御データは F-001 の hub・S3・`out/effective` を通らない（REQ-0029 は維持） | 既存系との分離 |
| AD-0016 / DD-0023 / MD-0003 | `so101_preflight.py` と `verify.sh` を使わず、`src/nasura_comm/arm_stream.py`（純粋ロジック）と `scripts/so101_arm_common.py` が、プロセスごとに自分の担当機器だけを検査する。検査項目：ハードウェアcheckout の commit が `8ec5487…` であること、udev ルールに担当機器があること、較正ファイルがあること、udev ルールのシリアル番号を持つ USB 機器が接続されていること。udev のリンク名ではなく、シリアル番号で COM／tty を探す | `verify.sh` は4台が同じLinux機にある前提で、Windows でも動かないため |
| DD-0024 | 較正の確認で LeRobot の対話プロンプトを使わない。モーターの較正値がファイルと違う場合は、トルクを切ってからファイルの値を書く（LeRobot で ENTER を押したときと同じ処理。値は生成しない）。Follower は、トルクを入れる前に Goal_Position を Present_Position に揃える | 無人起動のため。接続時にアームが跳ばないようにするため |
| DD-0025 | 設計どおり、`max_relative_target` の既定値は 5°。0 以下・数値以外・5° 超は拒否する | 変更なし |
| DD-0026 / MD-0004 | 車載側 `scripts/run_car_so101_remote.sh` は左右2つの Follower だけを起動し、どちらかが終了したら他方も停止する（TERM、5 秒後に KILL）。`run_car.sh`（映像）は起動しない（従来どおり別に起動する） | 暫定のため、構成を最小にした |
| 追加（設計に無い） | Follower は、受信が 500 ms 途絶えたら新しい目標を送らず、その位置で保持する（トルクは入れたまま）。プロセスの終了時は、設計どおりトルク無効で切断する | ネットワーク途絶時に脱力して落下させないため。最終停止は介添人による電源遮断（AD-0018） |
| 追加（設計に無い） | Leader 側は、読み取りが約 2 秒連続で失敗したら終了する（Follower は保持する） | Leader の抜去を操縦者に気づかせるため |
| DD-0027 | ログは `logs/so101-<leader|follower>-<side>-<時刻>.log`。supervisor ログは無い | 暫定 |
| 実行環境 | ラップトップに LeRobot（commit `5aa74557`、0.6.2、Python 3.12、CPU 版 torch）を `%USERPROFILE%\lebot\lerobot\.venv` に入れた。ハードウェア情報は `%USERPROFILE%\hardware` に `8ec5487` で置いた | 本人の許可（2026-10-04） |

## Designed but not implemented

- MD-0003 `so101_preflight.py`、MD-0004 `run_car_so101.sh`（4台を車載PCに直結する構成）。
- DD-0027 の supervisor ログ、DD-0028 の映像配信起動の委譲。

## Tests

- `tests/unit/test_arm_stream.py`（`impl_aware`）：udev ルールの解析、較正ファイルのパス、ハードウェアcheckout の検査、`max_relative_target` の範囲、フレームの検証、左右の取り違えの拒否、順序、新しいセッション、途絶の判定。
- ラップトップ上のループバック（偽の Leader・Follower）：追従を開始すること、Leader の停止から約 0.5 秒で保持に変わること、SIGINT でトルク無効の切断になることを確認した。
- 実機（SO-101・tailnet 越し）では未確認。
