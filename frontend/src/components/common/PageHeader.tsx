import type { ReactNode } from 'react';
import styles from './PageHeader.module.css';

export interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  kicker?: string;
  /** Right-aligned slot (badge, primary action). */
  aside?: ReactNode;
  /** Heading level for the document outline. Defaults to 1. */
  as?: 'h1' | 'h2';
}

export function PageHeader({ title, description, kicker, aside, as: Heading = 'h1' }: PageHeaderProps) {
  return (
    <div className={styles.header}>
      <div>
        {kicker && <div className={styles.kicker}>{kicker}</div>}
        <Heading className={styles.title}>{title}</Heading>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {aside && <div className={styles.aside}>{aside}</div>}
    </div>
  );
}
