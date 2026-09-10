import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { ProjectsPage } from './ProjectsPage';

describe('ProjectsPage', () => {
  it('renders the empty state (no fabricated rows) when no backend is connected', async () => {
    renderWithProviders(<ProjectsPage />, { route: '/projects' });

    expect(await screen.findByText('No projects yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /inspect a repository/i })).toBeInTheDocument();
    expect(screen.queryByRole('row')).not.toBeInTheDocument();
  });
});
