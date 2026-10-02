# Evidence 20261002T162600

- Target commit: `a2c55d42fde71cdda0aee1940534194e800698f9`
- Executed at: 2026-10-02T16:28:08+09:00
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

- unit: PASS=63 FAIL=0 NOT_EVALUATED=0
- integration: PASS=11 FAIL=0 NOT_EVALUATED=0
- e2e: PASS=19 FAIL=0 NOT_EVALUATED=0

## Coverage

- Total: 94.78
- Diff: 100.0
- Base: 7972a55f6851717ce801c419f84c05177d773f5c
- Status: FAIL

## RTM

- stale: 19

## Open DEV

- DEV-0001: 事前承認なしで設計書を発行する
- DEV-0002: ブラウザ側コードに自動単体試験を用意しない
- DEV-0003: 期限優先で ST の一部を省略する可能性がある
- DEV-0004: 実機でしか確認できない REQ に自動の verifies 試験が無い
- DEV-0005: 通信途絶停止を補助機能とし heartbeat timeout を 1,200 ms に延ばす

## Raw artifacts

- `.saal/artifacts/a2c55d42fde71cdda0aee1940534194e800698f9/20261002T162600`

