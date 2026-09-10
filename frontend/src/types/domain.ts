/**
 * Cryptiq domain model — the vocabulary the UI is written against.
 *
 * Every literal set here is taken from FRONTEND_BACKEND_CONTRACT.md and the
 * design source. The API layer (`services/`) is responsible for mapping the
 * backend's wire format onto these types; components never see raw responses.
 *
 * Epistemic layering is deliberate and load-bearing: a Finding separates what
 * was OBSERVED in the source from what Cryptiq INFERRED from it, and an AI
 * explanation is a third, clearly-subordinate layer. The types keep those
 * groups apart so a component cannot accidentally present a judgement as a fact.
 */

/* ------------------------------------------------------------------ enums --- */

export const INSPECTION_STATUSES = [
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
] as const;
export type InspectionStatus = (typeof INSPECTION_STATUSES)[number];

/** Migration-review priority. The engine only emits high/medium/low today;
 *  critical/informational exist in the contract vocabulary and are typed so the
 *  UI keeps working if they start appearing. */
export const FINDING_PRIORITIES = [
  'critical',
  'high',
  'medium',
  'low',
  'informational',
] as const;
export type FindingPriority = (typeof FINDING_PRIORITIES)[number];

export const FINDING_CONFIDENCES = ['high', 'medium', 'low', 'unknown'] as const;
export type FindingConfidence = (typeof FINDING_CONFIDENCES)[number];

/** Inferred cryptographic role. Matches the classifier vocabulary the backend
 *  migrated to (contract §Conflicts). */
export const CRYPTOGRAPHIC_ROLES = [
  'digital_signature',
  'key_establishment',
  'symmetric_encryption',
  'hash',
  'protocol',
  'unknown',
] as const;
export type CryptographicRole = (typeof CRYPTOGRAPHIC_ROLES)[number];

/** Disposition workflow shown in Review. The backend contract currently lists a
 *  narrower {OPEN, IN_REVIEW, REVIEWED}; the design's disposition actions
 *  (resolve / accept-risk / false-positive) are the visual source of truth and
 *  drive this wider set. `REVIEWED` maps onto `resolved`. */
export const FINDING_REVIEW_STATUSES = [
  'open',
  'in_review',
  'resolved',
  'accepted_risk',
  'false_positive',
] as const;
export type FindingReviewStatus = (typeof FINDING_REVIEW_STATUSES)[number];

/** Terminal dispositions — a finding in one of these states leaves the active
 *  Review queue. */
export const CLOSED_REVIEW_STATUSES: readonly FindingReviewStatus[] = [
  'resolved',
  'accepted_risk',
  'false_positive',
];

/** Recommended migration review path (contract `migration.review_path`). Never a
 *  drop-in replacement instruction. */
export const REVIEW_PATHS = [
  'ML-DSA / SLH-DSA',
  'ML-KEM',
  'KEY / IMPLEMENTATION REVIEW',
  'HASH / POLICY REVIEW',
  'MANUAL REVIEW',
] as const;
export type ReviewPath = (typeof REVIEW_PATHS)[number];

/* ------------------------------------------------------------- entities --- */

/** A repository Cryptiq knows about (Projects screen row). */
export interface Repository {
  readonly id: string;
  readonly name: string;
  readonly owner: string | null;
  readonly url: string | null;
  readonly language: string;
  readonly lastInspectedAt: string | null;
  readonly latestInspectionStatus: InspectionStatus | null;
  readonly findingsCount: number | null;
}

/** Counts by priority for one inspection. */
export interface SeverityBreakdown {
  readonly critical: number;
  readonly high: number;
  readonly medium: number;
  readonly low: number;
}

/** One inspection: one repository at one exact commit. */
export interface Inspection {
  readonly id: string;
  readonly repositoryId: string | null;
  readonly repositoryName: string;
  readonly language: string;
  readonly commitSha: string;
  readonly status: InspectionStatus;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
  readonly durationMs: number | null;
  readonly filesAnalyzed: number | null;
  readonly findingsCount: number;
  readonly severity: SeverityBreakdown;
  /** Populated only when `status` is `failed`: a stable code and a safe
   *  message. Never a stack trace. */
  readonly errorCode: string | null;
  readonly errorMessage: string | null;
}

/** One line of quoted source evidence. */
export interface EvidenceLine {
  readonly number: number;
  readonly text: string;
  readonly highlighted: boolean;
}

/** What was directly observed in the source at the commit — every field here is
 *  checkable by opening the file. */
export interface ObservedEvidence {
  readonly algorithm: string;
  readonly api: string;
  readonly filePath: string;
  readonly lineStart: number;
  readonly lineEnd: number;
  readonly commitSha: string;
  readonly repositoryName: string;
  readonly language: string;
  /** Quoted source, already truncated by the backend. Rendered as plain text. */
  readonly source: readonly EvidenceLine[];
}

/** What Cryptiq concluded from the observation. */
export interface InferredAssessment {
  readonly role: CryptographicRole;
  readonly confidence: FindingConfidence;
  /** Short factual statements backing the classification. */
  readonly reasons: readonly string[];
}

/** Migration-review guidance. `path` names material to read; it is never an
 *  instruction to swap an algorithm. */
export interface MigrationGuidance {
  readonly current: string;
  readonly path: readonly string[];
  readonly summary: string;
  readonly isMigrationCandidate: boolean;
}

/** Bounded impact within the scanned scope. */
export interface FindingImpact {
  readonly scope: 'statically_observed';
  readonly chain: readonly string[];
}

/** Present only when a reviewer has acted on the finding. */
export interface FindingReview {
  readonly id: string;
  readonly status: FindingReviewStatus;
  readonly assignee: string | null;
  readonly note: string | null;
  readonly updatedAt: string | null;
}

/** The full finding, as shown on the Finding Detail screen. */
export interface Finding {
  readonly id: string;
  readonly inspectionId: string;
  readonly priority: FindingPriority;
  readonly observed: ObservedEvidence;
  readonly inferred: InferredAssessment;
  readonly migration: MigrationGuidance;
  readonly impact: FindingImpact;
  readonly review: FindingReview | null;
  /** Whether the backend can currently produce an AI explanation for this
   *  finding. The finding itself never depends on it. */
  readonly aiExplanationAvailable: boolean;
}

/** Compact row for the Inspection Report findings table (contract
 *  `FindingSummary`). */
export interface FindingSummary {
  readonly id: string;
  readonly inspectionId: string;
  readonly priority: FindingPriority;
  readonly algorithm: string;
  readonly api: string;
  readonly role: CryptographicRole;
  readonly confidence: FindingConfidence;
  readonly filePath: string;
  readonly lineStart: number;
  readonly lineEnd: number | null;
  readonly reviewStatus: FindingReviewStatus | null;
}

/** One page of a paginated collection, with the metadata the pager renders. */
export interface Page<T> {
  readonly items: readonly T[];
  readonly total: number;
  readonly page: number;
  readonly pageSize: number;
  readonly pages: number;
}

/** Server-side filters for the findings table and the review queue. Every field
 *  is optional; omitted means "no constraint". Values are the domain tokens
 *  (`digital_signature`, `high`, …) — the API layer sends them as-is. */
export interface FindingFilters {
  readonly priority?: FindingPriority;
  readonly algorithm?: string;
  readonly role?: CryptographicRole;
  readonly confidence?: FindingConfidence;
  readonly status?: FindingReviewStatus;
}

/** Result of submitting a scan: the inspection plus whether it was served from
 *  an existing completed run rather than freshly queued. */
export interface SubmittedScan {
  readonly inspection: Inspection;
  readonly cached: boolean;
}

/** A row in the Review queue (contract `ReviewQueueItem`). */
export interface ReviewQueueItem {
  readonly reviewId: string;
  readonly findingId: string;
  readonly inspectionId: string;
  readonly priority: FindingPriority;
  readonly algorithm: string;
  readonly role: CryptographicRole;
  readonly reviewPath: readonly string[];
  readonly status: FindingReviewStatus;
  readonly assignee: string | null;
  readonly reasons: readonly string[];
  readonly filePath: string;
  readonly lineStart: number;
  readonly updatedAt: string | null;
}

/** Backend-produced AI explanation of an existing finding. Subordinate to the
 *  deterministic analysis; failure to load it must not break the finding. */
export interface FindingExplanation {
  readonly findingId: string;
  readonly provider: string;
  readonly model: string;
  readonly promptVersion: string;
  /** Short orientation line. */
  readonly summary: string;
  /** Structured explanatory sections. Empty string when the model omitted one. */
  readonly whyItMatters: string;
  readonly evidenceExplanation: string;
  readonly migrationExplanation: string;
  readonly impactExplanation: string;
  /** Caveats the model flagged about the evidence it was given. */
  readonly limitations: readonly string[];
  /** True when this response was served from cache (no fresh model call). */
  readonly cached: boolean;
  readonly generatedAt: string | null;
}

/* ---------------------------------------------------------- type guards --- */

export function isInspectionStatus(value: string): value is InspectionStatus {
  return (INSPECTION_STATUSES as readonly string[]).includes(value);
}
export function isFindingPriority(value: string): value is FindingPriority {
  return (FINDING_PRIORITIES as readonly string[]).includes(value);
}
export function isFindingConfidence(value: string): value is FindingConfidence {
  return (FINDING_CONFIDENCES as readonly string[]).includes(value);
}
export function isCryptographicRole(value: string): value is CryptographicRole {
  return (CRYPTOGRAPHIC_ROLES as readonly string[]).includes(value);
}
export function isFindingReviewStatus(value: string): value is FindingReviewStatus {
  return (FINDING_REVIEW_STATUSES as readonly string[]).includes(value);
}

export function isClosedReviewStatus(status: FindingReviewStatus): boolean {
  return CLOSED_REVIEW_STATUSES.includes(status);
}
