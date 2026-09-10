/**
 * Domain → presentation mappings. Every "what colour is a HIGH priority", "what
 * do we call the `digital_signature` role" decision is made here, once, so JSX
 * stays free of ternary ladders (master prompt §26).
 *
 * Colours are CSS custom-property references, not hex — the palette stays in
 * tokens.css.
 */

import type {
  CryptographicRole,
  FindingConfidence,
  FindingPriority,
  FindingReviewStatus,
  InspectionStatus,
} from '@/types/domain';

export interface Swatch {
  /** e.g. "var(--red)" — use directly as a colour value. */
  readonly color: string;
  readonly label: string;
}

/* ----------------------------------------------------------- priority --- */

const PRIORITY_META: Record<FindingPriority, Swatch> = {
  critical: { color: 'var(--red-solid)', label: 'Critical' },
  high: { color: 'var(--red)', label: 'High' },
  medium: { color: 'var(--amber)', label: 'Medium' },
  low: { color: 'var(--green)', label: 'Low' },
  informational: { color: 'var(--text-3)', label: 'Informational' },
};

export function getPriorityMeta(priority: FindingPriority): Swatch {
  return PRIORITY_META[priority];
}

/** Sort weight — higher is more urgent. Used by the Inspection Report table. */
export const PRIORITY_WEIGHT: Record<FindingPriority, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  informational: 0,
};

/* --------------------------------------------------------- confidence --- */

const CONFIDENCE_META: Record<FindingConfidence, { label: string; filled: boolean }> = {
  high: { label: 'High', filled: true },
  medium: { label: 'Medium', filled: false },
  low: { label: 'Low', filled: false },
  unknown: { label: 'Unknown', filled: false },
};

export function getConfidenceMeta(confidence: FindingConfidence): { label: string; filled: boolean } {
  return CONFIDENCE_META[confidence];
}

export const CONFIDENCE_WEIGHT: Record<FindingConfidence, number> = {
  high: 3,
  medium: 2,
  low: 1,
  unknown: 0,
};

/* --------------------------------------------------------------- role --- */

const ROLE_META: Record<CryptographicRole, { label: string; code: string }> = {
  digital_signature: { label: 'Digital Signature', code: 'DIGITAL_SIGNATURE' },
  key_establishment: { label: 'Key Establishment', code: 'KEY_ESTABLISHMENT' },
  symmetric_encryption: { label: 'Symmetric Encryption', code: 'SYMMETRIC_ENCRYPTION' },
  hash: { label: 'Hash', code: 'HASH' },
  protocol: { label: 'Protocol', code: 'PROTOCOL' },
  unknown: { label: 'Unclassified', code: 'UNKNOWN' },
};

export function getRoleLabel(role: CryptographicRole): string {
  return ROLE_META[role].label;
}
export function getRoleCode(role: CryptographicRole): string {
  return ROLE_META[role].code;
}

/* ------------------------------------------------- review disposition --- */

export interface ReviewStatusMeta {
  readonly label: string;
  readonly color: string;
  readonly background: string;
  readonly border: string;
}

const REVIEW_STATUS_META: Record<FindingReviewStatus, ReviewStatusMeta> = {
  open: {
    label: 'Open',
    color: 'var(--text-2)',
    background: 'transparent',
    border: 'var(--border-strong)',
  },
  in_review: {
    label: 'In Review',
    color: 'var(--amber)',
    background: 'color-mix(in srgb, var(--amber) 16%, transparent)',
    border: 'color-mix(in srgb, var(--amber) 45%, var(--border-strong))',
  },
  resolved: {
    label: 'Resolved',
    color: 'var(--green)',
    background: 'color-mix(in srgb, var(--green) 16%, transparent)',
    border: 'color-mix(in srgb, var(--green) 45%, var(--border-strong))',
  },
  accepted_risk: {
    label: 'Accepted Risk',
    color: 'var(--blue)',
    background: 'color-mix(in srgb, var(--blue) 16%, transparent)',
    border: 'color-mix(in srgb, var(--blue) 45%, var(--border-strong))',
  },
  false_positive: {
    label: 'False Positive',
    color: 'var(--text-3)',
    background: 'transparent',
    border: 'var(--border)',
  },
};

export function getReviewStatusMeta(status: FindingReviewStatus): ReviewStatusMeta {
  return REVIEW_STATUS_META[status];
}

/* --------------------------------------------------- inspection status --- */

const INSPECTION_STATUS_META: Record<InspectionStatus, Swatch> = {
  queued: { color: 'var(--text-2)', label: 'Queued' },
  running: { color: 'var(--amber)', label: 'Running' },
  completed: { color: 'var(--green)', label: 'Completed' },
  failed: { color: 'var(--red)', label: 'Failed' },
  cancelled: { color: 'var(--text-3)', label: 'Cancelled' },
};

export function getInspectionStatusMeta(status: InspectionStatus): Swatch {
  return INSPECTION_STATUS_META[status];
}
