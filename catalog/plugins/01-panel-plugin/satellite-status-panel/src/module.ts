import { PanelPlugin } from '@grafana/data';
import { SatelliteStatusPanel } from './SatelliteStatusPanel';
import { PanelOptions } from './types';

export const plugin = new PanelPlugin<PanelOptions>(SatelliteStatusPanel).setPanelOptions(
  (builder) => {
    builder
      .addBooleanSwitch({
        path: 'showTimestamp',
        name: 'タイムスタンプを表示',
        description: '最終更新時刻をパネル下部に表示します',
        defaultValue: true,
      })
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
      .addTextInput({
        path: 'unitSuffix',
        name: 'デフォルト単位',
        description: 'データフレームに単位が設定されていない場合に使用します',
        defaultValue: '%',
      });
  }
);
