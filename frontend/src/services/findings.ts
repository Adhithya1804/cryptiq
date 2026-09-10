/**
 * Findings — single finding detail, its (subordinate) AI explanation, and
 * recording a review disposition.
 */

import type {
  ContextualAssessment,
  Finding,
  FindingExplanation,
  FindingReview,
  FindingReviewStatus,
} from '@/types/domain';
import type {
  ApiContextualAssessmentDto,
  ApiDomainProfileDto,
  ApiExplanationDto,
  ApiFindingDto,
  ApiReviewBlock,
  CreateMigrationAssessmentRequest,
  SubmitReviewRequest,
} from '@/types/api';
import { assertBackendConfigured } from './config';
import { request } from './http';
import { mapContextualAssessment, mapExplanation, mapFinding, toReviewStatus } from './mappers';

export async function fetchFinding(findingId: string, signal?: AbortSignal): Promise<Finding> {
  assertBackendConfigured();
  const body = await request<ApiFindingDto>(
    `/findings/${encodeURIComponent(findingId)}`,
    signal ? { signal } : {},
  );
  return mapFinding(body);
}

/**
 * Request the AI explanation for a finding. This is deliberately isolated:
 * callers handle its rejection locally and the finding stays fully usable
 * without it. The request goes through the backend — the browser never talks to
 * Gemini, and it sends nothing but the finding id (no prompt, no source).
 * `POST` because the backend may generate and persist on first call; repeat
 * calls for the same unchanged finding are served from cache.
 */
export async function fetchFindingExplanation(
  findingId: string,
  signal?: AbortSignal,
): Promise<FindingExplanation> {
  assertBackendConfigured();
  const body = await request<ApiExplanationDto>(
    `/findings/${encodeURIComponent(findingId)}/explanation`,
    { method: 'POST', ...(signal ? { signal } : {}) },
  );
  return mapExplanation(body);
}

/**
 * Request the context-aware migration assessment for a finding.
 * Evaluates semantic role, application/domain context, and authoritative
 * cryptographic standards (NIST FIPS 203/204/205, SP 800-131A).
 */
export async function fetchMigrationAssessment(
  findingId: string,
  domainProfile?: ApiDomainProfileDto,
  signal?: AbortSignal,
): Promise<ContextualAssessment> {
  assertBackendConfigured();
  const payload: CreateMigrationAssessmentRequest = domainProfile
    ? { domain_profile: domainProfile }
    : {};
  const body = await request<ApiContextualAssessmentDto>(
    `/findings/${encodeURIComponent(findingId)}/migration-assessment`,
    {
      method: 'POST',
      body: payload,
      ...(signal ? { signal } : {}),
    },
  );
  return mapContextualAssessment(body);
}

const WIRE_STATUS: Record<FindingReviewStatus, string> = {
  open: 'OPEN',
  in_review: 'IN_REVIEW',
  resolved: 'RESOLVED',
  accepted_risk: 'ACCEPTED_RISK',
  false_positive: 'FALSE_POSITIVE',
};

export async function submitFindingReview(
  findingId: string,
  status: FindingReviewStatus,
  note?: string,
): Promise<FindingReview> {
  assertBackendConfigured();
  const payload: SubmitReviewRequest = { status: WIRE_STATUS[status], ...(note ? { note } : {}) };
  const body = await request<ApiReviewBlock>(`/findings/${encodeURIComponent(findingId)}/review`, {
    method: 'POST',
    body: payload,
  });
  return {
    id: body.id,
    status: toReviewStatus(body.status) ?? status,
    assignee: body.assigned_to,
    note: body.note,
    updatedAt: body.updated_at,
  };
}
