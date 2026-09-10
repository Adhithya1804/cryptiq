import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { Link } from 'react-router-dom';
import styles from './Breadcrumbs.module.css';

export interface Crumb {
  label: string;
  /** Omitted for the trailing (current) crumb. */
  to?: string;
}

interface BreadcrumbContextValue {
  crumbs: readonly Crumb[];
  setCrumbs: (crumbs: readonly Crumb[]) => void;
}

const BreadcrumbContext = createContext<BreadcrumbContextValue | null>(null);

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<readonly Crumb[]>([]);
  const value = useMemo(() => ({ crumbs, setCrumbs }), [crumbs]);
  return <BreadcrumbContext.Provider value={value}>{children}</BreadcrumbContext.Provider>;
}

function useBreadcrumbContext(): BreadcrumbContextValue {
  const context = useContext(BreadcrumbContext);
  if (!context) throw new Error('Breadcrumb hooks must be used within a BreadcrumbProvider');
  return context;
}

/**
 * Declare the breadcrumb trail for the current screen. Pass a stable `deps`
 * array (the dynamic parts of the trail) — the crumbs are re-published only when
 * it changes.
 */
export function useBreadcrumbs(build: () => readonly Crumb[], deps: readonly unknown[]): void {
  const { setCrumbs } = useBreadcrumbContext();
  useEffect(() => {
    setCrumbs(build());
    return () => setCrumbs([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setCrumbs, ...deps]);
}

export function BreadcrumbBar({ leading }: { leading?: ReactNode }) {
  const { crumbs } = useBreadcrumbContext();
  return (
    <nav className={styles.bar} aria-label="Breadcrumb">
      {leading}
      <ol className={styles.list}>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li key={`${crumb.label}-${index}`} className={styles.item}>
              {index > 0 && (
                <span className={styles.separator} aria-hidden>
                  /
                </span>
              )}
              {crumb.to && !isLast ? (
                <Link to={crumb.to} className={styles.link}>
                  {crumb.label}
                </Link>
              ) : (
                <span className={styles.current} aria-current={isLast ? 'page' : undefined}>
                  {crumb.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
