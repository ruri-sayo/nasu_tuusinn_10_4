# Evidence 20261002T000757

- Target commit: `2155c2347720058fc0fae52d14817fac98b76caa`
- Executed at: 2026-10-02T00:10:02+09:00
- Overall: **FAIL**

## Gates

- format: PASS
- lint: PASS
- typecheck: PASS
- secret_scan: NOT_CONFIGURED
- dependency_audit: NOT_CONFIGURED
- static_analysis: NOT_CONFIGURED
- saalco-check: FAIL
- test.unit: PASS
- test.integration: PASS
- test.e2e: PASS

## Tests

- unit: PASS=67 FAIL=0 NOT_EVALUATED=0
- integration: PASS=11 FAIL=0 NOT_EVALUATED=0
- e2e: PASS=20 FAIL=0 NOT_EVALUATED=0

## Coverage

- Total: 95.03
- Diff: 100.0
- Base: b76447da0ead504cce5ad7fca9cdff92f0afb76a
- Status: PASS

## RTM

- stale: 19

## Open DEV

- DEV-0001: 事前承認なしで設計書を発行する
- DEV-0002: ブラウザ側コードに自動単体試験を用意しない
- DEV-0003: 期限優先で ST の一部を省略する可能性がある
- DEV-0004: 実機でしか確認できない REQ に自動の verifies 試験が無い
- DEV-0005: 通信途絶停止を補助機能とし heartbeat timeout を 1,200 ms に延ばす

## Raw artifacts

- `.saal/artifacts/2155c2347720058fc0fae52d14817fac98b76caa/20261002T000757`

