# 評価軸 — Grafana を宇宙開発で使い倒すための観点

Grafana を「ただのグラフ表示」で終わらせないために、本リポジトリでは以下の軸で評価する。
各軸は `stack/` の完動デモで実際に触れて確かめられる。

## 1. データソース適合性

| データソース | クエリ言語 | 得意領域 | 本デモでの役割 |
|---|---|---|---|
| Prometheus | PromQL | リソース監視・メトリクス・アラート | インフラ／シミュレータ自身の監視 ③ |
| InfluxDB (v2) | Flux | 高頻度時系列・長期保存 | 衛星テレメトリ（電源/熱/姿勢/通信）① |
| TimescaleDB | SQL | リレーショナル + 時系列の両立 | 地上局パス・コンタクト・ミッションKPI ① |

**評価ポイント**: 同じ「時系列」でも、メトリクス（Prometheus）／高頻度テレメトリ（InfluxDB）／
イベント・台帳（TimescaleDB）で最適解が異なる。1 つの Grafana から使い分けられるかを見る。

## 2. as code 運用性（GitOps）

- データソースを `provisioning/datasources/*.yml` で宣言
- ダッシュボードを JSON + `provisioning/dashboards/*.yml` で宣言
- アラートルールを Prometheus rules / Grafana Alerting で宣言

→ **UI で作ってポチポチ**ではなく、リポジトリに全構成が入り、再現可能であること。宇宙運用では構成管理が必須。

## 3. 可視化表現力（宇宙ドメインで有用なパネル）

| パネル | 宇宙での用途 |
|---|---|
| Geomap | 衛星直下点（sub-satellite point）・地上局位置 |
| Time series | 電源/温度/姿勢レートのトレンド |
| Gauge / Stat | バッテリー SoC・ポインティング誤差の即値 |
| State timeline | 可視パス（AOS/LOS）・日照/食（eclipse） |
| Table | 直近コンタクト・地球観測キャプチャ一覧 |
| Bar gauge | サブシステム別の温度マージン |

## 4. アラート設計（異常検知）

宇宙機の典型的な FDIR（Fault Detection, Isolation and Recovery）に対応する閾値アラート:

- バッテリー SoC < 30%（電力危機）
- 任意ゾーン温度 > 上限 / < 下限（熱異常）
- ポインティング誤差 > 5°（姿勢喪失・タンブリング）
- ダウンリンク中の信号ロック喪失

→ Prometheus alert rules（`stack/prometheus/alerts.yml`）で実装。

## 5. 埋め込み・フロントエンド集約 ②

外部 Web アプリへ Grafana を統合する 3 方式を比較（詳細は
[`../catalog/frontend-embed/`](../catalog/frontend-embed/README.md)）:

| 方式 | 特徴 | 向き |
|---|---|---|
| iframe 埋め込み（panel/dashboard） | 最も手軽 | 社内ダッシュ統合 |
| Public dashboards | 認証なし公開 | ステータスページ |
| Grafana Scenes（埋め込み SDK） | React アプリにネイティブ統合 | 自社プロダクトへの組込み |
