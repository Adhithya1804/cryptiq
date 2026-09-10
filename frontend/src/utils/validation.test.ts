import { describe, expect, it } from 'vitest';
import { validateInspectionInput } from './validation';

describe('validateInspectionInput', () => {
  const validSha = 'a'.repeat(40);
  const validUrl = 'https://github.com/pyca/cryptography';

  it('accepts a valid GitHub URL and 40-hex SHA, trimming both', () => {
    const result = validateInspectionInput({
      repositoryUrl: `  ${validUrl}  `,
      commitSha: `  ${validSha.toUpperCase()}  `,
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.repositoryUrl).toBe(validUrl);
      expect(result.value.commitSha).toBe(validSha.toUpperCase());
    }
  });

  it('flags missing fields with the design copy', () => {
    const result = validateInspectionInput({ repositoryUrl: '', commitSha: '' });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.repositoryUrl).toBe('Repository URL is required.');
      expect(result.errors.commitSha).toBe('Commit SHA is required.');
    }
  });

  it('rejects a non-GitHub URL', () => {
    const result = validateInspectionInput({
      repositoryUrl: 'https://gitlab.com/foo/bar',
      commitSha: validSha,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.repositoryUrl).toBe('Invalid GitHub repository URL.');
  });

  it('rejects a short or non-hex commit SHA', () => {
    for (const sha of ['abc123', 'z'.repeat(40), `${validSha}0`]) {
      const result = validateInspectionInput({ repositoryUrl: validUrl, commitSha: sha });
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.errors.commitSha).toBe('Invalid commit SHA — expected 40 hex characters.');
      }
    }
  });

  it('accepts a repository URL with a trailing slash', () => {
    const result = validateInspectionInput({ repositoryUrl: `${validUrl}/`, commitSha: validSha });
    expect(result.ok).toBe(true);
  });
});
