# AGENTS.md

## Scope

- This file applies to the `sonic-analyzer` backend repo.
- The repo is a local Python audio-analysis service with two entry points:
  - `analyze.py`: raw CLI analyzer
  - `server.py`: FastAPI wrapper around the CLI
- There are no repo-local Cursor rules, `.cursorrules`, or Copilot instruction files in this repo as of 2026-03-10.

## Working Style For Agents

- Prefer small, surgical edits over broad refactors.
- Preserve the current contract between `analyze.py`, `server.py`, and the UI.
- Read `README.md`, `ARCHITECTURE.md`, and `JSON_SCHEMA.md` before changing API or payload behavior.
- Treat `stdout` vs `stderr` behavior as part of the product contract, not just an implementation detail.
- Do not silently change field names in raw CLI output or HTTP envelopes.

## Environment And Setup

- Python: use Python 3.10+.
- Create the local environment with:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

- Main runtime dependencies are declared in `requirements.txt`.
- If audio/DSP imports fail, check local native dependencies before editing code.

## Main Commands

- Preferred synced local stack from this repo: `./scripts/dev.sh`
- Run the CLI analyzer:

```bash
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes]
```

- Run the FastAPI server:

```bash
./venv/bin/python server.py
```

- The server currently binds to `0.0.0.0:8100` by default and honors `SONIC_ANALYZER_PORT`.
- The UI expects the backend at `http://127.0.0.1:8100` unless overridden.
- `./scripts/dev.sh` starts the sibling `../sonic-analyzer-UI` checkout on `http://127.0.0.1:3100` and overrides stale UI `.env` backend URLs for that session.
- The workspace-root `../scripts/dev.sh` flow is deprecated because it is not version-controlled in either repo.

## Validation Commands

- Minimal syntax validation:

```bash
./venv/bin/python -m py_compile server.py
```

- Run all backend tests:

```bash
./venv/bin/python -m unittest discover -s tests
```

- Run one test module:

```bash
./venv/bin/python -m unittest tests/test_server.py
./venv/bin/python -m unittest tests/test_analyze.py
```

- Run one test class:

```bash
./venv/bin/python -m unittest tests.test_server.ServerContractTests
./venv/bin/python -m unittest tests.test_analyze.AnalyzeStructuralSnapshotTests
```

- Run one test case:

```bash
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
./venv/bin/python -m unittest tests.test_analyze.AnalyzeStructuralSnapshotTests.test_duration_is_close_to_fixture_length
```

## Testing Expectations

- This repo uses stdlib `unittest`, not `pytest`.
- `tests/test_server.py` is the API contract suite; run it after changing request parsing, subprocess behavior, diagnostics, timing, or error envelopes.
- `tests/test_analyze.py` is a structural snapshot test for the raw analyzer JSON; run it after changing emitted fields or raw output shape.
- Prefer the narrowest useful test first, then the full suite.
- If you change CLI output keys, update docs and tests in the same change.

## File Map

- `analyze.py`: DSP pipeline, raw JSON generation, optional separation/transcription.
- `server.py`: HTTP transport, temp file handling, estimate/timeout logic, subprocess execution, response normalization.
- `tests/test_server.py`: OpenAPI and envelope contract tests.
- `tests/test_analyze.py`: generated WAV fixture and raw payload assertions.
- `ARCHITECTURE.md`: backend responsibilities and request flow.
- `JSON_SCHEMA.md`: raw CLI schema plus HTTP mapping notes.

## Code Style

- Follow the surrounding file style instead of introducing a new formatter profile.
- Use 4-space indentation.
- Prefer double quotes in Python files.
- Keep imports grouped in this order:
  1. standard library
  2. third-party packages
  3. local imports
- Separate import groups with a single blank line.
- Prefer short helper functions when they clarify coercion, normalization, or envelope building.
- Use trailing commas in multiline literals and call sites when the surrounding file does.

## Types And Data Handling

- Keep type hints on public helpers and contract-shaping functions.
- Use Python 3.10 style annotations such as `str | None`, `dict[str, Any]`, and `list[datetime]`.
- Preserve the current pattern of explicit coercion helpers for API payload normalization.
- When mapping raw analyzer output to `phase1`, prefer defensive conversion over blind passthrough for scalar fields.
- Default to returning stable, typed values instead of leaking inconsistent raw types into HTTP responses.

## Naming Conventions

- Use `snake_case` for functions, variables, and module-level helpers.
- Use `UPPER_SNAKE_CASE` for constants.
- Use descriptive private helpers prefixed with `_` when they are internal to a module.
- Use `PascalCase` for `unittest.TestCase` classes.
- Name tests after observable contract behavior, not implementation trivia.

## Error Handling

- Be defensive. Many analyzer feature functions intentionally catch exceptions and degrade gracefully.
- In `analyze.py`, preserve the pattern of logging warnings to `stderr` and returning `None`/null-friendly payload fragments when a feature fails.
- In `server.py`, preserve structured JSON error envelopes with `requestId`, `error`, and optional `diagnostics`.
- Do not replace stable backend errors with generic uncaught exceptions.
- When adding new failure paths, include enough detail for local debugging without changing public response shape unnecessarily.

## Output And Logging Contracts

- `analyze.py` must emit machine-readable JSON to `stdout` only.
- Human-readable progress, warnings, and errors belong on `stderr`.
- `server.py` emits a `[TIMING]` summary line to `stderr`; preserve that behavior when touching timing logic.
- Keep snippets and diagnostics bounded; avoid dumping massive payloads into error responses.

## Backend Contract Rules

- `POST /api/analyze/estimate` and `POST /api/analyze` are the important app-facing routes.
- Both routes accept multipart `track`, optional `transcribe`, optional ignored `dsp_json_override`, and `separate` / `--separate` query aliases.
- `server.py` normalizes raw analyzer output into `phase1`; it does not expose every raw field.
- The raw CLI schema and the HTTP schema are intentionally different; check `JSON_SCHEMA.md` before expanding or removing fields.
- `transcriptionDetail` is only present when `analyze.py` runs with `--transcribe`.

## Known Gotchas

- `--fast` is accepted by `analyze.py` but is currently a no-op.
- `dsp_json_override` is accepted by the server but ignored.
- The server always appends `--yes` when invoking `analyze.py`.
- README CORS docs have drifted before; trust `server.py` constants over prose if they disagree.
- The UI depends on the existing envelope structure, diagnostics fields, and timing keys.

## Change Checklist

- If you change API request parsing, run `tests/test_server.py`.
- If you change raw analyzer output, run `tests/test_analyze.py` and update docs.
- If you change timeout or diagnostics behavior, inspect both tests and `ARCHITECTURE.md`.
- If you add a new field, document whether it belongs to raw CLI output, HTTP `phase1`, or both.
- Before finishing, run the narrowest relevant test plus `./venv/bin/python -m unittest discover -s tests` if the change is broad.
