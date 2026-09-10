import { useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page } from '@/components/layout/Page';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { EmptyState } from '@/components/common/StateViews';
import { Button } from '@/components/common/Button';
import { StatusDot } from '@/components/common/StatusIndicators';
import { useBreadcrumbs } from '@/components/layout/Breadcrumbs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { fetchProject, fetchProjectInspections } from '@/services';
import { getInspectionStatusMeta } from '@/constants/domain';
import { formatCount, formatDate, formatDuration, shortCommit } from '@/utils/format';
import type { Inspection, Repository, SeverityBreakdown } from '@/types/domain';
import styles from './ProjectDetailPage.module.css';

interface ProjectDetailData {
  project: Repository;
  inspections: Inspection[];
}

const SEV_ROWS: { key: keyof SeverityBreakdown; label: string; color: string }[] = [
  { key: 'critical', label: 'Critical', color: 'var(--text-1)' },
  { key: 'high', label: 'High', color: 'var(--red)' },
  { key: 'medium', label: 'Medium', color: 'var(--amber)' },
  { key: 'low', label: 'Low', color: 'var(--green)' },
];

export function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();

  const loader = useCallback(
    async (signal: AbortSignal): Promise<ProjectDetailData> => {
      const [project, inspections] = await Promise.all([
        fetchProject(projectId, signal),
        fetchProjectInspections(projectId, signal),
      ]);
      return { project, inspections };
    },
    [projectId],
  );
  const { state, reload } = useAsyncResource(loader, [projectId]);

  const title = state.status === 'success' ? state.data.project.name : 'Project';
  useDocumentTitle(title);
  useBreadcrumbs(
    () => [{ label: 'Projects', to: '/projects' }, { label: title }],
    [title],
  );

  return (
    <Page>
      <AsyncBoundary state={state} onRetry={reload} errorTitle="This project could not be loaded">
        {({ project, inspections }) => (
          <ProjectDetailView
            project={project}
            inspections={inspections}
            onInspect={() => navigate('/inspect')}
            onOpenInspection={(id) => navigate(`/history/${id}`)}
          />
        )}
      </AsyncBoundary>
    </Page>
  );
}

interface ViewProps {
  project: Repository;
  inspections: Inspection[];
  onInspect: () => void;
  onOpenInspection: (id: string) => void;
}

function ProjectDetailView({ project, inspections, onInspect, onOpenInspection }: ViewProps) {
  const latest = inspections[0] ?? null;

  return (
    <>
      <div className={styles.header}>
        <div>
          <div className={styles.kicker}>Project</div>
          <h1 className={styles.title}>{project.name}</h1>
          <div className={styles.meta}>
            {project.url && <span>GitHub</span>}
            {project.url && <span className={styles.dotSep}>·</span>}
            <span>{project.language}</span>
            <span className={styles.dotSep}>·</span>
            <span>Exact revision</span>
            {latest && (
              <>
                <span className={styles.dotSep}>·</span>
                <span className={styles.metaMono}>{shortCommit(latest.commitSha)}</span>
              </>
            )}
          </div>
          <div className={styles.links}>
            {latest && (
              <button type="button" className={styles.link} onClick={() => onOpenInspection(latest.id)}>
                View Inspection
              </button>
            )}
          </div>
        </div>
        <Button size="sm" onClick={onInspect}>
          Inspect Repository
        </Button>
      </div>

      {latest ? (
        <>
          <div className={styles.topGrid}>
            <div className={styles.latestPanel}>
              <div className={styles.panelLabel}>Latest Inspection</div>
              <div className={styles.statusRow}>
                <StatusDot color={getInspectionStatusMeta(latest.status).color} size={7} />
                <span className={styles.statusLabel}>{getInspectionStatusMeta(latest.status).label}</span>
              </div>
              <div className={styles.latestStats}>
                <div>
                  <span className={styles.bigCount}>{formatCount(latest.findingsCount)}</span>
                  <span className={styles.bigCountUnit}>findings</span>
                </div>
                <div className={styles.latestMono}>{shortCommit(latest.commitSha)}</div>
                <div className={styles.latestMuted}>
                  {formatDate(latest.completedAt ?? latest.startedAt)}
                </div>
              </div>
            </div>
            <div className={styles.sideCards}>
              <div className={styles.sideCard}>
                <span>Files analyzed</span>
                <span>{formatCount(latest.filesAnalyzed)}</span>
              </div>
              <div className={styles.sideCard}>
                <span>Duration</span>
                <span>{formatDuration(latest.durationMs)}</span>
              </div>
            </div>
          </div>

          <div className={styles.findingsPanel}>
            <div className={styles.findingsHead}>
              <div className={styles.panelLabel} style={{ marginBottom: 0 }}>
                Findings
              </div>
              <div className={styles.findingsNote}>
                {formatCount(latest.findingsCount)} total findings — migration-review priorities, not
                vulnerabilities
              </div>
            </div>
            <div className={styles.sevGrid}>
              {SEV_ROWS.map((row) => (
                <div key={row.key} className={styles.sevCard}>
                  <div className={styles.sevLabel}>{row.label}</div>
                  <div className={styles.sevValue} style={{ color: row.color }}>
                    {latest.severity[row.key]}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <EmptyState
          kicker="Project"
          title="No inspections recorded"
          description="This repository has no completed inspections yet."
          action={
            <Button size="sm" onClick={onInspect}>
              Inspect this repository
            </Button>
          }
        />
      )}
    </>
  );
}
