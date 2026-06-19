import React from 'react';
import { render, screen } from '@testing-library/react';
import { createDataFrame, FieldType, LoadingState } from '@grafana/data';
import { SatelliteStatusPanel } from './SatelliteStatusPanel';
import { PanelOptions } from './types';

// @grafana/ui のテーマフックをモック
jest.mock('@grafana/ui', () => ({
  ...jest.requireActual('@grafana/ui'),
  useTheme2: () => ({
    colors: {
      success: { main: '#73BF69' },
      warning: { main: '#FF9830' },
      error: { main: '#F2495C' },
      text: { secondary: '#D9D9D9', disabled: '#888888' },
      background: { secondary: '#1F1F1F', primary: '#111111' },
      border: { weak: '#333333' },
    },
    spacing: (n: number) => `${n * 8}px`,
    shape: { radius: { default: '4px', pill: '999px' } },
    typography: {
      bodySmall: { fontSize: '12px' },
      body: { fontSize: '14px' },
      fontWeightBold: 700,
      fontFamilyMonospace: 'monospace',
    },
  }),
  useStyles2: (fn: (t: any) => any) => fn({
    colors: {
      success: { main: '#73BF69' },
      warning: { main: '#FF9830' },
      error: { main: '#F2495C' },
      text: { secondary: '#D9D9D9', disabled: '#888888' },
      background: { secondary: '#1F1F1F', primary: '#111111' },
      border: { weak: '#333333' },
    },
    spacing: (n: number) => `${n * 8}px`,
    shape: { radius: { default: '4px', pill: '999px' } },
    typography: {
      bodySmall: { fontSize: '12px' },
      body: { fontSize: '14px' },
      fontWeightBold: 700,
      fontFamilyMonospace: 'monospace',
    },
  }),
}));

// @emotion/css をモック（スタイル文字列をそのまま返す）
jest.mock('@emotion/css', () => ({
  css: (...args: any[]) => args.join(' '),
}));

const defaultOptions: PanelOptions = {
  warningThreshold: 70,
  criticalThreshold: 30,
  showTimestamp: false,
  unitSuffix: '%',
};

function makeProps(overrides: Partial<{
  series: any[];
  options: Partial<PanelOptions>;
}> = {}) {
  return {
    data: {
      state: LoadingState.Done,
      series: overrides.series ?? [],
      timeRange: {} as any,
    },
    options: { ...defaultOptions, ...(overrides.options ?? {}) },
    width: 400,
    height: 200,
    // 残りの必須 props は空実装
    id: 1,
    transparent: false,
    renderCounter: 0,
    title: '',
    eventBus: {} as any,
    timeRange: {} as any,
    timeZone: 'browser',
    fieldConfig: {} as any,
    onFieldConfigChange: jest.fn(),
    onOptionsChange: jest.fn(),
    onChangeTimeRange: jest.fn(),
    replaceVariables: (v: string) => v,
  };
}

describe('SatelliteStatusPanel', () => {
  it('データなしのとき案内メッセージを表示する', () => {
    render(<SatelliteStatusPanel {...makeProps()} />);
    expect(screen.getByText(/クエリを追加/)).toBeInTheDocument();
  });

  it('正常値 (82.4%) を NOMINAL で表示する', () => {
    const series = [
      createDataFrame({
        name: '電力',
        fields: [
          { name: 'Value', type: FieldType.number, values: [82.4] },
        ],
      }),
    ];
    render(<SatelliteStatusPanel {...makeProps({ series })} />);

    expect(screen.getByText('82.4')).toBeInTheDocument();
    expect(screen.getByTestId('status-badge-電力')).toHaveTextContent('NOMINAL');
  });

  it('警告値 (55%) を WARNING で表示する', () => {
    const series = [
      createDataFrame({
        name: '熱制御',
        fields: [
          { name: 'Value', type: FieldType.number, values: [55] },
        ],
      }),
    ];
    render(<SatelliteStatusPanel {...makeProps({ series })} />);

    expect(screen.getByTestId('status-badge-熱制御')).toHaveTextContent('WARNING');
  });

  it('危険値 (18.3%) を CRITICAL で表示する', () => {
    const series = [
      createDataFrame({
        name: '姿勢',
        fields: [
          { name: 'Value', type: FieldType.number, values: [18.3] },
        ],
      }),
    ];
    render(<SatelliteStatusPanel {...makeProps({ series })} />);

    expect(screen.getByTestId('status-badge-姿勢')).toHaveTextContent('CRITICAL');
  });

  it('空値を NO DATA で表示する', () => {
    const series = [
      createDataFrame({
        name: '通信',
        fields: [
          { name: 'Value', type: FieldType.number, values: [] },
        ],
      }),
    ];
    render(<SatelliteStatusPanel {...makeProps({ series })} />);

    expect(screen.getByTestId('status-badge-通信')).toHaveTextContent('NO DATA');
  });

  it('showTimestamp=true のとき最終更新を表示する', () => {
    const series = [
      createDataFrame({
        name: '電力',
        fields: [{ name: 'Value', type: FieldType.number, values: [90] }],
      }),
    ];
    render(
      <SatelliteStatusPanel
        {...makeProps({ series, options: { showTimestamp: true } })}
      />
    );
    expect(screen.getByText(/最終更新/)).toBeInTheDocument();
  });

  it('複数サブシステムを同時に表示できる', () => {
    const series = ['電力', '熱制御', '姿勢', '通信'].map((name, i) =>
      createDataFrame({
        name,
        fields: [{ name: 'Value', type: FieldType.number, values: [80 - i * 20] }],
      })
    );
    render(<SatelliteStatusPanel {...makeProps({ series })} />);

    expect(screen.getByText('電力')).toBeInTheDocument();
    expect(screen.getByText('熱制御')).toBeInTheDocument();
    expect(screen.getByText('姿勢')).toBeInTheDocument();
    expect(screen.getByText('通信')).toBeInTheDocument();
  });
});
