import type { Finding } from '@/types/domain';
import { getPriorityMeta, getRoleLabel } from '@/constants/domain';
import styles from './FindingHeader.module.css';

export function FindingHeader({ finding }: { finding: Finding }) {
  const priority = getPriorityMeta(finding.priority);
  return (
    <header className={styles.header}>
      <div className={styles.identity}>
        <div className={styles.titleRow}>
          <h1 className={styles.algorithm}>{finding.observed.algorithm}</h1>
          <span className={styles.role}>{getRoleLabel(finding.inferred.role)}</span>
        </div>
        {finding.inferred.reasons.length > 0 && (
          <ul className={styles.reasons}>
            {finding.inferred.reasons.map((reason, index) => (
              <li key={`${reason}-${index}`} className={styles.reason}>
                <span className={styles.reasonMark} aria-hidden />
                {reason}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div
        className={styles.priorityBox}
        style={{ borderColor: `color-mix(in srgb, ${priority.color} 35%, var(--border-strong))` }}
      >
        <div className={styles.priorityLabel}>Migration review priority</div>
        <div className={styles.priorityValue}>
          <span className={styles.priorityDot} style={{ background: priority.color }} aria-hidden />
          <span style={{ color: priority.color }}>{priority.label}</span>
        </div>
      </div>
    </header>
  );
}
