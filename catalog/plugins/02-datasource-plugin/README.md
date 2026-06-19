# 02 データソースプラグイン チュートリアル

独自のデータソースを Grafana に追加する方法を学びます。
ここでは **TLE (Two-Line Element Set) ファイルから衛星軌道データを取得する**
シンプルなデータソースプラグインを例に解説します。

---

## 概要: データソースプラグインとは

Grafana 標準では対応していない API やファイル形式からデータを取得し、
Grafana の「データフレーム」形式に変換して可視化できるようにするプラグインです。

```
外部 API / ファイル
      │
      ▼
┌─────────────────┐
│  DataSource     │  ← QueryEditor が生成したクエリを受け取る
│  (TypeScript)   │  ← HTTP リクエストや計算を実行
│                 │  ← DataFrame を返す
└─────────────────┘
      │
      ▼
  Grafana パネル
```

---

## ステップ 1: 雛形の生成

```bash
cd catalog/plugins/02-datasource-plugin

npx @grafana/create-plugin@latest

# 対話式プロンプトの回答例:
#   What is your organization name? → myorg
#   What is your plugin name?       → tle-datasource
#   What type of plugin?            → datasource
#   Do you want a backend?          → No  (フロントエンドのみで HTTP を叩く場合)
```

---

## ステップ 2: ファイル構成

```
tle-datasource/
├── src/
│   ├── module.ts              # プラグイン登録
│   ├── datasource.ts          # DataSourceApi の実装 (コアロジック)
│   ├── types.ts               # 型定義
│   ├── ConfigEditor.tsx       # 接続設定 UI（URL・認証など）
│   └── QueryEditor.tsx        # クエリ入力 UI
├── plugin.json
└── package.json
```

---

## ステップ 3: 型定義 (types.ts)

```typescript
// src/types.ts
import { DataSourceJsonData, DataQuery } from '@grafana/data';

// クエリ — ユーザーがクエリエディタで入力する情報
export interface TleQuery extends DataQuery {
  satelliteName: string;   // 衛星名でフィルタ
  parameter: 'latitude' | 'longitude' | 'altitude' | 'velocity';
  forecastHours: number;   // 何時間先まで計算するか
}

// データソース設定 — 接続設定 UI で入力される情報
export interface TleDataSourceOptions extends DataSourceJsonData {
  tleApiUrl: string;       // TLE データを返す API の URL
}

// 秘匿情報 — Grafana のシークレット保存を使う
export interface TleSecureJsonData {
  apiKey?: string;
}
```

---

## ステップ 4: DataSourceApi の実装 (datasource.ts)

```typescript
// src/datasource.ts
import {
  DataQueryRequest,
  DataQueryResponse,
  DataSourceApi,
  DataSourceInstanceSettings,
  MutableDataFrame,
  FieldType,
} from '@grafana/data';
import { getBackendSrv, getTemplateSrv } from '@grafana/runtime';
import { TleDataSourceOptions, TleQuery } from './types';

export class TleDataSource extends DataSourceApi<TleQuery, TleDataSourceOptions> {
  private readonly apiUrl: string;

  constructor(instanceSettings: DataSourceInstanceSettings<TleDataSourceOptions>) {
    super(instanceSettings);
    this.apiUrl = instanceSettings.jsonData.tleApiUrl || 'https://celestrak.org/SOCRATES/query.php';
  }

  // ① クエリの実行 — Grafana がパネルを描画するたびに呼ばれる
  async query(request: DataQueryRequest<TleQuery>): Promise<DataQueryResponse> {
    const { range } = request;

    const data = await Promise.all(
      request.targets
        .filter((t) => !t.hide && t.satelliteName)
        .map((target) => this.runQuery(target, range))
    );

    return { data };
  }

  private async runQuery(
    target: TleQuery,
    range: DataQueryRequest['range']
  ): Promise<MutableDataFrame> {
    // テンプレート変数を展開 ($satellite など)
    const name = getTemplateSrv().replace(target.satelliteName);

    // TLE API からデータ取得
    const tle = await this.fetchTle(name);

    // 軌道計算 → 時系列データフレームに変換
    return this.propagateOrbit(tle, target.parameter, range, target.refId);
  }

  private async fetchTle(name: string): Promise<string[]> {
    // getBackendSrv は Grafana のプロキシ経由で CORS 問題を回避
    const response = await getBackendSrv().datasourceRequest({
      url: `${this.apiUrl}?name=${encodeURIComponent(name)}&FORMAT=TLE`,
      method: 'GET',
    });
    // TLE は 3 行セット: name, line1, line2
    return response.data.trim().split('\n');
  }

  private propagateOrbit(
    tle: string[],
    parameter: TleQuery['parameter'],
    range: DataQueryRequest['range'],
    refId: string
  ): MutableDataFrame {
    const frame = new MutableDataFrame({
      refId,
      name: tle[0]?.trim(),
      fields: [
        { name: 'time', type: FieldType.time },
        { name: parameter, type: FieldType.number, config: { unit: getUnit(parameter) } },
      ],
    });

    // 時間範囲を 60 秒ステップで走査してデータポイントを追加
    // (実際には satellite.js などのライブラリで SGP4 計算)
    const step = 60_000; // 1分
    for (let t = range.from.valueOf(); t <= range.to.valueOf(); t += step) {
      const value = computeParameter(tle, t, parameter); // 実装は省略
      frame.appendRow([t, value]);
    }

    return frame;
  }

  // ② 接続テスト — データソース設定画面の「Test」ボタンで呼ばれる
  async testDatasource(): Promise<{ status: string; message: string }> {
    try {
      await getBackendSrv().datasourceRequest({
        url: this.apiUrl,
        method: 'GET',
      });
      return { status: 'success', message: 'TLE API に接続できました' };
    } catch (e) {
      return { status: 'error', message: `接続失敗: ${(e as Error).message}` };
    }
  }
}

function getUnit(parameter: TleQuery['parameter']): string {
  const units: Record<TleQuery['parameter'], string> = {
    latitude: 'degree',
    longitude: 'degree',
    altitude: 'km',
    velocity: 'velocitykms',
  };
  return units[parameter];
}

function computeParameter(
  _tle: string[],
  _time: number,
  _parameter: TleQuery['parameter']
): number {
  // TODO: satellite.js の sgp4() を使って実際に計算する
  return Math.random() * 100;
}
```

---

## ステップ 5: ConfigEditor — 接続設定 UI

```tsx
// src/ConfigEditor.tsx
import React from 'react';
import { DataSourcePluginOptionsEditorProps } from '@grafana/data';
import { InlineField, Input } from '@grafana/ui';
import { TleDataSourceOptions } from './types';

type Props = DataSourcePluginOptionsEditorProps<TleDataSourceOptions>;

export function ConfigEditor({ options, onOptionsChange }: Props) {
  return (
    <div>
      <InlineField label="TLE API URL" labelWidth={16} tooltip="TLE データを返す API のベース URL">
        <Input
          value={options.jsonData.tleApiUrl || ''}
          placeholder="https://celestrak.org/SOCRATES/query.php"
          onChange={(e) =>
            onOptionsChange({
              ...options,
              jsonData: { ...options.jsonData, tleApiUrl: e.currentTarget.value },
            })
          }
          width={40}
        />
      </InlineField>
    </div>
  );
}
```

---

## ステップ 6: QueryEditor — クエリ入力 UI

```tsx
// src/QueryEditor.tsx
import React from 'react';
import { QueryEditorProps } from '@grafana/data';
import { InlineField, Select, Input } from '@grafana/ui';
import { TleDataSource } from './datasource';
import { TleDataSourceOptions, TleQuery } from './types';

type Props = QueryEditorProps<TleDataSource, TleQuery, TleDataSourceOptions>;

const PARAMETER_OPTIONS = [
  { label: '緯度', value: 'latitude' },
  { label: '経度', value: 'longitude' },
  { label: '高度 (km)', value: 'altitude' },
  { label: '速度 (km/s)', value: 'velocity' },
];

export function QueryEditor({ query, onChange, onRunQuery }: Props) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <InlineField label="衛星名" labelWidth={12}>
        <Input
          value={query.satelliteName || ''}
          placeholder="ISS (ZARYA)"
          onChange={(e) => onChange({ ...query, satelliteName: e.currentTarget.value })}
          onBlur={onRunQuery}
          width={24}
        />
      </InlineField>
      <InlineField label="パラメータ" labelWidth={12}>
        <Select
          options={PARAMETER_OPTIONS}
          value={query.parameter || 'altitude'}
          onChange={(v) => {
            onChange({ ...query, parameter: v.value as TleQuery['parameter'] });
            onRunQuery();
          }}
          width={16}
        />
      </InlineField>
    </div>
  );
}
```

---

## ステップ 7: module.ts でプラグイン登録

```typescript
// src/module.ts
import { DataSourcePlugin } from '@grafana/data';
import { TleDataSource } from './datasource';
import { ConfigEditor } from './ConfigEditor';
import { QueryEditor } from './QueryEditor';
import { TleDataSourceOptions, TleQuery } from './types';

export const plugin = new DataSourcePlugin<TleDataSource, TleQuery, TleDataSourceOptions>(
  TleDataSource
)
  .setConfigEditor(ConfigEditor)
  .setQueryEditor(QueryEditor);
```

---

## バックエンドプラグインへの拡張

フロントエンド実行では CORS 制限や認証情報の露出が問題になる場合があります。
Go 製バックエンドを追加することで、Grafana サーバー側でリクエストを処理できます。

```bash
# 雛形生成時に "Do you want a backend?" → Yes を選択すると
# pkg/main.go と Mage ビルドスクリプトが追加される

# バックエンドビルド
mage -v build:linux

# フロントエンドと同時ビルド
yarn build && mage -v build:linux
```

バックエンドでの実装詳細は [Grafana Plugin SDK for Go](https://grafana.com/developers/plugin-tools/introduction/backend-plugins) を参照してください。

---

次のチュートリアルへ: [03 アプリプラグイン](../03-app-plugin/README.md)
