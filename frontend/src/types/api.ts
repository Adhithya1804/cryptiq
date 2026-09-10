/**
 * Wire shapes — what the Cryptiq backend sends and receives over HTTP.
 *
 * These mirror FRONTEND_BACKEND_CONTRACT.md ("Resolution: the canonical
 * finding" and the supporting shapes). Fields are typed loosely as `string`
 * where the backend sends an enum token in its own casing; `services/mappers.ts`
 * narrows and normalises them onto `types/domain.ts`.
 *
 * Nothing outside `services/` should import from this file.
 */

export interface ApiRepositoryRef {
  provider: string;
  owner: string;
  name: string;
  url: string | null;
}

export interface ApiLocation {
  file_path: string;
  start_line: number;
  end_line: number | null;
  start_column?: number | null;
  end_column?: number | null;
}

export interface ApiRepositoryDto {
  id: string;
  repository: ApiRepositoryRef;
  language: string;
  last_inspected_at: string | null;
  latest_inspection_status: string | null;
  findings_count: number | null;
}

export interface ApiSeverityBreakdown {
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
}

export interface ApiInspectionDto {
  id: string;
  repository_id: string | null;
  repository: ApiRepositoryRef;
  language: string;
  commit_sha: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  files_analyzed: number | null;
  findings_count: number;
  severity: ApiSeverityBreakdown;
  /** Set by `POST /scans` only: true when an identical completed scan was
   *  reused instead of a new one being queued. */
  cached?: boolean;
  /** Present on a failed scan: a stable machine code and a safe, human
   *  message. Never a stack trace. Null on a scan that has not failed. */
  error_code?: string | null;
  error_message?: string | null;
}

export interface ApiObservedBlock {
  algorithm: string;
  api: string;
  primitive?: string;
  library?: string;
  operation?: string;
  location: ApiLocation;
  source_excerpt: string;
  enclosing_function?: string | null;
  enclosing_class?: string | null;
  parser_version?: string;
  ruleset_version?: string;
}

export interface ApiInferenceBlock {
  role: string;
  rationale: string[] | string;
  confidence: string;
  evidence_basis?: string;
}

export interface ApiMigrationBlock {
  review_path: string | string[];
  rationale: string;
  is_migration_candidate: boolean;
  pqc_ruleset_version?: string;
  current?: string;
}

export interface ApiImpactBlock {
  scope: string;
  node_count?: number;
  nodes?: string[];
  relationships?: string[];
}

export interface ApiPriorityBlock {
  level: string;
  score?: number;
  reasons?: string[];
}

export interface ApiReviewBlock {
  id: string;
  status: string;
  assigned_to: string | null;
  note: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApiFindingDto {
  id: string;
  scan_id: string;
  repository: ApiRepositoryRef;
  commit_sha: string;
  language?: string;
  observed: ApiObservedBlock;
  inference: ApiInferenceBlock;
  migration: ApiMigrationBlock;
  impact: ApiImpactBlock;
  priority: ApiPriorityBlock;
  review: ApiReviewBlock | null;
  ai_explanation_available?: boolean;
}

export interface ApiFindingSummaryDto {
  id: string;
  scan_id: string;
  algorithm: string;
  api: string;
  operation?: string;
  role: string;
  confidence: string;
  review_path?: string | string[];
  is_migration_candidate?: boolean;
  priority: string;
  priority_score?: number;
  file_path: string;
  start_line: number;
  end_line: number | null;
  review_status: string | null;
}

export interface ApiReviewQueueItemDto {
  review_id: string;
  finding_id: string;
  scan_id: string;
  algorithm: string;
  api: string;
  role: string;
  review_path: string | string[];
  priority: string;
  priority_score?: number;
  status: string;
  assigned_to: string | null;
  note: string | null;
  reasons?: string[];
  file_path: string;
  start_line: number;
  updated_at: string | null;
}

export interface ApiExplanationDto {
  finding_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  summary: string;
  why_it_matters?: string;
  evidence_explanation?: string;
  migration_explanation?: string;
  impact_explanation?: string;
  limitations?: string[];
  cached?: boolean;
  generated_at: string | null;
}

export interface ApiListEnvelope<T> {
  items: T[];
  next_cursor?: string | null;
  total?: number;
}

/** One page of a collection: `GET /scans/{id}/findings`. */
export interface ApiPageEnvelope<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/* ------------------------------------------------------------ requests --- */

export interface CreateInspectionRequest {
  repository_url: string;
  commit_sha: string;
}

export interface SubmitReviewRequest {
  status: string;
  note?: string;
}

/** Body for `PATCH /review-items/{review_id}`. Omitted fields are left
 *  unchanged; `null` on `assigned_to` / `note` clears them. */
export interface UpdateReviewItemRequest {
  status?: string;
  assigned_to?: string | null;
  note?: string | null;
}

/** The backend may 202-and-queue, or return the created inspection outright. */
export interface CreateInspectionResponse {
  inspection: ApiInspectionDto;
}

export interface ApiErrorBody {
  message?: string;
  detail?: string | { msg?: string }[];
  code?: string;
  /** Cryptiq's own error envelope: `{ error: { code, message } }`. */
  error?: { code?: string; message?: string };
}
