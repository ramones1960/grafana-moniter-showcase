import { PanelOptions as GrafanaPanelOptions } from '@grafana/data';

export interface PanelOptions extends GrafanaPanelOptions {
  warningThreshold: number;
  criticalThreshold: number;
  showTimestamp: boolean;
  unitSuffix: string;
}

export type StatusLevel = 'ok' | 'warning' | 'critical' | 'unknown';

export interface SubsystemStatus {
  name: string;
  value: number | null;
  unit: string;
  level: StatusLevel;
}
