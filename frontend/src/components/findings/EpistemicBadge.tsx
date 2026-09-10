import styles from './EpistemicBadge.module.css';

/**
 * The "Observed" / "Inferred" labels that head the two evidence panels. This
 * distinction is load-bearing (contract §"Why the grouping is part of the
 * contract"): Observed = checkable facts from the source, Inferred = Cryptiq's
 * judgement. The badges look deliberately different so they can't be confused.
 */
export function EpistemicBadge({ kind }: { kind: 'observed' | 'inferred' }) {
  const label = kind === 'observed' ? 'Observed' : 'Inferred';
  return (
    <span className={`${styles.badge} ${styles[kind]}`}>
      <span className={styles.dot} aria-hidden />
      {label}
    </span>
  );
}
