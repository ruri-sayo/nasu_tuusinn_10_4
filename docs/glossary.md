# 用語対応表（Glossary）

コード（英語）と文書（日本語）で用語を揃えるための対応表。新しい用語は使う前にここへ追加する（規則 11.5）。

| 日本語 | English（コード上の表記） | 意味 |
|---|---|---|
| 中間サーバ上の Python プロセス | hub | ページ配信・シグナリング・入力→命令変換・heartbeat・監視集約 |
| 操縦ブースページ | booth | 中間サーバ上のブラウザページ（パイロットのカメラ・マイク、E-STOP） |
| Quest ページ | quest | Quest 3S 上の WebXR ページ |
| 車載メディアページ | car_media | 車載PC上のブラウザページ（X4・車載マイク・パイロット映像表示） |
| 車載制御プロセス | car_ctrl | 車載PC上の Python プロセス（制御受信・安全監視） |
| 上り／下り | up / down | NASURA（車載PC）から見た方向 |
| エンベロープ | envelope | 全メッセージ共通の包み `{topic, ver, seq, ts, src, payload}` |
| topic 登録表 | topic registry (`TopicSpec`) | topic の方向・チャネル・最大レートの宣言 |
| 固定 topic／拡張 topic | fixed topic / extension topic | コード直書きの安全系 topic／登録表で追加する topic |
| 実効命令 | effective command (`out/effective`) | 安全判定後に下流へ出す命令 |
| 安全状態機械 | safety state machine (`SafetyCore`) | INIT / RUN / STOP / ESTOP |
| 非常停止 | E-STOP (`sys/estop`) | ESTOP 状態へのラッチ |
| デッドマン | deadman | 押している間だけ走行を許すスイッチ |
| クラッチ | clutch | アーム操作の基準姿勢を取り直す操作 |
| シグナリング | signaling | WebRTC 接続確立のためのメッセージ交換 |
| セッション | session (S1 / S2 / S3) | S1: car_media→quest、S2: booth→car_media、S3: car_ctrl⇄hub |
| 介添人 | attendant | 競技中にロボットに付き、暴走時に物理的に止める人。安全の最終責任を負う |
