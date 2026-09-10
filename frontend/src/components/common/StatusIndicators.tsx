import type { CSSProperties } from 'react';
import type { FindingConfidence, FindingPriority, FindingReviewStatus, InspectionStatus } from '@/types/domain';
import {
  getConfidenceMeta,
  getInspectionStatusMeta,
  getPriorityMeta,
  getReviewStatusMeta,
} from '@/constants/domain';
import styles from './StatusIndicators.module.css';

/** A bare coloured status dot. */
export function StatusDot({ color, size = 6 }: { color: string; size?: number }) {
  return <span className={styles.dot} style={{ background: color, width: size, height: size }} aria-hidden />;
}

/** Priority as a coloured dot + word ("HIGH"). */
export function PriorityBadge({ priority, uppercase = true }: { priority: FindingPriority; uppercase?: boolean }) {
  const meta = getPriorityMeta(priority);
  const text = uppercase ? meta.label.toUpperCase() : meta.label;
  return (
    <span className={styles.priority}>
      <StatusDot color={meta.color} />
      <span className={styles.priorityLabel} style={{ color: meta.color }}>
        {text}
      </span>
    </span>
  );
}

/** Inspection lifecycle status as dot + label. */
export function InspectionStatusBadge({ status }: { status: InspectionStatus }) {
  const meta = getInspectionStatusMeta(status);
  return (
    <span className={styles.priority}>
      <StatusDot color={meta.color} />
      <span className={styles.confidenceLabel} style={{ color: meta.color }}>
        {meta.label}
      </span>
    </span>
  );
}

/** Review disposition as a bordered pill. */
export function ReviewStatusBadge({ status }: { status: FindingReviewStatus }) {
  const meta = getReviewStatusMeta(status);
  const style: CSSProperties = {
    background: meta.background,
    borderColor: meta.border,
    color: meta.color,
  };
  return (
    <span className={styles.reviewBadge} style={style}>
      <span className={styles.badgeDot} style={{ background: meta.color }} aria-hidden />
      {meta.label}
    </span>
  );
}

/** Confidence as a ringed dot (filled only for HIGH) + label. */
export function ConfidenceIndicator({ confidence }: { confidence: FindingConfidence }) {
  const meta = getConfidenceMeta(confidence);
  return (
    <span className={styles.confidence}>
      <span
        className={styles.confidenceDot}
        style={{ background: meta.filled ? 'var(--text-2)' : 'transparent' }}
        aria-hidden
      />
      <span className={styles.confidenceLabel}>{meta.label}</span>
    </span>
  );
}
