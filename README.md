# grafana-moniter-showcase

**Grafana の様々な利用方法を「宇宙開発」を題材に検討・評価する**ショーケースモノレポです。

Grafana は単なる「メトリクスのグラフ表示ツール」ではありません。
本リポジトリでは Grafana を次の **3 つの使い方**で評価します。

| # | 使い方 | 本リポジトリでの実証 |
|---|---|---|
| ① | **各種 DB との連携基盤** | Prometheus / InfluxDB / TimescaleDB の 3 データソースを provisioning（as code）で同居させ、用途別に使い分ける |
| ② | **Web アプリのフロントエンド集約** | ダッシュボード埋め込み（iframe / public dashboards / Grafana Scenes）で複数システムの画面を 1 つに集約する設計を提示 |
| ③ | **各種リソース監視** | Prometheus + exporter 群でインフラ／アプリのリソースを監視する王道構成 |

これらを **宇宙開発分野**（衛星テレメトリ / 地上局運用 / 地球観測ミッション）という
1 つのストーリーで束ね、**模擬テレメトリ生成器**が全データソースを一気通貫で駆動します。

> 姉妹リポジトリ [`compare-db-oss`](https://github.com/ramones1960/compare-db-oss) の流儀
> （カテゴリ別ディレクトリ・各単位が docker-compose で自己完結・Makefile 統一エントリ）を踏襲しています。
> Grafana のデータソース連携先として `compare-db-oss` の DB 群をそのまま接続することも可能です。

---

## クイックスタート（完動デモ）

第一弾として、**1 コマンドで立ち上がる「宇宙ミッション運用センター」スタック**を用意しています。

```bash
cd stack
cp .env.example .env        # 必要に応じて編集
docker compose up -d

# Grafana:    http://localhost:3000   (admin / admin)
# Prometheus: http://localhost:9090
# InfluxDB:   http://localhost:8086
```

起動後、Grafana には **4 つのダッシュボードが自動プロビジョニング**されます。

| ダッシュボード | データソース | 宇宙ユースケース |
|---|---|---|
| 🛰 Satellite Health | InfluxDB | 衛星テレメトリ / ヘルス監視（電源・姿勢・熱・通信） |
| 📡 Ground Station Ops | TimescaleDB | 地上局 / 運用監視（可視パス・コンタクト・ダウンリンク） |
| 🌍 Mission & Earth Observation | TimescaleDB + InfluxDB | 地球観測データ / ミッション KPI |
| 🖥 Infrastructure | Prometheus | リソース監視（シミュレータ／インフラ） |

詳細は [`stack/README.md`](stack/README.md) を参照。

---

## ディレクトリ構成

```
grafana-moniter-showcase/
├── docs/                      # 評価軸・Grafana利用パターン整理・宇宙監視の設計
├── stack/                     # ★第一弾: 完動「宇宙ミッション運用センター」スタック
│   ├── docker-compose.yml     #   Grafana + Prometheus + InfluxDB + TimescaleDB + simulator
│   ├── simulator/             #   模擬テレメトリ生成器（軌道・電源・熱・姿勢・通信）
│   ├── grafana/               #   datasource/dashboard as code
│   ├── prometheus/            #   スクレイプ設定・アラートルール
│   └── timescaledb/           #   スキーマ・初期データ
├── catalog/                   # 拡張カタログ（段階的に追加していく評価メニュー）
│   ├── datasources/           #   ① 各種DB連携の評価カタログ
│   ├── frontend-embed/        #   ② フロントエンド集約パターン
│   ├── resource-monitoring/   #   ③ リソース監視の深掘り（exporter別）
│   └── plugins/               #   ④ Grafana プラグイン自作チュートリアル
│       ├── 01-panel-plugin/   #      パネルプラグイン（衛星ステータス表示）
│       ├── 02-datasource-plugin/ #   データソースプラグイン（TLE 軌道データ）
│       └── 03-app-plugin/     #      アプリプラグイン（管制ポータル）
└── Makefile                   # 統一エントリポイント
```

---

## 評価の観点

本リポジトリは「Grafana で何ができるか」を**動かしながら**評価することを目的とします。
評価軸の詳細は [`docs/evaluation-axes.md`](docs/evaluation-axes.md) を参照してください（抜粋）。

- **データソース適合性** — 時系列・リレーショナル・メトリクスをそれぞれ最適なクエリ言語（Flux / SQL / PromQL）でどう扱うか
- **as code 運用性** — ダッシュボード・データソース・アラートをコードで管理できるか
- **可視化表現力** — Geomap / Time series / State timeline / Table など宇宙ドメインで有用なパネル
- **アラート設計** — バッテリー低下・温度上昇・姿勢喪失などの異常検知
- **埋め込み・集約** — 外部 Web フロントエンドへの統合のしやすさ

---

## ロードマップ

- [x] 第一弾: 完動「宇宙ミッション運用センター」スタック（本リポジトリ）
- [ ] `catalog/datasources/`: ClickHouse / Loki / Elasticsearch など他データソースの評価追加
- [ ] `catalog/frontend-embed/`: React アプリへの埋め込みサンプル実装
- [ ] `catalog/resource-monitoring/`: node / cAdvisor / blackbox exporter の個別深掘り
- [ ] Grafana Alerting → 通知連携（Slack / Webhook）のサンプル
- [x] `catalog/plugins/`: Grafana プラグイン自作チュートリアル（パネル・DS・アプリ）

---

## 将来方針: OpenTelemetry (OTel) への対応

現在のリソース監視は **Prometheus + exporter** の構成（メトリクスのみ）だが、
将来的に **OpenTelemetry** への移行・統合を検討している。

### 背景

Prometheus exporter はメトリクス収集に特化しており、ログ・トレースは別途スタックが必要になる。
OpenTelemetry はメトリクス・ログ・トレースを単一の標準 SDK / Collector で扱える業界標準として台頭しており、
Grafana も LGTM スタック（Loki・Grafana・Tempo・Mimir）で OTel をファーストクラスサポートしている。

### 想定するアーキテクチャ

```
機器 / アプリ / カスタム exporter
  └── OpenTelemetry Collector（エージェント）
        ├── metrics → Prometheus / Mimir（既存 Grafana ダッシュボードと互換）
        ├── logs    → Loki
        └── traces  → Tempo
              └── Grafana で一元可視化
```

現時点のカスタム exporter（`prometheus_client` ベース）は OTel の metrics SDK へ段階的に置き換え可能であり、
Grafana ダッシュボードは PromQL 互換のまま継続利用できる。

### 検討中の対応項目

- [ ] OTel Collector を `stack/` に追加し、既存 Prometheus スクレイプと並走させる PoC
- [ ] シミュレータの `PromSink` を OTel SDK（`opentelemetry-sdk`）に移行する評価
- [ ] Loki によるログ収集を追加し、メトリクスとログを Grafana で相関表示
- [ ] 地上系機器（アンテナ制御装置等）向けカスタム OTel Receiver の設計
