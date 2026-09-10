/**
 * Wire → domain mapping. Every value that crosses from `types/api.ts` into
 * `types/domain.ts` passes through here, so enum normalisation and defensive
 * defaults live in exactly one place.
 */

import type {
  ApiContextualAssessmentDto,
  ApiDomainProfileDto,
  ApiExplanationDto,
  ApiFindingDto,
  ApiFindingSummaryDto,
  ApiInspectionDto,
  ApiKnowledgeSourceDto,
  ApiRepositoryDto,
  ApiReviewQueueItemDto,
} from '@/types/api';
import {
  isAssessmentDecision,
  isContextualRole,
  isCryptographicRole,
  isFindingConfidence,
  isFindingPriority,
  isFindingReviewStatus,
  isInspectionStatus,
  type AssessmentDecision,
  type ContextualAssessment,
  type ContextualRole,
  type CryptographicRole,
  type DomainProfile,
  type EvidenceLine,
  type Finding,
  type FindingConfidence,
  type FindingExplanation,
  type FindingPriority,
  type FindingReviewStatus,
  type FindingSummary,
  type Inspection,
  type InspectionStatus,
  type KnowledgeSource,
  type Repository,
  type ReviewQueueItem,
  type SeverityBreakdown,
} from '@/types/domain';

const toToken = (value: string): string => value.trim().toLowerCase().replace(/[\s-]+/g, '_');

export function toInspectionStatus(value: string | null | undefined): InspectionStatus {
  const token = toToken(value ?? '');
  return isInspectionStatus(token) ? token : 'queued';
}

export function toPriority(value: string | null | undefined): FindingPriority {
  const token = toToken(value ?? '');
  return isFindingPriority(token) ? token : 'low';
}

export function toConfidence(value: string | null | undefined): FindingConfidence {
  const token = toToken(value ?? '');
  return isFindingConfidence(token) ? token : 'unknown';
}

export function toRole(value: string | null | undefined): CryptographicRole {
  const token = toToken(value ?? '');
  return isCryptographicRole(token) ? token : 'unknown';
}

export function toReviewStatus(value: string | null | undefined): FindingReviewStatus | null {
  if (value == null || value === '') return null;
  const token = toToken(value) === 'reviewed' ? 'resolved' : toToken(value);
  return isFindingReviewStatus(token) ? token : null;
}

function toStringList(value: string | string[] | null | undefined): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === 'string' && v.length > 0);
  if (typeof value === 'string' && value.trim()) return [value.trim()];
  return [];
}

function severity(input: ApiInspectionDto['severity'] | undefined): SeverityBreakdown {
  return {
    critical: input?.critical ?? 0,
    high: input?.high ?? 0,
    medium: input?.medium ?? 0,
    low: input?.low ?? 0,
  };
}

function repositoryName(ref: { owner?: string; name?: string }): string {
  const owner = ref.owner?.trim();
  const name = ref.name?.trim() ?? 'repository';
  return owner ? `${owner}/${name}` : name;
}

export function mapRepository(dto: ApiRepositoryDto): Repository {
  return {
    id: dto.id,
    name: repositoryName(dto.repository),
    owner: dto.repository.owner?.trim() || null,
    url: dto.repository.url?.trim() || null,
    language: dto.language || 'Unknown',
    lastInspectedAt: dto.last_inspected_at,
    latestInspectionStatus: dto.latest_inspection_status
      ? toInspectionStatus(dto.latest_inspection_status)
      : null,
    findingsCount: dto.findings_count,
  };
}

export function mapInspection(dto: ApiInspectionDto): Inspection {
  return {
    id: dto.id,
    repositoryId: dto.repository_id,
    repositoryName: repositoryName(dto.repository),
    language: dto.language || 'Unknown',
    commitSha: dto.commit_sha,
    status: toInspectionStatus(dto.status),
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    durationMs: dto.duration_ms,
    filesAnalyzed: dto.files_analyzed,
    findingsCount: dto.findings_count ?? 0,
    severity: severity(dto.severity),
    errorCode: dto.error_code ?? null,
    errorMessage: dto.error_message ?? null,
  };
}

function mapEvidenceLines(excerpt: string, startLine: number, endLine: number | null): EvidenceLine[] {
  const rows = excerpt.replace(/\n$/, '').split('\n');
  const lastHighlighted = endLine ?? startLine;
  return rows.map((text, index) => {
    const number = startLine + index;
    return { number, text, highlighted: number >= startLine && number <= lastHighlighted };
  });
}

export function mapFinding(dto: ApiFindingDto): Finding {
  const { observed, inference, migration, impact, priority, review } = dto;
  const lineStart = observed.location.start_line;
  const lineEnd = observed.location.end_line ?? lineStart;

  return {
    id: dto.id,
    inspectionId: dto.scan_id,
    priority: toPriority(priority.level),
    observed: {
      algorithm: observed.algorithm,
      api: observed.api,
      filePath: observed.location.file_path,
      lineStart,
      lineEnd,
      commitSha: dto.commit_sha,
      repositoryName: repositoryName(dto.repository),
      language: dto.language || 'Python',
      source: mapEvidenceLines(observed.source_excerpt ?? '', lineStart, lineEnd),
    },
    inferred: {
      role: toRole(inference.role),
      confidence: toConfidence(inference.confidence),
      reasons: Array.isArray(inference.rationale)
        ? inference.rationale
        : toStringList(inference.rationale),
    },
    migration: {
      current: migration.current?.trim() || observed.algorithm,
      path: toStringList(migration.review_path),
      summary: migration.rationale ?? '',
      isMigrationCandidate: Boolean(migration.is_migration_candidate),
    },
    impact: {
      scope: 'statically_observed',
      chain: impact.nodes && impact.nodes.length > 0 ? impact.nodes : toStringList(impact.relationships),
    },
    review: review
      ? {
          id: review.id,
          status: toReviewStatus(review.status) ?? 'open',
          assignee: review.assigned_to,
          note: review.note,
          updatedAt: review.updated_at,
        }
      : null,
    aiExplanationAvailable: dto.ai_explanation_available ?? false,
  };
}

export function mapFindingSummary(dto: ApiFindingSummaryDto): FindingSummary {
  return {
    id: dto.id,
    inspectionId: dto.scan_id,
    priority: toPriority(dto.priority),
    algorithm: dto.algorithm,
    api: dto.api,
    role: toRole(dto.role),
    confidence: toConfidence(dto.confidence),
    filePath: dto.file_path,
    lineStart: dto.start_line,
    lineEnd: dto.end_line,
    reviewStatus: toReviewStatus(dto.review_status),
  };
}

export function mapReviewQueueItem(dto: ApiReviewQueueItemDto): ReviewQueueItem {
  return {
    reviewId: dto.review_id,
    findingId: dto.finding_id,
    inspectionId: dto.scan_id,
    priority: toPriority(dto.priority),
    algorithm: dto.algorithm,
    role: toRole(dto.role),
    reviewPath: toStringList(dto.review_path),
    status: toReviewStatus(dto.status) ?? 'open',
    assignee: dto.assigned_to,
    reasons: dto.reasons ?? [],
    filePath: dto.file_path,
    lineStart: dto.start_line,
    updatedAt: dto.updated_at,
  };
}

export function mapExplanation(dto: ApiExplanationDto): FindingExplanation {
  return {
    findingId: dto.finding_id,
    provider: dto.provider,
    model: dto.model,
    promptVersion: dto.prompt_version,
    summary: dto.summary,
    whyItMatters: dto.why_it_matters ?? '',
    evidenceExplanation: dto.evidence_explanation ?? '',
    migrationExplanation: dto.migration_explanation ?? '',
    impactExplanation: dto.impact_explanation ?? '',
    limitations: dto.limitations ?? [],
    cached: dto.cached ?? false,
    generatedAt: dto.generated_at,
  };
}

export function toAssessmentDecision(value: string | null | undefined): AssessmentDecision {
  const token = (value ?? '').trim().toUpperCase();
  return isAssessmentDecision(token) ? token : 'INSUFFICIENT_CONTEXT';
}

export function toContextualRole(value: string | null | undefined): ContextualRole {
  const token = (value ?? '').trim().toUpperCase().replace(/[\s-]+/g, '_');
  return isContextualRole(token) ? token : 'UNKNOWN';
}

export function mapKnowledgeSource(dto: ApiKnowledgeSourceDto): KnowledgeSource {
  return {
    documentId: dto.document_id,
    chunkId: dto.chunk_id,
    title: dto.title,
    publisher: dto.publisher,
    url: dto.url,
    section: dto.section,
    version: dto.version,
    content: dto.content,
    relevanceScore: dto.relevance_score ?? 0,
  };
}

export function mapDomainProfile(
  dto: ApiDomainProfileDto | Record<string, unknown> | undefined,
): DomainProfile | null {
  if (!dto || typeof dto !== 'object') return null;
  const d = dto as ApiDomainProfileDto;
  return {
    domain: d.domain ?? 'GENERAL_SOFTWARE',
    latencySensitivity: d.latency_sensitivity ?? 'UNKNOWN',
    bandwidthConstraint: d.bandwidth_constraint ?? 'UNKNOWN',
    computeConstraint: d.compute_constraint ?? 'UNKNOWN',
    memoryConstraint: d.memory_constraint ?? 'UNKNOWN',
    batteryConstraint: d.battery_constraint ?? 'UNKNOWN',
    offlineOperation: d.offline_operation ?? null,
    signatureFrequency: d.signature_frequency ?? null,
    verificationFrequency: d.verification_frequency ?? null,
    payloadSizeSensitivity: d.payload_size_sensitivity ?? 'UNKNOWN',
    dataLongevity: d.data_longevity ?? null,
    regulatoryRequirements: d.regulatory_requirements ?? [],
    platformConstraints: d.platform_constraints ?? [],
    interoperabilityConstraints: d.interoperability_constraints ?? [],
  };
}

export function mapContextualAssessment(dto: ApiContextualAssessmentDto): ContextualAssessment {
  return {
    id: dto.id ?? null,
    findingId: dto.finding_id,
    fingerprint: dto.fingerprint,
    assessment: toAssessmentDecision(dto.assessment),
    confidence: toConfidence(dto.confidence),
    contextualRole: toContextualRole(dto.contextual_role),
    rationale: dto.rationale,
    pqcMigrationRequired: Boolean(dto.pqc_migration_required),
    migrationCandidate: dto.migration_candidate ?? null,
    alternatives: dto.alternatives ?? [],
    engineeringTradeoffs: dto.engineering_tradeoffs ?? [],
    requiredContext: dto.required_context ?? [],
    evidenceInterpretation: dto.evidence_interpretation ?? '',
    knowledgeSources: (dto.knowledge_sources ?? []).map(mapKnowledgeSource),
    limitations: dto.limitations ?? [],
    domainProfile: mapDomainProfile(dto.domain_profile),
    generatedBy: dto.generated_by ?? 'heuristic_advisor',
    model: dto.model ?? null,
    promptVersion: dto.prompt_version ?? null,
    cached: Boolean(dto.cached),
    createdAt: dto.created_at ?? null,
  };
}
