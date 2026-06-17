# stack — 宇宙ミッション運用センター（完動デモ）

1 コマンドで立ち上がる、Grafana の 3 つの使い方を宇宙開発で実証するスタック。

## 構成

```
┌──────────────┐   高頻度TM    ┌──────────┐
│  simulator   │──────────────▶│ InfluxDB │──┐
│ (模擬衛星)    │   パス/EO/KPI ┌──────────┐  │  Flux
│  軌道/電源/   │──────────────▶│TimescaleDB│─┤  SQL    ┌─────────┐
│  熱/姿勢/通信 │   /metrics    └──────────┘  ├────────▶│ Grafana │
│              │──────────────▶┌──────────┐  │  PromQL └─────────┘
└──────────────┘               │Prometheus│──┘
                               └──────────┘
```

| サービス | ポート | 役割 |
|---|---|---|
| grafana | 3000 | 可視化（4 ダッシュボード自動プロビジョニング） |
| prometheus | 9090 | 業務/リソースメトリクス + アラート評価 |
| influxdb | 8086 | 高頻度衛星テレメトリ（電源/熱/姿勢/通信/軌道） |
| timescaledb | 5432 | 地上局パス・地球観測キャプチャ・ミッションKPI・異常 |
| simulator | 8000 | 模擬テレメトリ生成器（`/metrics` を公開） |

## 起動

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f simulator   # AOS/LOS・撮像ログが流れる
```

- Grafana: http://localhost:3000 （`admin` / `admin`）→ フォルダ "Space Mission Ops"
- Prometheus: http://localhost:9090 （Status → Rules で FDIR アラート確認）
- InfluxDB: http://localhost:8086

> リポジトリ root から `make up` でも起動できます。

## ダッシュボード

| ファイル | データソース | 内容 |
|---|---|---|
| 🛰 Satellite Health | InfluxDB (Flux) | 電源・熱・姿勢・通信のテレメトリ |
| 📡 Ground Station Ops | TimescaleDB (SQL) | 可視パス・コンタクト実績・局別ダウンリンク |
| 🌍 Mission & Earth Observation | TimescaleDB | 撮像フットプリント(Geomap)・データバッファ・撮像一覧 |
| 🖥 Infrastructure & Resources | Prometheus (PromQL) | 業務メトリクス監視・地上局コンタクトのタイムライン |

ダッシュボードは `scripts/gen_dashboards.py` が**コードから生成**します（dashboard as code）。
編集する場合はジェネレータを直して再生成してください。

```bash
python3 ../scripts/gen_dashboards.py
```

## 時間加速について

`.env` の `SIM_TIME_SCALE`（既定 60）で軌道伝播を加速します。
**物理計算は加速時刻**で、**DB 書き込みのタイムスタンプは実時刻**にしているため、
1 周回（約 96 分）が実時間 約 96 秒で進み、Grafana の「直近 15 分」表示で
食（eclipse）の出入りや地上局パスが次々と観測できます。

リアルタイム相当にしたい場合は `SIM_TIME_SCALE=1.0` に設定してください。

## アラート（FDIR 相当）

`prometheus/alerts.yml` に実装。Prometheus UI の Status → Rules / Alerts で確認できます。
バッテリー低下・温度超過・姿勢喪失・データバッファ満杯を検知します。

## 静的検証（Docker 不要）

```bash
python3 ../scripts/validate.py
docker compose config -q          # compose 定義の検証（Docker があれば）
```

## トラブルシュート

- **ダッシュボードが空** → simulator がまだデータを書く前か、起動待ち。`docker compose logs simulator` を確認。InfluxDB/TimescaleDB の healthcheck 通過後に simulator が起動します。
- **InfluxDB パネルだけ空** → `.env` の `INFLUXDB_BUCKET` を変えた場合は `scripts/gen_dashboards.py` の `BUCKET` も合わせて再生成。
- **地上局パスが出ない** → 数分待つ（極域局 Svalbard が最も高頻度）。`SIM_TIME_SCALE` を上げると早く観測できます。
