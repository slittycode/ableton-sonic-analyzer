# AGENTS.md

This file provides guidance to AI coding agents working with the ASA (Sonic Analyzer) codebase.

## Project Overview

ASA is a local audio analysis tool for music producers. It analyzes audio files to extract measurable properties (tempo, key, loudness, spectral characteristics) and provides AI-powered interpretation for arrangement advice and musical descriptions.

### Core Philosophy

The system follows a **three-layer hybrid architecture** that separates deterministic measurement from AI interpretation:

1. **Measurement is authoritative** - DSP results from Essentia are the system's ground truth
2. **Symbolic extraction is best-effort** - Monophonic pitch tracking on separated stems, honest about uncertainty
3. **Interpretation is contextual** - Gemini provides musical insights grounded in measurements, not replacements for them

This split exists because frontier audio-language models (as of early 2026) still degrade on measurement tasks like BPM estimation and key detection. The hybrid approach leverages the strengths of each layer.

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — MEASUREMENT (Essentia/DSP)                          │
│  Deterministic, repeatable, authoritative                      │
│  BPM, LUFS, key, spectral balance, stereo, dynamics            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2 — SYMBOLIC EXTRACTION (torchcrepe/PENN)               │
│  Best-effort monophonic pitch on Demucs stems                  │
│  Bass + Other stems → MIDI notes with confidence               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — INTERPRETATION (Gemini)                             │
│  Grounded by Layer 1 measurements                              │
│  Arrangement advice, device mappings, musical descriptions     │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Frontend (`apps/ui`)

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19 | UI framework |
| TypeScript | 5.8 | Type safety |
| Vite | 6 | Build tool and dev server |
| Tailwind CSS | 4.1.14 | Styling with semantic tokens |
| WaveSurfer.js | 7.12.1 | Audio waveform visualization |
| midi-writer-js | 3.2.1 | MIDI file export |
| Vitest | 4.0.18 | Unit testing |
| Playwright | 1.58.2 | E2E/smoke testing |

### Backend (`apps/backend`)

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11.x | Runtime (3.12+ not supported for full setup) |
| FastAPI | 0.135.1 | HTTP API framework |
| Uvicorn | 0.41.0 | ASGI server |
| Essentia | 2.1b6.dev1389 | DSP analysis library |
| Demucs | 4.0.1 | Source separation |
| PyTorch | 2.10.0 | Deep learning backend |
| Google GenAI | 1.14.0+ | Gemini API client |
| SQLite | (builtin) | Run state persistence |

### Development Tools

- **Node.js**: 20+ for frontend
- **Python**: 3.11.x specifically for backend
- **Bash**: For orchestration scripts

## Project Structure

```
asa/
├── apps/
│   ├── ui/                    # React frontend
│   │   ├── src/
│   │   │   ├── components/    # React components
│   │   │   ├── services/      # API clients, business logic
│   │   │   ├── hooks/         # Custom React hooks
│   │   │   ├── utils/         # Utility functions
│   │   │   ├── types.ts       # Shared TypeScript types
│   │   │   └── config.ts      # App configuration
│   │   ├── tests/
│   │   │   ├── services/      # Vitest unit tests
│   │   │   └── smoke/         # Playwright E2E tests
│   │   ├── package.json
│   │   └── tsconfig.json
│   └── backend/               # Python backend
│       ├── analyze.py         # CLI analyzer (DSP engine)
│       ├── server.py          # FastAPI HTTP server
│       ├── analysis_runtime.py # SQLite persistence layer
│       ├── requirements.txt   # Python dependencies
│       ├── scripts/
│       │   └── bootstrap.sh   # Environment setup
│       ├── tests/             # unittest suite
│       └── prompts/           # Gemini system prompts
├── scripts/
│   ├── dev.sh                 # Full-stack dev launcher
│   └── test-e2e.sh            # E2E test runner
├── docs/
│   ├── ARCHITECTURE_STRATEGY.md  # Architecture decisions
│   └── *.md                   # Various technical docs
└── AGENTS.md                  # This file
```

### Key Frontend Modules

| File/Directory | Purpose |
|----------------|---------|
| `src/App.tsx` | Main application, upload flow, phase orchestration |
| `src/services/analyzer.ts` | Analysis orchestration and Gemini entry |
| `src/services/backendPhase1Client.ts` | Backend transport, parsing, error handling |
| `src/services/analysisRunsClient.ts` | Typed transport for run APIs |
| `src/types.ts` | Shared response contracts |
| `src/components/AnalysisResults.tsx` | Results display |
| `src/components/SessionMusicianPanel.tsx` | MIDI/piano roll UI |

### Key Backend Modules

| File | Purpose |
|------|---------|
| `analyze.py` | DSP pipeline, CLI entry point, raw JSON output |
| `server.py` | HTTP transport, temp file handling, response normalization |
| `analysis_runtime.py` | SQLite persistence, stage queues, artifact storage |
| `tests/test_server.py` | API contract tests |
| `tests/test_analyze.py` | Structural snapshot tests |

## Build and Development Commands

### Full Stack (Recommended)

Start both backend and UI with proper synchronization:

```bash
./scripts/dev.sh
```

This script:
1. Starts backend on `127.0.0.1:8100`
2. Waits for OpenAPI contract verification
3. Starts UI on `127.0.0.1:3100`
4. Handles graceful shutdown on Ctrl-C

### Backend Only

Setup (first time or after dependency changes):

```bash
./apps/backend/scripts/bootstrap.sh
```

Run the server:

```bash
./apps/backend/venv/bin/python apps/backend/server.py
# Or with custom port:
SONIC_ANALYZER_PORT=8100 ./apps/backend/venv/bin/python apps/backend/server.py
```

Run CLI analyzer directly:

```bash
./apps/backend/venv/bin/python apps/backend/analyze.py <audio_file> [--separate] [--transcribe] [--yes]
```

### Frontend Only

Setup:

```bash
cd apps/ui
npm install
```

Development server:

```bash
npm run dev:local      # Port 3100, localhost only
npm run dev            # Port 3000, host 0.0.0.0
```

Build:

```bash
npm run build
npm run preview        # Preview production build
```

### Verification Commands

Frontend full validation:

```bash
cd apps/ui
npm run verify         # lint + unit tests + build + smoke tests
```

Backend tests:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

Syntax checks:

```bash
cd apps/backend
./venv/bin/python -m py_compile server.py
./venv/bin/python -m py_compile analyze.py
```

### Single Test Commands

Frontend unit test:

```bash
cd apps/ui
npx vitest run tests/services/backendPhase1Client.test.ts
npx vitest run tests/services/backendPhase1Client.test.ts -t "test name"
```

Frontend smoke test:

```bash
cd apps/ui
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

Backend single test:

```bash
cd apps/backend
./venv/bin/python -m unittest tests.test_server
./venv/bin/python -m unittest tests.test_server.ServerContractTests
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
```

## Testing Strategy

### Frontend Testing

| Test Type | Tool | Location | Purpose |
|-----------|------|----------|---------|
| Unit | Vitest | `tests/services/` | Test business logic, parsers, clients |
| Smoke | Playwright | `tests/smoke/` | Critical path E2E tests |
| Live | Playwright | `tests/smoke/*-live*.spec.ts` | Tests against real backend/Gemini |

**Test Environment**: Vitest runs in `node` environment (not `jsdom`). Tests use mocks, fake timers, and payload fixtures.

**Important**: Playwright boots the app on `127.0.0.1:3100` for smoke tests.

### Backend Testing

| Test Type | Tool | Location | Purpose |
|-----------|------|----------|---------|
| Contract | unittest | `tests/test_server.py` | API envelope, error handling |
| Structural | unittest | `tests/test_analyze.py` | Raw analyzer JSON output |

**Testing Framework**: Uses stdlib `unittest`, not pytest.

### Test Data

- Backend tests generate temporary WAV fixtures
- Smoke tests may use `TEST_FLAC_PATH` environment variable for live backend tests
- Gemini live tests require `RUN_GEMINI_LIVE_SMOKE=true` and API key

## Code Style Guidelines

### Python (Backend)

- **Indentation**: 4 spaces
- **Quotes**: Prefer double quotes
- **Type hints**: Use Python 3.10+ style (`str | None`, `dict[str, Any]`)
- **Import order**: stdlib → third-party → local (separated by blank lines)
- **Naming**: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Private helpers**: Prefix with `_` when internal to module

Example:
```python
import json
from typing import Any

import numpy as np
from fastapi import FastAPI

from analysis_runtime import AnalysisRun


def _normalize_value(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
```

### TypeScript/React (Frontend)

- Follow the local style of the file you're editing
- **Naming**: `PascalCase` components/interfaces, `camelCase` functions/variables
- **Imports**: External packages first, then local modules
- **Components**: Use function components and hooks
- **Cleanup**: Always clean up timers, object URLs, audio resources in `useEffect`

### Tailwind CSS

- Use semantic tokens from `src/index.css` (`bg-bg-panel`, `text-text-secondary`)
- Maintain Ableton-inspired dark visual language
- Keep motion purposeful and lightweight

## Security Considerations

### API Keys

- **Gemini API Key**: Stored in backend environment, NOT exposed to frontend
- Frontend Phase 2 uses backend-mediated Gemini calls
- Never commit API keys to the repository

### CORS

Backend allows these origins:
- `http://localhost:3000`, `http://127.0.0.1:3000`
- `http://localhost:3100`, `http://127.0.0.1:3100`
- `http://localhost:5173`, `http://127.0.0.1:5173`

### File Uploads

- Temporary files are written to disk during analysis
- Files are cleaned up after processing (success or error)
- Maximum inline upload size: 100MB (base64 encoded)
- Larger files use Gemini Files API

### Local Development Only

Current quality bar is for local development. Do not present as production-ready security until:
- Gemini access is moved out of browser bundle (if applicable)
- Proper authentication is implemented
- Input validation is hardened

## Environment Configuration

### Frontend Environment Variables

Create `apps/ui/.env` from `.env.example`:

```bash
# Required for backend connection
VITE_API_BASE_URL="http://127.0.0.1:8100"

# Enable Phase 2 Gemini features
VITE_ENABLE_PHASE2_GEMINI="true"

# For direct Gemini access (if implemented)
VITE_GEMINI_API_KEY="your_key_here"

# Disable HMR for testing
DISABLE_HMR="true"
```

### Backend Environment Variables

```bash
# Server port (default: 8100)
SONIC_ANALYZER_PORT=8100

# Gemini API key for Phase 2
GEMINI_API_KEY="your_key_here"
```

### Test Environment Variables

```bash
# Live backend smoke tests
TEST_FLAC_PATH=/path/to/track.flac
VITE_API_BASE_URL=http://127.0.0.1:8100

# Live Gemini smoke tests
RUN_GEMINI_LIVE_SMOKE=true
VITE_ENABLE_PHASE2_GEMINI=true
VITE_GEMINI_API_KEY=your_key_here
```

## Network Configuration

### Canonical Local Ports

| Service | Port | URL |
|---------|------|-----|
| UI dev server | 3100 | http://127.0.0.1:3100 |
| Backend API | 8100 | http://127.0.0.1:8100 |

### API Endpoints

Backend exposes:

- `POST /api/analyze/estimate` - Get runtime estimate
- `POST /api/analyze` - Run full analysis
- `POST /api/phase2` - Gemini interpretation
- `GET /openapi.json` - OpenAPI schema
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc documentation

## Deployment

### Current Status

The system is designed for **local development** use. Current limitations:

- SQLite database stored locally (`.runtime/analysis_runs.sqlite3`)
- Artifact storage on local filesystem
- No authentication/authorization layer
- Python 3.11.x requirement for full setup

### Deployment Considerations

Before production deployment:

1. Move to proper database (PostgreSQL)
2. Implement cloud storage for artifacts
3. Add authentication layer
4. Containerize with Docker
5. Implement proper secret management
6. Add rate limiting and resource controls

## Sub-Project Documentation

For detailed information specific to each app, see:

- `apps/ui/AGENTS.md` - Frontend-specific guidance, React patterns, styling rules
- `apps/backend/AGENTS.md` - Backend-specific guidance, DSP pipeline, testing expectations
- `apps/backend/ARCHITECTURE.md` - Backend component responsibilities
- `apps/backend/JSON_SCHEMA.md` - Raw CLI and HTTP schema documentation
- `docs/ARCHITECTURE_STRATEGY.md` - Architecture decisions and roadmap

## Important Constraints

1. **Python Version**: Backend requires Python 3.11.x for full-feature local setup. Python 3.12+ is not yet supported because Essentia 2.1b6 wheels are only published for 3.11 on macOS arm64.

2. **No Repo-Wide Formatting**: No ESLint/Prettier/Ruff baseline is enforced. Follow the style of the surrounding file.

3. **Contract Boundaries**:
   - Measurement result is authoritative
   - Symbolic transcription is injected from symbolic stage (not copied from measurement)
   - UI/backend contract is strict and strongly typed

4. **Before Structural Changes**: Read `docs/ARCHITECTURE_STRATEGY.md` first. It contains the reasoning behind the current design and planned experiments.

## Common Tasks

### Adding a New DSP Feature

1. Add function in `apps/backend/analyze.py`
2. Update raw JSON output schema (document in `JSON_SCHEMA.md`)
3. Update `server.py` normalization if needed
4. Update frontend `types.ts` if new fields exposed via HTTP
5. Add tests in `tests/test_analyze.py`

### Adding a New API Endpoint

1. Add route in `apps/backend/server.py`
2. Run contract tests: `./venv/bin/python -m unittest tests.test_server`
3. Update OpenAPI will be automatic
4. Add frontend client method in `src/services/`
5. Update frontend types in `src/types.ts`

### Debugging Backend Issues

1. Check logs on stderr (timing, diagnostics)
2. Run CLI directly: `./venv/bin/python analyze.py <file> --yes`
3. Verify JSON output is valid
4. Run contract tests to isolate issue

## Change Checklist

Before submitting changes:

- [ ] If changing API request parsing, run `tests/test_server.py`
- [ ] If changing raw analyzer output, run `tests/test_analyze.py` and update docs
- [ ] If changing timeout or diagnostics, inspect both tests and `ARCHITECTURE.md`
- [ ] If adding a new field, document whether it belongs to raw CLI output, HTTP `phase1`, or both
- [ ] Run narrowest relevant test first, then full suite for broad changes
- [ ] Frontend: run `npm run verify` for app-wide changes
- [ ] Backend: run `./venv/bin/python -m unittest discover -s tests`

## Getting Help

- Review `docs/ARCHITECTURE_STRATEGY.md` for architecture reasoning
- Check `apps/backend/JSON_SCHEMA.md` for API contracts
- See `README.md` at repo root and in each app directory
- Review existing tests for usage examples
