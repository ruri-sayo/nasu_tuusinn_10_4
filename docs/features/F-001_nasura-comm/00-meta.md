---
feature: F-001
title: NASURA通信系 PoC
tier: M
status: draft
version: 0
---

# F-001 NASURA通信系 PoC

## 概要

けいはんなロボットアバターチャレンジ用アバターロボット NASURA と操縦ブース（Quest 3S＋中間サーバ）を結ぶ通信系を、WebRTC ベースで構築する。

- NASURA → 操縦者：360°映像（Insta360 X4）、車載音声、テレメトリ（今回は枠のみ）
- 操縦者 → NASURA：パイロット映像・音声、操作命令

10/4 の実機確認に間に合わせる PoC であり、以降の作り直しを前提とする。ただし「メッセージ形式（エンベロープ＋topic登録）」と「安全機構（heartbeat・E-STOP）」は作り直し後も引き継ぐ前提で設計する。

## Tier 判定

**M**。複数ノード（Quest／中間サーバ／車載PC）・複数プロセスにまたがり、結合テストが必須。安全機能を含むが、PoC であり期限優先のため L にはしない。

## スコープ

| 区分 | 内容 |
|---|---|
| 対象 | シグナリング、メディア3系統（S1/S2）、制御プレーン（S3）、安全機構、車載ローカルI/F（UDP）、監視 |
| 対象外 | Raspberry Pi／Drive との接続（別Feature。本Featureは localhost UDP に実効命令を吐くところまで）、アーム制御（IK・Limit）、AIアノテーション、3Dアバター方式、認証 |

## 期限

- 2026-10-04：実機（車載PC＋中間サーバ＋Quest 3S）で全要素の送受信を確認

## 文書

| 文書 | 内容 |
|---|---|
| 10-requirements.md | REQ-0001〜REQ-0019 |
| 20-architecture.md | AD-0001〜AD-0010、リスク |
| 30-detailed-design.md | DD-0001〜DD-0016、メッセージ定義 |
| 40-unit-test-spec.md | UT-0001〜UT-0013 |
| 50-integration-test-spec.md | IT-0001〜IT-0007 |
| 60-system-e2e-spec.md | ST-0001〜ST-0013 |
| 45 / 70 / 80 / 90 | 実装差分・受け入れ・Outcome・逸脱 |

## 経緯

要件・設計判断は 2026-09-28〜29 のチャット議論で合意済み（本人が「議論で詰めたので事前承認不要」と判断）。承認記録は `saalco approve` で事後に付与する（DEV-0001）。
