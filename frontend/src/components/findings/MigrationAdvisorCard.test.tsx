import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import type { ContextualAssessment, Finding } from '@/types/domain';
import type * as Services from '@/services';
import { MigrationAdvisorCard } from './MigrationAdvisorCard';

const fetchMigrationAssessment = vi.hoisted(() => vi.fn());

vi.mock('@/services', async (importOriginal) => ({
  ...(await importOriginal<typeof Services>()),
  fetchMigrationAssessment,
}));

function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'f-sha256-tile',
    inspectionId: 's1',
    priority: 'low',
    observed: {
      algorithm: 'SHA-256',
      api: 'hashes.SHA256',
      filePath: 'src/drone/tile_cache.py',
      lineStart: 142,
      lineEnd: 142,
      commitSha: 'c1d2e3f4',
      repositoryName: 'drone-systems/nav',
      language: 'Python',
      source: [],
    },
    inferred: { role: 'hash', confidence: 'high', reasons: ['Used for content addressing'] },
    migration: { current: 'SHA-256', path: ['HASH / POLICY REVIEW'], summary: '', isMigrationCandidate: false },
    impact: { scope: 'statically_observed', chain: [] },
    review: null,
    aiExplanationAvailable: true,
    ...overrides,
  };
}

function makeAssessment(overrides: Partial<ContextualAssessment> = {}): ContextualAssessment {
  return {
    id: 'ma-1',
    findingId: 'f-sha256-tile',
    fingerprint: 'sha256-tile-fingerprint',
    assessment: 'KEEP',
    confidence: 'high',
    contextualRole: 'CONTENT_ADDRESSING',
    rationale:
      'SHA-256 is utilized strictly for map tile deduplication and content addressing. As a collision-resistant cryptographic hash, it is not broken by Shor\'s algorithm and must not be mapped to post-quantum signature schemes like ML-DSA.',
    pqcMigrationRequired: false,
    migrationCandidate: null,
    alternatives: ['SHA-384', 'SHA-512', 'SHAKE256'],
    engineeringTradeoffs: [
      'Zero signature size overhead compared to lattice schemes',
      'Minimal compute overhead on embedded ARM Cortex-M processor',
    ],
    requiredContext: ['Deployment platform', 'Telemetry bandwidth'],
    evidenceInterpretation: 'Content addressing tile cache line 142',
    knowledgeSources: [
      {
        documentId: 'NIST SP 800-131A',
        chunkId: 'sp800-131a-hash',
        title: 'Transitioning the Use of Cryptographic Algorithms and Key Lengths',
        publisher: 'NIST',
        url: 'https://csrc.nist.gov/publications/detail/sp/800-131a/rev-2/final',
        section: '5.1.2',
        version: 'Rev. 2',
        content: 'SHA-256 remains acceptable for hashing, data integrity, and content addressing beyond 2030.',
        relevanceScore: 0.95,
      },
    ],
    limitations: ['Assumes SHA-256 is not reused for authentication tokens'],
    domainProfile: {
      domain: 'AUTONOMOUS_DRONE',
      latencySensitivity: 'HIGH',
      bandwidthConstraint: 'HIGH',
      computeConstraint: 'HIGH',
      memoryConstraint: 'MEDIUM',
      batteryConstraint: 'HIGH',
      offlineOperation: true,
      payloadSizeSensitivity: 'HIGH',
      dataLongevity: 'LONG_TERM',
      regulatoryRequirements: [],
      platformConstraints: ['arm-cortex-m'],
      interoperabilityConstraints: ['mavlink'],
    },
    generatedBy: 'ContextAdvisorService',
    model: 'gemini-2.5-flash',
    promptVersion: 'context-advisor-v1',
    cached: false,
    createdAt: '2026-09-10T12:00:00Z',
    ...overrides,
  };
}

describe('MigrationAdvisorCard', () => {
  beforeEach(() => {
    fetchMigrationAssessment.mockReset();
  });

  it('renders closed toggle button initially', () => {
    renderWithProviders(<MigrationAdvisorCard finding={makeFinding()} />);
    expect(
      screen.getByRole('button', { name: /context-aware migration advisor/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/tier 1 · deterministic fact/i)).not.toBeInTheDocument();
  });

  it('shows loading state while assessment is being fetched', async () => {
    const user = userEvent.setup();
    let resolve!: (value: ContextualAssessment) => void;
    fetchMigrationAssessment.mockReturnValue(
      new Promise<ContextualAssessment>((r) => {
        resolve = r;
      }),
    );

    renderWithProviders(<MigrationAdvisorCard finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /context-aware migration advisor/i }));

    expect(screen.getByText(/synthesizing context and authoritative standards/i)).toBeInTheDocument();
    resolve(makeAssessment());
    expect(await screen.findByText(/DECISION: KEEP/i)).toBeInTheDocument();
  });

  it('renders all three epistemic tiers with authoritative sources and trade-offs', async () => {
    const user = userEvent.setup();
    fetchMigrationAssessment.mockResolvedValue(makeAssessment());

    renderWithProviders(<MigrationAdvisorCard finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /context-aware migration advisor/i }));

    // Tier 1: Fact
    expect(await screen.findByText(/tier 1 · deterministic fact/i)).toBeInTheDocument();
    expect(screen.getByText('hashes.SHA256')).toBeInTheDocument();
    expect(screen.getAllByText('CONTENT_ADDRESSING').length).toBeGreaterThanOrEqual(1);

    // Tier 2: Context
    expect(screen.getByText(/tier 2 · application context/i)).toBeInTheDocument();
    expect(screen.getByText('AUTONOMOUS_DRONE')).toBeInTheDocument();

    // Tier 3: Recommendation
    expect(screen.getByText(/tier 3 · contextual recommendation/i)).toBeInTheDocument();
    expect(screen.getByText(/DECISION: KEEP — Fit-for-purpose in this semantic role/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 is utilized strictly for map tile deduplication/i)).toBeInTheDocument();
    expect(screen.getByText(/Zero signature size overhead compared to lattice schemes/i)).toBeInTheDocument();

    // Authoritative Citations
    expect(screen.getByText(/NIST SP 800-131A/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 remains acceptable for hashing/i)).toBeInTheDocument();
  });

  it('handles error state and allows retry', async () => {
    const user = userEvent.setup();
    fetchMigrationAssessment.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<MigrationAdvisorCard finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /context-aware migration advisor/i }));

    expect(await screen.findByText(/failed to evaluate migration advice: Network error/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();

    fetchMigrationAssessment.mockResolvedValue(makeAssessment());
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByText(/DECISION: KEEP/i)).toBeInTheDocument();
  });
});
