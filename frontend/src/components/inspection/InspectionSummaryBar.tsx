import { Fragment, type ReactNode } from 'react';
import type { Inspection } from '@/types/domain';
import { SeverityLegend } from './Severity';
import { formatCount, formatDateTime, formatDuration } from '@/utils/format';
import styles from './InspectionSummaryBar.module.css';

interface Metric {
  label: string;
  value: ReactNode;
}

export function InspectionSummaryBar({ inspection }: { inspection: Inspection }) {
  const metrics: Metric[] = [
    { label: 'Inspected', value: formatDateTime(inspection.completedAt ?? inspection.startedAt) },
    { label: 'Duration', value: formatDuration(inspection.durationMs) },
    { label: 'Files analyzed', value: formatCount(inspection.filesAnalyzed) },
    { label: 'Findings', value: formatCount(inspection.findingsCount) },
    { label: 'Severity breakdown', value: <SeverityLegend severity={inspection.severity} /> },
  ];

  return (
    <div className={styles.bar}>
      {metrics.map((metric, index) => (
        <Fragment key={metric.label}>
          {index > 0 && <span className={styles.divider} aria-hidden />}
          <div className={styles.metric}>
            <div className={styles.label}>{metric.label}</div>
            <div className={styles.value}>{metric.value}</div>
          </div>
        </Fragment>
      ))}
    </div>
  );
}
