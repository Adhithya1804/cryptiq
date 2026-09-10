import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route, Navigate } from 'react-router-dom';
import { renderWithProviders } from '@/test/render';
import { DEFAULT_SETTINGS_SECTION } from '@/constants/navigation';
import { SettingsPage } from './SettingsPage';

function renderSettings(initialRoute = '/settings/workspace') {
  return renderWithProviders(
    <Routes>
      <Route path="/settings" element={<Navigate to={`/settings/${DEFAULT_SETTINGS_SECTION}`} replace />} />
      <Route path="/settings/:section" element={<SettingsPage />} />
    </Routes>,
    { route: initialRoute },
  );
}

describe('SettingsPage', () => {
  describe('Navigation and Section Structure', () => {
    it('renders only functional sections in the settings navigation', () => {
      renderSettings('/settings/workspace');

      const nav = screen.getByRole('navigation', { name: /settings sections/i });
      expect(nav).toBeInTheDocument();

      // Functional sections must be present
      expect(screen.getByRole('button', { name: /^workspace$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^analysis$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^cryptographic policy$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^integrations$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^notifications$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^danger zone$/i })).toBeInTheDocument();

      // Removed sections MUST be absent
      expect(screen.queryByRole('button', { name: /access/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /audit/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /security/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /appearance/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /pages/i })).not.toBeInTheDocument();
    });

    it.each([
      ['access', '/settings/access'],
      ['audit', '/settings/audit'],
      ['security', '/settings/security'],
      ['appearance', '/settings/appearance'],
      ['pages', '/settings/pages'],
    ])('redirects invalid/removed section %s to workspace', (_name, route) => {
      renderSettings(route);

      // Should redirect to workspace
      expect(screen.getByRole('heading', { level: 2, name: /^workspace$/i })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 2, name: /access/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 2, name: /audit log/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 2, name: /security/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 2, name: /appearance/i })).not.toBeInTheDocument();
    });

    it('renders analysis section correctly', () => {
      renderSettings('/settings/analysis');
      expect(screen.getByRole('heading', { level: 2, name: /^analysis$/i })).toBeInTheDocument();
      expect(screen.getByText('Static analysis')).toBeInTheDocument();
      expect(screen.getByText('Supported languages')).toBeInTheDocument();
    });

    it('renders cryptographic policy section correctly', () => {
      renderSettings('/settings/crypto');
      expect(screen.getByRole('heading', { level: 2, name: /^cryptographic policy$/i })).toBeInTheDocument();
      expect(screen.getByText('NIST Post-Quantum Cryptography')).toBeInTheDocument();
    });

    it('renders notifications section correctly', () => {
      renderSettings('/settings/notifications');
      expect(screen.getByRole('heading', { level: 2, name: /^notifications$/i })).toBeInTheDocument();
      expect(screen.getByText('New high-priority finding')).toBeInTheDocument();
    });

    it('renders danger zone section correctly', () => {
      renderSettings('/settings/danger');
      expect(screen.getByText('Export workspace data')).toBeInTheDocument();
      expect(screen.getByText('Delete repository')).toBeInTheDocument();
      expect(screen.getByText('Delete workspace')).toBeInTheDocument();
    });
  });

  describe('Integrations & CI/CD Installation', () => {
    it('displays CI/CD with Install CLI action and no Coming Soon label', () => {
      renderSettings('/settings/integrations');

      // GitHub card is present
      expect(screen.getByText('GitHub')).toBeInTheDocument();

      // CI/CD card is present
      expect(screen.getByText('CI/CD')).toBeInTheDocument();

      // "Install CLI" button action is visible
      const installButton = screen.getByRole('button', { name: /install cli/i });
      expect(installButton).toBeInTheDocument();

      // Descriptive purpose is clear
      expect(
        screen.getByText(
          'Install the CRYPTIQ CLI to run cryptographic analysis locally or integrate it into CI workflows.',
        ),
      ).toBeInTheDocument();

      // Supported repository install command is visible
      expect(screen.getAllByText('pip install -e ".[dev]"').length).toBeGreaterThan(0);

      // Verify CI/CD does not have a "Coming Soon" badge
      const comingSoonBadges = screen.getAllByText(/coming soon/i);
      for (const badge of comingSoonBadges) {
        const parentRow = badge.closest('div');
        expect(parentRow?.textContent).not.toContain('CI/CD');
      }
    });

    it('toggles CLI installation instructions and allows copying commands', async () => {
      const user = userEvent.setup();
      renderSettings('/settings/integrations');

      const installButton = screen.getByRole('button', { name: /install cli/i });
      await user.click(installButton);

      // Instructions title should now be visible
      expect(screen.getByText('Installation & CI Usage')).toBeInTheDocument();

      // Check for real supported commands from cryptiq/CLI.md
      expect(screen.getByText('cryptiq version')).toBeInTheDocument();
      expect(screen.getByText(/cryptiq scan \. --format sarif > cryptiq\.sarif/)).toBeInTheDocument();
      expect(screen.getByText(/cryptiq diff --base "origin\/\${github\.base_ref}" --head HEAD/)).toBeInTheDocument();

      // Copy buttons are present and clickable
      const copyButtons = screen.getAllByRole('button', { name: /copy/i });
      expect(copyButtons.length).toBe(4);
      await user.click(copyButtons[0]!);
    });
  });
});
