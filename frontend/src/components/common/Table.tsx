import type { CSSProperties, ReactNode } from 'react';
import styles from './Table.module.css';

export type SortDirection = 'asc' | 'desc';
export interface SortState<K extends string> {
  key: K;
  direction: SortDirection;
}

/**
 * CSS-grid table primitives. The design renders every table as a grid inside a
 * horizontally-scrollable frame with a `min-width`; these components make that
 * pattern reusable without inventing a heavyweight generic table.
 */

export function TableScroll({ minWidth, children }: { minWidth: number; children: ReactNode }) {
  return (
    <div className={styles.scroll}>
      <div className={styles.frame} style={{ minWidth }}>
        {children}
      </div>
    </div>
  );
}

interface RowProps {
  template: string;
  children: ReactNode;
}

export function HeaderRow({ template, children }: RowProps) {
  return (
    <div className={`${styles.row} ${styles.headerRow}`} style={{ gridTemplateColumns: template }}>
      {children}
    </div>
  );
}

export function Row({ template, children }: RowProps) {
  return (
    <div className={styles.row} style={{ gridTemplateColumns: template }}>
      {children}
    </div>
  );
}

export function ClickableRow({
  template,
  onClick,
  ariaLabel,
  children,
}: RowProps & { onClick: () => void; ariaLabel: string }) {
  return (
    <button
      type="button"
      className={styles.rowButton}
      style={{ display: 'grid', gridTemplateColumns: template }}
      onClick={onClick}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  );
}

export function HeaderCell({ children }: { children: ReactNode }) {
  return <div className={styles.headerCell}>{children}</div>;
}

export function SortableHeaderCell<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: K;
  sort: SortState<K>;
  onSort: (key: K) => void;
}) {
  const active = sort.key === sortKey;
  const arrow = active ? (sort.direction === 'desc' ? '▼' : '▲') : '';
  const nextDirectionLabel = active && sort.direction === 'desc' ? 'ascending' : 'descending';
  return (
    <div className={styles.headerCell}>
      <button
        type="button"
        className={styles.sortButton}
        onClick={() => onSort(sortKey)}
        aria-label={`Sort by ${label}, ${active ? `currently ${sort.direction}ending` : nextDirectionLabel}`}
      >
        {label}
        <span className={styles.sortArrow} aria-hidden>
          {arrow}
        </span>
      </button>
    </div>
  );
}

export interface CellProps {
  children: ReactNode;
  mono?: boolean;
  strong?: boolean;
  compact?: boolean;
  truncate?: boolean;
  stack?: boolean;
  title?: string;
  style?: CSSProperties;
}

export function Cell({ children, mono, strong, compact, truncate, stack, title, style }: CellProps) {
  const className = [
    styles.cell,
    mono ? styles.mono : '',
    strong ? styles.strong : '',
    compact ? styles.compact : '',
    stack ? styles.stack : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={className} title={title} style={style}>
      {truncate ? <span className={styles.truncate}>{children}</span> : children}
    </div>
  );
}
