import { useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { EmptyState, Skeleton } from '@/components/common/StateViews';
import { ReviewStatusBadge } from '@/components/common/StatusIndicators';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { fetchReviewQueue } from '@/services';
import { getPriorityMeta, getRoleLabel } from '@/constants/domain';
import { fileName, formatRelativeTime } from '@/utils/format';
import { isClosedReviewStatus, type FindingReviewStatus, type ReviewQueueItem } from '@/types/domain';
import styles from './ReviewPage.module.css';

type TabId = 'active' | 'open' | 'in_review' | 'completed';

const TABS: { id: TabId; label: string }[] = [
  { id: 'active', label: 'Active' },
  { id: 'open', label: 'Open' },
  { id: 'in_review', label: 'In Review' },
  { id: 'completed', label: 'Completed' },
];

function matchesTab(status: FindingReviewStatus, tab: TabId): boolean {
  switch (tab) {
    case 'active':
      return status === 'open' || status === 'in_review';
    case 'open':
      return status === 'open';
    case 'in_review':
      return status === 'in_review';
    case 'completed':
      return isClosedReviewStatus(status);
  }
}

function parseTab(value: string | null): TabId {
  return TABS.some((tab) => tab.id === value) ? (value as TabId) : 'active';
}

const EMPTY_COPY: Record<TabId, string> = {
  active: 'No findings are waiting for review.',
  open: 'No open findings.',
  in_review: 'Nothing is currently in review.',
  completed: 'No findings have been dispositioned yet.',
};

export function ReviewPage() {
  useDocumentTitle('Review');
  useBreadcrumbs(() => [{ label: 'Review' }], []);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('tab'));

  const loader = useCallback((signal: AbortSignal) => fetchReviewQueue(signal), []);
  const { state, reload } = useAsyncResource(loader, []);

  const selectTab = (tab: TabId) => {
    setSearchParams(tab === 'active' ? {} : { tab }, { replace: true });
  };

  return (
    <Page>
      <PageHeader
        title="Review"
        description="Findings requiring human action. Open a finding to investigate and record a disposition."
      />

      <div className={styles.tabs} role="tablist" aria-label="Review queue filter">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`review-tab-${tab.id}`}
            aria-selected={tab.id === activeTab}
            aria-controls="review-panel"
            className={styles.tab}
            onClick={() => selectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div id="review-panel" role="tabpanel" aria-labelledby={`review-tab-${activeTab}`}>
        <AsyncBoundary
          state={state}
          onRetry={reload}
          errorTitle="The review queue could not be loaded"
          loading={<QueueSkeleton />}
        >
          {(items) => (
            <FilteredQueue
              items={items}
              tab={activeTab}
              onOpen={(findingId) => navigate(`/findings/${findingId}?from=review`)}
            />
          )}
        </AsyncBoundary>
      </div>
    </Page>
  );
}

function FilteredQueue({
  items,
  tab,
  onOpen,
}: {
  items: readonly ReviewQueueItem[];
  tab: TabId;
  onOpen: (findingId: string) => void;
}) {
  const filtered = useMemo(() => items.filter((item) => matchesTab(item.status, tab)), [items, tab]);

  if (filtered.length === 0) {
    return <EmptyState kicker="Review" title="Nothing to review" description={EMPTY_COPY[tab]} />;
  }

  return (
    <div className={styles.list}>
      {filtered.map((item) => (
        <ReviewQueueCard key={item.reviewId} item={item} onOpen={() => onOpen(item.findingId)} />
      ))}
    </div>
  );
}

function ReviewQueueCard({ item, onOpen }: { item: ReviewQueueItem; onOpen: () => void }) {
  const priority = getPriorityMeta(item.priority);
  const location = `${item.filePath}:${item.lineStart}`;
  // Each reason is already a full sentence ending in a period; join with a
  // space so two of them don't render "…API.. …".
  const why = item.reasons.slice(0, 2).join(' ');

  return (
    <button
      type="button"
      className={styles.card}
      style={{ borderLeftColor: priority.color }}
      onClick={onOpen}
      aria-label={`Review ${item.algorithm} finding at ${fileName(item.filePath)}:${item.lineStart}`}
    >
      <div className={styles.cardTop}>
        <div className={styles.cardHead}>
          <div className={styles.titleRow}>
            <span className={styles.priorityWord} style={{ color: priority.color }}>
              {priority.label.toUpperCase()}
            </span>
            <span className={styles.findingLabel}>{item.algorithm}</span>
            <span className={styles.role}>{getRoleLabel(item.role)}</span>
          </div>
          <div className={styles.location} title={location}>
            {fileName(item.filePath)}:{item.lineStart}
          </div>
        </div>
        <ReviewStatusBadge status={item.status} />
      </div>

      <div className={styles.cardBody}>
        <div className={styles.col}>
          <div className={styles.colLabel}>Why review is required</div>
          <div className={styles.colBody}>
            {why ? (/[.!?]$/.test(why) ? why : `${why}.`) : 'Flagged for migration review.'}
          </div>
        </div>
        <div className={styles.col}>
          <div className={styles.colLabel}>Recommended migration review path</div>
          <div className={styles.chips}>
            {item.reviewPath.length > 0 ? (
              item.reviewPath.map((path) => (
                <span key={path} className={styles.chip}>
                  {path}
                </span>
              ))
            ) : (
              <span className={styles.chip}>MANUAL REVIEW</span>
            )}
          </div>
        </div>
        <div className={styles.reviewerCol}>
          <div className={styles.colLabel}>Reviewer</div>
          <div className={styles.colBody}>{item.assignee ?? 'Unassigned'}</div>
          <div className={styles.age}>{formatRelativeTime(item.updatedAt)}</div>
        </div>
      </div>
    </button>
  );
}

function QueueSkeleton() {
  return (
    <div className={styles.list}>
      {[0, 1, 2].map((row) => (
        <div key={row} className={styles.card} style={{ cursor: 'default' }}>
          <Skeleton width={260} height={14} />
          <Skeleton width="80%" height={12} />
        </div>
      ))}
    </div>
  );
}
