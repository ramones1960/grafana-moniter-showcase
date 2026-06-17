# catalog/datasources — ① 各種DB連携の評価カタログ

Grafana を「各種 DB との連携基盤」として評価するための拡張メニュー。
`stack/` の完動デモでは **Prometheus / InfluxDB / TimescaleDB** の 3 つを実証済み。
ここには段階的に他のデータソースを追加し、宇宙開発ワークロードでの適合性を比較する。

## 評価ステータス

| データソース | クエリ言語 | 宇宙での想定用途 | 状態 |
|---|---|---|---|
| Prometheus | PromQL | リソース/業務メトリクス監視・アラート | ✅ `stack/` で実証 |
| InfluxDB v2 | Flux | 高頻度テレメトリの長期保存・ダウンサンプリング | ✅ `stack/` で実証 |
| TimescaleDB | SQL | 地上局パス・撮像台帳・KPI（リレーショナル+時系列） | ✅ `stack/` で実証 |
| ClickHouse | SQL | 大量テレメトリのカラムナ分析・アーカイブ集計 | ⬜ 予定 |
| Loki | LogQL | 運用ログ・地上系イベントログの集約 | ⬜ 予定 |
| Elasticsearch / OpenSearch | Lucene/DSL | 全文検索・異常ログ調査 | ⬜ 予定 |
| PostgreSQL (pgvector) | SQL | 異常パターンの類似検索（AI/RAG連携） | ⬜ 予定 |

> 姉妹リポジトリ [`compare-db-oss`](https://github.com/ramones1960/compare-db-oss) には
> これらの DB が docker-compose で個別起動できる形で揃っている。
> Grafana のデータソースとして接続すれば、DB ごとの Grafana 適合性をそのまま比較評価できる。

## 連携手順の雛形（compare-db-oss の DB を繋ぐ場合）

1. `compare-db-oss/databases/<category>/<db>` を起動
2. 本リポジトリの Grafana provisioning にデータソースを追記
   （`stack/grafana/provisioning/datasources/datasources.yml` を参照）
3. ネットワークを共有（外部ネットワーク参加 or `host.docker.internal`）
4. ダッシュボードを `scripts/gen_dashboards.py` に追加

## 比較観点

- **クエリ表現力**: 時系列集計・結合・ウィンドウ関数の書きやすさ
- **書き込みスループット**: 高頻度テレメトリに耐えるか
- **保持・ダウンサンプリング**: 長期運用での容量戦略
- **Grafana プラグイン成熟度**: 変数・アラート・Explore 対応
