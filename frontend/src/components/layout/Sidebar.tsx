import { useState, type KeyboardEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  PRIMARY_NAV,
  SETTINGS_NAV_ITEM,
  type SidebarMode,
} from '@/constants/navigation';
import { CryptiqMark } from './CryptiqMark';
import styles from './Sidebar.module.css';

export interface SidebarProps {
  mode: SidebarMode;
  onModeChange: (mode: SidebarMode) => void;
  /** id of the primary nav item (or 'settings') that should read as active. */
  activeId: string;
  isMobile: boolean;
  drawerOpen: boolean;
  onDrawerClose: () => void;
}

function nextMode(mode: SidebarMode): SidebarMode {
  return mode === 'collapsed' ? 'expanded' : 'collapsed';
}

export function Sidebar({
  mode,
  onModeChange,
  activeId,
  isMobile,
  drawerOpen,
  onDrawerClose,
}: SidebarProps) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  const [focusWithin, setFocusWithin] = useState(false);

  const isOverlay = !isMobile && (mode === 'auto' || mode === 'collapsed');
  const revealed = isMobile
    ? true
    : mode === 'expanded' || ((mode === 'auto' || mode === 'collapsed') && (hovered || focusWithin));
  const showLabels = revealed;

  const navTo = (path: string) => {
    navigate(path);
    if (isMobile) onDrawerClose();
  };

  const onListKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && isMobile) onDrawerClose();
  };

  const className = [
    styles.sidebar,
    isMobile ? `${styles.drawer} ${drawerOpen ? styles.drawerOpen : ''}` : '',
    !isMobile && isOverlay ? styles.overlay : styles.inFlow,
    !isMobile && revealed ? styles.expanded : '',
    !isMobile && isOverlay && revealed ? styles.revealed : '',
    showLabels ? '' : styles.collapsed,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <>
      {!isMobile && mode === 'auto' && (
        <div className={styles.autoStrip} onMouseEnter={() => setHovered(true)} aria-hidden />
      )}
      {!isMobile && mode === 'collapsed' && <div className={styles.spacer} aria-hidden />}
      {isMobile && drawerOpen && (
        <button type="button" className={styles.scrim} aria-label="Close navigation" onClick={onDrawerClose} />
      )}

      <aside
        className={className}
        aria-label="Primary"
        aria-hidden={isMobile && !drawerOpen}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setFocusWithin(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setFocusWithin(false);
        }}
        onKeyDown={onListKeyDown}
      >
        <div className={styles.header}>
          <Link to="/inspect" aria-label="Cryptiq home" onClick={() => isMobile && onDrawerClose()}>
            <CryptiqMark />
          </Link>
          {showLabels && <div className={styles.wordmark}>CRYPTIQ</div>}
        </div>

        <nav className={styles.nav} aria-label="Sections">
          {PRIMARY_NAV.map((item) => {
            const active = item.id === activeId;
            return (
              <button
                key={item.id}
                type="button"
                className={styles.navItem}
                aria-current={active ? 'page' : undefined}
                title={showLabels ? undefined : item.label}
                onClick={() => navTo(item.path)}
              >
                <span className={styles.navDot} aria-hidden />
                {showLabels ? <span className={styles.navLabel}>{item.label}</span> : (
                  <span className="sr-only">{item.label}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div className={styles.grow} />

        <hr className={styles.rule} />

        <button
          type="button"
          className={styles.navItem}
          aria-current={activeId === 'settings' ? 'page' : undefined}
          title={showLabels ? undefined : SETTINGS_NAV_ITEM.label}
          onClick={() => navTo(SETTINGS_NAV_ITEM.path)}
        >
          <span className={styles.navDot} aria-hidden />
          {showLabels ? (
            <span className={styles.navLabel}>{SETTINGS_NAV_ITEM.label}</span>
          ) : (
            <span className="sr-only">{SETTINGS_NAV_ITEM.label}</span>
          )}
        </button>

        {!isMobile && (
          <button
            type="button"
            className={styles.collapseToggle}
            onClick={() => onModeChange(nextMode(mode))}
            aria-pressed={mode === 'collapsed'}
            title="Toggle sidebar"
          >
            <span className={styles.collapseGlyph} aria-hidden>
              {mode === 'collapsed' ? '»' : '«'}
            </span>
            {showLabels && <span>Collapse</span>}
          </button>
        )}

        {showLabels && (
          <p className={styles.footnote}>
            Static analysis only.
            <br />
            Repository code is never executed.
          </p>
        )}
      </aside>
    </>
  );
}
