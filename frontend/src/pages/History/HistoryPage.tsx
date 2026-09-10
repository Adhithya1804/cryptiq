import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { PageHeader } from '@/components/common/PageHeader';
import { Button } from '@/components/common/Button';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { EmptyState, Skeleton } from '@/components/common/StateViews';
import { RepositoryIdentity } from '@/components/common/RepositoryIdentity';
import { StatusDot } from '@/components/common/StatusIndicators';
import { Cell, ClickableRow, HeaderCell, HeaderRow, Row, TableScroll } from '@/components/common/Table';
import { SeverityCluster } from '@/components/inspection/Severity';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { fetchHistory } from '@/services';
import { getInspectionStatusMeta } from '@/constants/domain';
import { formatCount, formatDate, formatDuration, shortCommit } from '@/utils/format';
import type { Inspection } from '@/types/domain';

const TEMPLATE = 'minmax(160px, 1.4fr) 130px 150px 110px 70px 80px 220px 90px';
const MIN_WIDTH = 1000;

function Head() {
  return (
    <HeaderRow template={TEMPLATE}>
      <HeaderCell>Repository</HeaderCell>
      <HeaderCell>Commit</HeaderCell>
      <HeaderCell>Date</HeaderCell>
      <HeaderCell>Status</HeaderCell>
      <HeaderCell>Files</HeaderCell>
      <HeaderCell>Findings</HeaderCell>
      <HeaderCell>Critical / High / Med / Low</HeaderCell>
      <HeaderCell>Duration</HeaderCell>
    </HeaderRow>
  );
}

export function HistoryPage() {
  useDocumentTitle('History');
  useBreadcrumbs(() => [{ label: 'History' }], []);
  const navigate = useNavigate();

  const loader = useCallback((signal: AbortSignal) => fetchHistory(signal), []);
  const { state, reload } = useAsyncResource(loader, []);

  return (
    <Page>
      <PageHeader
        title="History"
        description="Previous inspections. Each inspection reports on one repository at one exact commit — open one for its full report."
      />

      <div style={{ marginTop: 20 }}>
        <AsyncBoundary
          state={state}
          onRetry={reload}
          errorTitle="History could not be loaded"
          loading={<HistorySkeleton />}
          isEmpty={(rows: Inspection[]) => rows.length === 0}
          empty={
            <EmptyState
              kicker="History"
              title="No inspections yet"
              description="Inspections you run appear here with their findings breakdown and timing."
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
              {rows.map((inspection) => (
                <HistoryRow
                  key={inspection.id}
                  inspection={inspection}
                  onOpen={() => navigate(`/history/${inspection.id}`)}
                />
              ))}
            </TableScroll>
          )}
        </AsyncBoundary>
      </div>
    </Page>
  );
}

function HistoryRow({ inspection, onOpen }: { inspection: Inspection; onOpen: () => void }) {
  const statusMeta = getInspectionStatusMeta(inspection.status);
  return (
    <ClickableRow
      template={TEMPLATE}
      onClick={onOpen}
      ariaLabel={`Open inspection of ${inspection.repositoryName} at ${shortCommit(inspection.commitSha)}`}
    >
      <Cell stack>
        <RepositoryIdentity name={inspection.repositoryName} secondary={inspection.language} />
      </Cell>
      <Cell mono>{shortCommit(inspection.commitSha)}</Cell>
      <Cell>{formatDate(inspection.completedAt ?? inspection.startedAt)}</Cell>
      <Cell>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: statusMeta.color }}>
          <StatusDot color={statusMeta.color} />
          {statusMeta.label}
        </span>
      </Cell>
      <Cell mono>{formatCount(inspection.filesAnalyzed)}</Cell>
      <Cell mono strong>
        {formatCount(inspection.findingsCount)}
      </Cell>
      <Cell>
        <SeverityCluster severity={inspection.severity} />
      </Cell>
      <Cell mono style={{ color: 'var(--text-3)' }}>
        {formatDuration(inspection.durationMs)}
      </Cell>
    </ClickableRow>
  );
}

function HistorySkeleton() {
  return (
    <TableScroll minWidth={MIN_WIDTH}>
      <Head />
      {[0, 1, 2].map((row) => (
        <Row key={row} template={TEMPLATE}>
          {Array.from({ length: 8 }).map((_, index) => (
            <Cell key={index}>
              <Skeleton width={index === 0 ? 160 : 60} height={12} />
            </Cell>
          ))}
        </Row>
      ))}
    </TableScroll>
  );
}
