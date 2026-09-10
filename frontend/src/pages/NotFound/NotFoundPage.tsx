import { useNavigate } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { EmptyState } from '@/components/common/StateViews';
import { Button } from '@/components/common/Button';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export function NotFoundPage() {
  useDocumentTitle('Not found');
  useBreadcrumbs(() => [{ label: 'Not found' }], []);
  const navigate = useNavigate();

  return (
    <Page>
      <EmptyState
        kicker="404"
        title="This page does not exist"
        description="The address may be mistyped, or the resource is no longer available."
        action={
          <Button size="sm" onClick={() => navigate('/inspect')}>
            Go to Inspect
          </Button>
        }
      />
    </Page>
  );
}
