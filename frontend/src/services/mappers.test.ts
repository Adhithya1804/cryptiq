import { describe, expect, it } from 'vitest';
import type { ApiFindingDto, ApiInspectionDto } from '@/types/api';
import { mapFinding, mapInspection, toReviewStatus, toRole } from './mappers';

const baseFinding: ApiFindingDto = {
  id: 'f1',
  scan_id: 's1',
  repository: { provider: 'github', owner: 'pyca', name: 'cryptography', url: null },
  commit_sha: '1f903f5e9d8de0c4b2a19d8de0c4b2a19d8de0c4',
  language: 'Python',
  observed: {
    algorithm: 'RSA',
    api: 'RSAPrivateKey.sign',
    location: { file_path: 'src/rsa.py', start_line: 40, end_line: 43 },
    source_excerpt: 'def sign(self):\n    return self._backend.sign()\n',
  },
  inference: { role: 'DIGITAL_SIGNATURE', rationale: ['Direct module API'], confidence: 'HIGH' },
  migration: { review_path: 'ML-DSA / SLH-DSA', rationale: 'Consult the signature review path.', is_migration_candidate: true },
  impact: { scope: 'STATICALLY_OBSERVED', nodes: ['sign()', 'issue_cert()'] },
  priority: { level: 'HIGH', score: 80, reasons: ['public-key primitive'] },
  review: null,
  ai_explanation_available: true,
};

describe('mapFinding', () => {
  it('keeps observed facts and inferred judgement in separate groups', () => {
    const finding = mapFinding(baseFinding);
    expect(finding.observed.algorithm).toBe('RSA');
    expect(finding.observed.api).toBe('RSAPrivateKey.sign');
    expect(finding.observed).not.toHaveProperty('role');
    expect(finding.observed).not.toHaveProperty('confidence');
    expect(finding.inferred.role).toBe('digital_signature');
    expect(finding.inferred.confidence).toBe('high');
  });

  it('marks the exact evidence lines as highlighted', () => {
    const finding = mapFinding(baseFinding);
    expect(finding.observed.source.map((line) => line.number)).toEqual([40, 41]);
    expect(finding.observed.source.every((line) => line.highlighted)).toBe(true);
  });

  it('normalises the migration review path into a list', () => {
    expect(mapFinding(baseFinding).migration.path).toEqual(['ML-DSA / SLH-DSA']);
  });

  it('falls back to safe defaults on a malformed payload', () => {
    const malformed = {
      ...baseFinding,
      inference: { role: 'something-unexpected', rationale: 'n/a', confidence: '' },
      priority: { level: 'unheard-of' },
      impact: { scope: 'x' },
    } as unknown as ApiFindingDto;
    const finding = mapFinding(malformed);
    expect(finding.inferred.role).toBe('unknown');
    expect(finding.inferred.confidence).toBe('unknown');
    expect(finding.priority).toBe('low');
    expect(finding.impact.chain).toEqual([]);
  });
});

describe('mapInspection', () => {
  const dto: ApiInspectionDto = {
    id: 's1',
    repository_id: 'r1',
    repository: { provider: 'github', owner: 'pyca', name: 'cryptography', url: null },
    language: 'Python',
    commit_sha: 'abc',
    status: 'COMPLETED',
    started_at: null,
    completed_at: null,
    duration_ms: null,
    files_analyzed: null,
    findings_count: 5,
    severity: { high: 2 },
  };

  it('defaults every severity bucket and lowercases status', () => {
    const inspection = mapInspection(dto);
    expect(inspection.status).toBe('completed');
    expect(inspection.severity).toEqual({ critical: 0, high: 2, medium: 0, low: 0 });
    expect(inspection.repositoryName).toBe('pyca/cryptography');
  });
});

describe('enum normalisers', () => {
  it('maps the backend REVIEWED status onto resolved', () => {
    expect(toReviewStatus('REVIEWED')).toBe('resolved');
    expect(toReviewStatus('in_review')).toBe('in_review');
    expect(toReviewStatus(null)).toBeNull();
  });

  it('lowercases and underscores role tokens', () => {
    expect(toRole('KEY_ESTABLISHMENT')).toBe('key_establishment');
    expect(toRole('Symmetric Encryption')).toBe('symmetric_encryption');
  });
});
