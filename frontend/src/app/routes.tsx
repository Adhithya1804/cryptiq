import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { DEFAULT_SETTINGS_SECTION } from '@/constants/navigation';
import { InspectPage } from '@/pages/Inspect/InspectPage';

/**
 * Route table. The Inspect screen (the product's entry point) is bundled with
 * the shell; every other screen is a lazily-loaded chunk so the initial payload
 * stays small.
 */
export const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppLayout />,
      children: [
      { index: true, element: <Navigate to="/inspect" replace /> },
      { path: 'inspect', element: <InspectPage /> },
      {
        path: 'projects',
        lazy: () => import('@/pages/Projects/ProjectsPage').then((m) => ({ Component: m.ProjectsPage })),
      },
      {
        path: 'projects/:projectId',
        lazy: () =>
          import('@/pages/ProjectDetail/ProjectDetailPage').then((m) => ({
            Component: m.ProjectDetailPage,
          })),
      },
      {
        path: 'history',
        lazy: () => import('@/pages/History/HistoryPage').then((m) => ({ Component: m.HistoryPage })),
      },
      {
        path: 'history/:inspectionId',
        lazy: () =>
          import('@/pages/InspectionReport/InspectionReportPage').then((m) => ({
            Component: m.InspectionReportPage,
          })),
      },
      {
        path: 'findings/:findingId',
        lazy: () =>
          import('@/pages/FindingDetail/FindingDetailPage').then((m) => ({
            Component: m.FindingDetailPage,
          })),
      },
      {
        path: 'review',
        lazy: () => import('@/pages/Review/ReviewPage').then((m) => ({ Component: m.ReviewPage })),
      },
      { path: 'settings', element: <Navigate to={`/settings/${DEFAULT_SETTINGS_SECTION}`} replace /> },
      {
        path: 'settings/:section',
        lazy: () => import('@/pages/Settings/SettingsPage').then((m) => ({ Component: m.SettingsPage })),
      },
      {
        path: '*',
        lazy: () => import('@/pages/NotFound/NotFoundPage').then((m) => ({ Component: m.NotFoundPage })),
      },
      ],
    },
  ],
  { future: { v7_relativeSplatPath: true } },
);
