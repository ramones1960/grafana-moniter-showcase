# Grafana プラグイン自作チュートリアル

このディレクトリでは、Grafana のプラグインを自作・拡張する方法を段階的に学べるチュートリアルを提供します。
このリポジトリの宇宙ミッション運用テーマに沿った実用的なサンプルを通じて、プラグイン開発の全体像を把握できます。

## プラグインの種類

Grafana のプラグインには主に3種類あります。

| 種類 | 用途 | 本チュートリアルの例 |
|------|------|------|
| **パネルプラグイン** | カスタム可視化パネル | 衛星サブシステム・ステータス表示 |
| **データソースプラグイン** | 独自のデータ取得ロジック | TLE ファイルから軌道データを取得 |
| **アプリプラグイン** | 複数ページ・パネル・DSを統合したアプリ | 宇宙ミッション管制ポータル |

---

## チュートリアル一覧

### [01 パネルプラグイン](./01-panel-plugin/README.md)
最もよく使われるプラグイン種別。独自のデータ可視化コンポーネントを React + TypeScript で作成します。

**学べること**
- `@grafana/create-plugin` による雛形生成
- `PanelPlugin` API の使い方
- Grafana テーマシステムへの対応
- パネルオプション（設定 UI）の追加
- Jest によるユニットテスト

### [02 データソースプラグイン](./02-datasource-plugin/README.md)
独自の API やファイル形式からデータを取得し、Grafana のデータフレームに変換します。

**学べること**
- `DataSourcePlugin` / `DataSourceApi` の実装
- クエリエディタの作成
- データフレームへの変換パターン
- 設定画面（接続先・認証）の実装

### [03 アプリプラグイン](./03-app-plugin/README.md)
複数のパネル・データソース・カスタムページを束ねた総合アプリを作成します。

**学べること**
- アプリプラグインのルーティング
- カスタムページ（React Router）
- ナビゲーションの統合
- バックエンドプロキシの利用

---

## 共通の開発環境セットアップ

### 必要なツール

```bash
# Node.js 20+ (LTS)
node --version   # v20.x.x 以上

# Docker & Docker Compose (Grafana 実行用)
docker --version

# yarn (推奨) または npm
yarn --version
```

### Grafana 開発用インスタンスの起動

このリポジトリのスタックをそのまま開発用に使えます。

```bash
# リポジトリルートで
cd stack && docker compose up -d

# Grafana: http://localhost:3000 (admin/admin)
```

プラグインをホットリロード付きで開発するには、`grafana.ini` でプラグインパスを追加するか、
後述の `docker-compose.override.yml` を使います。

### プラグインディレクトリのマウント設定

`stack/docker-compose.override.yml` を作成（git 管理外）することで、
開発中のプラグインを Grafana に認識させられます。

```yaml
# stack/docker-compose.override.yml (例)
services:
  grafana:
    environment:
      - GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=myorg-satellite-status-panel
    volumes:
      - ../catalog/plugins/01-panel-plugin/satellite-status-panel/dist:/var/lib/grafana/plugins/satellite-status-panel
```

---

## プラグイン開発の基本フロー

```
1. create-plugin で雛形生成
       ↓
2. plugin.json でメタデータ設定
       ↓
3. src/ で React/TypeScript 実装
       ↓
4. yarn dev でウォッチビルド
       ↓
5. Grafana でプラグインを確認（ホットリロード）
       ↓
6. yarn test でユニットテスト
       ↓
7. yarn build で本番ビルド
       ↓
8. (オプション) プラグイン署名 → Grafana Cloud / プライベート配布
```

---

## 参考リソース

- [Grafana Plugin Tools 公式ドキュメント](https://grafana.com/developers/plugin-tools/)
- [Grafana UI コンポーネントカタログ](https://developers.grafana.com/ui/latest/)
- [Grafana GitHub サンプルプラグイン](https://github.com/grafana/grafana-plugin-examples)
- [Plugin SDK for Go（バックエンドプラグイン）](https://grafana.com/developers/plugin-tools/introduction/backend-plugins)
