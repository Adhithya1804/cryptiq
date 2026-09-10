import type { ReactElement, ReactNode } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PreferencesProvider } from '@/app/providers/PreferencesProvider';
import { ToastProvider } from '@/app/providers/ToastProvider';
import { BreadcrumbProvider } from '@/components/layout/Breadcrumbs';

interface Options extends Omit<RenderOptions, 'wrapper'> {
  route?: string;
}

/** Render a component inside the app's providers and a memory router. */
export function renderWithProviders(ui: ReactElement, { route = '/', ...options }: Options = {}) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter
        initialEntries={[route]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <PreferencesProvider>
          <ToastProvider>
            <BreadcrumbProvider>{children}</BreadcrumbProvider>
          </ToastProvider>
        </PreferencesProvider>
      </MemoryRouter>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
