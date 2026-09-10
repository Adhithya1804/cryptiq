import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import type { Finding, FindingExplanation } from '@/types/domain';
import type * as Services from '@/services';
import { AiExplanation } from './AiExplanation';

const fetchFindingExplanation = vi.hoisted(() => vi.fn());

vi.mock('@/services', async (importOriginal) => ({
  ...(await importOriginal<typeof Services>()),
  fetchFindingExplanation,
}));

function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'f1',
    inspectionId: 's1',
    priority: 'high',
    observed: {
      algorithm: 'RSA',
      api: 'RSAPrivateKey.sign',
      filePath: 'src/rsa.py',
      lineStart: 40,
      lineEnd: 43,
      commitSha: 'abc1234567',
      repositoryName: 'pyca/cryptography',
      language: 'Python',
      source: [],
    },
    inferred: { role: 'digital_signature', confidence: 'high', reasons: [] },
    migration: { current: 'RSA', path: ['ML-DSA / SLH-DSA'], summary: '', isMigrationCandidate: true },
    impact: { scope: 'statically_observed', chain: [] },
    review: null,
    aiExplanationAvailable: true,
    ...overrides,
  };
}

function makeExplanation(overrides: Partial<FindingExplanation> = {}): FindingExplanation {
  return {
    findingId: 'f1',
    provider: 'gemini',
    model: 'gemini-2.5-flash',
    promptVersion: 'gemini-explanation-v1',
    summary: 'RSA private-key signing is used here.',
    whyItMatters: 'Signatures are in scope for post-quantum review.',
    evidenceExplanation: 'The excerpt calls key.sign on an RSAPrivateKey.',
    migrationExplanation: 'Cryptiq routes this to its signature review path.',
    impactExplanation: 'The observed scope is the Signer class.',
    limitations: ['Only the shown lines were considered.'],
    cached: false,
    generatedAt: null,
    ...overrides,
  };
}

describe('AiExplanation', () => {
  beforeEach(() => {
    fetchFindingExplanation.mockReset();
  });

  it('shows the unavailable line and no toggle when the backend cannot explain', () => {
    renderWithProviders(<AiExplanation finding={makeFinding({ aiExplanationAvailable: false })} />);
    expect(screen.getByText('AI explanation unavailable for this finding.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /explain with ai/i })).not.toBeInTheDocument();
  });

  it('shows a loading state while the explanation request is in flight', async () => {
    const user = userEvent.setup();
    let resolve!: (value: FindingExplanation) => void;
    fetchFindingExplanation.mockReturnValue(
      new Promise<FindingExplanation>((r) => {
        resolve = r;
      }),
    );

    renderWithProviders(<AiExplanation finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /explain with ai/i }));

    expect(await screen.findByText(/generating explanation/i)).toBeInTheDocument();
    resolve(makeExplanation());
    expect(await screen.findByText('RSA private-key signing is used here.')).toBeInTheDocument();
  });

  it('renders the structured explanation beside the deterministic evidence', async () => {
    const user = userEvent.setup();
    fetchFindingExplanation.mockResolvedValue(makeExplanation());

    renderWithProviders(<AiExplanation finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /explain with ai/i }));

    // Deterministic facts remain visible and labelled as such.
    expect(await screen.findByText(/deterministic finding/i)).toBeInTheDocument();
    expect(screen.getByText('RSAPrivateKey.sign')).toBeInTheDocument();

    // Structured AI sections render.
    expect(screen.getByText('AI explanation')).toBeInTheDocument();
    expect(screen.getByText(/signatures are in scope/i)).toBeInTheDocument();
    expect(screen.getByText('Migration context')).toBeInTheDocument();
    expect(screen.getByText(/only the shown lines were considered/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot change the detected algorithm/i)).toBeInTheDocument();
  });

  it('degrades gracefully when the explanation request fails, leaving the finding intact', async () => {
    const user = userEvent.setup();
    fetchFindingExplanation.mockRejectedValue(new Error('boom'));

    renderWithProviders(<AiExplanation finding={makeFinding()} />);
    await user.click(screen.getByRole('button', { name: /explain with ai/i }));

    // Evidence facts still render from the deterministic finding...
    expect(await screen.findByText('RSAPrivateKey.sign')).toBeInTheDocument();
    // ...and the failure is contained to this panel.
    expect(await screen.findByText(/AI explanation is unavailable right now/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});
