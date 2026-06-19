# 03 アプリプラグイン チュートリアル

複数のパネル・データソース・カスタムページを一つにまとめた**宇宙ミッション管制ポータル**を
アプリプラグインとして構築する方法を学びます。

---

## 概要: アプリプラグインとは

アプリプラグインは Grafana の左サイドバーにナビゲーション項目を追加し、
独自の React ページ、ダッシュボード、データソースをセットにして配布できるプラグイン種別です。

```
Grafana サイドバー
  └── 🚀 ミッション管制 (アプリプラグイン)
       ├── 衛星一覧 (カスタムページ)
       ├── ライブテレメトリ (ダッシュボード)
       └── 軌道ビューワ (カスタムページ + Leaflet.js)
```

---

## ステップ 1: 雛形の生成

```bash
cd catalog/plugins/03-app-plugin

npx @grafana/create-plugin@latest

# 対話式プロンプト:
#   What is your organization name? → myorg
#   What is your plugin name?       → mission-control-app
#   What type of plugin?            → app
```

生成後の主要ファイル:

```
mission-control-app/
├── src/
│   ├── module.ts              # アプリ登録
│   ├── plugin.json
│   ├── pages/
│   │   ├── SatelliteList.tsx  # 衛星一覧ページ
│   │   └── OrbitViewer.tsx    # 軌道ビューワページ
│   └── components/
│       └── AppConfig.tsx      # アプリ設定 UI
├── provisioning/              # 自動プロビジョニング用 YAML
│   └── plugins/
│       └── mission-control-app.yaml
└── package.json
```

---

## ステップ 2: plugin.json でルートを宣言

```json
{
  "type": "app",
  "name": "Mission Control App",
  "id": "myorg-mission-control-app",
  "includes": [
    {
      "type": "page",
      "name": "衛星一覧",
      "path": "/a/myorg-mission-control-app/satellites",
      "role": "Viewer",
      "addToNav": true,
      "defaultNav": true
    },
    {
      "type": "page",
      "name": "軌道ビューワ",
      "path": "/a/myorg-mission-control-app/orbit",
      "role": "Viewer",
      "addToNav": true
    },
    {
      "type": "dashboard",
      "name": "ライブテレメトリ",
      "path": "dashboards/live-telemetry.json"
    }
  ],
  "dependencies": {
    "grafanaDependency": ">=10.0.0",
    "plugins": [
      { "type": "datasource", "id": "myorg-tle-datasource", "name": "TLE Datasource" }
    ]
  }
}
```

---

## ステップ 3: module.ts でアプリを登録

```typescript
// src/module.ts
import { AppPlugin } from '@grafana/data';
import { AppConfig } from './components/AppConfig';
import { App } from './components/App';

export const plugin = new AppPlugin<{}>()
  .setRootPage(App)         // ルーティングを担当する Root コンポーネント
  .addConfigPage({
    title: '設定',
    icon: 'cog',
    body: AppConfig,
    id: 'configuration',
  });
```

---

## ステップ 4: ルーティング (App.tsx)

`@grafana/runtime` の `usePluginLinks` や React Router でページを切り替えます。

```tsx
// src/components/App.tsx
import React from 'react';
import { Route, Switch, useRouteMatch } from 'react-router-dom';
import { AppRootProps } from '@grafana/data';
import { SatelliteList } from '../pages/SatelliteList';
import { OrbitViewer } from '../pages/OrbitViewer';

export function App(_props: AppRootProps) {
  const { path } = useRouteMatch();

  return (
    <Switch>
      <Route exact path={`${path}/satellites`} component={SatelliteList} />
      <Route exact path={`${path}/orbit`} component={OrbitViewer} />
      <Route component={SatelliteList} />
    </Switch>
  );
}
```

---

## ステップ 5: カスタムページの実装例

```tsx
// src/pages/SatelliteList.tsx
import React, { useEffect, useState } from 'react';
import { css } from '@emotion/css';
import { getBackendSrv } from '@grafana/runtime';
import { Button, LoadingPlaceholder, useStyles2, useTheme2 } from '@grafana/ui';
import { GrafanaTheme2 } from '@grafana/data';

interface Satellite {
  name: string;
  noradId: string;
  status: 'active' | 'inactive';
}

const getStyles = (theme: GrafanaTheme2) => ({
  container: css({
    padding: theme.spacing(3),
    maxWidth: 800,
  }),
  heading: css({
    fontSize: theme.typography.h3.fontSize,
    marginBottom: theme.spacing(2),
  }),
  table: css({
    width: '100%',
    borderCollapse: 'collapse',
    '& th, & td': {
      padding: theme.spacing(1),
      borderBottom: `1px solid ${theme.colors.border.weak}`,
      textAlign: 'left',
    },
  }),
});

export function SatelliteList() {
  const styles = useStyles2(getStyles);
  const [satellites, setSatellites] = useState<Satellite[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Grafana バックエンドプロキシ経由で外部 API を呼ぶ
    getBackendSrv()
      .get('/api/plugins/myorg-mission-control-app/resources/satellites')
      .then((data: Satellite[]) => {
        setSatellites(data);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <LoadingPlaceholder text="衛星データを取得中..." />;
  }

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>監視対象衛星一覧</h2>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>衛星名</th>
            <th>NORAD ID</th>
            <th>状態</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {satellites.map((sat) => (
            <tr key={sat.noradId}>
              <td>{sat.name}</td>
              <td>{sat.noradId}</td>
              <td>{sat.status === 'active' ? '🟢 稼働中' : '🔴 停止'}</td>
              <td>
                <Button variant="secondary" size="sm" href={`orbit?id=${sat.noradId}`}>
                  軌道を見る
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

## ステップ 6: プロビジョニング設定

アプリプラグインはプロビジョニング YAML で自動有効化できます。
`docker-compose.yml` から参照するディレクトリに配置します。

```yaml
# provisioning/plugins/mission-control-app.yaml
apiVersion: 1
apps:
  - type: myorg-mission-control-app
    org_id: 1
    org_name: Main Org.
    disabled: false
    jsonData:
      someSetting: value
```

---

## アプリプラグインの主な活用シーン

| シーン | 内容 |
|--------|------|
| **管制ポータル** | 複数ダッシュボード + カスタム衛星一覧ページを統合 |
| **SLA レポート** | 定期レポートページ + PDF エクスポート機能 |
| **ITSM 連携** | Jira/ServiceNow への直接チケット起票 UI |
| **マルチテナント管理** | 組織/チーム単位での設定画面 |

---

## まとめ

| プラグイン種別 | 適用場面 | 実装の複雑さ |
|----------------|----------|-------------|
| パネル | カスタム可視化 | ★☆☆ |
| データソース | 独自データ取得 | ★★☆ |
| アプリ | 統合ポータル | ★★★ |

最初は **パネルプラグイン** から始め、データ取得を自作したくなったら **データソースプラグイン**、
複数機能を一つのパッケージにまとめたくなったら **アプリプラグイン** へと発展させるのが定石です。

---

## 参考: プラグイン署名と配布

```bash
# 1. Grafana Cloud の "Plugin Upload" でアカウントを作成
# 2. ACCESS_POLICY_TOKEN を発行
# 3. 署名
GRAFANA_ACCESS_POLICY_TOKEN=<token> yarn sign

# 4. 社内 Grafana に配置
cp -r dist/ /var/lib/grafana/plugins/myorg-mission-control-app/

# 5. grafana.ini で署名を確認 (または未署名を許可)
[plugins]
allow_loading_unsigned_plugins = myorg-mission-control-app
```

プラグインを Grafana マーケットプレイスで公開する場合は
[Plugin submission guidelines](https://grafana.com/developers/plugin-tools/publish-a-plugin/publish-a-plugin) を参照してください。
