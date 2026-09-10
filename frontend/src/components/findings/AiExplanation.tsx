import { useCallback, useState } from 'react';
import type { ApiError } from '@/types/common';
import type { Finding, FindingExplanation } from '@/types/domain';
import { fetchFindingExplanation, toApiError } from '@/services';
import { getRoleCode } from '@/constants/domain';
import { lineRange } from '@/utils/format';
import { Spinner } from '@/components/common/Spinner';
import styles from './AiExplanation.module.css';

type LoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; explanation: FindingExplanation }
  | { status: 'error'; error: ApiError };

/**
 * On-demand AI explanation of a finding. Deliberately self-contained: it is a
 * subordinate layer over the deterministic analysis, the request goes through
 * the backend (the browser never calls Gemini), and any failure here is shown
 * inline without affecting the rest of the finding (master prompt §11).
 */
export function AiExplanation({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const [load, setLoad] = useState<LoadState>({ status: 'idle' });

  const runFetch = useCallback(() => {
    setLoad({ status: 'loading' });
    fetchFindingExplanation(finding.id).then(
      (explanation) => setLoad({ status: 'ready', explanation }),
      (cause: unknown) => setLoad({ status: 'error', error: toApiError(cause) }),
    );
  }, [finding.id]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && load.status === 'idle') runFetch();
  };

  if (!finding.aiExplanationAvailable) {
    return <p className={styles.unavailable}>AI explanation unavailable for this finding.</p>;
  }

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.toggle}
        onClick={toggle}
        aria-expanded={open}
        aria-controls="ai-explanation-panel"
      >
        <span className={styles.icon} aria-hidden />
        {open ? 'Hide AI explanation' : 'Explain with AI'}
      </button>

      {open && (
        <div id="ai-explanation-panel" className={styles.panel}>
          <div className={styles.evidenceLabel}>Deterministic finding — the AI only explains this</div>
          <dl className={styles.evidence}>
            <Row term="Detected algorithm" value={finding.observed.algorithm} />
            <Row term="Source lines" value={lineRange(finding.observed.lineStart, finding.observed.lineEnd)} />
            <Row term="Detected API" value={finding.observed.api} />
            <Row term="Inferred role" value={getRoleCode(finding.inferred.role)} accent />
            <Row
              term="Review path"
              value={finding.migration.path.join(', ') || 'MANUAL REVIEW'}
            />
          </dl>

          {load.status === 'loading' && (
            <p className={styles.status}>
              <Spinner size={12} /> Generating explanation…
            </p>
          )}
          {load.status === 'error' && (
            <div className={styles.error} role="alert">
              <span>
                AI explanation is unavailable right now. The deterministic finding above is
                unaffected.
              </span>
              <button type="button" className={styles.retry} onClick={runFetch}>
                Try again
              </button>
            </div>
          )}
          {load.status === 'ready' && (
            <div className={styles.result}>
              <div className={styles.aiLabel}>AI explanation</div>
              <p className={styles.summary}>{load.explanation.summary}</p>

              <Section title="Why it matters" body={load.explanation.whyItMatters} />
              <Section title="Reading the evidence" body={load.explanation.evidenceExplanation} />
              <Section title="Migration context" body={load.explanation.migrationExplanation} />
              <Section title="Impact" body={load.explanation.impactExplanation} />

              {load.explanation.limitations.length > 0 && (
                <div className={styles.limitations}>
                  <div className={styles.limitationsTitle}>Limitations</div>
                  <ul>
                    {load.explanation.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className={styles.disclaimer}>
                Generated from the established Cryptiq evidence above; it cannot change the
                detected algorithm, role, or migration path
                {load.explanation.model ? ` · ${load.explanation.model}` : ''}
                {load.explanation.cached ? ' · cached' : ''}.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ term, value, accent = false }: { term: string; value: string; accent?: boolean }) {
  return (
    <div className={styles.evidenceRow}>
      <dt>{term}</dt>
      <dd style={accent ? { color: 'var(--blue)' } : undefined}>{value}</dd>
    </div>
  );
}

/** One explanatory section. Rendered only when the model supplied a body. */
function Section({ title, body }: { title: string; body: string }) {
  if (!body.trim()) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      <p className={styles.sectionBody}>{body}</p>
    </div>
  );
}
