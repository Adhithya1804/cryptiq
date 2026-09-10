import type { ObservedEvidence } from '@/types/domain';
import { shortCommit } from '@/utils/format';
import styles from './SourceEvidence.module.css';

/**
 * Quoted source lines for a finding. Rendered strictly as text — repository
 * content is untrusted and never interpreted as markup (master prompt §18).
 */
export function SourceEvidence({ observed }: { observed: ObservedEvidence }) {
  return (
    <figure className={styles.panel}>
      <figcaption className={styles.header}>
        <span className={styles.file}>{observed.filePath}</span>
        <span className={styles.meta}>
          {observed.language} · {shortCommit(observed.commitSha)}
        </span>
      </figcaption>
      <pre className={styles.body} tabIndex={0} aria-label={`Source excerpt from ${observed.filePath}`}>
        {observed.source.map((line) => (
          <div
            key={line.number}
            className={`${styles.line} ${line.highlighted ? styles.highlighted : ''}`}
          >
            <span className={styles.gutter}>{line.number}</span>
            <span className={styles.code}>{line.text.length > 0 ? line.text : ' '}</span>
          </div>
        ))}
      </pre>
    </figure>
  );
}
