import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { ErrorState, LoadingState } from '@/components/common/StateViews';
import { DefinitionList } from '@/components/common/Surface';
import { FindingHeader } from '@/components/findings/FindingHeader';
import { ReviewActionBar, type ReviewAction } from '@/components/findings/ReviewActionBar';
import { EpistemicBadge } from '@/components/findings/EpistemicBadge';
import { SourceEvidence } from '@/components/findings/SourceEvidence';
import { ImpactChain } from '@/components/findings/ImpactChain';
import { ReviewPathCard } from '@/components/findings/ReviewPathCard';
import { MigrationAdvisorCard } from '@/components/findings/MigrationAdvisorCard';
import { AiExplanation } from '@/components/findings/AiExplanation';
import { useBreadcrumbs, type Crumb } from '@/components/layout/Breadcrumbs';
import { useToast } from '@/app/providers/ToastProvider';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import {
  fetchFinding,
  HttpError,
  submitFindingReview,
  toApiError,
  updateReviewItem,
} from '@/services';
import { getConfidenceMeta, getRoleCode } from '@/constants/domain';
import { lineRange, shortCommit } from '@/utils/format';
import type { Finding, FindingReviewStatus } from '@/types/domain';
import styles from './FindingDetailPage.module.css';

const ACTION_STATUS: Record<Exclude<ReviewAction, 'keep_open'>, FindingReviewStatus> = {
  start: 'in_review',
  resolved: 'resolved',
  accepted_risk: 'accepted_risk',
  false_positive: 'false_positive',
};
const ACTION_TOAST: Record<ReviewAction, string> = {
  start: 'Moved to In Review',
  resolved: 'Marked Resolved — removed from active queue',
  accepted_risk: 'Marked Accepted Risk — removed from active queue',
  false_positive: 'Marked False Positive — removed from active queue',
  keep_open: 'Kept in Review',
};

export function FindingDetailPage() {
  const { findingId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { notify } = useToast();

  const mode = searchParams.get('from') === 'review' ? 'review' : 'report';
  const inspectionParam = searchParams.get('inspection');

  const loader = useCallback((signal: AbortSignal) => fetchFinding(findingId, signal), [findingId]);
  const { state, reload } = useAsyncResource(loader, [findingId]);

  const [statusOverride, setStatusOverride] = useState<FindingReviewStatus | null>(null);
  const [reviewIdOverride, setReviewIdOverride] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const title = state.status === 'success' ? state.data.observed.algorithm : 'Finding';
  useDocumentTitle(title);

  useBreadcrumbs(() => {
    if (state.status !== 'success') {
      return mode === 'review'
        ? [{ label: 'Review', to: '/review' }, { label: 'Finding' }]
        : [{ label: 'History', to: '/history' }, { label: 'Finding' }];
    }
    const finding = state.data;
    if (mode === 'review') {
      return [{ label: 'Review', to: '/review' }, { label: finding.observed.algorithm }];
    }
    const inspectionId = inspectionParam ?? finding.inspectionId;
    const crumbs: Crumb[] = [{ label: 'History', to: '/history' }];
    if (inspectionId) {
      crumbs.push({
        label: `${finding.observed.repositoryName} @ ${shortCommit(finding.observed.commitSha)}`,
        to: `/history/${inspectionId}`,
      });
    }
    crumbs.push({ label: finding.observed.algorithm });
    return crumbs;
  }, [state.status, title, mode, inspectionParam]);

  const runAction = useCallback(
    (action: ReviewAction, reviewId: string | null) => {
      if (action === 'keep_open') {
        notify(ACTION_TOAST.keep_open);
        return;
      }
      const nextStatus = ACTION_STATUS[action];
      setPending(true);
      // Prefer the canonical id-keyed PATCH when the finding already has a
      // review row; fall back to the finding-keyed create for one that does
      // not. Either way the backend is authoritative — a rejected transition
      // (409 INVALID_REVIEW_TRANSITION) is surfaced, never faked.
      const promise = reviewId
        ? updateReviewItem(reviewId, { status: nextStatus })
        : submitFindingReview(findingId, nextStatus);
      promise.then(
        (review) => {
          setStatusOverride(review.status);
          setReviewIdOverride(review.id);
          setPending(false);
          notify(ACTION_TOAST[action]);
        },
        (cause: unknown) => {
          setPending(false);
          if (cause instanceof HttpError && cause.code === 'INVALID_REVIEW_TRANSITION') {
            notify(cause.message || 'That review change is not allowed from the current state.');
            return;
          }
          notify(toApiError(cause).message);
        },
      );
    },
    [findingId, notify],
  );

  if (state.status === 'idle' || state.status === 'loading') {
    return (
      <Page>
        <LoadingState label="Loading finding…" />
      </Page>
    );
  }
  if (state.status === 'error') {
    return (
      <Page>
        <ErrorState error={state.error} onRetry={reload} title="This finding could not be loaded" />
      </Page>
    );
  }

  const finding = state.data;
  const reviewId = reviewIdOverride ?? finding.review?.id ?? null;
  return (
    <FindingDetailView
      finding={finding}
      mode={mode}
      status={statusOverride ?? finding.review?.status ?? 'open'}
      pending={pending}
      onAction={(action) => runAction(action, reviewId)}
      onOpenInReview={() => navigate(`/findings/${finding.id}?from=review`)}
    />
  );
}

interface ViewProps {
  finding: Finding;
  mode: 'review' | 'report';
  status: FindingReviewStatus;
  pending: boolean;
  onAction: (action: ReviewAction) => void;
  onOpenInReview: () => void;
}

function FindingDetailView({ finding, mode, status, pending, onAction, onOpenInReview }: ViewProps) {
  const observedItems = useMemo(
    () => [
      { term: 'Algorithm', value: finding.observed.algorithm },
      { term: 'API', value: finding.observed.api },
      { term: 'Repository', value: finding.observed.repositoryName },
      { term: 'File', value: finding.observed.filePath, title: finding.observed.filePath },
      { term: 'Lines', value: lineRange(finding.observed.lineStart, finding.observed.lineEnd) },
      { term: 'Commit', value: shortCommit(finding.observed.commitSha) },
    ],
    [finding.observed],
  );

  const inferredItems = useMemo(
    () => [
      {
        term: 'Role',
        value: <span className={styles.roleValue}>{getRoleCode(finding.inferred.role)}</span>,
      },
      { term: 'Confidence', value: getConfidenceMeta(finding.inferred.confidence).label, plain: true },
    ],
    [finding.inferred],
  );

  return (
    <div>
      <FindingHeader finding={finding} />
      <ReviewActionBar
        status={status}
        mode={mode}
        pending={pending}
        onAction={onAction}
        onOpenInReview={onOpenInReview}
      />

      <div className={styles.grid}>
        <div className={styles.left}>
          <div className={styles.sectionLabel}>Source evidence</div>
          <SourceEvidence observed={finding.observed} />

          <div className={`${styles.sectionLabel} ${styles.spaced}`}>Impact within scanned scope</div>
          <ImpactChain chain={finding.impact.chain} />
        </div>

        <div className={styles.right}>
          <div className={styles.block}>
            <EpistemicBadge kind="observed" />
            <DefinitionList items={observedItems} />
          </div>
          <hr className={styles.divider} />

          <div className={styles.block}>
            <EpistemicBadge kind="inferred" />
            <DefinitionList items={inferredItems} />
          </div>
          <hr className={styles.divider} />

          <div className={styles.reviewPathWrap}>
            <ReviewPathCard finding={finding} />
          </div>

          <MigrationAdvisorCard finding={finding} />
          <AiExplanation finding={finding} />
        </div>
      </div>
    </div>
  );
}
