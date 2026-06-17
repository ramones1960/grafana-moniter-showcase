# catalog/frontend-embed — ② Webアプリのフロントエンド集約

Grafana を「複数システムの画面を 1 つに集約するフロントエンド基盤」として評価する。
宇宙開発では **ミッション運用ポータル**（社内向け）と **対外ミッションステータスページ**（公開）の
2 つの典型シナリオに対応する。

## 集約パターン比較

| 方式 | 仕組み | 実装コスト | 認証 | 宇宙での用途 |
|---|---|---|---|---|
| iframe 埋め込み | パネル/ダッシュボードの share URL を iframe | ★（最小） | Grafana 認証/匿名 | 社内運用ポータルに各班のダッシュを集約 |
| Public dashboards | 認証不要の公開 URL | ★ | なし | 打上げライブのミッションステータス公開 |
| Grafana Scenes | React SDK でパネルを部品化 | ★★★ | アプリ側 | 自社運用システムにネイティブ統合 |
| Snapshot | 静的スナップショット | ★ | 共有リンク | 異常解析レポート・事後検証 |

## iframe 埋め込みを試す

`stack/.env` で埋め込みを許可する:

```bash
GF_ALLOW_EMBEDDING=true   # → docker compose up -d で再起動
```

Grafana の各パネル右上 → Share → Embed で iframe スニペットが得られる。
社内ポータル HTML に貼るだけで「Satellite Health」「Ground Station Ops」を 1 画面に集約できる。

```html
<!-- 例: ミッション運用ポータル -->
<iframe src="http://localhost:3000/d-solo/sat-health/?panelId=2&theme=dark"
        width="450" height="200" frameborder="0"></iframe>
```

## ロードマップ

- [ ] `mission-portal/` … iframe で 4 ダッシュボードを集約した最小 HTML ポータル
- [ ] `scenes-app/` … Grafana Scenes で運用画面を React に組み込むサンプル
- [ ] Public dashboards でのミッションステータス公開手順
