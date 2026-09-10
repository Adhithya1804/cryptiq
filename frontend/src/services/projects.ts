/**
 * Projects (repositories Cryptiq knows about).
 */

import type { Inspection, Repository } from '@/types/domain';
import type { ApiInspectionDto, ApiListEnvelope, ApiRepositoryDto } from '@/types/api';
import { assertBackendConfigured, isBackendConfigured } from './config';
import { request } from './http';
import { mapInspection, mapRepository } from './mappers';

export async function fetchProjects(signal?: AbortSignal): Promise<Repository[]> {
  if (!isBackendConfigured()) return [];
  const body = await request<ApiListEnvelope<ApiRepositoryDto>>('/projects', signal ? { signal } : {});
  return body.items.map(mapRepository);
}

export async function fetchProject(projectId: string, signal?: AbortSignal): Promise<Repository> {
  assertBackendConfigured();
  const body = await request<ApiRepositoryDto>(
    `/projects/${encodeURIComponent(projectId)}`,
    signal ? { signal } : {},
  );
  return mapRepository(body);
}

export async function fetchProjectInspections(
  projectId: string,
  signal?: AbortSignal,
): Promise<Inspection[]> {
  assertBackendConfigured();
  const body = await request<ApiListEnvelope<ApiInspectionDto>>(
    `/projects/${encodeURIComponent(projectId)}/inspections`,
    signal ? { signal } : {},
  );
  return body.items.map(mapInspection);
}
