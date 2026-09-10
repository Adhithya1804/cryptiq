import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { PageHeader } from '@/components/common/PageHeader';
import { Button } from '@/components/common/Button';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { EmptyState, Skeleton } from '@/components/common/StateViews';
import { RepositoryIdentity } from '@/components/common/RepositoryIdentity';
import { InspectionStatusBadge } from '@/components/common/StatusIndicators';
import { Cell, ClickableRow, HeaderCell, HeaderRow, Row, TableScroll } from '@/components/common/Table';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { fetchProjects } from '@/services';
import { formatCount, formatRelativeTime } from '@/utils/format';
import type { Repository } from '@/types/domain';

const TEMPLATE = 'minmax(200px, 1.6fr) 150px 160px 110px';
const MIN_WIDTH = 720;

function Head() {
  return (
    <HeaderRow template={TEMPLATE}>
      <HeaderCell>Repository</HeaderCell>
      <HeaderCell>Last inspected</HeaderCell>
      <HeaderCell>Latest status</HeaderCell>
      <HeaderCell>Findings</HeaderCell>
    </HeaderRow>
  );
}

export function ProjectsPage() {
  useDocumentTitle('Projects');
  useBreadcrumbs(() => [{ label: 'Projects' }], []);
  const navigate = useNavigate();

  const loader = useCallback((signal: AbortSignal) => fetchProjects(signal), []);
  const { state, reload } = useAsyncResource(loader, []);

  return (
    <Page>
      <PageHeader
        title="Projects"
        description="Repositories Cryptiq has inspected. Open one for its inspection history and latest findings."
      />

      <div style={{ marginTop: 24 }}>
        <AsyncBoundary
          state={state}
          onRetry={reload}
          errorTitle="Projects could not be loaded"
          loading={<ProjectsSkeleton />}
          isEmpty={(rows: Repository[]) => rows.length === 0}
          empty={
            <EmptyState
              kicker="Projects"
              title="No projects yet"
              description="Once you inspect a repository it appears here with its history and latest findings."
              action={
                <Button size="sm" onClick={() => navigate('/inspect')}>
                  Inspect a repository
                </Button>
              }
            />
          }
        >
          {(rows) => (
            <TableScroll minWidth={MIN_WIDTH}>
              <Head />
              {rows.map((project) => (
                <ProjectRow
                  key={project.id}
                  project={project}
                  onOpen={() => navigate(`/projects/${project.id}`)}
                />
              ))}
            </TableScroll>
          )}
        </AsyncBoundary>
      </div>
    </Page>
  );
}

function ProjectRow({ project, onOpen }: { project: Repository; onOpen: () => void }) {
  return (
    <ClickableRow template={TEMPLATE} onClick={onOpen} ariaLabel={`Open ${project.name}`}>
      <Cell stack>
        <RepositoryIdentity name={project.name} secondary={project.language} />
      </Cell>
      <Cell>{formatRelativeTime(project.lastInspectedAt)}</Cell>
      <Cell>
        {project.latestInspectionStatus ? (
          <InspectionStatusBadge status={project.latestInspectionStatus} />
        ) : (
          <span style={{ color: 'var(--text-3)' }}>—</span>
        )}
      </Cell>
      <Cell mono strong>
        {formatCount(project.findingsCount)}
      </Cell>
    </ClickableRow>
  );
}

function ProjectsSkeleton() {
  return (
    <TableScroll minWidth={MIN_WIDTH}>
      <Head />
      {[0, 1, 2].map((row) => (
        <Row key={row} template={TEMPLATE}>
          <Cell>
            <Skeleton width={180} height={12} />
          </Cell>
          <Cell>
            <Skeleton width={90} height={12} />
          </Cell>
          <Cell>
            <Skeleton width={80} height={12} />
          </Cell>
          <Cell>
            <Skeleton width={40} height={12} />
          </Cell>
        </Row>
      ))}
    </TableScroll>
  );
}
