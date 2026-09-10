import type { ReactNode } from 'react';
import styles from './Page.module.css';

/** Consistent screen padding wrapper. `narrow` matches the Inspect form column;
 *  the default matches every other screen in the design (36px 48px). */
export function Page({
  children,
  narrow = false,
  className,
}: {
  children: ReactNode;
  narrow?: boolean;
  className?: string;
}) {
  return (
    <div className={[styles.page, narrow ? styles.narrow : '', className ?? ''].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}
