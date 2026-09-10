import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useLocalStorageState } from '@/hooks/useLocalStorageState';
import { SIDEBAR_MODE_STORAGE_KEY, type SidebarMode } from '@/constants/navigation';

export type MotionPreference = 'full' | 'reduced';
export type DensityPreference = 'comfortable' | 'compact';

interface PreferencesValue {
  sidebarMode: SidebarMode;
  setSidebarMode: (mode: SidebarMode) => void;
  motion: MotionPreference;
  setMotion: (motion: MotionPreference) => void;
  density: DensityPreference;
  setDensity: (density: DensityPreference) => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

const SIDEBAR_MODES: readonly SidebarMode[] = ['expanded', 'collapsed', 'auto'];
const MOTIONS: readonly MotionPreference[] = ['full', 'reduced'];
const DENSITIES: readonly DensityPreference[] = ['comfortable', 'compact'];

const oneOf = <T extends string>(list: readonly T[]) => (raw: string): T | null =>
  (list as readonly string[]).includes(raw) ? (raw as T) : null;

/**
 * App-wide UI preferences (sidebar behaviour, motion, table density). Persisted
 * per-browser via localStorage so UI preferences and the layout stay in
 * sync. These are conveniences, not data — a blank store just yields defaults.
 */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [sidebarMode, setSidebarMode] = useLocalStorageState<SidebarMode>(
    SIDEBAR_MODE_STORAGE_KEY,
    'expanded',
    oneOf(SIDEBAR_MODES),
  );
  const [motion, setMotion] = useLocalStorageState<MotionPreference>(
    'cryptiq.motion',
    'full',
    oneOf(MOTIONS),
  );
  const [density, setDensity] = useLocalStorageState<DensityPreference>(
    'cryptiq.density',
    'comfortable',
    oneOf(DENSITIES),
  );

  useEffect(() => {
    document.documentElement.dataset.motion = motion;
    return () => {
      delete document.documentElement.dataset.motion;
    };
  }, [motion]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
    return () => {
      delete document.documentElement.dataset.density;
    };
  }, [density]);

  const value = useMemo<PreferencesValue>(
    () => ({ sidebarMode, setSidebarMode, motion, setMotion, density, setDensity }),
    [sidebarMode, setSidebarMode, motion, setMotion, density, setDensity],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  const context = useContext(PreferencesContext);
  if (!context) throw new Error('usePreferences must be used within a PreferencesProvider');
  return context;
}
