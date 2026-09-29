# nasura_comm

けいはんなロボットアバターチャレンジ用アバターロボット NASURA と操縦ブース（Quest 3S＋中間サーバ）を結ぶ通信系 PoC（F-001）。

開発は [SAALCO](https://github.com/ruri-sayo/saal_cording_rule) による SAAL 開発規則に従う。エージェント向けの指示は [AGENTS.md](AGENTS.md)。

## 文書

| 文書 | 内容 |
|---|---|
| [docs/features/F-001_nasura-comm/](docs/features/F-001_nasura-comm/) | 要件・設計・試験仕様・逸脱 |
| [docs/input/HANDOFF.md](docs/input/HANDOFF.md) | 実装引き継ぎ（実装順 P1〜P5） |
| [docs/glossary.md](docs/glossary.md) | 用語対応表 |
| [docs/rules/SAAL-DEV-RULES.md](docs/rules/SAAL-DEV-RULES.md) | 開発規則（正本） |

## 構成

```
src/nasura_comm/   Python（hub・car_ctrl・純粋ロジック）
web/               ブラウザページ（common / car / booth / quest / vendor）
scripts/           起動スクリプト・検証ツール
tests/             unit / integration / e2e
```

## 開発環境

```bash
uv sync
```

```bash
saalco check
```

品質ゲートとテストのコマンドは [docs/project.md](docs/project.md) に定義している。
