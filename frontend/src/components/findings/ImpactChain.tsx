import { Fragment } from 'react';
import styles from './ImpactChain.module.css';

/** Bounded static-scope impact, shown as a left-to-right chain of call sites. */
export function ImpactChain({ chain }: { chain: readonly string[] }) {
  if (chain.length === 0) {
    return <p className={styles.empty}>No downstream usage was observed within the scanned scope.</p>;
  }
  return (
    <div className={styles.chain}>
      {chain.map((node, index) => (
        <Fragment key={`${node}-${index}`}>
          {index > 0 && (
            <span className={styles.connector} aria-hidden>
              →
            </span>
          )}
          <span className={styles.node}>{node}</span>
        </Fragment>
      ))}
    </div>
  );
}
