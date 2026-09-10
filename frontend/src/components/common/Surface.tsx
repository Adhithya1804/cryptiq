import type { CSSProperties, ReactNode } from 'react';
import styles from './Surface.module.css';

export function Panel({
  children,
  padded = true,
  inset = false,
  className,
  style,
}: {
  children: ReactNode;
  padded?: boolean;
  inset?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={[styles.panel, padded ? styles.padded : '', inset ? styles.inset : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
      style={style}
    >
      {children}
    </div>
  );
}

export interface Definition {
  term: string;
  value: ReactNode;
  /** Rendered plain (sans) instead of mono. */
  plain?: boolean;
  title?: string;
}

export function DefinitionList({ items }: { items: readonly Definition[] }) {
  return (
    <dl className={styles.defList}>
      {items.map((item) => (
        <div key={item.term} className={styles.defRow}>
          <dt>{item.term}</dt>
          <dd
            title={item.title}
            style={item.plain ? { fontFamily: 'var(--sans)' } : undefined}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
