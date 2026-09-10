import { useEffect, useState } from 'react';
import { Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { usePreferences } from '@/app/providers/PreferencesProvider';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { Sidebar } from './Sidebar';
import { BreadcrumbBar, BreadcrumbProvider } from './Breadcrumbs';
import styles from './AppLayout.module.css';

function activeNavId(pathname: string, from: string | null): string {
  if (pathname.startsWith('/inspect')) return 'inspect';
  if (pathname.startsWith('/projects')) return 'projects';
  if (pathname.startsWith('/history') || pathname.startsWith('/inspections')) return 'history';
  if (pathname.startsWith('/review')) return 'review';
  if (pathname.startsWith('/settings')) return 'settings';
  if (pathname.startsWith('/findings')) return from === 'review' ? 'review' : 'history';
  return 'inspect';
}

export function AppLayout() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isMobile = useMediaQuery('(max-width: 767px)');

  const { sidebarMode, setSidebarMode } = usePreferences();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  // Send focus to the main region on navigation so keyboard users don't have to
  // traverse the sidebar on every page change.
  useEffect(() => {
    document.getElementById('main-content')?.focus({ preventScroll: true });
  }, [location.pathname]);

  const activeId = activeNavId(location.pathname, searchParams.get('from'));

  return (
    <BreadcrumbProvider>
      <div className={styles.shell}>
        <a href="#main-content" className={styles.skipLink}>
          Skip to content
        </a>
        <Sidebar
          mode={sidebarMode}
          onModeChange={setSidebarMode}
          activeId={activeId}
          isMobile={isMobile}
          drawerOpen={drawerOpen}
          onDrawerClose={() => setDrawerOpen(false)}
        />
        <main id="main-content" className={styles.main} tabIndex={-1}>
          <BreadcrumbBar
            leading={
              isMobile ? (
                <button
                  type="button"
                  className={styles.menuButton}
                  aria-label="Open navigation"
                  aria-expanded={drawerOpen}
                  onClick={() => setDrawerOpen(true)}
                >
                  ☰
                </button>
              ) : null
            }
          />
          <ErrorBoundary section="This screen" resetKey={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </BreadcrumbProvider>
  );
}
