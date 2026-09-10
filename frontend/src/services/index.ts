/**
 * Public surface of the API layer. Pages and hooks import from here; nothing
 * imports `http.ts`, `mappers.ts`, `client.ts` or a resource module directly.
 */

export { apiConfig, isBackendConfigured, NO_BACKEND_MESSAGE } from './config';
export { HttpError } from './errors';
export { toApiError, isAbortError } from './http';

export { fetchProjects, fetchProject, fetchProjectInspections } from './projects';
export { fetchHistory, fetchInspection, submitInspection, submitScan } from './inspections';
export {
  fetchFinding,
  fetchFindingExplanation,
  submitFindingReview,
} from './findings';
export { fetchReviewQueue } from './review';

/** Canonical endpoint client — paged + server-filtered. */
export {
  createScan,
  getScan,
  getFindings,
  getFinding,
  getReviewQueue,
  updateReviewItem,
} from './client';
