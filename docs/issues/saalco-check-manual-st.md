# saalco check が手動 ST の PASS を数えない／DEV で WARNING に格下げできない

（ruri-sayo/saal_cording_rule に立てる Issue の下書き。2026-10-02 時点では起票できなかったため、ここに置く。DEV-0004 参照）

## 概要

SAALCO 1.0.0 の `saalco check` は、`verify: test` の REQ の検証充足を pytest の `verifies` マーカーだけで判定する。`60-system-e2e-spec.md` に `method: manual`・`result: PASS` の ST を記録しても数えない（`saalco trace` の `verified` 判定は手動 ST を数える）。さらに、この ERROR（`REQ-xxxx: no Specification-derived verifies test`）は `_dev_downgrade` の対象（4.6・6.4・6.8・7.1・7.3）に入っていないため、DEV を記録しても WARNING に格下げできない。

その結果、Quest 実機・人の知覚など、自動試験で判定できない要件を持つプロジェクトでは、手動 ST を実施して PASS を記録しても `saalco check` と `saalco evidence` の saalco-check ゲートが恒常的に FAIL になる。

## 再現手順

```bash
mkdir demo && cd demo
saalco init --name demo --type system --language python --non-interactive
saalco new feature "Demo" --tier S
saalco new req --feature F-001 "実機でだけ確認できる要件"
saalco new st --feature F-001 "実機確認"
```

`10-requirements.md` の REQ-0001 を `covers: -`、`60-system-e2e-spec.md` の ST-0001 を次のようにする。

```markdown
### ST-0001: 実機確認

covers: REQ-0001
method: manual
result: PASS
commit: <HEAD のフル hash>
executed_by: someone
executed_at: 2026-10-02
```

```bash
saalco check
```

期待：手動 ST の PASS で REQ-0001 が充足とみなされる（または DEV で WARNING にできる）。
実際：`ERROR REQ-0001: no Specification-derived verifies test` が出る。`rule: 6.6` 等の DEV を `status: open`・`scope: REQ-0001` で記録しても変わらない。

該当箇所：`src/saalco/checks.py` の `verified_ids`（`markers` の `verifies` だけから作る）と、`_dev_downgrade` の対象規則。

## 実例

nasu_tuusinn_10_4 の F-001 で発生。REQ-0001・0002・0003・0005・0008・0017 が該当。
DEV-0004：https://github.com/ruri-sayo/nasu_tuusinn_10_4/blob/main/docs/features/F-001_nasura-comm/90-deviations.md

## 対応案

1. `check` の充足判定に、`trace` と同じ条件（`method: manual`・`result: PASS`・commit が current）の手動 ST を加える。
2. または、この ERROR を DEV（例：規則 4.8 または 6.6）で WARNING に格下げできるようにする。
