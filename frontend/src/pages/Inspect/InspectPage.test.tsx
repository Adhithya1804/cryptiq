import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { NO_BACKEND_MESSAGE } from '@/services';
import { InspectPage } from './InspectPage';

const VALID_URL = 'https://github.com/pyca/cryptography';
const VALID_SHA = 'a'.repeat(40);

describe('InspectPage', () => {
  it('shows field-level validation before making a request', async () => {
    const user = userEvent.setup();
    renderWithProviders(<InspectPage />);

    await user.click(screen.getByRole('button', { name: /inspect repository/i }));

    expect(await screen.findByText('Repository URL is required.')).toBeInTheDocument();
    expect(screen.getByText('Commit SHA is required.')).toBeInTheDocument();
  });

  it('rejects a non-GitHub URL and an invalid SHA', async () => {
    const user = userEvent.setup();
    renderWithProviders(<InspectPage />);

    await user.type(screen.getByLabelText('Repository URL'), 'https://example.com/x/y');
    await user.type(screen.getByLabelText('Commit SHA'), 'nope');
    await user.click(screen.getByRole('button', { name: /inspect repository/i }));

    expect(await screen.findByText('Invalid GitHub repository URL.')).toBeInTheDocument();
    expect(screen.getByText('Invalid commit SHA — expected 40 hex characters.')).toBeInTheDocument();
  });

  it('surfaces the connection error and preserves input when no backend is connected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<InspectPage />);

    await user.type(screen.getByLabelText('Repository URL'), VALID_URL);
    await user.type(screen.getByLabelText('Commit SHA'), VALID_SHA);
    await user.click(screen.getByRole('button', { name: /inspect repository/i }));

    expect(await screen.findByText(NO_BACKEND_MESSAGE)).toBeInTheDocument();
    expect(screen.getByLabelText('Repository URL')).toHaveValue(VALID_URL);
    expect(screen.getByLabelText('Commit SHA')).toHaveValue(VALID_SHA);
  });

  it('clears a field error as soon as the user edits that field', async () => {
    const user = userEvent.setup();
    renderWithProviders(<InspectPage />);

    await user.click(screen.getByRole('button', { name: /inspect repository/i }));
    expect(await screen.findByText('Repository URL is required.')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Repository URL'), 'h');
    await waitFor(() => expect(screen.queryByText('Repository URL is required.')).not.toBeInTheDocument());
  });
});
