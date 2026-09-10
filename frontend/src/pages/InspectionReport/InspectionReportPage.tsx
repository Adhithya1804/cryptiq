import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { EmptyState } from '@/components/common/StateViews';
import {
  ConfidenceIndicator,
  PriorityBadge,
  StatusDot,
} from '@/components/common/StatusIndicators';
import {
  Cell,
  ClickableRow,
  HeaderCell,
  HeaderRow,
  SortableHeaderCell,
  TableScroll,
  type SortState,
} from '@/components/common/Table';
import { InspectionSummaryBar } from '@/components/inspection/InspectionSummaryBar';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { fetchInspection, getFindings } from '@/services';
import {
  CONFIDENCE_WEIGHT,
  PRIORITY_WEIGHT,
  getInspectionStatusMeta,
  getRoleCode,
} from '@/constants/domain';
import { lineRange, pluralize, shortCommit, shortenPath } from '@/utils/format';
import type { RemoteData } from '@/types/common';
import type { FindingSummary, Inspection, Page as ResultPage } from '@/types/domain';
import styles from './InspectionReportPage.module.css';

type SortKey = 'priority' | 'algorithm' | 'confidence';
const TEMPLATE = '110px 130px 190px minmax(0, 1fr) 70px 130px';
const MIN_WIDTH = 820;
const PAGE_SIZE = 50;

function compareFindings(a: FindingSummary, b: FindingSummary, sort: SortState<SortKey>): number {
  const direction = sort.direction === 'desc' ? -1 : 1;
  switch (sort.key) {
    case 'priority':
      return (PRIORITY_WEIGHT[a.priority] - PRIORITY_WEIGHT[b.priority]) * direction;
    case 'confidence':
      return (CONFIDENCE_WEIGHT[a.confidence] - CONFIDENCE_WEIGHT[b.confidence]) * direction;
    case 'algorithm':
      return a.algorithm.localeCompare(b.algorithm) * direction;
  }
}

export function InspectionReportPage() {
  const { inspectionId = '' } = useParams();
  const navigate = useNavigate();
  const filterId = useId();

  const inspectionLoader = useCallback(
    (signal: AbortSignal) => fetchInspection(inspectionId, signal),
    [inspectionId],
  );
  const { state, reload, refresh } = useAsyncResource(inspectionLoader, [inspectionId]);

  // A backend scan runs asynchronously: while it is queued or running, poll for
  // the authoritative state. The poll is a background refresh (no loading
  // flash), stops the moment the scan reaches a terminal state, and is torn
  // down on unmount. No client-side progress is invented.
  const liveStatus = state.status === 'success' ? state.data.status : null;
  const isRunning = liveStatus === 'queued' || liveStatus === 'running';
  useEffect(() => {
    if (!isRunning) return;
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [isRunning, refresh]);

  const title = state.status === 'success' ? state.data.repositoryName : 'Inspection';
  useDocumentTitle(title);
  useBreadcrumbs(
    () => [
      { label: 'History', to: '/history' },
      {
        label:
          state.status === 'success'
            ? `${state.data.repositoryName} @ ${shortCommit(state.data.commitSha)}`
            : 'Report',
      },
    ],
    [state.status, title],
  );

  const [sort, setSort] = useState<SortState<SortKey>>({ key: 'priority', direction: 'desc' });
  const [filter, setFilter] = useState('');
  const [appliedFilter, setAppliedFilter] = useState('');
  const [page, setPage] = useState(1);

  // Debounce the free-text filter into the server query; changing it resets to
  // the first page so the pager never points past the new result set.
  useEffect(() => {
    const t = setTimeout(() => setAppliedFilter(filter.trim()), 300);
    return () => clearTimeout(t);
  }, [filter]);
  useEffect(() => {
    setPage(1);
  }, [appliedFilter, inspectionId]);

  const findingsLoader = useCallback(
    (signal: AbortSignal) =>
      getFindings(inspectionId, {
        page,
        pageSize: PAGE_SIZE,
        signal,
        ...(appliedFilter ? { filters: { algorithm: appliedFilter } } : {}),
      }),
    [inspectionId, page, appliedFilter],
  );
  const findings = useAsyncResource(findingsLoader, [inspectionId, page, appliedFilter]);
  // While a scan is still running, keep the findings view fresh too.
  useEffect(() => {
    if (!isRunning) return;
    const timer = setInterval(findings.refresh, 2500);
    return () => clearInterval(timer);
  }, [isRunning, findings.refresh]);

  return (
    <Page>
      <AsyncBoundary state={state} onRetry={reload} errorTitle="This inspection could not be loaded">
        {(inspection) => (
          <ReportBody
            inspection={inspection}
            findingsState={findings.state}
            onRetryFindings={findings.reload}
            sort={sort}
            onSort={(key) =>
              setSort((prev) => ({
                key,
                direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc',
              }))
            }
            filter={filter}
            onFilterChange={setFilter}
            filterId={filterId}
            page={page}
            onPageChange={setPage}
            onOpenFinding={(id) =>
              navigate(`/findings/${id}?from=report&inspection=${inspection.id}`)
            }
          />
        )}
      </AsyncBoundary>
    </Page>
  );
}

interface ReportBodyProps {
  inspection: Inspection;
  findingsState: RemoteData<ResultPage<FindingSummary>>;
  onRetryFindings: () => void;
  sort: SortState<SortKey>;
  onSort: (key: SortKey) => void;
  filter: string;
  onFilterChange: (value: string) => void;
  filterId: string;
  page: number;
  onPageChange: (page: number) => void;
  onOpenFinding: (id: string) => void;
}

function ReportBody({
  inspection,
  findingsState,
  onRetryFindings,
  sort,
  onSort,
  filter,
  onFilterChange,
  filterId,
  page,
  onPageChange,
  onOpenFinding,
}: ReportBodyProps) {
  const statusMeta = getInspectionStatusMeta(inspection.status);
  const result = findingsState.status === 'success' ? findingsState.data : null;
  const total = result?.total ?? 0;
  const pages = result?.pages ?? 1;

  const visible = useMemo(() => {
    if (!result) return [];
    return [...result.items].sort((a, b) => compareFindings(a, b, sort));
  }, [result, sort]);

  return (
    <>
      <div className={styles.headerRow}>
        <div>
          <div className={styles.metaLine}>
            Commit <strong>{shortCommit(inspection.commitSha)}</strong> · Language{' '}
            <strong>{inspection.language}</strong>
          </div>
          <h1 className={styles.title}>{inspection.repositoryName}</h1>
          <div className={styles.statusLine}>
            <StatusDot color={statusMeta.color} />
            <span>{statusMeta.label}</span>
          </div>
        </div>
      </div>

      <div className={styles.summary}>
        <InspectionSummaryBar inspection={inspection} />
      </div>

      {inspection.status === 'failed' && (
        <div className={styles.failureNotice} role="alert">
          <div className={styles.failureTitle}>Analysis failed</div>
          <div className={styles.failureBody}>
            {inspection.errorMessage ??
              'The repository could not be analyzed. Please retry the scan.'}
          </div>
          {inspection.errorCode && (
            <div className={styles.failureCode}>{inspection.errorCode}</div>
          )}
        </div>
      )}

      <div className={styles.tableHead}>
        <div className={styles.tableHeadLabel}>What this inspection discovered</div>
        <div className={styles.tableHeadRight}>
          <label htmlFor={filterId} className="sr-only">
            Filter findings by algorithm
          </label>
          <input
            id={filterId}
            type="search"
            className={styles.filterInput}
            placeholder="Filter by algorithm…"
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
          />
          <div className={styles.count} aria-live="polite">
            {result ? pluralize(total, 'finding') : '…'}
          </div>
        </div>
      </div>

      <AsyncBoundary
        state={findingsState}
        onRetry={onRetryFindings}
        errorTitle="The findings could not be loaded"
      >
        {(pageData) =>
          pageData.total === 0 ? (
            <EmptyState
              kicker="Findings"
              title={filter ? 'No findings match this filter' : 'No findings in this inspection'}
              description={
                filter
                  ? 'No cryptographic usage matched the algorithm you searched for.'
                  : inspection.status === 'completed'
                    ? 'Cryptiq did not record any cryptographic usage for this repository at this commit.'
                    : inspection.status === 'failed'
                      ? 'The analysis did not complete, so there are no findings. See the message above and retry the scan.'
                      : 'Findings appear here once the analysis completes.'
              }
            />
          ) : (
            <>
              <TableScroll minWidth={MIN_WIDTH}>
                <HeaderRow template={TEMPLATE}>
                  <SortableHeaderCell label="Priority" sortKey="priority" sort={sort} onSort={onSort} />
                  <SortableHeaderCell label="Algorithm" sortKey="algorithm" sort={sort} onSort={onSort} />
                  <HeaderCell>Role</HeaderCell>
                  <HeaderCell>File</HeaderCell>
                  <HeaderCell>Line</HeaderCell>
                  <SortableHeaderCell label="Confidence" sortKey="confidence" sort={sort} onSort={onSort} />
                </HeaderRow>
                {visible.map((finding) => (
                  <ClickableRow
                    key={finding.id}
                    template={TEMPLATE}
                    onClick={() => onOpenFinding(finding.id)}
                    ariaLabel={`Open ${finding.algorithm} finding in ${finding.filePath}`}
                  >
                    <Cell>
                      <PriorityBadge priority={finding.priority} />
                    </Cell>
                    <Cell mono strong>
                      {finding.algorithm}
                    </Cell>
                    <Cell mono truncate title={getRoleCode(finding.role)}>
                      {getRoleCode(finding.role)}
                    </Cell>
                    <Cell mono truncate title={finding.filePath}>
                      {shortenPath(finding.filePath)}
                    </Cell>
                    <Cell mono>{lineRange(finding.lineStart, finding.lineEnd)}</Cell>
                    <Cell>
                      <ConfidenceIndicator confidence={finding.confidence} />
                    </Cell>
                  </ClickableRow>
                ))}
              </TableScroll>

              {pages > 1 && (
                <nav className={styles.pager} aria-label="Findings pages">
                  <button
                    type="button"
                    className={styles.pagerBtn}
                    onClick={() => onPageChange(Math.max(page - 1, 1))}
                    disabled={page <= 1}
                  >
                    Previous
                  </button>
                  <span className={styles.pagerInfo} aria-live="polite">
                    Page {page} of {pages} · {pluralize(pageData.total, 'finding')}
                  </span>
                  <button
                    type="button"
                    className={styles.pagerBtn}
                    onClick={() => onPageChange(Math.min(page + 1, pages))}
                    disabled={page >= pages}
                  >
                    Next
                  </button>
                </nav>
              )}
            </>
          )
        }
      </AsyncBoundary>
    </>
  );
}
