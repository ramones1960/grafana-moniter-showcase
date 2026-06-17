# catalog/resource-monitoring — ③ リソース監視の深掘り

Grafana + Prometheus の王道「リソース監視」を exporter 別に深掘りする拡張メニュー。
`stack/` ではシミュレータが `prometheus_client` で**衛星ヘルスを業務メトリクス**として公開し、
「アプリのリソース監視」と同じ流儀で扱う例を実証済み。

宇宙開発の地上系（運用センター・地上局のサーバ群）は普通の IT インフラなので、
標準的な exporter スタックがそのまま活きる。

## exporter カタログ

| exporter | 監視対象 | 主なメトリクス | 状態 |
|---|---|---|---|
| アプリ計装 (prometheus_client) | 衛星ヘルスサマリ | SoC/温度/姿勢/コンタクト | ✅ `stack/` で実証 |
| node_exporter | 運用センターのホスト | CPU/メモリ/ディスク/NW | ⬜ 予定 |
| cAdvisor | コンテナ群 | コンテナ別リソース | ⬜ 予定 |
| blackbox_exporter | 地上局エンドポイント外形監視 | 死活・遅延・証明書期限 | ⬜ 予定 |
| postgres_exporter | TimescaleDB 自体の健全性 | コネクション/レプリ遅延 | ⬜ 予定 |

## アラート設計（実装済み）

`stack/prometheus/alerts.yml` に FDIR 相当の閾値アラートを実装:

- BatteryLow / BatteryCritical（電力危機）
- ThermalHigh（熱異常）
- AttitudeLoss（姿勢喪失）
- DataBufferFull（オンボード蓄積満杯）

## ロードマップ

- [ ] node_exporter + cAdvisor を stack に追加し「地上系インフラ監視」ダッシュボードを追加
- [ ] blackbox_exporter で地上局 API の外形監視
- [ ] Grafana Alerting → Slack / Webhook 通知連携
