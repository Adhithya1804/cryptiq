import type { SeverityBreakdown } from '@/types/domain';
import styles from './Severity.module.css';

const ORDER: { key: keyof SeverityBreakdown; short: string; long: string; color: string }[] = [
  { key: 'critical', short: 'C', long: 'Critical', color: 'var(--text-3)' },
  { key: 'high', short: 'H', long: 'High', color: 'var(--red)' },
  { key: 'medium', short: 'M', long: 'Medium', color: 'var(--amber)' },
  { key: 'low', short: 'L', long: 'Low', color: 'var(--green)' },
];

/** Compact "3C 1H 4M 2L" cluster for dense table rows. */
export function SeverityCluster({ severity }: { severity: SeverityBreakdown }) {
  return (
    <span className={styles.cluster}>
      {ORDER.map(({ key, short, long, color }) => (
        <span key={key} className={styles.chip} style={{ color }} title={`${severity[key]} ${long}`}>
          {severity[key]}
          {short}
        </span>
      ))}
    </span>
  );
}

/** Spaced "3 Critical · 1 High · …" legend for the report summary bar. */
export function SeverityLegend({ severity }: { severity: SeverityBreakdown }) {
  return (
    <span className={styles.legend}>
      {ORDER.map(({ key, long, color }) => (
        <span key={key} className={styles.legendItem} style={{ color }}>
          {severity[key]} {long}
        </span>
      ))}
    </span>
  );
}
