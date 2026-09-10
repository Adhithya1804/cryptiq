import { useCallback, useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { PageHeader } from '@/components/common/PageHeader';
import { TextField } from '@/components/common/TextField';
import { Button } from '@/components/common/Button';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { submitInspection, toApiError } from '@/services';
import type { ApiError } from '@/types/common';
import {
  validateInspectionInput,
  type InspectionFieldErrors,
} from '@/utils/validation';
import styles from './InspectPage.module.css';

type SubmitState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; error: ApiError };

const ASSURANCES = ['Static inspection', 'Exact commit', 'Repository code is never executed'];

export function InspectPage() {
  useDocumentTitle('Inspect');
  useBreadcrumbs(() => [{ label: 'Inspect' }], []);
  const navigate = useNavigate();

  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [commitSha, setCommitSha] = useState('');
  const [fieldErrors, setFieldErrors] = useState<InspectionFieldErrors>({});
  const [submit, setSubmit] = useState<SubmitState>({ status: 'idle' });

  const isSubmitting = submit.status === 'submitting';

  const clearFieldError = useCallback((field: keyof InspectionFieldErrors) => {
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (isSubmitting) return;

      const validation = validateInspectionInput({ repositoryUrl, commitSha });
      if (!validation.ok) {
        setFieldErrors(validation.errors);
        return;
      }
      setFieldErrors({});
      setSubmit({ status: 'submitting' });

      void submitInspection(validation.value).then(
        (inspection) => navigate(`/history/${encodeURIComponent(inspection.id)}`),
        // Input is deliberately preserved so the user can retry without retyping.
        (cause: unknown) => setSubmit({ status: 'error', error: toApiError(cause) }),
      );
    },
    [commitSha, isSubmitting, navigate, repositoryUrl],
  );

  const submitLabel = useMemo(() => (isSubmitting ? 'Inspecting…' : 'Inspect Repository'), [isSubmitting]);

  return (
    <Page narrow>
      <PageHeader
        kicker="Inspect"
        title="Inspect Repository"
        description="Cryptiq performs static cryptographic inspection of a repository at one exact revision. The repository's code is never executed."
      />

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <TextField
          label="Repository URL"
          name="repositoryUrl"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://github.com/owner/repository"
          value={repositoryUrl}
          onChange={(event) => {
            setRepositoryUrl(event.target.value);
            clearFieldError('repositoryUrl');
          }}
          {...(fieldErrors.repositoryUrl ? { error: fieldErrors.repositoryUrl } : {})}
        />
        <TextField
          label="Commit SHA"
          name="commitSha"
          autoComplete="off"
          spellCheck={false}
          placeholder="40-character commit SHA"
          value={commitSha}
          onChange={(event) => {
            setCommitSha(event.target.value);
            clearFieldError('commitSha');
          }}
          {...(fieldErrors.commitSha ? { error: fieldErrors.commitSha } : {})}
        />

        <div className={styles.submitRow}>
          <Button type="submit" loading={isSubmitting}>
            {submitLabel}
          </Button>
        </div>

        {submit.status === 'error' && (
          <div className={styles.errorBox} role="alert">
            <span className={styles.errorMessage}>{submit.error.message}</span>
            <button
              type="button"
              className={styles.dismiss}
              onClick={() => setSubmit({ status: 'idle' })}
            >
              Retry
            </button>
          </div>
        )}
      </form>

      <ul className={styles.assurances}>
        {ASSURANCES.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Page>
  );
}
