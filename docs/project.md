---
kind: PROJECT
name: nasura_comm
type: system
language: python
saal_rules_version: 1.1
saalco_version: 1.0.0
raw_evidence_location: .saal/artifacts
raw_evidence_retention: until next release
gate.01.format: uv run ruff format --check .
gate.02.lint: uv run ruff check .
gate.03.typecheck: uv run mypy src
gate.04.secret_scan:
gate.05.dependency_audit:
gate.06.static_analysis:
test.unit: uv run pytest tests/unit
test.integration: uv run pytest tests/integration
test.e2e: uv run pytest tests/e2e
---

# nasura_comm
