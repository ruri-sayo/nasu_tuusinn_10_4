# F-001 実装引き継ぎ（Claude Code 向け）

## 最初にやること

1. プロジェクトが未初期化なら `saalco init`（type: system）。
2. `docs/features/F-001_nasura-comm/` をこの束のものに置き換える。
3. `docs/ids.ledger` にこの束の台帳を追記する。既存プロジェクトで番号が衝突する場合は、`saalco new` で採番し直し、文書内の ID と `covers:` を一括置換する（番号は手で決めない）。
4. 文書ヘッダのキーが `saalco new` の生成テンプレートと違う場合は、ヘッダだけテンプレートに合わせる（本文は変えない）。
5. `saalco check` が通ることを確認する。承認は本人が `saalco approve` で行う（DEV-0001：承認前の実装着手は許容済み）。

## 実装順（10/4 に間に合わせる優先順）

| 段 | 内容 | 確認 |
|---|---|---|
| P1 | hub サーバ（静的配信・/config.json・/topics.json・/ws）、SignalRouter、web/common | UT-0012、IT-0005 |
| P2 | car_media → quest（S1）。Mac テストの XR ビューアを `web/quest/xr-view.js` に流用 | 開発機で fake device、ST-0001〜0003 |
| P3 | booth → car_media（S2） | ST-0004、0005 |
| P4 | envelope / topics / filters / mapping / control / safety / local_io、S3、car_ctrl | UT-0001〜0011、IT-0001〜0003、0007 |
| P5 | /status、booth の監視表示、テレメトリ経路、ログ | UT-0013、IT-0004、0006 |

## 守ること

- 試験マーカー（`verifies` / `impl_aware`）の付け方は SAALCO の AGENTS.md に従う。UT・IT は 40/50 の仕様から書き、実装を見て書いたものは `impl_aware` にする。
- コード・コメントは英語。module docstring に Responsibilities / Non-responsibilities、ネットワーク・UDP・外部プロセス起動の Side Effects を必ず書く。
- 純粋ロジックのモジュールに I/O や実時間の取得を入れない（時刻は引数）。
- 固定 topic の処理を登録表経由にしない。安全系は直書き。
- three.js などブラウザ依存は `web/vendor/` に置き、CDN を使わない（会場でインターネットが無い可能性）。
- ブラウザの `alert` / `confirm` / `prompt` を使わない。
- 設計と違う実装をしたら `45-implementation-diff.md` に記入し、設計書を同じ commit で更新する。

## 本人に確認が要る場面

- Mac テストの XR ビューアのコードが見当たらないとき（three.js で新規に書く前に聞く）。
- X4 の Webカメラモードの解像度が 1920×960 を出せないとき。
- 設計の変更が安全機構（DD-0005〜DD-0007）に及ぶとき。
