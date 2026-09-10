import { RouterProvider } from 'react-router-dom';
import { PreferencesProvider } from './providers/PreferencesProvider';
import { ToastProvider } from './providers/ToastProvider';
import { router } from './routes';

export function App() {
  return (
    <PreferencesProvider>
      <ToastProvider>
        <RouterProvider router={router} future={{ v7_startTransition: true }} />
      </ToastProvider>
    </PreferencesProvider>
  );
}
