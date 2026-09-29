---
title: SAAL ソフトウェア開発規則
version: 1.1
status: released
released: 2026-09-24
---

# SAAL ソフトウェア開発規則 v1.1

## 0. 本規則の読み方

| 章 | 内容 |
|---|---|
| 1 | 目的・適用範囲・Verification/Validationの分担 |
| 2 | 開発モデルと標準開発フロー（Bootstrap → V-cycle → Outcome） |
| 3 | 人間とAIの役割、人間の介入点 |
| 4 | V-cycle 各工程の規定 |
| 5 | テストの種別と独立性 |
| 6 | トレーサビリティとID体系 |
| 7 | 自動品質ゲート |
| 8 | Evidence（証拠）の記録と保存 |
| 9 | Outcome（研究系／システム系） |
| 10 | 標準ディレクトリ構造と文書管理 |
| 11 | コード記述規則と記述言語 |
| 12 | 欠陥・変更・逸脱の管理 |
| 13 | 支援ツール `saal` 仕様 |
| 14 | 品質保証の基本思想 |
| 15 | 本規則の改訂方針 |

---

## 1. 目的と適用範囲

### 1.1 目的

本規則は、SAALにおけるソフトウェア開発の品質と再現性を確保することを目的とする。

AIによる実装比率が高い開発では、コード品質を「人間がコードを読んで問題ないと判断した」という属人的な確認に依存させない。代わりに、

- 開発工程の明文化
- 工程に対応した設計・試験文書の保存
- 要求とテストの対応関係の機械的な追跡
- 自動品質ゲートと多段階のテスト
- 特定commitに紐づいたEvidenceの保存

を組み合わせ、**実装が定義された手続きを通過し、その証拠が残っていること**を品質保証の根拠とする。

本規則の下で主張する命題は、次の形である。

> この機能は REQ-0012〜REQ-0018 に対して、本規則の設計・実装・検証工程を通過しており、その証拠は commit `abc1234` の Evidence manifest に記録されている。

### 1.2 Verification と Validation の分担

本規則が担保するのは **Verification** のみである。

- **Verification（本規則が担保）**：各工程の成果物が上流工程で定義された要求に適合していること。要件定義書に書かれた要求が実装として成立していること。
- **Validation（本規則の範囲外）**：その要件定義がそもそも作るべきものだったか。実利用上の目的に照らして妥当か。

Validationは人間が単独で負う責任であり、開発プロセスによって代替・担保できるものではない。本規則は、Validationを担保しているかのような主張を行わない。

この区別はV&Vの標準的な定義に対応する（IEEE Std 1012）。

### 1.3 適用対象

SAALで開発する全てのソフトウェアを対象とする。適用の厳密さは Tier（第2.4項）で調整する。

以下は対象外とする。対象外のコードを本体へ取り込む時点で、本規則の対象となる。

- 使い捨てのスクリプト、対話的な探索コード（notebook等）
- 外部から導入した成果物そのもの（それを利用するコードは対象）

### 1.4 プロジェクト種別

各プロジェクトは、Bootstrap時に次のいずれかの種別を宣言する。種別は Outcome フェーズ（第9章）の流れを決める。

| 種別 | 最終成果 |
|---|---|
| `research` | 再現可能な研究結果 |
| `system` | 運用されるSAALシステム |

---

## 2. 開発モデルと標準開発フロー

### 2.1 基本方針

**全体はアジャイル、機能単位ではV字モデル**とする。

PoC・研究開発を含むため、初期段階で完全な仕様を確定することよりも、動作する実装を作り、評価と改善を繰り返すことを優先する。一方、個々の機能はV字モデルに従って設計・実装・検証する。

SAAL全体の開発モデルは単発のV字ではなく、**V字モデルを内包したアジャイルループ**である。

### 2.2 3フェーズ構成

```
┌─────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  Bootstrap  │ → │  Development V-cycle │ → │       Outcome        │
└─────────────┘   └──────────────────────┘   └──────────────────────┘
                            ↑                  research: 結果生成・固定 → 完了
                            │                  system:   Release → Deploy → Operation
                            └────── Feedback（不具合・改善・新要求）──────┘
```

#### Phase 1: Bootstrap

規則を適用するための初期状態を作る。

```
SAAL標準テンプレート配置（saal init）
 → Git初期化
 → プロジェクト種別の宣言（research / system）
 → Feature登録（saal new feature）
 → 要件定義開始
```

既存プロジェクトを本規則へ移行する場合も、Bootstrapから開始する（第10.5項）。

#### Phase 2: Development V-cycle

```
REQ（要件定義）
 → AD（基本設計）
 → DD / MD（詳細設計・モジュール設計）
 → Test Specification（試験仕様）
 → Implementation（実装）
 → Automated Quality Gate
 → Unit Test
 → Integration Test
 → System / E2E Test
 → Acceptance / Validation
```

V字上の対応関係は次のとおり。

| 設計工程 | 対応する試験 | 文書ID | 試験ID |
|---|---|---|---|
| 要件定義 | システム／E2Eテスト | REQ | ST |
| 基本設計 | 結合テスト | AD | IT |
| 詳細設計・モジュール設計 | 単体テスト | DD / MD | UT |

**Test Specification は実装より前に置く。** 試験項目は上流文書から導出し、実装から導出しない（第5章）。

#### Phase 3: Outcome

プロジェクト種別により分岐する（第9章）。

- **research**：Acceptance → Experiment Execution → Result Generation → 実行条件・結果・Evidence固定 → 完了
- **system**：Acceptance → Release → Deployment → Operation → Feedback → 次のREQ

### 2.3 アジャイルループとしての運用

- 1つのV-cycleは1つのFeature（またはその改訂）を単位とする。
- 複数のFeatureのV-cycleは並行してよい。
- 運用・実験から得られた不具合・改善要求・新要求は、新規または改訂REQとしてV-cycleの入口へ戻す（第9.3項、第12章）。
- 既存Featureの改訂は、影響する最上流の工程からV-cycleをやり直す。影響しない工程の成果物は再利用してよい。

### 2.4 適用Tier

Featureの規模・影響範囲に応じて必須成果物を調整する。

| | **Tier S** | **Tier M** | **Tier L** |
|---|---|---|---|
| 目安 | 単一モジュール内の小機能。外部IF変更なし | 複数モジュールにまたがる。内部IF変更あり | 外部IF・データ契約・永続化・HW・他システム連携に影響 |
| 要件定義書 | 必須（数行可） | 必須 | 必須 |
| 基本設計書 | 省略可（既存AD参照） | 必須 | 必須 |
| 詳細設計書 | 必須 | 必須 | 必須 |
| モジュール設計書 | DDに統合 | DDに統合可 | 必須（分離） |
| 試験仕様 | UTのみ必須 | UT・IT必須 | UT・IT・ST必須 |
| 単体テスト | 必須 | 必須 | 必須 |
| 結合テスト | 省略可 | 必須 | 必須 |
| ST/E2E | 簡易記録可 | 必須 | 必須 |
| 人間の設計承認 | REQ・DD | REQ・AD・DD | REQ・AD・DD・MD |

Tierは `00-meta.md` に宣言する。**Tierの判定はAIが提案し、人間が承認する。** Tierを下げる判断自体が設計判断であり、記録対象である。

---

## 3. 人間とAIの役割

### 3.1 基本原則

**AIが作業を進め、人間が重要な判断点・承認点で介入する。**

人間とAIが毎工程で対等に作業するのではない。人間が主として握るのは次の4つである。

| 人間が握るもの | 内容 |
|---|---|
| **What** | 何を作るか（要件） |
| **Architecture** | 大きな構造をどうするか |
| **Decision** | AIが提案した設計判断を承認するか |
| **Validation** | 最終的にその成果物を受け入れるか |

次は、可能な限りAIおよび `saal` ツールに委譲する。

- 詳細設計案・モジュール設計案の生成
- 試験仕様の作成とテストコード生成
- 実装
- 自動品質検査、テスト実行、Coverage取得
- ID採番、RTM生成、Evidence収集

### 3.2 人間の介入点

V-cycle中、人間が介入するのは次の点に限る。これ以外の工程はAIとツールで完結してよい。

| # | 介入点 | 人間の作業 | 記録方法 |
|---|---|---|---|
| H1 | 要件定義 | 要件を決定する | `saal approve 10-requirements.md` |
| H2 | 基本設計 | 構造を決定・承認する（Tier M以上） | `saal approve 20-architecture.md` |
| H3 | 詳細設計 | 設計判断・Tier・検証方法を承認する | `saal approve 30-detailed-design.md` |
| H4 | 依存・逸脱 | 依存追加、設計外の副作用追加、規則逸脱を承認する | PR上の承認、`90-deviations.md` |
| H5 | ST/E2E | 自動化できない試験項目を実施する | 試験結果として記録 |
| H6 | Acceptance | 受け入れ判断を行う（Validation） | `70-acceptance.md` |

承認は `saal approve` の実行のみで完結する。承認者・日時・バージョン・内容hashはツールが自動記録し、人間がhash等を意識する必要はない（第6.5項）。

### 3.3 最終責任

AIは設計・実装・テスト工程の主要な実施主体となるが、最終的な責任主体は人間とする。

---

## 4. V-cycle 各工程の規定

### 4.1 要件定義（REQ）

**主担当：人間**（AIは整理・抜け漏れ指摘・選択肢提示を補助）

- 1要件は1つの検証可能な主張とする。「〜が望ましい」など検証不能な記述は要件としない。
- 要件IDは `saal new req` で採番する。
- 成果物：`10-requirements.md`

### 4.2 基本設計（AD）

**主担当：人間＋AI　承認：人間（H2）**

システム全体の構成、主要コンポーネント、責務分割、通信方式、データフロー、外部システムとの境界を決定する。AIとの議論で設計案を作るが、方向性は人間が決定する。

- 成果物：`20-architecture.md`（機能横断の設計は `docs/architecture/`）

### 4.3 詳細設計（DD）

**主担当：AI　承認：人間（H3）**

クラス構成、状態管理、主要インターフェース、処理フロー、例外処理をAIが設計する。人間はコードを逐一確認する代わりに、ここで次を確認する。

- 責務分割が適切か
- 不自然な依存関係がないか
- 状態の所有者が明確か
- 将来の変更を阻害する構造になっていないか
- 各設計項目の検証方法（第6.4項）が妥当か

- 成果物：`30-detailed-design.md`

### 4.4 モジュール設計（MD）

**主担当：AI**

各モジュール・クラス・主要関数の責務、入出力、依存関係、制約を定義する。Tier S / M ではDDに統合してよい。統合した場合も、モジュール単位の責務・入出力・制約が記述されていることを要する。

- 成果物：`35-module-design.md`（統合時は `30-detailed-design.md` 内）

### 4.5 試験仕様（Test Specification）

**主担当：AI**

DD/MD承認後、**実装に着手する前に**、上流文書から試験仕様を作成する。

| 試験 | 導出元 | 成果物 |
|---|---|---|
| 単体テスト | DD / MD | `40-unit-test-spec.md` |
| 結合テスト | AD | `50-integration-test-spec.md` |
| システム／E2E | REQ | `60-system-e2e-spec.md` |

試験仕様とそのテストコードは Specification-derived Test（第5.1項）として扱う。人間による試験仕様の個別承認は必須としない。試験仕様が上流の検証対象項目を網羅していることは `saal check` が機械的に確認する。

### 4.6 実装

**主担当：AI**

承認済みの設計に従ってAIが実装する。人間による全コードの逐次レビューは品質保証の必須条件としない。

ただし次は人間の承認（H4）を要する。

- 依存ライブラリの追加・更新
- 設計文書に記載のない外部通信・ファイル書き込み・永続化・実機駆動の追加
- 設計からの逸脱（第12.3項）

実装完了時、AIは**設計との差分レポート**（設計にないが実装した事項／設計にあるが実装していない事項）を提出する。これは全コードレビューの代替ではなく、設計と実装の乖離を低コストで検出する手段である。

### 4.7 単体テスト・結合テスト

**実施：テストツール＋AI　確認：人間（結果とゲート通過の確認のみ）**

- 単体テストは関数・クラス・モジュール単位の動作を確認する。
- 結合テストは、基本設計で定義したコンポーネント間の関係（インターフェース、データ受け渡し、状態遷移）が成立していることを確認する。
- 人間はテストコードを逐一確認することを必須としない。テストが実行されたこと、検証対象項目が網羅されていること、PASSしていること、Coverage基準を満たしていることを確認する。これらは `saal check` と Evidence により機械的に示される。

### 4.8 システムテスト兼E2Eテスト（Verification）

**試験項目作成：AI＋人間　実施：自動化部分はツール、残りは人間（H5）**

実利用と同じ入口から操作し、最終的な出力まで一連の処理が成立することを確認する。AIが要件定義書から試験項目を列挙し、人間が必要な項目を追加する。各試験項目は検証対象のREQ IDを明示する。

最低限、次を確認する。

- 実際の利用方法でシステムが動作する
- 主要ユースケースが完遂できる
- 要件定義で要求した機能が成立する

自動化可能な項目は自動化し、人間は実機動作・目視確認・操作感など自動化困難な項目に絞る。

Tier S では「E2Eテスト：実施、問題なし（commit `abc1234`, 2026-09-21）」程度の簡潔な記録でよい。ただしcommit hashと日付は省略しない。

### 4.9 受け入れ判断（Acceptance / Validation）

**実施：人間のみ（H6）　本規則の担保範囲外**

ST/E2EがPASSしたことは「要件定義書に書いた通りのものができた」ことを示すにすぎない。要件定義自体の妥当性は、人間が単独で判断する。

SAALでは開発者と主要利用者が原則として同一であるため、独立した受け入れテスト工程は設けない。これは要件を書いた本人が要件の妥当性を判定する構造であり、この限界は本規則では解消されない。

緩和策として次を推奨する（必須ではない）。

- 要件定義書のみをAIに渡し、設計意図を与えない状態で要件と実装の齟齬を監査させる
- 要件定義と受け入れ判断の間に時間を置く

受け入れ判断は `70-acceptance.md` に記録する。これは本規則が担保する証拠ではなく、**人間の判断の記録**である。

---

## 5. テストの種別と独立性

### 5.1 2種類のテスト

AIが実装し、同じAIが実装を見てテストを書くと、実装の誤りがテストに写し取られる（自己採点）。これを防ぎつつwhite-box testingの利点も保つため、テストを次の2種類に区別する。

| | **Specification-derived Test** | **Implementation-aware Test** |
|---|---|---|
| 導出元 | 上流文書（REQ / AD / DD / MD）と公開IF定義 | 実装コード |
| 実装参照 | **禁止** | 可 |
| 作成時期 | 実装前（第4.5項） | 実装後いつでも |
| 主な用途 | 設計通りに作られていることの確認 | 境界値、分岐網羅、robustness、回帰テスト |
| 位置づけ | **Verificationの主要証拠** | 補助的品質保証 |
| 必須性 | 検証対象項目ごとに原則必須 | 任意 |
| マーカー | `@pytest.mark.verifies("<ID>")` | `@pytest.mark.impl_aware` |

### 5.2 Specification-derived Test の作成条件

- テストコードの生成は、**実装コードを参照しないコンテキスト**（別セッション・別エージェント等）で行う。
- 生成時の入力は、上流文書と公開インターフェース定義（シグネチャ・型・docstring）に限る。
- 実装完了後に Specification-derived Test を新規追加する場合も、同じ条件で作成する。

この条件は手続き上の要求であり、ツールで完全に強制することはできない。そのため、作成条件を守れなかったテストは `impl_aware` として扱う。**迷った場合は `impl_aware` に分類する**（証拠の強度を過大に主張しないため）。

### 5.3 Implementation-aware Test

- 実装を確認した上で自由に追加してよい。
- 回帰テスト（第12.1項）は原則こちらに分類する。
- 上流IDとの関連を示したい場合は `@pytest.mark.impl_aware("DD-0005")` のように参照を付けてよい。ただしRTM上の検証充足には数えない。
- 失敗した場合の扱いは Specification-derived Test と同等とする（品質ゲートは通過しない）。

---

## 6. トレーサビリティとID体系

### 6.1 原則

REQ → 設計 → テスト → Evidence の対応関係を**機械的に追跡可能**にする。

手で維持する対応表は必ず実態から乖離し、乖離した対応表は誤った証拠を残す。したがって、

**人が書くのは「その項目が何をカバーし、どう検証するか」の最小限の行のみとし、対応表そのものは生成物とする。**

### 6.2 ID体系

| 接頭辞 | 対象 | 採番 |
|---|---|---|
| `F-nnn` | Feature（ディレクトリ単位） | `saal new feature` |
| `REQ-nnnn` | 要件 | `saal new req` |
| `AD-nnnn` | 基本設計項目 | `saal new ad` |
| `DD-nnnn` | 詳細設計項目 | `saal new dd` |
| `MD-nnnn` | モジュール設計項目 | `saal new md` |
| `UT-nnnn` / `IT-nnnn` / `ST-nnnn` | 試験仕様項目 | `saal new ut` 等 |

- **IDは全て `saal` が自動採番する。人間もAIも番号を自分で決めない。**
- IDはプロジェクト内でグローバルに一意とする（Featureごとの番号空間は持たない）。
- 廃止したIDは再利用しない。

### 6.3 文書ヘッダ

ネスト・リスト記法・クオートを使用しない、フラットな `key: value` のみとする。

```
---
kind: DD
feature: F-001
status: approved
version: 3
approved_by: miura
approved_at: 2026-09-21
approved_hash: 9f2c41ab
---
```

- `status`：`draft` / `approved` / `superseded`
- `version`, `approved_by`, `approved_at`, `approved_hash` は `saal approve` のみが書き込む。人間・AIは編集しない。

### 6.4 項目の記述

各項目は見出しで宣言し、直下に `covers:` と `verify:` を置く。

```markdown
### DD-0005: Adapterの共通インターフェース

covers: REQ-0012, REQ-0013
verify: test

（本文）
```

```markdown
### DD-0006: AdapterをStrategy Patternで分離する

covers: REQ-0012
verify: review

（本文）
```

`covers:` は上流の項目IDを指す。REQ項目は連鎖の起点であるため `covers: -` とする。

`verify:` は検証方法を示す。

| 値 | 意味 | 充足条件 |
|---|---|---|
| `test` | テストで検証する | Specification-derived Test が1件以上存在し、最新EvidenceでPASS |
| `review` | 設計レビューで検証する（構造・方針などの設計判断） | 当該文書が承認済みで、承認後に改変されていない |
| `static` | 品質ゲートの静的検査で検証する | 本文に担保する検査（ツール・ルール）を明記し、最新Evidenceでゲート通過 |

- `verify:` を省略した場合は `test` とみなす。
- REQ項目は原則 `test`（ST/E2Eで検証）とする。`review` / `static` とする場合は理由を本文に記す。
- **テスト対応が必須なのは `verify: test` の項目のみ**である。設計判断そのものを無理にテスト対象にしない。
- 各項目の `verify:` の妥当性は、H3（詳細設計承認）で人間が確認する。

### 6.5 承認記録と改変検知

`saal approve <path>` は次を自動で行う。

1. 文書本文（ヘッダの承認関連キーを除く）の content hash を計算する
2. `status: approved`、`approved_by`（git configのuser.name）、`approved_at`、`approved_hash` を記録する
3. `version` を1つ進める

承認後に文書を変更すると、`saal check` が現在のhashと `approved_hash` の不一致を検出し、品質ゲートを落とす。再度 `saal approve` を実行すれば解消する。

**ユーザー操作は `saal approve` の1コマンドのみ**とし、hash・バージョンの管理は全てツールが行う。

### 6.6 テストコードのマーカー

```python
@pytest.mark.verifies("DD-0005")    # 単体テスト → 詳細設計項目
def test_adapter_interface(): ...

@pytest.mark.verifies("AD-0002")    # 結合テスト → 基本設計項目
def test_bridge_adapter_wiring(): ...

@pytest.mark.verifies("REQ-0012")   # ST/E2E → 要件
def test_caller_is_model_agnostic(): ...

@pytest.mark.impl_aware             # 補助テスト（充足に数えない）
def test_adapter_rejects_empty_path(): ...
```

UTはDD/MDを、ITはADを、ST/E2EはREQを指す。RTMは `covers:` の連鎖を辿ってREQまで解決する。

### 6.7 実装ファイル

**実装ファイルには対応関係を記述しない。** テストと実装の対応は、coverage.py の測定コンテキスト（`pytest --cov-context=test`）から導出する。

### 6.8 RTM（要求トレーサビリティマトリクス）

`saal trace` が `docs/trace/rtm.csv` および `rtm.md` を生成する。人間は編集しない。

列：

```
req_id, requirement, feature, design_ids, impl_files, unit_tests, integration_tests, e2e_tests, verify_status, evidence_commit
```

REQ行の `verify_status` が `verified` となる条件：

- REQ自身の検証（通常はST/E2E）が充足している
- そのREQを `covers:` する全ての設計項目の検証が、`verify:` に応じて充足している（第6.4項）
- 上記の根拠となるEvidenceが同一commitのものである

充足していない行は未検証の要件であり、`saal check` が検出する。

---

## 7. 自動品質ゲート

### 7.1 構成

```
Implementation
 ↓ Formatter
 ↓ Linter（docstring規則を含む）
 ↓ Type Check
 ↓ Secret Scan            （常時）
 ↓ Dependency Audit       （常時）
 ↓ Static Analysis        （必要時）
 ↓ saal check             （トレーサビリティ・承認・hash・逸脱）
 ↓ Unit Test + Coverage
 ↓ Integration Test
 ↓ System / E2E Test（自動化分）
```

- Secret Scan と Dependency Audit は実行コストが小さく事故の重大度が高いため、常時実行とする。
- 具体的なツールは言語・プロジェクトごとに決定し、`docs/project.md` に記載する。
- CIまたはローカルスクリプトから一括実行可能にする。
- **自動品質ゲートを通過していないコードは完成扱いにしない。**

### 7.2 実行環境の固定

- 依存関係のロックファイル（`uv.lock` 等）をGit管理する。
- ロックファイルの変更は依存追加・更新として扱い、人間の承認（H4）を要する。

### 7.3 Coverage基準

- 新規・変更コードの行カバレッジ **80%以上**（差分に対して）
- プロジェクト全体のカバレッジを直前のEvidence記録時点より低下させない
- 下回る場合は逸脱記録（第12.3項）を残した上で通過させてよい

Coverageは下限であって目標ではない。数値自体を追求しない。

---

## 8. Evidenceの記録と保存

### 8.1 目的

Evidenceの目的は次の1点である。

**特定commitに対して、その時点でどのテストをどの環境で実行し、何がPASSしたかを後から再確認できること。**

### 8.2 保存方針：manifestはGit、生データは別保存

運用コストと証拠性を両立させるため、2層に分ける。

| 層 | 内容 | 保存先 | Git管理 |
|---|---|---|---|
| **manifest** | 実行記録の要約と、生データのhash | `evidence/<commit>/manifest.json` | **する** |
| **summary** | 人間向けの要約 | `evidence/<commit>/summary.md` | **する** |
| **raw** | JUnit XML、`.coverage` DB、全ログ等 | `.saal/artifacts/<commit>/` → プロジェクトが定める保存先へ退避 | しない |

- manifestには各生データファイルのhashを記録する。生データを後から照合した際、改変の有無を検証できる。
- 生データを失った場合でも、manifestに記録されたcommit・ロックファイルhash・実行環境から、テストを再実行して再確認できる。**manifestが一次証拠、生データは補強証拠**とする。
- 生データの退避先と保持期間はプロジェクトごとに `docs/project.md` に定める。

### 8.3 manifestの記録項目

`saal evidence` が自動収集する。人間は記入しない。

- 対象commit hash
- 実行日時
- 実行環境（OS / 言語バージョン / ロックファイルhash）
- 使用ツールとそのバージョン
- 品質ゲート各段の結果
- 個別テストごとのID・種別（`verifies` / `impl_aware`）・PASS/FAIL
- Coverage数値（全体・差分）
- 生データ各ファイルのhashと退避先

「PASSしました」のみの記録は証拠として扱わない。

### 8.4 記録の条件

- **Evidenceは作業ツリーがクリーンな状態（未commitの変更がない状態）でのみ記録する。** `saal evidence` は未commit変更があれば記録を拒否する。
- Evidenceは対象commitの**後続commit**でGitに追加される。manifest内の対象commit hashにより対応を示す。

### 8.5 Evidence Package

Feature完成時またはリリース時に、`saal evidence --package <feature>` により次を一式で提示する。Evidence Packageは既存記録から生成するビューであり、重複保存しない。

1. 要件定義書
2. RTM（当該FeatureのREQ行が全て `verified`）
3. 品質ゲート・テスト結果のmanifest
4. 承認記録（誰が・いつ・どのバージョン・どのhashを承認したか）
5. 逸脱記録（存在する場合）
6. 設計と実装の差分レポート

---

## 9. Outcome

### 9.1 研究系（`research`）

研究コードでは運用が最終目的ではなく、**再現可能な研究結果を生成すること**が最終成果である。

```
System / E2E Test
 → Acceptance
 → Experiment Execution
 → Result Generation
 → 実行条件・結果・Evidence固定
 → 完了
```

**研究系コードの完成点は、E2E PASSではなく、結果生成と再現条件の固定までとする。**

結果ごとに、少なくとも次を対応付けて記録する。

- code commit（Evidence記録済みのもの）
- dataset version
- model（名称・バージョンまたは重みのhash）
- config
- seed
- 実行環境
- result（結果の所在とhash）

記録先は `80-outcome.md` とし、結果データ本体の保存先はプロジェクトが定める。v1.0ではこれ以上の仕組み化を要求しない。

コードを変更して再実験した場合、それは新しい結果であり、新しい記録を追加する。既存の記録を上書きしない。

### 9.2 システム系（`system`）

```
System / E2E Test
 → Acceptance
 → Release
 → Deployment
 → Operation
 → Feedback → New / Updated Requirement → 次のV-cycle
```

- Releaseは、Evidence Packageが揃ったcommitに対してのみ行う。
- リリース記録（バージョン、対象commit、デプロイ先、日付）を `80-outcome.md` に残す。

### 9.3 Feedbackループ

運用・実験から得られた次の事項は、新規または改訂REQとしてV-cycleへ戻す。

- 不具合（第12.1項の原因分類を経る）
- 改善要求
- 新機能要求
- 実利用上のフィードバック

---

## 10. 標準ディレクトリ構造と文書管理

### 10.1 構造

`saal init` が次の構造を配置する。

```
<project>/
  docs/
    project.md                   # 種別・ツール構成・Evidence保存先・規則バージョン
    rules/
      SAAL-DEV-RULES.md          # 適用している規則のコピー
    architecture/                # 機能横断の全体設計・共通規約
    features/
      F-001_<name>/
        00-meta.md               # Tier・概要・状態
        10-requirements.md
        20-architecture.md
        30-detailed-design.md
        35-module-design.md      # Tier Lのみ分離
        40-unit-test-spec.md
        50-integration-test-spec.md
        60-system-e2e-spec.md
        70-acceptance.md         # 受け入れ判断（規則の担保範囲外）
        80-outcome.md            # 研究：結果記録 ／ システム：リリース記録
        90-deviations.md         # 逸脱記録
    trace/
      rtm.csv                    # 生成物
      rtm.md                     # 生成物
  evidence/
    <commit>/
      manifest.json              # 生成物
      summary.md                 # 生成物
  src/
  tests/
    unit/
    integration/
    e2e/
  .saal/                         # ツール作業領域（Git管理外）
    artifacts/
```

### 10.2 構造上の意図

- **Featureが第一階層、工程が第二階層**とする。1FeatureのV字を1ディレクトリで一覧できる。
- 番号接頭辞により、一覧がV字の順に並び、欠けた工程が目視で分かる。
- `docs/trace/` と `evidence/` は全て生成物であり、手で書かない。
- Tierにより不要なファイルは作成しなくてよい。

### 10.3 Gitとの結合

- 文書はコードと同一リポジトリで管理する。
- **設計変更を伴う実装は、設計文書の更新と実装を同一のPR（またはcommit）に含める。**
- PR本文には対象Feature IDと、`saal trace` が出力したRTM該当行を記載する。

「工程を通過した記録」をGit履歴に埋め込むことで、事後の改竄を困難にする。

### 10.4 文書量

文書量そのものを品質指標としない。単純なFeatureは短い文章で構わない。

重要なのは、**その工程を実施したことと、その判断結果を後から追跡できること**である。

### 10.5 既存プロジェクトの移行

既存プロジェクトを本規則へ移行する場合：

1. `saal init` で標準構造を追加する（既存の `src/` `tests/` は移動してよい）
2. 既存機能をFeatureとして登録する
3. 既存機能について、要件と設計を**現状から逆起こし**して文書化し、人間が承認する
4. 既存テストは原則 `impl_aware` として扱う（実装を見て書かれたものであるため）
5. `verify: test` の項目に対して Specification-derived Test を追加し、RTMを `verified` にする

移行途中の状態は逸脱記録に残す。移行完了前のFeatureについて、本規則準拠を主張しない。

---

## 11. コード記述規則

コードは、人間だけでなく将来そのコードを扱うAIにも理解しやすい状態を維持する。コメントは処理内容の説明ではなく、**責務、境界、制約、前提**を明示することを重視する。

### 11.1 ファイル上部 / module docstring

- **必須**：このファイルの目的、Responsibilities（担当する範囲）
- **推奨**：Non-responsibilities（担当しない範囲）
- **必要時**：外部依存、HW依存、通信先、DB・API等との関係、実行環境、スレッド・非同期処理の前提、その他重要な制約

Non-responsibilitiesは、将来AIが機能を追加する際にモジュールの責務を逸脱することを防ぐ目的でも利用する。

### 11.2 Class docstring

- **必須**：クラスの責務
- **必要時**：保持する重要な状態、Lifecycle、Invariant、HW・IO・外部リソースとの関係、スレッド・非同期処理との関係
- **複雑なクラスでは推奨**：担当しないこと

statefulなクラスでは、状態の意味とライフサイクルを明確にする。

### 11.3 Function / Method docstring

原則として「何をする関数か」を簡潔に記述する。Args / Returns / Side Effects / Raises / 前提条件 / 呼び出し条件は必要に応じて記述する。

型ヒントのみで意味が明確な場合、冗長な説明を要求しない。一方、型から判断できない次の情報は**必ず記載する**。

- 単位、許容範囲、特殊な値の意味、`None` の意味
- 座標系、タイムアウト、HW固有値

次のSide Effectsが存在する場合は**必ず明記する**。

- ファイル変更、DB更新、ネットワーク通信、実機駆動、GPIO操作、外部プロセス起動

### 11.4 準拠確認

| 対象 | 確認方法 |
|---|---|
| docstringの存在・書式 | Linter（ruffの `D` ルール等）で自動判定 |
| Responsibilities / Non-responsibilities の妥当性 | H3（詳細設計承認）で人間が確認 |
| Side Effectsの記載漏れ | 設計との差分レポート（第4.6項）で検出 |

### 11.5 記述言語

コードと文書で使う言語を次のとおり定める。

| 対象 | 言語 |
|---|---|
| コード、コメント、docstring | 英語 |
| 設計文書・仕様書・報告文書の本文 | 日本語 |
| 見出し、front matter のキー、ID、機械が照合する固定の項目名（`Responsibilities`、`Side Effects` など） | 英語のまま固定 |

- 英語のコードと日本語の文書で用語が揺れないよう、用語の対応表（日本語と英語）を `docs/glossary.md` に置く。新しい用語を導入するときは、先に対応表へ追加する。
- `saal` が照合する見出し・キー・項目名（項目見出し `### ID: title`、`covers:`・`verify:` などのメタ情報行、文書ヘッダのキー）は翻訳しない。
- 既存文書の本文が英語の場合、翻訳は別途計画して行う。改訂する文書と新しく書く文書には、本項を適用する。

---

## 12. 欠陥・変更・逸脱の管理

### 12.1 欠陥発生時

テスト失敗、または受け入れ後・運用中の不具合が発生した場合：

1. **原因工程を分類して記録する**：要件漏れ / 設計漏れ / 実装誤り / テスト漏れ
2. **該当工程まで戻る。** 設計起因であれば設計文書を改版し、再承認する。コードのみ修正して設計文書が古いまま残る状態を許さない（承認hashの不一致として `saal check` でも検出される）。
3. 再発防止の回帰テストを追加する（原則 `impl_aware`）。
4. 要件漏れ・設計漏れの場合は、Specification-derived Test も追加する。

原因工程の分類は、本規則自体の弱点を分析する材料として蓄積する。

### 12.2 回帰テスト

修正時は既存の自動テスト一式を再実行する。部分実行のみで完了としない。

### 12.3 逸脱記録

規則の要求を満たさずに進める場合、`90-deviations.md` に次を記録する。

- 逸脱した規則の条項
- 理由
- 影響範囲
- 解消予定（または恒久的逸脱である旨）
- 判断者と日付

**逸脱記録のない逸脱を認めない。** 逸脱記録の仕組みがなければ、「規則を守った」という主張自体が検証不能になる。

---

## 13. 支援ツール `saal` 仕様

本規則を運用可能にするための最小限のCLI。**人間・AIの双方が、ID採番・対応表更新・承認記録・証拠収集を手作業で行わないこと**を目的とする。v1.0時点のテスト関連機能はPython（pytest / coverage.py）を前提とする。

### 13.1 `saal init [--type research|system]`

- 標準ディレクトリ構造（第10.1項）と雛形を配置する
- `docs/project.md` に種別と規則バージョンを記録する
- `.saal/` を `.gitignore` に追加する
- Git未初期化であれば初期化する

### 13.2 `saal new <kind> [--feature F-nnn] "<title>"`

- `kind`：`feature` / `req` / `ad` / `dd` / `md` / `ut` / `it` / `st`
- 既存IDを走査して次のIDを自動採番する
- 文書が存在しなければ雛形ごと作成し、存在すれば項目見出しと `covers:` / `verify:` 行の雛形を追記する
- 採番したIDを標準出力に返す

### 13.3 `saal approve <path>`

- 本文のcontent hashを計算し、`status` / `approved_by` / `approved_at` / `approved_hash` / `version` を記録する（第6.5項）
- ユーザーへの追加入力を要求しない

### 13.4 `saal trace`

入力：

- `docs/features/**/*.md` の項目ID・`covers:`・`verify:`
- pytestマーカー（`verifies` / `impl_aware`）
- coverage.py の測定コンテキスト
- 最新Evidenceのmanifest

出力：`docs/trace/rtm.csv`、`docs/trace/rtm.md`（第6.8項）

### 13.5 `saal check`

品質ゲートの一段として実行し、違反があれば非ゼロで終了する。

1. `covers:` / `verifies` の参照先IDが存在しない
2. `verify: test` の項目に Specification-derived Test が紐付いていない
3. `verify: static` の項目に担保する検査の記載がない
4. 承認済み文書の現在のhashが `approved_hash` と一致しない
5. 承認されていない設計に対応する実装が存在する
6. 文書ヘッダの必須キー欠落・形式エラー
7. `00-meta.md` のTier宣言が欠落している
8. Tierに応じた必須文書が存在しない
9. Coverage基準未達で、対応する逸脱記録がない

### 13.6 `saal evidence [--package <feature>]`

- 作業ツリーがクリーンでなければ拒否する
- 品質ゲートとテストを実行し、manifestとsummaryを `evidence/<commit>/` に、生データを `.saal/artifacts/<commit>/` に出力する（第8章）
- `--package` 指定時は、当該FeatureのEvidence Packageを生成する（第8.5項）

### 13.7 設計上の制約

- 文書ヘッダはフラットな `key: value` のみとし、YAMLライブラリに依存しない自前パーサで読む
- CSVは**出力にのみ使用する**。対応表を人間がCSV/YAMLで手入力する運用を採らない
- `saal` 自体も本規則の適用対象とする

---

## 14. 品質保証の基本思想

SAALでは、コード品質を人間による全コードレビューに依存させない。

Verificationは次の組み合わせによって実現する。

- 人間による要件決定（What）
- 人間によるアーキテクチャ決定（Architecture）
- 人間による設計判断の承認（Decision）
- AIによる設計・実装
- 上流文書から導出され、実装を参照せずに作成された試験（Specification-derived Test）
- 自動品質ゲート
- 自動単体テスト・結合テスト
- システム／E2Eテスト
- 要求単位でのトレーサビリティの機械的検査
- 特定commitに紐づくEvidenceの保存

目標は、

「人間がコードを読んだから大丈夫」

ではなく、

**「定義された設計・実装・検証工程を通過し、要求単位での検証対応が機械的に確認され、その記録が特定commitに紐づいて残っているため、一定の信頼性を持つ」**

状態を作ることである。

Validation（作るべきものを作ったか）は本規則の範囲外であり、人間が単独で負う。

また、開発速度を過度に損なわないため、文書化や試験を目的化しない。小さなFeatureでは小さなV字を、重要なFeatureでは厳密なV字を回し、プロジェクト全体として継続的に動作品を改善していく。

---

## 15. 本規則の改訂方針

- v1.0の発行をもって、本規則の設計フェーズを終了する。
- 以降の改訂は、机上の検討ではなく、**実運用で見つかった問題を根拠として**行う。
- 運用フェーズでは、既存プロジェクトのv1.0準拠への移行と、新規プロジェクトのv1.0による開発を並行し、規則・`saal`・文書量・承認フロー・テストフロー等の問題点を洗い出す。
- 改訂提案には、根拠となった事例（プロジェクト、Feature、発生した問題）を添える。
- 各プロジェクトは `docs/project.md` に適用している規則バージョンを記録する。規則の改訂は既存プロジェクトへ自動適用しない。

---

## 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 0.1 | — | 初版 |
| 0.2 | 2026-09-21 | V&V適用範囲の明示、RTMの必須化、テスト独立性、ディレクトリ標準化、ID自動採番と支援ツール仕様、欠陥・逸脱管理、Evidence Package、Coverage基準、Tier制 |
| 1.0 | 2026-09-21 | 確定版。標準開発フロー（Bootstrap → V-cycle → Outcome）、人間の介入点（H1〜H6）、研究系／システム系のOutcome分岐とFeedbackループ、承認hashによる改変検知、Specification-derived / Implementation-aware Testの区別、設計項目の検証方法（`verify:`）、Evidence保存方針（manifestはGit・生データは別保存）、既存プロジェクト移行手順、`saal init` の追加、改訂方針 |
| 1.1 | 2026-09-24 | 第11.5項「記述言語」を追加（コード・コメント・docstringは英語、文書本文は日本語、見出し・キー・ID・機械照合項目は英語固定、用語対応表 `docs/glossary.md`）。SAALCO 自身の開発で、英語のコードと日本語の文書の間で用語が揺れる問題が生じたことを根拠とする |
