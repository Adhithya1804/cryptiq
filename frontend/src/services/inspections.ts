/**
 * Inspections — the history list, a single scan's state, and starting a scan.
 *
 * "Inspection" and "scan" are the same entity. Reads of a single scan and the
 * submit both go through the canonical `/scans` client; the history list still
 * uses `/inspections` (the collection the backend exposes for it).
 */

import type { Finding, Inspection, SubmittedScan } from '@/types/domain';
import type { ApiInspectionDto, ApiListEnvelope } from '@/types/api';
import type { ValidatedInspectionInput } from '@/utils/validation';
import { isBackendConfigured } from './config';
import { createScan, getScan } from './client';
import { request } from './http';
import { mapInspection } from './mappers';
import { fetchFinding } from './findings';

export async function fetchHistory(signal?: AbortSignal): Promise<Inspection[]> {
  if (!isBackendConfigured()) return [];
  const body = await request<ApiListEnvelope<ApiInspectionDto>>('/inspections', signal ? { signal } : {});
  return body.items.map(mapInspection);
}

export async function fetchInspection(inspectionId: string, signal?: AbortSignal): Promise<Inspection> {
  return getScan(inspectionId, signal);
}

/** Start a scan and learn whether it was queued fresh or served from cache. */
export async function submitScan(input: ValidatedInspectionInput): Promise<SubmittedScan> {
  return createScan(input);
}

/** Start a scan, returning just the inspection (back-compat surface). Rejects —
 *  never fabricates a result — when no backend is connected. */
export async function submitInspection(input: ValidatedInspectionInput): Promise<Inspection> {
  const { inspection } = await createScan(input);
  return inspection;
}

export { fetchFinding };
export type { Finding };
