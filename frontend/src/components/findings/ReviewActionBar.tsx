import { Button } from '@/components/common/Button';
import { ReviewStatusBadge } from '@/components/common/StatusIndicators';
import { isClosedReviewStatus, type FindingReviewStatus } from '@/types/domain';
import styles from './ReviewActionBar.module.css';

export type ReviewAction = 'start' | 'resolved' | 'accepted_risk' | 'false_positive' | 'keep_open';

interface ReviewActionBarProps {
  status: FindingReviewStatus;
  /** "review" shows disposition controls; "report" shows a hand-off to Review. */
  mode: 'review' | 'report';
  pending: boolean;
  onAction: (action: ReviewAction) => void;
  onOpenInReview: () => void;
}

export function ReviewActionBar({
  status,
  mode,
  pending,
  onAction,
  onOpenInReview,
}: ReviewActionBarProps) {
  return (
    <div className={styles.bar}>
      <div className={styles.statusGroup}>
        <span className={styles.statusLabel}>Status</span>
        <ReviewStatusBadge status={status} />
      </div>

      {mode === 'review' ? (
        <div className={styles.actions}>
          {status === 'open' && (
            <Button size="sm" loading={pending} onClick={() => onAction('start')}>
              Start Review
            </Button>
          )}
          {status === 'in_review' && (
            <>
              <Button size="sm" variant="positive" loading={pending} onClick={() => onAction('resolved')}>
                Mark Resolved
              </Button>
              <Button size="sm" variant="accent" disabled={pending} onClick={() => onAction('accepted_risk')}>
                Accept Risk
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={pending}
                onClick={() => onAction('false_positive')}
              >
                False Positive
              </Button>
              <Button size="sm" variant="subtle" disabled={pending} onClick={() => onAction('keep_open')}>
                Keep Open
              </Button>
            </>
          )}
          {isClosedReviewStatus(status) && (
            <span className={styles.note}>Disposition recorded — removed from active Review.</span>
          )}
        </div>
      ) : (
        <div className={styles.actions}>
          <span className={styles.note}>
            Inspection reports summarize findings. Disposition happens in Review.
          </span>
          <Button size="xs" variant="secondary" onClick={onOpenInReview}>
            Open in Review Queue →
          </Button>
        </div>
      )}
    </div>
  );
}
