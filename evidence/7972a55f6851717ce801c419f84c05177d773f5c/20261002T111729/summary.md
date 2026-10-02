# Evidence 20261002T111729

- Target commit: `7972a55f6851717ce801c419f84c05177d773f5c`
- Executed at: 2026-10-02T11:19:49+09:00
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

- Total: 95.11
- Diff: 100.0
- Base: 2155c2347720058fc0fae52d14817fac98b76caa
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

- `.saal/artifacts/7972a55f6851717ce801c419f84c05177d773f5c/20261002T111729`

