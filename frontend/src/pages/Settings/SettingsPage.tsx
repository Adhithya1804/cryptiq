import { useState, type ReactNode } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { Toggle } from '@/components/common/Toggle';
import { CheckBox } from '@/components/common/CheckBox';
import { Button } from '@/components/common/Button';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useToast } from '@/app/providers/ToastProvider';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { isBackendConfigured } from '@/services';
import {
  DEFAULT_SETTINGS_SECTION,
  SETTINGS_SECTIONS,
} from '@/constants/navigation';
import {
  ANALYSIS_TOGGLES,
  COMING_SOON_INTEGRATIONS,
  COMMIT_OPTIONS,
  ENVIRONMENT_OPTIONS,
  FLAGGED_ALGORITHMS,
  NOTIFICATION_EVENTS,
  POSTURE_OPTIONS,
  SCOPE_OPTIONS,
  createDefaultSettings,
  type NotificationChannel,
  type SettingsFormState,
} from './settingsOptions';
import styles from './SettingsPage.module.css';

const NO_SAVE_SECTIONS = new Set(['integrations', 'danger']);
const VALID_SECTIONS = new Set(SETTINGS_SECTIONS.map((section) => section.id));

export function SettingsPage() {
  const { section = DEFAULT_SETTINGS_SECTION } = useParams();
  const navigate = useNavigate();
  const { notify } = useToast();

  useDocumentTitle('Settings');
  useBreadcrumbs(() => [{ label: 'Settings' }], []);

  const [form, setForm] = useState<SettingsFormState>(createDefaultSettings);

  const update = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  if (!VALID_SECTIONS.has(section)) {
    return <Navigate to={`/settings/${DEFAULT_SETTINGS_SECTION}`} replace />;
  }

  const showSave = !NO_SAVE_SECTIONS.has(section);

  return (
    <>
      <div className={styles.header}>
        <h1 className={styles.title}>Settings</h1>
        <p className={styles.description}>
          Workspace-wide configuration and policy. Repository-specific settings live on each repository.
        </p>
      </div>

      <div className={styles.layout}>
        <nav className={styles.nav} aria-label="Settings sections">
          {SETTINGS_SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`${styles.navItem} ${item.danger ? styles.danger : ''}`}
              aria-current={item.id === section ? 'page' : undefined}
              onClick={() => navigate(`/settings/${item.id}`)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <section className={styles.content} aria-live="polite">
          {section === 'workspace' && <WorkspaceSection form={form} update={update} />}
          {section === 'analysis' && <AnalysisSection form={form} update={update} />}
          {section === 'crypto' && <CryptoSection form={form} update={update} />}
          {section === 'integrations' && <IntegrationsSection onAction={notify} />}
          {section === 'notifications' && <NotificationsSection form={form} update={update} />}
          {section === 'danger' && <DangerSection onAction={notify} />}

          {showSave && (
            <div className={styles.saveBar}>
              <Button size="sm" onClick={() => notify('Settings saved')}>
                Save Changes
              </Button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- helpers --- */

type Updater = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className={styles.row}>
      <div>
        <div className={styles.rowLabel}>{label}</div>
        {hint && <div className={styles.rowHint}>{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function ReadOnlyValue({ children, mono = false }: { children: ReactNode; mono?: boolean }) {
  return <div className={mono ? styles.rowValueMono : styles.rowValue}>{children}</div>;
}

/* --------------------------------------------------------------- sections --- */

function WorkspaceSection({ form, update }: { form: SettingsFormState; update: Updater }) {
  return (
    <>
      <h2 className={styles.sectionTitle}>Workspace</h2>
      <div className={styles.rows}>
        <Row label="Organization name">
          <input
            className={styles.textInput}
            value={form.organizationName}
            aria-label="Organization name"
            onChange={(event) => update('organizationName', event.target.value)}
          />
        </Row>
        <Row label="Workspace ID">
          <ReadOnlyValue mono>{isBackendConfigured() ? '—' : 'Not provisioned'}</ReadOnlyValue>
        </Row>
        <Row label="Environment">
          <SegmentedControl
            legend="Environment"
            options={ENVIRONMENT_OPTIONS}
            value={form.environment}
            onChange={(value) => update('environment', value)}
          />
        </Row>
        <Row label="Default branch">
          <ReadOnlyValue mono>main</ReadOnlyValue>
        </Row>
        <Row label="Timezone">
          <ReadOnlyValue>UTC</ReadOnlyValue>
        </Row>
        <Row label="Data retention">
          <ReadOnlyValue>12 months</ReadOnlyValue>
        </Row>
      </div>
    </>
  );
}

function AnalysisSection({ form, update }: { form: SettingsFormState; update: Updater }) {
  return (
    <>
      <h2 className={styles.sectionTitle}>Analysis</h2>
      <div className={styles.rows}>
        <Row label="Analysis mode">
          <ReadOnlyValue mono>Static analysis</ReadOnlyValue>
        </Row>
        <Row label="Supported languages">
          <ReadOnlyValue mono>Python</ReadOnlyValue>
        </Row>
        <Row label="Repository scope">
          <SegmentedControl
            legend="Repository scope"
            options={SCOPE_OPTIONS}
            value={form.scope}
            onChange={(value) => update('scope', value)}
          />
        </Row>
        <Row label="Commit handling">
          <SegmentedControl
            legend="Commit handling"
            options={COMMIT_OPTIONS}
            value={form.commitHandling}
            onChange={(value) => update('commitHandling', value)}
          />
        </Row>
        <Row label="Excluded paths">
          <ReadOnlyValue mono>vendor/, node_modules/, tests/fixtures/</ReadOnlyValue>
        </Row>
        {ANALYSIS_TOGGLES.map((label) => (
          <Row key={label} label={label}>
            <Toggle
              label={label}
              checked={form.analysisFlags[label] ?? false}
              onChange={(checked) =>
                update('analysisFlags', { ...form.analysisFlags, [label]: checked })
              }
            />
          </Row>
        ))}
      </div>
    </>
  );
}

function CryptoSection({ form, update }: { form: SettingsFormState; update: Updater }) {
  return (
    <>
      <h2 className={styles.sectionTitle}>Cryptographic Policy</h2>
      <p className={styles.sectionIntro}>
        Configures detection, prioritization, and recommended review paths. Cryptiq does not modify or
        replace algorithms automatically.
      </p>
      <div className={styles.rows}>
        <Row label="Target standard">
          <ReadOnlyValue mono>NIST Post-Quantum Cryptography</ReadOnlyValue>
        </Row>
        <Row label="Migration posture">
          <SegmentedControl
            legend="Migration posture"
            options={POSTURE_OPTIONS}
            value={form.posture}
            onChange={(value) => update('posture', value)}
          />
        </Row>
        <div>
          <div className={styles.rowLabel} style={{ marginBottom: 10 }}>
            Algorithms to flag
          </div>
          <div className={styles.stackList}>
            {FLAGGED_ALGORITHMS.map((label) => (
              <div key={label} className={styles.row}>
                <div className={styles.rowValueMono}>{label}</div>
                <Toggle
                  label={`Flag ${label}`}
                  checked={form.flaggedAlgorithms[label] ?? false}
                  onChange={(checked) =>
                    update('flaggedAlgorithms', { ...form.flaggedAlgorithms, [label]: checked })
                  }
                />
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className={styles.rowLabel} style={{ marginBottom: 10 }}>
            Preferred review paths
          </div>
          <div className={styles.stackList}>
            <div className={styles.rowValueMono}>
              Digital signatures <span style={{ color: 'var(--text-3)' }}>→</span>{' '}
              <span style={{ color: 'var(--text-1)' }}>ML-DSA / SLH-DSA</span>
            </div>
            <div className={styles.rowValueMono}>
              Key establishment <span style={{ color: 'var(--text-3)' }}>→</span>{' '}
              <span style={{ color: 'var(--text-1)' }}>ML-KEM / Hybrid migration</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function IntegrationsSection({ onAction }: { onAction: (message: string) => void }) {
  const connected = isBackendConfigured();
  const [showCliInstructions, setShowCliInstructions] = useState(false);

  const handleCopy = (text: string, message: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(() => {
        // clipboard access can be denied in unsupported environments
      });
    }
    onAction(message);
  };

  const handleInstallCli = () => {
    setShowCliInstructions((prev) => !prev);
    handleCopy('pip install -e ".[dev]"', 'Copied CLI install command: pip install -e ".[dev]"');
  };

  return (
    <>
      <h2 className={styles.sectionTitle}>Integrations</h2>
      <div className={styles.card}>
        <div className={styles.cardHead}>
          <div className={styles.cardTitle}>GitHub</div>
          <span className={connected ? styles.badgePositive : styles.badgeNeutral}>
            {connected ? 'Connected' : 'Not connected'}
          </span>
        </div>
        <div className={styles.cardRows}>
          <div className={styles.cardRow}>
            <span>Repository access</span>
            <span>Read-only</span>
          </div>
          <div className={styles.cardRow}>
            <span>Webhook status</span>
            <span>{connected ? 'Active' : 'Inactive'}</span>
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => onAction('GitHub connection is managed by your workspace administrator.')}
          >
            Manage connection
          </Button>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHead}>
          <div className={styles.cardTitle}>CI/CD</div>
          <Button size="xs" variant="secondary" onClick={handleInstallCli}>
            Install CLI
          </Button>
        </div>
        <p className={styles.cardDescription}>
          Install the CRYPTIQ CLI to run cryptographic analysis locally or integrate it into CI workflows.
        </p>
        <div className={styles.cardRows}>
          <div className={styles.cardRow}>
            <span>Execution mode</span>
            <span>Local (offline) or Remote API</span>
          </div>
          <div className={styles.cardRow}>
            <span>Package location</span>
            <span className={styles.rowValueMono}>cryptiq/</span>
          </div>
          <div className={styles.cardRow}>
            <span>Install command</span>
            <span className={styles.rowValueMono}>pip install -e &quot;.[dev]&quot;</span>
          </div>
        </div>
        {showCliInstructions && (
          <div className={styles.cliInstructions}>
            <div className={styles.cliInstructionsTitle}>Installation &amp; CI Usage</div>
            <div className={styles.cliStep}>
              <div className={styles.cliStepLabel}>1. Install CLI from repository package</div>
              <div className={styles.commandBox}>
                <code className={styles.commandCode}>pip install -e &quot;.[dev]&quot;</code>
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => handleCopy('pip install -e ".[dev]"', 'Copied installation command')}
                >
                  Copy
                </Button>
              </div>
            </div>
            <div className={styles.cliStep}>
              <div className={styles.cliStepLabel}>2. Verify installation</div>
              <div className={styles.commandBox}>
                <code className={styles.commandCode}>cryptiq version</code>
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => handleCopy('cryptiq version', 'Copied verify command')}
                >
                  Copy
                </Button>
              </div>
            </div>
            <div className={styles.cliStep}>
              <div className={styles.cliStepLabel}>3. CI Workflow — Local scan to SARIF</div>
              <div className={styles.commandBox}>
                <code className={styles.commandCode}>cryptiq scan . --format sarif &gt; cryptiq.sarif</code>
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() =>
                    handleCopy('cryptiq scan . --format sarif > cryptiq.sarif', 'Copied CI scan command')
                  }
                >
                  Copy
                </Button>
              </div>
            </div>
            <div className={styles.cliStep}>
              <div className={styles.cliStepLabel}>4. CI Workflow — PR Diff Gating</div>
              <div className={styles.commandBox}>
                <code className={styles.commandCode}>cryptiq diff --base &quot;origin/${'{'}github.base_ref{'}'}&quot; --head HEAD</code>
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() =>
                    handleCopy(
                      'cryptiq diff --base "origin/${{ github.base_ref }}" --head HEAD',
                      'Copied PR diff gating command',
                    )
                  }
                >
                  Copy
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {COMING_SOON_INTEGRATIONS.map((name) => (
        <div key={name} className={styles.comingSoonRow}>
          <span>{name}</span>
          <span className={styles.badgeNeutral}>Coming soon</span>
        </div>
      ))}
    </>
  );
}

function NotificationsSection({ form, update }: { form: SettingsFormState; update: Updater }) {
  const channels: { key: NotificationChannel; label: string }[] = [
    { key: 'app', label: 'In-app' },
    { key: 'email', label: 'Email' },
    { key: 'slack', label: 'Slack' },
  ];
  return (
    <>
      <h2 className={styles.sectionTitle}>Notifications</h2>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', paddingBottom: 10 }}>
              Event
            </th>
            {channels.map((channel) => (
              <th
                key={channel.key}
                style={{ fontSize: 11, color: 'var(--text-3)', width: 70, paddingBottom: 10 }}
              >
                {channel.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {NOTIFICATION_EVENTS.map((event) => (
            <tr key={event}>
              <td style={{ fontSize: '12.5px', color: 'var(--text-1)', padding: '8px 0' }}>{event}</td>
              {channels.map((channel) => (
                <td key={channel.key} style={{ textAlign: 'center' }}>
                  <CheckBox
                    label={`${event} — ${channel.label}`}
                    checked={form.notifications[event]?.[channel.key] ?? false}
                    onChange={(checked) =>
                      update('notifications', {
                        ...form.notifications,
                        [event]: {
                          ...(form.notifications[event] ?? { app: false, email: false, slack: false }),
                          [channel.key]: checked,
                        },
                      })
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function DangerSection({ onAction }: { onAction: (message: string) => void }) {
  const unavailable = 'Not available — no backend is connected in this environment.';
  return (
    <>
      <div className={styles.dangerTitle}>Danger Zone</div>
      <div className={styles.stackList}>
        <div className={styles.dangerRow}>
          <div className={styles.rowLabel}>Export workspace data</div>
          <Button size="xs" variant="secondary" onClick={() => onAction(unavailable)}>
            Export
          </Button>
        </div>
        <div className={`${styles.dangerRow} ${styles.critical}`}>
          <div className={styles.rowLabel}>Delete repository</div>
          <Button size="xs" variant="danger" onClick={() => onAction(unavailable)}>
            Delete
          </Button>
        </div>
        <div className={`${styles.dangerRow} ${styles.critical}`}>
          <div className={styles.rowLabel}>Delete workspace</div>
          <Button size="xs" variant="danger" onClick={() => onAction(unavailable)}>
            Delete
          </Button>
        </div>
      </div>
    </>
  );
}
