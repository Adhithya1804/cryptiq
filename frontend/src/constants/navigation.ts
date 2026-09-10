/**
 * Navigation model — the sidebar primary items and the Settings sub-sections.
 * Order and labels match the design source.
 */

export interface NavItem {
  readonly id: string;
  readonly label: string;
  readonly path: string;
  /** Other route prefixes that should light this item as active. */
  readonly matches?: readonly string[];
}

export const PRIMARY_NAV: readonly NavItem[] = [
  { id: 'inspect', label: 'Inspect', path: '/inspect' },
  { id: 'projects', label: 'Projects', path: '/projects' },
  { id: 'history', label: 'History', path: '/history', matches: ['/history', '/inspections'] },
  { id: 'review', label: 'Review', path: '/review' },
];

export const SETTINGS_NAV_ITEM: NavItem = {
  id: 'settings',
  label: 'Settings',
  path: '/settings',
};

export type SidebarMode = 'expanded' | 'collapsed' | 'auto';

export const SIDEBAR_MODE_STORAGE_KEY = 'cryptiq.sidebarMode';

export interface SettingsSection {
  readonly id: string;
  readonly label: string;
  readonly danger?: boolean;
}

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'crypto', label: 'Cryptographic Policy' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'danger', label: 'Danger Zone', danger: true },
];

export const DEFAULT_SETTINGS_SECTION = 'workspace';
