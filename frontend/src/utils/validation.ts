/**
 * Input validation for the Inspect form. Runs before any request is made.
 * Patterns and messages match the design source verbatim.
 */

export const GITHUB_URL_PATTERN = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/i;
export const COMMIT_SHA_PATTERN = /^[0-9a-f]{40}$/i;

export interface InspectionInput {
  repositoryUrl: string;
  commitSha: string;
}

export interface InspectionFieldErrors {
  repositoryUrl?: string;
  commitSha?: string;
}

/** A validated, trimmed pair. Only produced when both fields pass. */
export interface ValidatedInspectionInput {
  readonly repositoryUrl: string;
  readonly commitSha: string;
}

export type InspectionValidation =
  | { ok: true; value: ValidatedInspectionInput }
  | { ok: false; errors: InspectionFieldErrors };

export function validateInspectionInput(input: InspectionInput): InspectionValidation {
  const repositoryUrl = input.repositoryUrl.trim();
  const commitSha = input.commitSha.trim();
  const errors: InspectionFieldErrors = {};

  if (!repositoryUrl) {
    errors.repositoryUrl = 'Repository URL is required.';
  } else if (!GITHUB_URL_PATTERN.test(repositoryUrl)) {
    errors.repositoryUrl = 'Invalid GitHub repository URL.';
  }

  if (!commitSha) {
    errors.commitSha = 'Commit SHA is required.';
  } else if (!COMMIT_SHA_PATTERN.test(commitSha)) {
    errors.commitSha = 'Invalid commit SHA — expected 40 hex characters.';
  }

  if (errors.repositoryUrl || errors.commitSha) {
    return { ok: false, errors };
  }
  return { ok: true, value: { repositoryUrl, commitSha } };
}
