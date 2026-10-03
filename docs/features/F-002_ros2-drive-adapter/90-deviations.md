---
kind: DEV
feature: F-002
status: draft
---

# Deviations

### DEV-0006: 期限優先による承認前実装と実機起動

rule: 2.4, 3.2, 4.3, 4.4, 4.5, 4.6
scope: F-002の設計承認、試験仕様作成、実装、ROS 2・Insta360 X4・モータ系の実機起動
status: open
reason: 2026-10-04の実機稼働を最優先とし、ユーザーが「今は承認フェーズは飛ばす」と明示した。物理E-stopが有効であることを実機起動の前提とする。依存は導入済みのROS 2 Humbleとjoy_motor_controllerに限定する。
resolution: 実機確認後、00-meta.md、10-requirements.md、20-architecture.md、30-detailed-design.md、35-module-design.mdを人間がレビューし、承認または改訂する。差分は45-implementation-diff.mdに記録する。
decided_by: user
decided_at: 2026-10-03
