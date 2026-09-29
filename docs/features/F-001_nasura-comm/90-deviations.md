---
kind: DEV
feature: F-001
status: draft
---

# F-001 逸脱記録

### DEV-0001: 事前承認なしで設計書を発行する

rule: 4.6
scope: F-001, src/, web/, scripts/, tests/
status: open
reason: 要件・設計はチャット議論（2026-09-28〜29）で本人と合意済みであり、本人判断で事前の承認手続きを省略して発行する。承認記録は `saalco approve` で事後に付与する。承認前に実装へ着手することを許容する。
resolution: H1〜H3（10-requirements.md、20-architecture.md、00-meta.md、30-detailed-design.md）の承認が `saalco approve` で記録された時点で解消。
decided_by:
decided_at:

### DEV-0002: ブラウザ側コードに自動単体試験を用意しない

rule: 4.7
scope: F-001, web/
status: open
reason: v1.0 の試験ツールは Python 前提であり、JavaScript の試験基盤を 10/4 までに整える余裕が無い。ブラウザ側の設計項目（DD-0011〜DD-0015）と、ブラウザ・実回線が無いと結合試験できない基本設計項目（AD-0003 メディア設定、AD-0010 ネットワーク構成）は `verify: review` とし、ST（実機試験）で機能を確認する。作り直し時に JS の試験基盤を導入するか再検討する。
resolution: 作り直し時に JS の試験基盤を導入するか再検討する。導入しない場合は恒久的逸脱として扱う。
decided_by:
decided_at:

### DEV-0003: 期限優先で ST の一部を省略する可能性がある

rule: 4.8
scope: F-001, 60-system-e2e-spec.md（ST-0011〜ST-0013）
status: open
reason: 10/4 の実機確認で時間が足りない場合、ST-0011（自動復帰）・ST-0012（監視・負荷）・ST-0013（テレメトリ）を後日に回すことを許容する。ST-0001〜ST-0010 は省略しない（ST-0008〜ST-0010 は安全に関わるため必須）。省略した場合は結果欄に「未実施」と理由を書く。
resolution: 省略した ST を後日実施し、結果欄に記録した時点で解消。省略しなかった場合はその時点で解消。
decided_by:
decided_at:

### DEV-0004: 実機でしか確認できない REQ に自動の verifies 試験が無い

rule: 6.6
scope: F-001, REQ-0001, REQ-0002, REQ-0003, REQ-0005, REQ-0008, REQ-0017
status: open
reason: REQ-0001（Quest ブラウザだけで成立）、REQ-0002（全天球表示・頭部追従）、REQ-0003・REQ-0005（会話が成立する音声遅延）、REQ-0008（低遅延優先・遅れフレームの破棄）、REQ-0017（tailnet・HTTPS 配信）は、Quest 実機・tailnet・実回線・人の知覚が必要で、開発機の自動 E2E 試験では要件の基準を判定できない。これらは ST（method: manual、H5）で確認する。ただし SAALCO 1.0.0 の `saalco check` は、REQ の検証充足を pytest の `verifies` マーカーだけで判定し、手動 ST の PASS を数えない（`saalco trace` は数える）。また、この ERROR は DEV で WARNING に格下げできない。そのため、手動 ST を実施して PASS を記録した後も、この6件は `saalco check` の ERROR として残る。判定できない試験に `verifies` を付けたり、`verify:` を事実と異なる値に変えたりはしない。
resolution: 10/4 以降の実機試験で ST-0001〜0005・ST-0011 等を実施し、60-system-e2e-spec.md に method: manual の結果を記録する。SAALCO 側で「手動 ST の PASS を check の充足に数える」か「この ERROR を DEV で格下げ可能にする」かを決め、対応されたら本 DEV を閉じる。
decided_by:
decided_at:
