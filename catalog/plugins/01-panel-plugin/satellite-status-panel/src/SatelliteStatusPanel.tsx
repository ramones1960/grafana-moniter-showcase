import React, { useMemo } from 'react';
import { css } from '@emotion/css';
import { DataFrame, FieldType, GrafanaTheme2, PanelProps } from '@grafana/data';
import { useStyles2, useTheme2 } from '@grafana/ui';
import { PanelOptions, StatusLevel, SubsystemStatus } from './types';

// ─── ヘルパー関数 ────────────────────────────────────────────────────────────

function getLatestValue(frame: DataFrame): number | null {
  const field = frame.fields.find((f) => f.type === FieldType.number);
  if (!field || field.values.length === 0) {
    return null;
  }
  const val = field.values[field.values.length - 1];
  return val == null ? null : Number(val);
}

function getFieldUnit(frame: DataFrame, fallback: string): string {
  const field = frame.fields.find((f) => f.type === FieldType.number);
  return field?.config?.unit || fallback;
}

function computeLevel(
  value: number | null,
  warningThreshold: number,
  criticalThreshold: number
): StatusLevel {
  if (value == null) {
    return 'unknown';
  }
  if (value < criticalThreshold) {
    return 'critical';
  }
  if (value < warningThreshold) {
    return 'warning';
  }
  return 'ok';
}

const STATUS_LABEL: Record<StatusLevel, string> = {
  ok: 'NOMINAL',
  warning: 'WARNING',
  critical: 'CRITICAL',
  unknown: 'NO DATA',
};

// ─── スタイル定義 ─────────────────────────────────────────────────────────────

const getStyles = (theme: GrafanaTheme2) => ({
  wrapper: css({
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: theme.spacing(1),
    padding: theme.spacing(1),
    overflow: 'auto',
    fontFamily: theme.typography.fontFamilyMonospace,
    boxSizing: 'border-box',
  }),
  grid: css({
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: theme.spacing(1),
    flex: 1,
  }),
  card: css({
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing(0.5),
    padding: theme.spacing(1.5),
    borderRadius: theme.shape.radius.default,
    background: theme.colors.background.secondary,
    border: `1px solid ${theme.colors.border.weak}`,
    minHeight: 90,
  }),
  subsystemName: css({
    fontSize: theme.typography.bodySmall.fontSize,
    color: theme.colors.text.secondary,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    textAlign: 'center',
  }),
  valueRow: css({
    display: 'flex',
    alignItems: 'baseline',
    gap: theme.spacing(0.25),
  }),
  value: css({
    fontSize: '1.6rem',
    fontWeight: theme.typography.fontWeightBold,
    lineHeight: 1,
  }),
  unit: css({
    fontSize: theme.typography.bodySmall.fontSize,
    color: theme.colors.text.secondary,
  }),
  statusBadge: css({
    fontSize: '0.65rem',
    fontWeight: theme.typography.fontWeightBold,
    letterSpacing: '0.08em',
    padding: `${theme.spacing(0.25)} ${theme.spacing(0.75)}`,
    borderRadius: theme.shape.radius.pill,
    color: theme.colors.background.primary,
  }),
  timestamp: css({
    fontSize: theme.typography.bodySmall.fontSize,
    color: theme.colors.text.disabled,
    textAlign: 'right',
    paddingTop: theme.spacing(0.5),
  }),
  noData: css({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: theme.colors.text.disabled,
    fontSize: theme.typography.body.fontSize,
  }),
});

// ─── サブコンポーネント: ステータスカード ─────────────────────────────────────

interface StatusCardProps {
  status: SubsystemStatus;
  styles: ReturnType<typeof getStyles>;
  theme: GrafanaTheme2;
}

function StatusCard({ status, styles, theme }: StatusCardProps) {
  const levelColors: Record<StatusLevel, string> = {
    ok: theme.colors.success.main,
    warning: theme.colors.warning.main,
    critical: theme.colors.error.main,
    unknown: theme.colors.text.disabled,
  };

  const color = levelColors[status.level];
  const displayValue = status.value != null ? status.value.toFixed(1) : '—';

  return (
    <div className={styles.card}>
      <span className={styles.subsystemName}>{status.name}</span>
      <div className={styles.valueRow}>
        <span className={styles.value} style={{ color }}>
          {displayValue}
        </span>
        {status.unit && <span className={styles.unit}>{status.unit}</span>}
      </div>
      <span
        className={styles.statusBadge}
        style={{ backgroundColor: color }}
        data-testid={`status-badge-${status.name}`}
      >
        {STATUS_LABEL[status.level]}
      </span>
    </div>
  );
}

// ─── メインパネルコンポーネント ───────────────────────────────────────────────

export function SatelliteStatusPanel({
  data,
  options,
  width,
  height,
}: PanelProps<PanelOptions>) {
  const theme = useTheme2();
  const styles = useStyles2(getStyles);

  const statuses: SubsystemStatus[] = useMemo(() => {
    return data.series.map((frame) => {
      const value = getLatestValue(frame);
      return {
        name: frame.name || frame.refId || 'Unknown',
        value,
        unit: getFieldUnit(frame, options.unitSuffix),
        level: computeLevel(value, options.warningThreshold, options.criticalThreshold),
      };
    });
  }, [data.series, options.warningThreshold, options.criticalThreshold, options.unitSuffix]);

  if (statuses.length === 0) {
    return (
      <div className={styles.noData} style={{ width, height }}>
        クエリを追加してサブシステムデータを表示します
      </div>
    );
  }

  const now = new Date().toLocaleTimeString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div className={styles.wrapper} style={{ width, height }}>
      <div className={styles.grid}>
        {statuses.map((s) => (
          <StatusCard key={s.name} status={s} styles={styles} theme={theme} />
        ))}
      </div>
      {options.showTimestamp && (
        <div className={styles.timestamp}>最終更新: {now}</div>
      )}
    </div>
  );
}
