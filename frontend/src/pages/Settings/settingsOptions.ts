/**
 * Static option lists and default local state for the Settings screen. These are
 * workspace *configuration* defaults (not backend records) — the design ships
 * them as component state and this app does the same.
 */

export const ENVIRONMENT_OPTIONS = [
  { value: 'production', label: 'Production' },
  { value: 'staging', label: 'Staging' },
] as const;

export const SCOPE_OPTIONS = [
  { value: 'full', label: 'Full repository' },
  { value: 'changed', label: 'Changed files only' },
] as const;

export const COMMIT_OPTIONS = [
  { value: 'exact', label: 'Exact commit' },
  { value: 'head', label: 'Default branch HEAD' },
] as const;

export const POSTURE_OPTIONS = [
  { value: 'informational', label: 'Informational' },
  { value: 'review', label: 'Review required' },
  { value: 'strict', label: 'Strict' },
] as const;

export const ANALYSIS_TOGGLES = [
  'Include generated code',
  'Include test code',
  'Dependency analysis',
  'Secret detection',
] as const;

export const FLAGGED_ALGORITHMS = ['RSA', 'ECDSA', 'X25519', 'SHA-1', 'Legacy primitives'] as const;

export const NOTIFICATION_EVENTS = [
  'New high-priority finding',
  'Finding assigned to me',
  'Review status changed',
  'Inspection completed',
  'Inspection failed',
] as const;

export type NotificationChannel = 'app' | 'email' | 'slack';

export const COMING_SOON_INTEGRATIONS = ['GitLab', 'Bitbucket', 'Slack', 'Jira'] as const;

export interface SettingsFormState {
  organizationName: string;
  environment: string;
  scope: string;
  commitHandling: string;
  analysisFlags: Record<string, boolean>;
  posture: string;
  flaggedAlgorithms: Record<string, boolean>;
  notifications: Record<string, Record<NotificationChannel, boolean>>;
}

export function createDefaultSettings(): SettingsFormState {
  return {
    organizationName: 'Cryptiq Security',
    environment: 'production',
    scope: 'full',
    commitHandling: 'exact',
    analysisFlags: {
      'Include generated code': false,
      'Include test code': true,
      'Dependency analysis': true,
      'Secret detection': true,
    },
    posture: 'review',
    flaggedAlgorithms: {
      RSA: true,
      ECDSA: true,
      X25519: true,
      'SHA-1': true,
      'Legacy primitives': true,
    },
    notifications: {
      'New high-priority finding': { app: true, email: true, slack: true },
      'Finding assigned to me': { app: true, email: true, slack: false },
      'Review status changed': { app: true, email: false, slack: false },
      'Inspection completed': { app: true, email: false, slack: false },
      'Inspection failed': { app: true, email: true, slack: true },
    },
  };
}
