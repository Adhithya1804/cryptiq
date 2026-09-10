import type { Finding } from '@/types/domain';
import { getRoleLabel } from '@/constants/domain';
import styles from './ReviewPathCard.module.css';

/**
 * Migration review guidance. `path` names material to consult — it is never a
 * "replace X with Y" instruction, and the copy must not read like one.
 */
export function ReviewPathCard({ finding }: { finding: Finding }) {
  const { migration, inferred } = finding;
  return (
    <div className={styles.card}>
      <div className={styles.kicker}>{getRoleLabel(inferred.role)} · Review path</div>
      <div className={styles.row}>
        <div>
          <div className={styles.smallLabel}>Current</div>
          <span className={styles.currentChip}>{migration.current}</span>
        </div>
        <span className={styles.arrow} aria-hidden>
          →
        </span>
        <div className={styles.pathCol}>
          <div className={styles.smallLabel}>Review path</div>
          <div className={styles.chips}>
            {migration.path.length > 0 ? (
              migration.path.map((step) => (
                <span key={step} className={styles.pathChip}>
                  {step}
                </span>
              ))
            ) : (
              <span className={styles.pathChip}>MANUAL REVIEW</span>
            )}
          </div>
        </div>
      </div>
      {migration.summary && <p className={styles.summary}>{migration.summary}</p>}
    </div>
  );
}
