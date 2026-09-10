import { useCallback, useState } from 'react';
import type { ApiError } from '@/types/common';
import type { ContextualAssessment, Finding } from '@/types/domain';
import { fetchMigrationAssessment, toApiError } from '@/services';
import { lineRange } from '@/utils/format';
import { Spinner } from '@/components/common/Spinner';
import { EpistemicBadge } from './EpistemicBadge';
import styles from './MigrationAdvisorCard.module.css';

type LoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; assessment: ContextualAssessment }
  | { status: 'error'; error: ApiError };

const DOMAIN_OPTIONS = [
  { value: 'AUTONOMOUS_DRONE', label: 'Autonomous Drone / Avionics' },
  { value: 'CLOUD_INFRASTRUCTURE', label: 'Cloud Infrastructure' },
  { value: 'FINTECH', label: 'Fintech / Financial Systems' },
  { value: 'GENERAL_SOFTWARE', label: 'General Software' },
] as const;

export function MigrationAdvisorCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState<string>('AUTONOMOUS_DRONE');
  const [load, setLoad] = useState<LoadState>({ status: 'idle' });

  const runAssess = useCallback(
    (domainToUse: string) => {
      setLoad({ status: 'loading' });
      fetchMigrationAssessment(finding.id, { domain: domainToUse }).then(
        (assessment) => setLoad({ status: 'ready', assessment }),
        (cause: unknown) => setLoad({ status: 'error', error: toApiError(cause) }),
      );
    },
    [finding.id],
  );

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && load.status === 'idle') {
      runAssess(selectedDomain);
    }
  };

  const handleDomainChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newDomain = e.target.value;
    setSelectedDomain(newDomain);
    runAssess(newDomain);
  };

  const statusClass =
    load.status === 'ready'
      ? {
          KEEP: styles.statusKeep,
          MIGRATE: styles.statusMigrate,
          REVIEW: styles.statusReview,
          INSUFFICIENT_CONTEXT: styles.statusInsufficient,
        }[load.assessment.assessment]
      : undefined;

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.toggle}
        onClick={toggle}
        aria-expanded={open}
        aria-controls="migration-advisor-panel"
      >
        <div className={styles.toggleTitle}>
          <span className={styles.toggleIcon} aria-hidden />
          <span>{open ? 'Hide Context-Aware Migration Advisor' : 'Context-Aware Migration Advisor'}</span>
        </div>
        {load.status === 'ready' && (
          <span className={`${styles.toggleStatusBadge} ${statusClass}`}>
            {load.assessment.assessment}: {load.assessment.contextualRole}
          </span>
        )}
      </button>

      {open && (
        <div id="migration-advisor-panel" className={styles.panel}>
          <div className={styles.header}>
            <h4 className={styles.headerTitle}>Context-Aware Migration Advisor</h4>
            <p className={styles.headerSubtitle}>
              Rigorous three-tier assessment separating deterministic static findings from
              application domain constraints and authoritative cryptographic guidance.
            </p>
          </div>

          <div className={styles.controlsBar}>
            <label className={styles.domainLabel}>
              <span>Domain Context:</span>
              <select
                className={styles.domainSelect}
                value={selectedDomain}
                onChange={handleDomainChange}
                disabled={load.status === 'loading'}
              >
                {DOMAIN_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={styles.reassessBtn}
              onClick={() => runAssess(selectedDomain)}
              disabled={load.status === 'loading'}
            >
              {load.status === 'loading' ? 'Evaluating…' : 'Re-assess'}
            </button>
          </div>

          {load.status === 'loading' && (
            <div className={styles.loadingBox}>
              <Spinner size={14} /> Synthesizing context and authoritative standards…
            </div>
          )}

          {load.status === 'error' && (
            <div className={styles.errorBox} role="alert">
              <span>Failed to evaluate migration advice: {load.error.message}</span>
              <button
                type="button"
                className={styles.retryBtn}
                onClick={() => runAssess(selectedDomain)}
              >
                Retry
              </button>
            </div>
          )}

          {load.status === 'ready' && (
            <div className={styles.tierContainer}>
              {/* TIER 1: DETERMINISTIC FACT */}
              <div className={styles.tierCard}>
                <div className={styles.tierHeader}>
                  <EpistemicBadge kind="observed" label="Tier 1 · Deterministic Fact" />
                </div>
                <p className={styles.tierExplanation}>
                  Established strictly by the static analysis engine. Downstream advisory
                  models cannot modify, dismiss, or invent findings.
                </p>
                <div className={styles.factGrid}>
                  <div className={styles.factItem}>
                    <span className={styles.factLabel}>Observed Algorithm</span>
                    <span className={styles.factValue}>{finding.observed.algorithm}</span>
                  </div>
                  <div className={styles.factItem}>
                    <span className={styles.factLabel}>Detected API</span>
                    <span className={styles.factValue}>{finding.observed.api}</span>
                  </div>
                  <div className={styles.factItem}>
                    <span className={styles.factLabel}>Source Location</span>
                    <span className={styles.factValue}>
                      {lineRange(finding.observed.lineStart, finding.observed.lineEnd)}
                    </span>
                  </div>
                  <div className={styles.factItem}>
                    <span className={styles.factLabel}>Static Semantic Role</span>
                    <span className={styles.factValue}>{load.assessment.contextualRole}</span>
                  </div>
                </div>
              </div>

              {/* TIER 2: APPLICATION & DOMAIN CONTEXT */}
              <div className={styles.tierCard}>
                <div className={styles.tierHeader}>
                  <EpistemicBadge kind="context" label="Tier 2 · Application Context" />
                </div>
                <p className={styles.tierExplanation}>
                  Engineering constraints and operational environment defining performance,
                  bandwidth, and platform envelopes.
                </p>
                {load.assessment.domainProfile && (
                  <div className={styles.constraintsGrid}>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Domain</span>
                      <span className={styles.constraintLevel}>
                        {load.assessment.domainProfile.domain}
                      </span>
                    </div>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Bandwidth</span>
                      <span
                        className={`${styles.constraintLevel} ${
                          load.assessment.domainProfile.bandwidthConstraint === 'HIGH'
                            ? styles.constraintHigh
                            : styles.constraintLow
                        }`}
                      >
                        {load.assessment.domainProfile.bandwidthConstraint}
                      </span>
                    </div>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Compute</span>
                      <span className={styles.constraintLevel}>
                        {load.assessment.domainProfile.computeConstraint}
                      </span>
                    </div>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Battery / Power</span>
                      <span className={styles.constraintLevel}>
                        {load.assessment.domainProfile.batteryConstraint}
                      </span>
                    </div>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Payload Size</span>
                      <span className={styles.constraintLevel}>
                        {load.assessment.domainProfile.payloadSizeSensitivity}
                      </span>
                    </div>
                    <div className={styles.constraintPill}>
                      <span className={styles.constraintName}>Offline Operation</span>
                      <span className={styles.constraintLevel}>
                        {load.assessment.domainProfile.offlineOperation === null
                          ? 'UNKNOWN'
                          : load.assessment.domainProfile.offlineOperation
                            ? 'YES'
                            : 'NO'}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* TIER 3: CONTEXTUAL RECOMMENDATION */}
              <div className={styles.tierCard}>
                <div className={styles.tierHeader}>
                  <EpistemicBadge kind="recommendation" label="Tier 3 · Contextual Recommendation" />
                  {load.assessment.migrationCandidate && (
                    <span className={styles.candidateBadge}>
                      Target: {load.assessment.migrationCandidate}
                    </span>
                  )}
                </div>

                <div
                  className={`${styles.decisionBanner} ${
                    {
                      KEEP: styles.decisionBannerKeep,
                      MIGRATE: styles.decisionBannerMigrate,
                      REVIEW: styles.decisionBannerReview,
                      INSUFFICIENT_CONTEXT: styles.decisionBannerInsufficient,
                    }[load.assessment.assessment]
                  }`}
                >
                  <span
                    className={`${styles.decisionTitle} ${
                      {
                        KEEP: styles.decisionTitleKeep,
                        MIGRATE: styles.decisionTitleMigrate,
                        REVIEW: styles.decisionTitleReview,
                        INSUFFICIENT_CONTEXT: styles.decisionTitleInsufficient,
                      }[load.assessment.assessment]
                    }`}
                  >
                    {load.assessment.assessment === 'KEEP' &&
                      'DECISION: KEEP — Fit-for-purpose in this semantic role'}
                    {load.assessment.assessment === 'MIGRATE' &&
                      'DECISION: MIGRATE — Post-quantum migration required'}
                    {load.assessment.assessment === 'REVIEW' &&
                      'DECISION: REVIEW — Context-dependent migration path'}
                    {load.assessment.assessment === 'INSUFFICIENT_CONTEXT' &&
                      'DECISION: INSUFFICIENT CONTEXT — Evaluation requires deployment detail'}
                  </span>
                  <span className={styles.factLabel}>
                    Confidence: {load.assessment.confidence.toUpperCase()}
                  </span>
                </div>

                <div className={styles.rationaleBox}>
                  <strong>Architectural Rationale:</strong> {load.assessment.rationale}
                </div>

                {load.assessment.engineeringTradeoffs.length > 0 && (
                  <div>
                    <div className={styles.sectionHeading}>Engineering Trade-offs</div>
                    <ul className={styles.tradeoffsList}>
                      {load.assessment.engineeringTradeoffs.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {load.assessment.knowledgeSources.length > 0 && (
                  <div>
                    <div className={styles.sectionHeading}>
                      Authoritative Cryptographic Knowledge Sources
                    </div>
                    <div className={styles.knowledgeGrid}>
                      {load.assessment.knowledgeSources.map((source) => (
                        <div key={source.chunkId} className={styles.knowledgeCard}>
                          <div className={styles.knowledgeCardHeader}>
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noreferrer"
                              className={styles.knowledgeTitleLink}
                            >
                              {source.title} ({source.documentId})
                            </a>
                            <span className={styles.knowledgeMeta}>
                              {source.publisher} · Section {source.section}
                            </span>
                          </div>
                          <p className={styles.knowledgeContent}>{source.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {load.assessment.limitations.length > 0 && (
                  <div>
                    <div className={styles.sectionHeading}>Limitations & Boundary Assumptions</div>
                    <ul className={styles.limitationsList}>
                      {load.assessment.limitations.map((lim, idx) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* FOOTER METADATA */}
              <div className={styles.footerDisclaimer}>
                <span className={styles.footerNotice}>
                  Subordinate advisory layer. Deterministic findings take absolute precedence.
                </span>
                <span className={styles.footerMetadata}>
                  Engine: {load.assessment.generatedBy}
                  {load.assessment.model ? ` · ${load.assessment.model}` : ''}
                  {load.assessment.cached ? ' · cached' : ''}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
