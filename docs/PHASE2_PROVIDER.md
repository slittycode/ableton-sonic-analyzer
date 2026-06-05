# Phase 2 Provider Abstraction (Gemini ↔ MOSS) — STEP ONE Licence Gate + Build

Status: **STEP ONE complete — split verdict (weights clean, code unlicensed).
Maintainer chose to build the default-off research experiment (option A). The
provider abstraction, the mock-capable MOSS sidecar, and the citation-accuracy
eval are implemented and verified; the real MOSS model path stays a licence-gated
stub and the live MOSS-vs-Gemini numbers remain blocked (see below).**

> **What was built (option A).** All default-off; Gemini stays the product default.
> - `apps/backend/phase2_provider.py` — `Phase2Provider` seam + `MossSidecarProvider`
>   + `resolve_external_phase2_provider()` (env `ASA_PHASE2_PROVIDER`, default `gemini`).
> - `apps/backend/server.py` — one guarded asymmetric branch in
>   `_run_interpretation_request_with_profile_config`; the Gemini path is unchanged
>   when no external provider is selected. MOSS output flows through the **same**
>   shared tail — parse/salvage + `_validate_phase2_citation_paths` +
>   `apply_live12_catalogue_gates` + the frozen `recommendations.v1` contract
>   (ADR 0003, `build_validated_recommendations`) — so it gets the identical
>   schema and chain-of-custody enforcement for free.
> - `apps/backend/moss_sidecar/` — standalone FastAPI sidecar (own venv). `mock`
>   mode = deterministic, schema-valid, Phase-1-grounded output; `model` mode = a
>   501 stub that executes **no** OpenMOSS code (licence gate).
> - `apps/backend/scripts/evaluate_phase2_providers.py` +
>   `phase2_provider_evaluation.py` — citation-accuracy eval over the fixed
>   `recommendation_tracks/` corpus, reusing the production validators.
> - `apps/backend/tests/test_phase2_provider.py` — 16 contract tests (resolver,
>   mock schema/citation validity, sidecar client, eval scorer).
>
> **Verified** (Python 3.11 venv with the DSP stack):
> - `tests/test_phase2_provider.py` — **22/22 pass**, incl. a MOSS-branch
>   integration test that *executes* `_run_interpretation_request_with_profile_config`
>   with `ASA_PHASE2_PROVIDER=moss` (mocked sidecar HTTP) and asserts the result
>   flows through the shared parse/validate tail (`ok:True`, schema-valid), plus a
>   test that the Gemini default never touches the sidecar.
> - `tests/test_server.py` — **223/223 pass**, so the asymmetric branch is
>   behavior-preserving for the Gemini path (not just by inspection). The Gemini
>   client is still constructed before the `try`, so a client-construction error
>   still propagates as `INTERPRETATION_SETUP_FAILED`, exactly as before.
> - The eval runs on all 5 real corpus tracks (mock: 100% schema-valid / 100%
>   citation-accuracy / 100% grounding-coverage; Gemini + split correctly
>   `BLOCKED`); the sidecar mock + gated 501 stub behave.
>
> **Not run:** the full backend `unittest discover` (the slow Essentia analyzer
> tests are unrelated — no `analyze.py` change, so golden snapshots /
> `EXPECTED_TOP_LEVEL_KEYS` are unaffected) and any live model/Gemini call.

Goal: add a `Phase2Provider` abstraction so Phase 2 interpretation can be routed to
either Gemini (current, product default) or a self-hosted OpenMOSS **MOSS-Audio** model
run as a FastAPI sidecar — fed the same audio + Phase-1 JSON, emitting the identical
measurement-cited `Phase2Result` schema. Phase 1 stays ground truth; recommendations must
cite, never invent (PURPOSE.md invariant #1/#2).

The goal made this explicit and first: **"STEP ONE: confirm OpenMOSS/MOSS-Audio code AND
model-weight licences permit self-host + derivative use — if not, stop and report."**

---

## STEP ONE — Licence verification (primary sources, 2026-06-05)

**Verdict: SPLIT. Weights pass cleanly; the inference code does not.**

### ✅ Model weights — Apache-2.0 (clean)

Every official `OpenMOSS-Team/MOSS-Audio-*` weights repo on HuggingFace declares
`license: apache-2.0` in its card metadata, verified directly via the HF API
(`cardData.license`), not via a search summary:

| Repo | License | Gated | Acceptable-use rider |
|---|---|---|---|
| `OpenMOSS-Team/MOSS-Audio-4B-Instruct` | apache-2.0 | `false` | none (`extra_gated_prompt: null`) |
| `OpenMOSS-Team/MOSS-Audio-8B-Instruct` | apache-2.0 | `false` | none |
| `OpenMOSS-Team/MOSS-Audio-4B-Thinking` | apache-2.0 | `false` | none |
| `OpenMOSS-Team/MOSS-Audio-8B-Thinking` | apache-2.0 | `false` | none |
| `OpenMOSS-Team/MOSS-Audio-Tokenizer` (required at inference) | apache-2.0 | `false` | none |

No NonCommercial clause, no research-only clause, no click-through gate. The backbone is
Qwen3 (also Apache-2.0). **The weights permit self-host + derivative + commercial use.**

### ⚠️ Inference / modeling code — no effective licence (UNCONFIRMED)

The forward-pass code is **not** in the Apache-2.0 HF repo. The HF weights repo ships only
`configuration_moss_audio.py` + `processing_moss_audio.py`, and its `config.json`
`auto_map` declares **only** `AutoConfig` + `AutoProcessor` — **no `AutoModel` entry**
(`architectures: ["MossAudioModel"]`, a custom class with no in-repo definition). The
actual `modeling_moss_audio.py` / `hf_inference.py` / `audio_io.py` live only in the GitHub
repo `OpenMOSS/MOSS-Audio` under `src/`, and:

1. That GitHub repo has **no LICENSE/COPYING/NOTICE file anywhere in its tree**
   (`GET /repos/OpenMOSS/MOSS-Audio/license` → HTTP 404; recursive tree scan → none).
2. Its `pyproject.toml` says `license = { file = "LICENSE" }` — a **dangling reference to a
   file that does not exist**.
3. The README's only licence sentence is *"**Models** in MOSS-Audio are licensed under the
   Apache License 2.0"* — i.e. the **weights**, not unambiguously the code.
4. The documented run-path is `git clone … && pip install -e . && python infer.py` — i.e.
   executing that unlicensed code. `moss_audio` is **not** upstreamed into (Apache-2.0)
   `transformers`.

Absent a licence file, code defaults to **all rights reserved** under copyright. The
dangling `pyproject` reference is the signature of an **oversight** (the intent is clearly
open — Apache-2.0 weights, Qwen3 base), **not** a deliberate restriction like the MSST
separation backend (which is affirmatively AGPL + CC-BY-NC-SA NonCommercial). But as
published, **the code you must run carries no grant.**

### Consequence

- **Not promotable to the product Phase 2 path** until OpenMOSS publishes the missing
  GitHub LICENSE (or upstreams `moss_audio` into Apache-2.0 `transformers`).
- **Gemini stays the product default.** Treat MOSS exactly like the MSST backend: a
  **default-off, isolated research experiment**, documented caveat, never on the product
  request path.
- **Clean-runtime unblock path worth verifying:** the Apache-2.0 *weights* could in
  principle be served by an independent, cleanly-licensed runtime that does **not** use
  OpenMOSS's unlicensed modeling code — e.g. a community GGUF build
  (`cstr/MOSS-Audio-4B-Instruct-GGUF`, apache-2.0) via llama.cpp, **if** that runtime
  actually supports `moss_audio` audio-**in** inference (unverified — llama.cpp audio-in
  for this arch is not confirmed). That path would sidestep the code-licence issue
  entirely.

---

## Eval feasibility — the DoD's live numbers are blocked three ways (today)

The DoD wants a "citation-accuracy eval vs Gemini on a fixed set." All three inputs are
currently unavailable on this machine:

1. **MOSS** cannot be run without executing the unlicensed modeling code (and is a heavy
   8B/4B download); see above.
2. **`GEMINI_API_KEY` is unset** locally → the Gemini baseline can't be generated live.
3. **The fixed set has no audio.** `apps/backend/tests/fixtures/recommendation_tracks/*`
   ships `phase1_fingerprint.json` + `manifest.json` + MIDI, but **no rendered audio**
   (it "awaits owner Ableton renders"). An audio-in model has nothing to listen to.

Honest consequence: the deliverable is the **harness + fixed set + documented procedure +
a programmatic, validator-backed citation scorer**, runnable now against a deterministic
mock/recorded provider, with the live MOSS-vs-Gemini numbers **explicitly stated as
blocked** pending (1) an upstream LICENSE (or clean runtime), (2) a Gemini key, (3) audio
renders. No fabricated comparison numbers.

---

## Decision (maintainer) — **A chosen (2026-06-05)**

Given the split verdict, how far should the MOSS experiment be built now? (Tracked so the
choice is explicit, mirroring the licence-care shown on the MSST backend.) **The maintainer
chose A** — see "What was built" at the top.

- **A — Build the default-off research experiment now (recommended). ← CHOSEN.** Provider abstraction
  (Gemini default, product-safe), a contract/mock MOSS sidecar emitting the identical
  schema, and the citation-accuracy harness — all executing **no** unlicensed code and
  fabricating no numbers. The real MOSS model wiring stays a gated, documented stub until
  the LICENSE lands. Less encumbered than the MSST backend the repo already ships this way.
- **B — Report only; wait for the upstream LICENSE** before any MOSS-specific code.
- **C — Pursue clarification upstream** (file an issue asking OpenMOSS to add the GitHub
  LICENSE) and revisit.

---

## Design (for option A) — provider seam

- `ASA_PHASE2_PROVIDER=gemini` (default) `| moss`. Default-off; the product path is the
  Gemini path, unchanged.
- `phase2_provider.py`: a `Phase2Provider` protocol + `GeminiPhase2Provider` (wraps the
  existing `server.py` `_execute_interpretation_attempt` orchestration) +
  `MossPhase2Provider` (HTTP client to the sidecar). Resolver keyed on the env var.
- Sidecar (`apps/backend/moss_sidecar/`): standalone FastAPI app, **own venv / own
  requirements** (isolation mirrors `separation_backend.py` MSST + MT3), accepts
  `{audio, phase1_json}`, reuses `prompts/phase2_system.txt`, returns the identical
  `Phase2Result`. Ships a `--mock` deterministic mode so the abstraction + harness are
  testable with no model and no GPU.
- **Identical schema** is enforced by routing **both** providers through the existing
  validators (`server_phase2._is_valid_phase2_shape`, `_validate_phase2_citation_paths`,
  `phase2_catalogue_gates.apply_live12_catalogue_gates`). One schema, one validator, two
  providers.
- **Eval** (`scripts/evaluate_phase2_providers.py` + module): fixed
  `recommendation_tracks/` set → each provider → citation-accuracy score computed by
  reusing `_validate_phase2_citation_paths` (cited `phase1Fields` that resolve vs invented)
  → report + the documented "offline-good-enough vs Gemini-wins" split. Research-only.

When information conflicts: PURPOSE.md > CLAUDE.md. Phase 1 stays ground truth; MOSS, like
Gemini, may interpret but never override a measured value.
