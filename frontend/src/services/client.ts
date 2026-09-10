/**
 * The Cryptiq API client — the one place that knows the canonical endpoint
 * paths and their query/response shapes:
 *
 *   POST   /scans                     createScan
 *   GET    /scans/{id}                getScan
 *   GET    /scans/{id}/findings       getFindings   (paged + server-filtered)
 *   GET    /findings/{id}             getFinding
 *   GET    /review-queue             getReviewQueue (paged + server-filtered)
 *   PATCH  /review-items/{id}         updateReviewItem
 *
 * Every function returns a mapped domain type; components never see a wire DTO.
 * Raw `fetch` still lives only in `http.ts` — this module builds on `request()`.
 */

import type {
  ApiContextualAssessmentDto,
  ApiDomainProfileDto,
  ApiFindingDto,
  ApiFindingSummaryDto,
  ApiInspectionDto,
  ApiListEnvelope,
  ApiPageEnvelope,
  ApiReviewBlock,
  ApiReviewQueueItemDto,
  CreateInspectionRequest,
  CreateMigrationAssessmentRequest,
  UpdateReviewItemRequest,
} from '@/types/api';
import type {
  ContextualAssessment,
  Finding,
  FindingFilters,
  FindingReview,
  FindingReviewStatus,
  FindingSummary,
  Inspection,
  Page,
  ReviewQueueItem,
  SubmittedScan,
} from '@/types/domain';
import type { ValidatedInspectionInput } from '@/utils/validation';
import { assertBackendConfigured, isBackendConfigured } from './config';
import { request, type RequestOptions } from './http';
import {
  mapContextualAssessment,
  mapFinding,
  mapFindingSummary,
  mapInspection,
  mapReviewQueueItem,
  toReviewStatus,
} from './mappers';

const enc = encodeURIComponent;

/** Wire tokens for the review workflow — the backend wants upper snake case. */
const WIRE_REVIEW_STATUS: Record<FindingReviewStatus, string> = {
  open: 'OPEN',
  in_review: 'IN_REVIEW',
  resolved: 'RESOLVED',
  accepted_risk: 'ACCEPTED_RISK',
  false_positive: 'FALSE_POSITIVE',
};

function filterQuery(filters: FindingFilters | undefined): RequestOptions['query'] {
  if (!filters) return {};
  return {
    priority: filters.priority,
    algorithm: filters.algorithm?.trim() || undefined,
    role: filters.role,
    confidence: filters.confidence,
    status: filters.status ? WIRE_REVIEW_STATUS[filters.status] : undefined,
  };
}

/* --------------------------------------------------------------- scans --- */

/**
 * Submit a scan. The backend answers `202` for a freshly queued scan or `200`
 * with `cached: true` when an identical completed scan already exists — either
 * way this resolves to the inspection and the `cached` flag. Rejects (never
 * fabricates a result) when no backend is connected.
 */
export async function createScan(input: ValidatedInspectionInput): Promise<SubmittedScan> {
  assertBackendConfigured();
  const payload: CreateInspectionRequest = {
    repository_url: input.repositoryUrl,
    commit_sha: input.commitSha,
  };
  const dto = await request<ApiInspectionDto>('/scans', { method: 'POST', body: payload });
  return { inspection: mapInspection(dto), cached: Boolean(dto.cached) };
}

/** Read one scan's authoritative state (used by the report page's poll). */
export async function getScan(scanId: string, signal?: AbortSignal): Promise<Inspection> {
  assertBackendConfigured();
  const dto = await request<ApiInspectionDto>(`/scans/${enc(scanId)}`, signal ? { signal } : {});
  return mapInspection(dto);
}

/** One page of a scan's findings, filtered on the server. */
export async function getFindings(
  scanId: string,
  options: { page?: number; pageSize?: number; filters?: FindingFilters; signal?: AbortSignal } = {},
): Promise<Page<FindingSummary>> {
  assertBackendConfigured();
  const { page = 1, pageSize = 50, filters, signal } = options;
  const body = await request<ApiPageEnvelope<ApiFindingSummaryDto>>(
    `/scans/${enc(scanId)}/findings`,
    {
      query: { page, page_size: pageSize, ...filterQuery(filters) },
      ...(signal ? { signal } : {}),
    },
  );
  return {
    items: body.items.map(mapFindingSummary),
    total: body.total,
    page: body.page,
    pageSize: body.page_size,
    pages: body.pages,
  };
}

/* ------------------------------------------------------------ findings --- */

export async function getFinding(findingId: string, signal?: AbortSignal): Promise<Finding> {
  assertBackendConfigured();
  const dto = await request<ApiFindingDto>(`/findings/${enc(findingId)}`, signal ? { signal } : {});
  return mapFinding(dto);
}

export async function getMigrationAssessment(
  findingId: string,
  domainProfile?: ApiDomainProfileDto,
  signal?: AbortSignal,
): Promise<ContextualAssessment> {
  assertBackendConfigured();
  const payload: CreateMigrationAssessmentRequest = domainProfile
    ? { domain_profile: domainProfile }
    : {};
  const dto = await request<ApiContextualAssessmentDto>(
    `/findings/${enc(findingId)}/migration-assessment`,
    {
      method: 'POST',
      body: payload,
      ...(signal ? { signal } : {}),
    },
  );
  return mapContextualAssessment(dto);
}

/* -------------------------------------------------------- review queue --- */

/**
 * One page of the global review queue. Passing `page` makes the backend
 * paginate and filter server-side; `total` is always the full match count.
 */
export async function getReviewQueue(
  options: { page?: number; pageSize?: number; filters?: FindingFilters; signal?: AbortSignal } = {},
): Promise<Page<ReviewQueueItem>> {
  const { page = 1, pageSize = 50, filters, signal } = options;
  if (!isBackendConfigured()) {
    return { items: [], total: 0, page, pageSize, pages: 1 };
  }
  const body = await request<ApiListEnvelope<ApiReviewQueueItemDto>>('/review-queue', {
    query: { page, page_size: pageSize, ...filterQuery(filters) },
    ...(signal ? { signal } : {}),
  });
  const total = body.total ?? body.items.length;
  return {
    items: body.items.map(mapReviewQueueItem),
    total,
    page,
    pageSize,
    pages: Math.max(Math.ceil(total / pageSize), 1),
  };
}

/**
 * Update one review item by its id. Only the fields present are sent, so a
 * caller can change the status without touching the note or assignee. A `409`
 * from the backend (`INVALID_REVIEW_TRANSITION`) surfaces as an `HttpError`
 * with that code — callers must not fake a successful change.
 */
export async function updateReviewItem(
  reviewId: string,
  changes: { status?: FindingReviewStatus; assignedTo?: string | null; note?: string | null },
): Promise<FindingReview> {
  assertBackendConfigured();
  const payload: UpdateReviewItemRequest = {};
  if (changes.status !== undefined) payload.status = WIRE_REVIEW_STATUS[changes.status];
  if (changes.assignedTo !== undefined) payload.assigned_to = changes.assignedTo;
  if (changes.note !== undefined) payload.note = changes.note;

  const body = await request<ApiReviewBlock>(`/review-items/${enc(reviewId)}`, {
    method: 'PATCH',
    body: payload,
  });
  return {
    id: body.id,
    status: toReviewStatus(body.status) ?? changes.status ?? 'open',
    assignee: body.assigned_to,
    note: body.note,
    updatedAt: body.updated_at,
  };
}
