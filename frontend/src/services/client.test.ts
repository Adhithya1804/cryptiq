import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The client refuses to run without a configured backend; give it one and make
// the guard a no-op so these tests exercise the real request/mapping path.
vi.mock('./config', () => ({
  isBackendConfigured: () => true,
  assertBackendConfigured: () => undefined,
  apiConfig: { baseUrl: 'http://api.test/api/v1', timeoutMs: 5000 },
  NO_BACKEND_MESSAGE: 'no backend',
}));

import {
  createScan,
  getFinding,
  getFindings,
  getReviewQueue,
  getScan,
  updateReviewItem,
} from './client';
import { HttpError } from './errors';

interface Recorded {
  url: URL;
  init: RequestInit;
}

let calls: Recorded[] = [];

/** Await a promise expected to reject, and return the rejection as an HttpError. */
function firstCall(): Recorded {
  const call = calls[0];
  if (!call) throw new Error('no request was made');
  return call;
}

async function caught(promise: Promise<unknown>): Promise<HttpError> {
  try {
    await promise;
  } catch (error) {
    return error as HttpError;
  }
  throw new Error('expected the promise to reject');
}

function respondWith(body: unknown, init: { status?: number } = {}) {
  const status = init.status ?? 200;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, requestInit: RequestInit) => {
      calls.push({ url: new URL(input), init: requestInit });
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(body),
      } as unknown as Response);
    }),
  );
}

beforeEach(() => {
  calls = [];
});
afterEach(() => {
  vi.restoreAllMocks();
});

const INSPECTION = {
  id: 'scan-1',
  repository_id: 'repo-1',
  repository: { provider: 'github', owner: 'pyca', name: 'cryptography', url: null },
  language: 'Python',
  commit_sha: '1f903f5ed2e5e316f345a927555e48535829d8de',
  status: 'QUEUED',
  started_at: null,
  completed_at: null,
  duration_ms: null,
  files_analyzed: null,
  findings_count: 0,
  severity: { critical: 0, high: 0, medium: 0, low: 0 },
};

const SUMMARY = {
  id: 'f-1',
  scan_id: 'scan-1',
  algorithm: 'RSA',
  api: 'RSAPrivateKey.sign',
  operation: 'sign',
  role: 'DIGITAL_SIGNATURE',
  confidence: 'HIGH',
  review_path: 'ML-DSA / SLH-DSA',
  is_migration_candidate: true,
  priority: 'HIGH',
  priority_score: 80,
  file_path: 'src/rsa.py',
  start_line: 10,
  end_line: 12,
  review_status: 'OPEN',
};

describe('createScan', () => {
  it('POSTs the snake_case payload to /scans and maps the inspection', async () => {
    respondWith(INSPECTION, { status: 202 });

    const result = await createScan({
      repositoryUrl: 'https://github.com/pyca/cryptography',
      commitSha: INSPECTION.commit_sha,
    });

    expect(firstCall().url.pathname).toBe('/api/v1/scans');
    expect(firstCall().init.method).toBe('POST');
    expect(JSON.parse(firstCall().init.body as string)).toEqual({
      repository_url: 'https://github.com/pyca/cryptography',
      commit_sha: INSPECTION.commit_sha,
    });
    expect(result.cached).toBe(false);
    expect(result.inspection).toMatchObject({ id: 'scan-1', status: 'queued' });
  });

  it('reports a cached scan (200 + cached:true) without re-queuing', async () => {
    respondWith({ ...INSPECTION, status: 'COMPLETED', findings_count: 1042, cached: true }, { status: 200 });

    const result = await createScan({ repositoryUrl: 'x', commitSha: 'y' });

    expect(result.cached).toBe(true);
    expect(result.inspection.status).toBe('completed');
    expect(result.inspection.findingsCount).toBe(1042);
  });
});

describe('getScan', () => {
  it('reads /scans/{id}', async () => {
    respondWith({ ...INSPECTION, status: 'RUNNING' });
    const inspection = await getScan('scan-1');
    expect(firstCall().url.pathname).toBe('/api/v1/scans/scan-1');
    expect(inspection.status).toBe('running');
  });
});

describe('getFindings', () => {
  it('sends page, page_size and server-side filters, and returns page metadata', async () => {
    respondWith({ items: [SUMMARY], total: 1042, page: 3, page_size: 50, pages: 21 });

    const result = await getFindings('scan-1', {
      page: 3,
      pageSize: 50,
      filters: { algorithm: 'rsa', role: 'digital_signature', priority: 'high', status: 'in_review' },
    });

    const q = firstCall().url.searchParams;
    expect(firstCall().url.pathname).toBe('/api/v1/scans/scan-1/findings');
    expect(q.get('page')).toBe('3');
    expect(q.get('page_size')).toBe('50');
    expect(q.get('algorithm')).toBe('rsa');
    expect(q.get('role')).toBe('digital_signature');
    expect(q.get('priority')).toBe('high');
    expect(q.get('status')).toBe('IN_REVIEW');

    expect(result).toMatchObject({ total: 1042, page: 3, pageSize: 50, pages: 21 });
    expect(result.items[0]).toMatchObject({ algorithm: 'RSA', role: 'digital_signature' });
  });

  it('omits absent filters from the query', async () => {
    respondWith({ items: [], total: 0, page: 1, page_size: 50, pages: 1 });
    await getFindings('scan-1', { page: 1 });
    const q = firstCall().url.searchParams;
    expect(q.has('algorithm')).toBe(false);
    expect(q.has('role')).toBe(false);
    expect(q.has('status')).toBe(false);
  });
});

describe('getFinding', () => {
  it('reads /findings/{id} and maps the nested blocks', async () => {
    respondWith({
      id: 'f-1',
      scan_id: 'scan-1',
      repository: INSPECTION.repository,
      commit_sha: INSPECTION.commit_sha,
      language: 'Python',
      observed: {
        algorithm: 'RSA',
        api: 'RSAPrivateKey.sign',
        operation: 'sign',
        location: { file_path: 'src/rsa.py', start_line: 10, end_line: 12 },
        source_excerpt: 'return key.sign(payload)',
      },
      inference: { role: 'DIGITAL_SIGNATURE', rationale: ['signs data'], confidence: 'HIGH' },
      migration: {
        review_path: 'ML-DSA / SLH-DSA',
        rationale: 'FIPS-204',
        is_migration_candidate: true,
        current: 'RSA',
      },
      impact: { scope: 'STATICALLY_OBSERVED', node_count: 1, nodes: ['sign'], relationships: [] },
      priority: { level: 'HIGH', score: 80, reasons: [] },
      review: {
        id: 'r-1',
        status: 'OPEN',
        assigned_to: null,
        note: null,
        created_at: null,
        updated_at: null,
      },
      ai_explanation_available: false,
    });

    const finding = await getFinding('f-1');
    expect(firstCall().url.pathname).toBe('/api/v1/findings/f-1');
    expect(finding.observed.source.map((l) => l.text).join('\n')).toBe('return key.sign(payload)');
    expect(finding.inferred.role).toBe('digital_signature');
    expect(finding.review?.id).toBe('r-1');
  });
});

describe('getReviewQueue', () => {
  it('paginates and derives pages from total', async () => {
    respondWith({
      items: [
        {
          review_id: 'r-1',
          finding_id: 'f-1',
          scan_id: 'scan-1',
          algorithm: 'RSA',
          api: 'RSAPrivateKey.sign',
          role: 'DIGITAL_SIGNATURE',
          review_path: 'ML-DSA / SLH-DSA',
          priority: 'HIGH',
          priority_score: 80,
          status: 'OPEN',
          assigned_to: null,
          note: null,
          reasons: ['post-quantum'],
          file_path: 'src/rsa.py',
          start_line: 10,
          updated_at: null,
        },
      ],
      total: 132,
    });

    const result = await getReviewQueue({ page: 1, pageSize: 50, filters: { algorithm: 'rsa' } });
    expect(firstCall().url.pathname).toBe('/api/v1/review-queue');
    expect(firstCall().url.searchParams.get('page')).toBe('1');
    expect(firstCall().url.searchParams.get('algorithm')).toBe('rsa');
    expect(result.total).toBe(132);
    expect(result.pages).toBe(3);
    expect(result.items[0]).toMatchObject({ reviewId: 'r-1', algorithm: 'RSA' });
  });
});

describe('updateReviewItem', () => {
  it('PATCHes /review-items/{id} with only the fields provided', async () => {
    respondWith({
      id: 'r-1',
      status: 'IN_REVIEW',
      assigned_to: 'alice',
      note: null,
      created_at: null,
      updated_at: '2026-09-10T00:00:00',
    });

    const review = await updateReviewItem('r-1', { status: 'in_review' });

    expect(firstCall().url.pathname).toBe('/api/v1/review-items/r-1');
    expect(firstCall().init.method).toBe('PATCH');
    expect(JSON.parse(firstCall().init.body as string)).toEqual({ status: 'IN_REVIEW' });
    expect(review).toMatchObject({ id: 'r-1', status: 'in_review', assignee: 'alice' });
  });

  it('can clear the assignee with an explicit null', async () => {
    respondWith({ id: 'r-1', status: 'OPEN', assigned_to: null, note: null, created_at: null, updated_at: null });
    await updateReviewItem('r-1', { assignedTo: null });
    expect(JSON.parse(firstCall().init.body as string)).toEqual({ assigned_to: null });
  });

  it('propagates a 409 INVALID_REVIEW_TRANSITION as an HttpError with that code', async () => {
    respondWith(
      { error: { code: 'INVALID_REVIEW_TRANSITION', message: 'A review cannot move from RESOLVED to OPEN.' } },
      { status: 409 },
    );

    const error = await caught(updateReviewItem('r-1', { status: 'open' }));
    expect(error).toBeInstanceOf(HttpError);
    expect(error.code).toBe('INVALID_REVIEW_TRANSITION');
    expect(error.status).toBe(409);
  });
});

describe('API errors', () => {
  it('surfaces a 404 from getScan as an HttpError', async () => {
    respondWith({ error: { code: 'not_found', message: 'No inspection with id "nope".' } }, { status: 404 });
    const error = await caught(getScan('nope'));
    expect(error).toBeInstanceOf(HttpError);
    expect(error.status).toBe(404);
    expect(error.message).toContain('No inspection');
  });

  it('surfaces a 422 validation error from getFindings', async () => {
    respondWith({ error: { code: 'validation_error', message: "'bad' is not a valid priority." } }, { status: 422 });
    const error = await caught(getFindings('scan-1', { filters: { priority: 'bad' as never } }));
    expect(error).toBeInstanceOf(HttpError);
    expect(error.status).toBe(422);
  });
});
