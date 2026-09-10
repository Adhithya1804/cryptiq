# Cryptiq frontend

Production React + TypeScript frontend for Cryptiq — deterministic cryptographic
static analysis. This is an engineered implementation of the Claude Design source
(`Cryptiq.dc.html`); the visual design is the source of truth and was preserved.

## Stack

- **React 18** + **TypeScript** (strict, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`)
- **Vite 5** build / dev server
- **react-router-dom 6** for real URLs (deep-links, back button, refresh)
- **Vitest** + **Testing Library** for behavioural tests
- Plain CSS with design tokens + CSS Modules — no CSS framework, no component library

## Getting started

```bash
npm install
cp .env.example .env      # optional — see "Backend" below
npm run dev
```

| Script | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | Typecheck + production build to `dist/` |
| `npm run typecheck` | `tsc` project build, no emit |
| `npm run lint` | ESLint (type-checked rules, `--max-warnings 0`) |
| `npm run test` | Vitest run |
| `npm run test:watch` | Vitest watch |

## Backend

The app talks to the backend through a single service layer (`src/services/`),
with every canonical endpoint centralised in `src/services/client.ts`
(`createScan`, `getScan`, `getFindings`, `getFinding`, `getReviewQueue`,
`updateReviewItem`). Set the base URL via a build-time environment variable —
`VITE_API_BASE_URL`, or `NEXT_PUBLIC_API_URL` as an alias:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

`.env.development.local` already sets this to `http://localhost:8000/api/v1` for
local development. Do not hard-code a production URL — configure it per
environment.

When the base URL is **unset**, the app runs in "no backend connected" mode,
matching the design's `data-service.js` boundary: read screens render their
empty states and starting an inspection reports a connection error instead of
fabricating a result. Nothing is mocked or stubbed — the screens are wired for
real data.

### Running the full stack locally

```bash
# 1. Backend API + in-process scan worker (from ../cryptiq)
cd ../cryptiq
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
RUN_WORKER=true uvicorn app.main:app --host 127.0.0.1 --port 8000
#    RUN_WORKER=true keeps the async scan worker in the same process. To run it
#    separately instead, start the API with RUN_WORKER=false and run the worker
#    loop as its own process.

# 2. Frontend (this package, in another terminal)
npm install
npm run dev            # http://localhost:5173, reads .env.development.local
```

Backend env vars: `DATABASE_URL` (default `sqlite:///./cryptiq.db`),
`CORS_ALLOW_ORIGINS` (defaults already include `:5173` and `:3000`),
`RUN_WORKER`, `GITHUB_TOKEN` (optional, raises the GitHub rate limit),
`GEMINI_API_KEY` (optional — when absent the "Explain with AI" panel shows an
"unavailable" state and never calls Gemini). No secret is ever sent to the
browser.

### Demo flow

1. Open `/inspect`, enter `https://github.com/pyca/cryptography` and commit
   `1f903f5ed2e5e316f345a927555e48535829d8de`, click **Inspect Repository**.
2. The report page shows the scan as queued → running (polled every 2s) and then
   the findings table. A repeat submit of the same commit returns the stored
   result immediately (`POST /scans` → `200 cached: true`), with no re-scan.
3. Findings are paginated (50/page) and the filter box narrows by algorithm
   server-side, resetting to page 1.
4. Open a finding for the observed / inferred / migration / priority / impact
   hero screen with the verbatim source excerpt.
5. In **Review**, open an item and move it OPEN → In Review → Resolved; the
   change is `PATCH /review-items/{id}` and persists.

Only public configuration belongs in `.env`. Secrets (GitHub tokens, the Gemini
API key, database credentials) live on the backend; anything bundled into the
browser build is world-readable. The browser never calls Gemini directly — AI
explanations are fetched through the backend and are a subordinate layer that
can fail without breaking a finding.

## Architecture

```
src/
├── app/              router, providers (preferences, toast)
├── components/
│   ├── common/       Button, TextField, Table, AsyncBoundary, state views, badges…
│   ├── layout/       AppLayout, Sidebar, Breadcrumbs, Page
│   ├── findings/     FindingHeader, SourceEvidence, ReviewPathCard, AiExplanation…
│   └── inspection/   InspectionSummaryBar, Severity
├── pages/            one folder per screen (Inspect, Projects, History, …)
├── services/         HTTP boundary, per-resource modules, wire→domain mappers
├── types/            domain model, wire shapes, shared types
├── hooks/            useAsyncResource, useMediaQuery, useLocalStorageState…
├── constants/        domain→presentation maps, navigation model
├── utils/            format + validation (pure, unit-tested)
└── styles/           design tokens + global stylesheet
```

Data flow is one-directional: **UI → page → `useAsyncResource` → service → HTTP**.
Components never construct a `fetch`, a URL, or a header, and never see a raw
response — `services/mappers.ts` normalises the wire format onto `types/domain.ts`.

Every data-driven screen renders exactly one of loading / error / empty / success
via `<AsyncBoundary>`.

## Domain model notes

A finding keeps **observed** facts (checkable against the source at the commit)
separate from **inferred** judgement (role, confidence) and from the AI
explanation layer. The types enforce that separation so a component cannot
present a judgement as a fact. Priority is a *migration-review priority*, not a
vulnerability severity. See `FRONTEND_BACKEND_CONTRACT.md` in the repo root.
