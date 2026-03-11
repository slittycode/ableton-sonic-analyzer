# AGENTS.md

## Scope

- This file applies to the `sonic-analyzer-UI` frontend repo.
- Stack: React 19, TypeScript, Vite 6, Tailwind CSS v4, Vitest, Playwright.
- The app talks to the local `sonic-analyzer` backend.
- No repo-local `.cursorrules`, `.cursor/rules/`, or `.github/copilot-instructions.md` exist here as of 2026-03-10.

## Working Style For Agents

- Prefer small, reviewable edits over broad UI rewrites.
- Preserve the backend contract enforced by `src/services/backendPhase1Client.ts` and `src/types.ts`.
- Read `README.md` before changing scripts, env handling, smoke tests, or backend integration behavior.
- Keep bundle-size-sensitive patterns in place unless there is a clear reason to change them.
- Follow the surrounding file style; this repo is not fully formatter-normalized.

## Environment And Setup

- Use Node 20+.
- Install dependencies: `npm install`
- Create a local env file when needed: `cp .env.example .env`
- Key env vars:
  - `VITE_API_BASE_URL`
  - `VITE_ENABLE_PHASE2_GEMINI`
  - `VITE_GEMINI_API_KEY`
  - `RUN_GEMINI_LIVE_SMOKE`
  - `DISABLE_HMR`

## Main Commands

- Preferred synced local stack from the workspace root: `cd .. && ./scripts/dev.sh`
- Dev server: `npm run dev`
- Synced local UI only: `VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local`
- Build: `npm run build`
- Preview build: `npm run preview`
- Clean build output: `npm run clean`

## Lint, Typecheck, And Test Commands

- This repo does not currently use ESLint or Prettier.
- Typecheck: `npm run lint`
- All Vitest tests: `npm test`
- Unit/service suite: `npm run test:unit`
- Playwright smoke suite: `npm run test:smoke`
- Full validation chain: `npm run verify`

## Single-Test Recipes

- One Vitest file:

```bash
npx vitest run tests/services/backendPhase1Client.test.ts
```

- One Vitest test by name:

```bash
npx vitest run tests/services/backendPhase1Client.test.ts -t "accepts a valid backend payload"
```

- One smoke spec:

```bash
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

- Live backend smoke:

```bash
TEST_FLAC_PATH=/path/to/track.flac VITE_API_BASE_URL=http://127.0.0.1:8100 npm run test:smoke -- tests/smoke/upload-phase1-live.spec.ts
```

- Live Gemini smoke:

```bash
RUN_GEMINI_LIVE_SMOKE=true VITE_ENABLE_PHASE2_GEMINI=true VITE_GEMINI_API_KEY=your_key_here VITE_API_BASE_URL=http://127.0.0.1:8100 npm run test:smoke:live-gemini
```

## Testing Expectations

- Vitest runs in a `node` environment, not `jsdom`.
- `tests/services` relies heavily on mocks, fake timers, and payload fixtures.
- `tests/smoke` uses Playwright and usually stubs backend and Gemini calls unless a spec is explicitly live.
- Playwright boots the app on `127.0.0.1:3100`; keep that in mind when debugging smoke failures.
- Prefer the smallest relevant test first, then `npm run verify` for broader changes.

## File Map

- `src/App.tsx`: upload flow, estimate flow, phase orchestration, diagnostic log state.
- `src/services/backendPhase1Client.ts`: backend transport, parsing, timeout handling, error mapping.
- `src/services/analyzer.ts`: phase orchestration and Gemini entry.
- `src/types.ts`: shared frontend contract types.
- `src/index.css`: Tailwind theme tokens and visual language.
- `tests/services/*`: unit and service tests.
- `tests/smoke/*`: smoke and live smoke coverage.

## Code Style

- Follow the local style of the file you are editing.
- Newer UI files mostly use single quotes and spaced imports.
- Some service files still use double quotes and different spacing; do not churn files only for style.
- Use semicolons where the surrounding file uses them.
- Keep imports grouped with external packages first and local modules after.
- Prefer relative imports unless the file already uses the `@` alias.

## React And TypeScript Conventions

- Use function components and hooks.
- Keep derived state in helpers or `useMemo` instead of recomputing noisy transforms inline.
- Clean up timers, object URLs, audio resources, and async side effects in `useEffect` cleanup paths.
- Prefer explicit interfaces and types for backend payloads, props, and view models.
- Keep parser and transport code defensive: validate unknown JSON and throw typed client errors.
- Preserve non-null assertions only where the repo already relies on stable DOM assumptions, such as `main.tsx`.

## Naming Conventions

- `PascalCase` for React components, exported interfaces, and component filenames.
- `camelCase` for functions, variables, helpers, and state setters.
- `UPPER_SNAKE_CASE` for module-level constants.
- Name test files after the unit under test, for example `backendPhase1Client.test.ts`.
- Prefer behavior-focused test names from the caller's point of view.

## Error Handling

- Keep backend errors normalized through `BackendClientError` and `mapBackendError`.
- Use `AbortController` timeouts for network requests.
- Preserve the current behavior where estimate failures surface in the UI but do not necessarily block analysis.
- Swallow teardown-only cleanup failures when they are non-user-facing.
- Avoid broad silent catches in business logic unless the surrounding code already intentionally degrades gracefully.

## Styling And UI Rules

- This app uses Tailwind CSS v4 plus semantic tokens in `src/index.css`.
- Reuse semantic tokens like `bg-bg-panel` and `text-text-secondary` before adding new raw colors.
- Preserve the existing Ableton-inspired dark visual language unless the task explicitly changes design direction.
- Keep motion purposeful and lightweight.
- Maintain mobile-safe layouts and avoid regressions in the upload and results flow.

## Backend Contract Rules

- The app expects `POST /api/analyze/estimate` and `POST /api/analyze`.
- `src/types.ts` and `src/services/backendPhase1Client.ts` are the frontend source of truth for the response contract.
- The UI depends on `phase1`, `diagnostics`, and stable error envelopes.
- Do not assume the backend returns every raw analyzer field; `server.py` exposes a normalized subset.
- If you change frontend expectations, verify they still match backend docs and tests.

## Known Gotchas

- `src/config.ts` falls back to `http://127.0.0.1:8100` if `VITE_API_BASE_URL` is unset.
- `.env.example` uses `http://127.0.0.1:8100`; stale local `.env` files can still pin `localhost:8000` or `127.0.0.1:8010`, but `../scripts/dev.sh` overrides that for the spawned UI process.
- Phase 2 Gemini is disabled unless both the feature flag and API key are present.
- Audio files over 20MB take the Gemini Files API path; do not break that branch casually.
- `npm run lint` does not cover tests because `tsconfig.json` excludes `tests`, `playwright.config.ts`, and `vitest.config.ts`.

## Change Checklist

- If you change backend transport or parsing, run the relevant `tests/services` file first.
- If you change upload, orchestration, or rendered flow behavior, run the relevant Playwright smoke spec.
- If you touch shared types or config, run `npm run lint` and at least one targeted test.
- If you change app-wide behavior or build config, run `npm run verify`.
- Before finishing, make sure the commands in this file still match `package.json`.
