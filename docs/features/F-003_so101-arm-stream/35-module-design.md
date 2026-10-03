---
kind: MD
feature: F-003
status: draft
---

# Module Design

### MD-0003: SO-101事前検査モジュール

covers: DD-0023, DD-0024, DD-0025
verify: test

`src/nasura_comm/so101_preflight.py` は設定を値オブジェクトとして読み、純粋な検査と起動引数生成を提供する。

- `PreflightConfig`: checkout、commit、実行ファイル、較正root、相対目標制限、初期安定時間を保持する。
- `validate_config(config)`: ファイル、commit、数値範囲を検査し、全エラーを返す。実機を開かない。
- `arm_command(side, config)`: 左右の公開対応表から引数配列を生成する。shell文字列を生成しない。
- CLI `python -m nasura_comm.so101_preflight`: ハードウェア側 `verify.sh` を実行し、成功時だけ0を返す。

Responsibilitiesは起動前検査と決定的な引数生成である。Non-responsibilitiesはシリアル接続、サーボ駆動、
較正、映像配信、子プロセス監視である。

### MD-0004: 車載アーム・配信起動スクリプト

covers: DD-0026, DD-0027, DD-0028
verify: test

`scripts/run_car_so101.sh` は安全確認オプションの受付、事前検査呼び出し、左右LeRobotと既存
`run_car.sh` の起動、ログ振り分け、終了伝播だけを担う。

Responsibilitiesは3子プロセスのライフサイクルと診断ログである。Non-responsibilitiesはLeRobot内部制御、
較正値解釈、F-001通信、カメラ選択である。Side Effectsはログファイル作成、外部プロセス起動、
USBシリアル経由の実機駆動、既存 `run_car.sh` によるネットワーク通信とChromium起動である。
