# 01 パネルプラグイン チュートリアル

衛星サブシステムのステータスをミッション管制スタイルで表示するカスタムパネルを作成します。
完成品は `satellite-status-panel/` ディレクトリにあります。

---

## 作るもの

```
┌─────────────────────────────────────────────────────────┐
│  🛰️  衛星サブシステム ステータス                          │
├────────────┬────────────┬────────────┬──────────────────┤
│  🟢 電力    │  🟡 熱制御  │  🔴 姿勢   │  🟢 通信         │
│  82.4%     │  67.2%     │  18.3%     │  95.1%           │
│  NOMINAL   │  WARNING   │  CRITICAL  │  NOMINAL         │
├────────────┴────────────┴────────────┴──────────────────┤
│  最終更新: 2026-06-19 14:23:45 JST                       │
└─────────────────────────────────────────────────────────┘
```

各フィールドを時系列データから読み取り、しきい値に応じて色を変えます。
このリポジトリの `stack/` で動く InfluxDB や Prometheus のデータをそのまま使えます。

---

## ステップ 1: 雛形の生成

```bash
# 作業ディレクトリを作成
mkdir -p catalog/plugins/01-panel-plugin
cd catalog/plugins/01-panel-plugin

# Grafana 公式の create-plugin ツールで雛形を生成
npx @grafana/create-plugin@latest

# 対話式プロンプトの回答例:
#   What is your organization name? → myorg
#   What is your plugin name?       → satellite-status-panel
#   What type of plugin?            → panel
#   Do you want a backend?          → No
```

生成直後のディレクトリ構造:

```
satellite-status-panel/
├── src/
│   ├── module.ts          # プラグインのエントリポイント
│   ├── components/
│   │   └── SimplePanel.tsx  # デフォルトのパネルコンポーネント
│   └── types.ts           # オプション型定義
├── plugin.json            # プラグインメタデータ
├── package.json
├── tsconfig.json
└── .eslintrc
```

---

## ステップ 2: plugin.json の設定

`plugin.json` はプラグインのメタデータを定義します。

```json
{
  "$schema": "https://raw.githubusercontent.com/grafana/grafana/main/docs/sources/developers/plugins/plugin.schema.json",
  "type": "panel",
  "name": "Satellite Status Panel",
  "id": "myorg-satellite-status-panel",
  "info": {
    "description": "Displays satellite subsystem status in a mission control style",
    "author": { "name": "My Organization" },
    "keywords": ["satellite", "status", "space", "mission"],
    "version": "1.0.0",
    "updated": "2026-06-19"
  },
  "dependencies": {
    "grafanaDependency": ">=10.0.0",
    "plugins": []
  }
}
```

**重要**: `id` は `<組織名>-<プラグイン名>` の形式にします。Grafana 公式マーケットプレイスでは一意性が必要です。

---

## ステップ 3: 型定義 (types.ts)

パネルオプションの TypeScript 型を定義します。

```typescript
// src/types.ts
import { PanelOptions as GrafanaPanelOptions } from '@grafana/data';

export interface PanelOptions extends GrafanaPanelOptions {
  warningThreshold: number;   // 警告しきい値 (%)
  criticalThreshold: number;  // 危険しきい値 (%)
  showTimestamp: boolean;     // 最終更新時刻の表示
  unitSuffix: string;         // 単位サフィックス（例: "%", "°C"）
}

export type StatusLevel = 'ok' | 'warning' | 'critical' | 'unknown';

export interface SubsystemStatus {
  name: string;
  value: number | null;
  unit: string;
  level: StatusLevel;
}
```

---

## ステップ 4: パネルコンポーネントの実装

`src/SatelliteStatusPanel.tsx` を作成します（サンプルは `satellite-status-panel/src/` を参照）。

### Grafana パネルの Props 構造

```typescript
import { PanelProps } from '@grafana/data';
import { PanelOptions } from './types';

// PanelProps<T> に含まれる主なプロパティ:
//   data       : PanelData     - クエリ結果のデータフレーム群
//   options    : T             - パネルオプション（エディタで設定した値）
//   width      : number        - パネルの現在の幅 (px)
//   height     : number        - パネルの現在の高さ (px)
//   timeRange  : TimeRange     - 選択中の時間範囲
//   onChangeTimeRange          - 時間範囲を変更するコールバック

export const SatelliteStatusPanel: React.FC<PanelProps<PanelOptions>> = ({
  data,
  options,
  width,
  height,
}) => {
  // data.series は DataFrame[] — 各クエリ結果が1つの DataFrame
  // ...
};
```

### データフレームから最新値を取り出す

```typescript
import { DataFrame, FieldType, getLastNotNullFieldValue } from '@grafana/data';

function getLatestValue(frame: DataFrame): number | null {
  // 最初の数値フィールドを探す
  const field = frame.fields.find(f => f.type === FieldType.number);
  if (!field || field.values.length === 0) {
    return null;
  }
  // 末尾（最新）の値を返す
  return field.values[field.values.length - 1] ?? null;
}

function getFieldUnit(frame: DataFrame): string {
  const field = frame.fields.find(f => f.type === FieldType.number);
  return field?.config?.unit ?? '';
}
```

### Grafana テーマの使い方

```typescript
import { useTheme2, useStyles2 } from '@grafana/ui';
import { GrafanaTheme2, css } from '@grafana/data';

// useTheme2 でライト/ダークテーマに対応したカラートークンを取得
const theme = useTheme2();

// ステータスに応じたカラートークン
const statusColors: Record<StatusLevel, string> = {
  ok:       theme.colors.success.main,
  warning:  theme.colors.warning.main,
  critical: theme.colors.error.main,
  unknown:  theme.colors.text.disabled,
};

// useStyles2 で CSS-in-JS を定義（テーマ変数を関数で受け取る）
const getStyles = (theme: GrafanaTheme2) => ({
  card: css({
    background: theme.colors.background.secondary,
    borderRadius: theme.shape.radius.default,
    padding: theme.spacing(1.5),
  }),
});
const styles = useStyles2(getStyles);
```

---

## ステップ 5: モジュールエントリポイント (module.ts)

`module.ts` はプラグインを Grafana に登録し、パネルオプションエディタを定義します。

```typescript
// src/module.ts
import { PanelPlugin } from '@grafana/data';
import { SatelliteStatusPanel } from './SatelliteStatusPanel';
import { PanelOptions } from './types';

export const plugin = new PanelPlugin<PanelOptions>(SatelliteStatusPanel)
  .setPanelOptions(builder => {
    builder
      // ブール型スイッチ
      .addBooleanSwitch({
        path: 'showTimestamp',
        name: 'タイムスタンプを表示',
        description: '最終更新時刻をパネル下部に表示します',
        defaultValue: true,
      })
      // 数値入力
      .addNumberInput({
        path: 'warningThreshold',
        name: '警告しきい値 (%)',
        description: 'この値を下回ると黄色で表示します',
        defaultValue: 70,
        settings: { min: 0, max: 100, step: 1 },
      })
      .addNumberInput({
        path: 'criticalThreshold',
        name: '危険しきい値 (%)',
        description: 'この値を下回ると赤色で表示します',
        defaultValue: 30,
        settings: { min: 0, max: 100, step: 1 },
      })
      // テキスト入力
      .addTextInput({
        path: 'unitSuffix',
        name: 'デフォルト単位',
        description: 'データフレームに単位がない場合に使用します',
        defaultValue: '%',
      });
  });
```

---

## ステップ 6: 開発サーバーの起動

```bash
cd catalog/plugins/01-panel-plugin/satellite-status-panel

# 依存パッケージをインストール
yarn install

# ウォッチモードでビルド（ファイル変更時に自動再ビルド）
yarn dev
```

`dist/` ディレクトリが生成されます。Grafana にマウントするか、
`docker-compose.override.yml` を使ってホットリロードを有効にします。

```bash
# Grafana を起動（stack/ ディレクトリから）
cd ../../../../stack
docker compose up -d

# プラグインを追加でマウント（override ファイルを作成してから再起動）
docker compose down && docker compose up -d
```

---

## ステップ 7: ユニットテスト

```bash
# テストを実行
yarn test

# ウォッチモード
yarn test --watch

# カバレッジレポート
yarn test --coverage
```

テストの書き方は `satellite-status-panel/src/SatelliteStatusPanel.test.tsx` を参照してください。

```typescript
// テストの基本パターン
import { render, screen } from '@testing-library/react';
import { SatelliteStatusPanel } from './SatelliteStatusPanel';
import { createDataFrame, FieldType } from '@grafana/data';

it('正常値を緑色で表示する', () => {
  const data = {
    series: [
      createDataFrame({
        name: '電力',
        fields: [
          { name: 'Value', type: FieldType.number, values: [82.4] },
        ],
      }),
    ],
  };

  render(
    <SatelliteStatusPanel
      data={data as any}
      options={{ warningThreshold: 70, criticalThreshold: 30, showTimestamp: false, unitSuffix: '%' }}
      width={400}
      height={200}
      // ... 他の必須 props
    />
  );

  expect(screen.getByText('82.4')).toBeInTheDocument();
  expect(screen.getByText('NOMINAL')).toBeInTheDocument();
});
```

---

## ステップ 8: 本番ビルドと署名

```bash
# 最適化された本番ビルド
yarn build

# (任意) プラグインの署名 — Grafana Cloud にアップロードする場合に必要
# GRAFANA_ACCESS_POLICY_TOKEN 環境変数を設定してから:
yarn sign --rootUrls http://localhost:3000/
```

**署名なしで使う場合** (開発・社内利用): `grafana.ini` または環境変数で許可します。

```ini
# grafana.ini
[plugins]
allow_loading_unsigned_plugins = myorg-satellite-status-panel
```

```bash
# Docker Compose の場合
GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=myorg-satellite-status-panel
```

---

## 完成品ファイル一覧

```
satellite-status-panel/
├── src/
│   ├── module.ts                      # プラグイン登録・オプション定義
│   ├── types.ts                       # TypeScript 型定義
│   ├── SatelliteStatusPanel.tsx       # メインパネルコンポーネント
│   └── SatelliteStatusPanel.test.tsx  # ユニットテスト
├── plugin.json                        # プラグインメタデータ
├── package.json                       # 依存パッケージ
└── tsconfig.json                      # TypeScript 設定
```

次のチュートリアルへ: [02 データソースプラグイン](../02-datasource-plugin/README.md)
