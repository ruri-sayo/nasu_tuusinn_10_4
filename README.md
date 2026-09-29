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
uv run pytest tests/unit tests/integration
```

```bash
saalco check
```

品質ゲートとテストのコマンドは [docs/project.md](docs/project.md) に定義している。

## 開発機での確認（カメラ無し）

hub と car_ctrl を起動する。

```bash
uv run python -m nasura_comm.hub --port 8080
```

```bash
uv run python -m nasura_comm.car --hub ws://127.0.0.1:8080/ws
```

Chrome を fake device で起動し、`http://localhost:8080/car/`・`/booth/`・`/quest/` をそれぞれ別のウィンドウ（別プロファイル）で開く。`localhost` は secure context なので HTTP のままカメラ API が使える（WebXR の Enter VR は HTTPS の Quest でのみ）。

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir=/tmp/nasura-car --use-fake-device-for-media-stream --use-fake-ui-for-media-stream http://localhost:8080/car/
```

booth ページで S1〜S3 が `connected`、車載状態が `RUN` になれば通信系は成立している。UDP out は次で見られる。

```bash
uv run python scripts/dump_effective.py
```

同じ role のページを2つ開くと、先に開いた方は「置き換えられました」と表示して止まる（role ごとに接続は1本）。

## 本番構成（Tailscale）

中間サーバ（hub・booth）：

```bash
sudo tailscale up --advertise-routes=<ブースLANのCIDR>
```

管理画面で subnet route を承認したあと、HTTPS で公開する（初回のみ）。

```bash
tailscale serve --bg 8080
```

```bash
scripts/run_hub.sh
```

booth は中間サーバの Chromium で `https://<hub>.<tailnet>.ts.net/booth/` を開く。

車載PC（car_ctrl・car_media）：

```bash
sudo tailscale up --accept-routes
```

```bash
HUB_HOST=<hub>.<tailnet>.ts.net scripts/run_car.sh
```

Quest 3S：Quest Browser で `https://<hub>.<tailnet>.ts.net/quest/` を開き、マイクを許可して「VR で見る」。

`*.ts.net` を Quest が解決できない場合（R-1）は、hub を `--bind 0.0.0.0 --tls-self-signed` で起動し、`https://<中間サーバのLAN IP>:8080/quest/` を開いて証明書警告を一度許可する。車載側は `run_car.sh` の代わりに `--insecure` を付けて car_ctrl を起動する。

## ローカル I/F（車載）

| 方向 | アドレス | 内容 |
|---|---|---|
| 出力 | `127.0.0.1:47001` | `out/effective`（20 Hz）。受け手は 200 ms 途絶または `state != "RUN"` で停止すること |
| 入力 | `127.0.0.1:47002` | 登録済み拡張 topic のテレメトリ（エンベロープ1個／データグラム） |

拡張 topic は `src/nasura_comm/topics.py` の `EXTENSIONS` に1行追加する。試しに流すには：

```bash
uv run python scripts/fake_telemetry.py tlm/test_value --hz 5 --seconds 10
```
