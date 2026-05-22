# External Repo Incorporation Review — 2026-05-13

> **Archived 2026-05-15.** Completed review. Outcomes:
> - **Track 1 (loudness)** — verification spike confirmed Essentia's `LoudnessEBUR128` is correct on stereo program material; sample-rate threading fix shipped in [PR #34](https://github.com/slittycode/ableton-sonic-analyzer/pull/34). Reassigned spectrogram landed as an opt-in spectral enhancement in [PR #43](https://github.com/slittycode/ableton-sonic-analyzer/pull/43).
> - **Track 2 (schema + CSV export)** — ADR ratified at [`docs/adr/0001-phase1-json-schema-v1.md`](../adr/0001-phase1-json-schema-v1.md); CSV exporter shipped in [PR #35](https://github.com/slittycode/ableton-sonic-analyzer/pull/35).
> - **Track 3 (REST adopt list)** — URL-mode ingestion ([PR #36](https://github.com/slittycode/ableton-sonic-analyzer/pull/36)), `X-Admin-Key` ([PR #37](https://github.com/slittycode/ableton-sonic-analyzer/pull/37)), source-audio re-serve ([PR #40](https://github.com/slittycode/ableton-sonic-analyzer/pull/40)), and additive `publicStatus` ([PR #42](https://github.com/slittycode/ableton-sonic-analyzer/pull/42)) all landed. SDIF deferred.
>
> Kept here for the rationale trail; the action items are no longer live.

**Subject:** Evaluating openmeters, soundscope, Partiels, and forever-jukebox against ASA's mission and current implementation.

**Authored by:** Claude (review-only branch `claude/review-asa-repos-5XA5r`).
No code changes; this is an evaluation document.

**Anchor:** [PURPOSE.md](../../PURPOSE.md) — the user-value test and the
decision framework. Every recommendation below traces back to one of
its three "build it" criteria or its "stop and reconsider" branch.

---

## TL;DR

| Track | Plan's framing | This review's read | Recommendation |
| --- | --- | --- | --- |
| 1 — LUFS via openmeters + soundscope oracle | "Likely tracks an older BS.1770 rev" | **Unverified premise.** Essentia 2.1b6 (`LoudnessEBUR128`) implements EBU R128 v3.0 / BS.1770-3+. The user-facing delta to 1770-5 is mostly editorial. Spectral reassignment is the real prize, and it is significant work. | **Defer Track 1 as written.** First do a 1-day spike to (a) confirm Essentia's revision and (b) compare ASA's `lufsIntegrated` against the EBU R128 test set. If deltas are within ±0.1 LU, the loudness rewrite has no user value. Spectral reassignment is a separate, larger effort — treat it as its own track. |
| 2 — Schema via Partiels | "ASA's JSON output should be a subset of what serious analysis tools already emit" | **Misreads Partiels.** Its CSV is three flat columns (`time, duration, label/value`). Its JSON is sparse and undocumented. ASA's schema is *richer*, not poorer. There is nothing to be a "subset of." | **Reframe and proceed.** The right adoption is a *tabular CSV view per time-series field* (lufsCurve, tempoCurve, spectralBalanceTimeSeries, etc.), patterned after Partiels' `time, duration, value` columns. Defer SDIF indefinitely (no demand, no payoff). Ship a single ADR + per-time-series CSV exporter. |
| 3 — REST via forever-jukebox | "Closest public precedent for ASA's product surface" | **Closer than the plan acknowledges in transport, further than the plan acknowledges in output shape.** Both poll an async job; that's where the similarity ends. forever-jukebox emits Echo Nest beats/segments/sections for *playback*. ASA emits production-recreation measurements. ASA's API is already richer in 3 of 5 dimensions. | **Do the side-by-side, but expect a short adopt list.** Worth lifting: URL-based input (`POST /api/analysis/url`), simpler client-facing state machine, retry-on-retryable. Worth rejecting: Echo Nest output schema, 20 MB upload cap, Spotify/YouTube search. ASA already wins on error envelope, staged execution, and ownership/auth. |

**Sequencing recommendation:** Track 2 (scoped down) → Track 3 (audit + targeted lift) → Track 1 (gated on the verification spike). This matches the plan's order but with lower ambition on Tracks 1 and 2 and a tighter target on Track 3.

---

## License Map (read this before reading any of the target sources)

| Repo | License | Implication for ASA |
| --- | --- | --- |
| **ASA** (this repo) | MIT ([LICENSE](../../LICENSE)) | Permissive; can adopt MIT/BSD/Apache code with attribution. **Cannot vendor GPL code.** |
| **openmeters** | GPL-3.0 | Algorithms are not copyrightable, but copied/translated *code* is. Read the **ITU-R BS.1770-5 standard PDF** for the algorithm; do not read openmeters' source if you intend to write a clean-room port. Treat as inspiration-only. |
| **soundscope** | MIT | Code-compatible. But it's TUI-only with no JSON/CLI numeric output, so it can only serve as a *manual* cross-check, not an automated oracle. |
| **Partiels** | GPL-3.0 | File-format schemas are facts, not copyrightable expression; mirroring its CSV column shape is safe. Do not vendor Partiels code. |
| **forever-jukebox** | MIT | Code-compatible; safe to read and selectively port. |

**The plan's framing of "port algorithms (NOT fork — Rust → Essentia.js / JS)" misses one thing:** Rust → JS is not the boundary that matters here. ASA's measurement layer is **Python (Essentia)**, not JS/WASM. There is no Essentia.js in this codebase ([analyze_core.py:8](../../apps/backend/analyze_core.py)). Re-implementing in JS/WASM would be a second port to the wrong runtime — see Track 1 below.

---

## Track 1 — Loudness path (openmeters, soundscope as oracle)

### Where ASA's loudness lives today

- Implementation: [`analyze_core.py:186-230`](../../apps/backend/analyze_core.py) — calls `essentia.standard.LoudnessEBUR128()`.
- True-peak: separate path via `essentia.standard.TruePeakDetector()` at [`analyze_core.py:233-`](../../apps/backend/analyze_core.py).
- Fields emitted: `lufsIntegrated`, `lufsRange`, `lufsMomentaryMax`, `lufsShortTermMax`, `lufsCurve.{shortTerm,momentary}[]`, `truePeak`, `crestFactor`, `plr`. All gated by `EXPECTED_TOP_LEVEL_KEYS` in [`tests/test_analyze.py:26-43`](../../apps/backend/tests/test_analyze.py).
- Curves are downsampled via `_downsample_lufs_array` in `dsp_utils.py` for payload size.

### What openmeters offers

- Rust, GPL-3.0, ~135 ★, BS.1770-5 (Nov 2023). Built on RustFFT/RealFFT.
- Spectrogram with spectral reassignment — the README cites academic references in source headers, but per the README this is on the spectrogram visual path, not the loudness path.
- Standalone Linux PipeWire app. Not a library, not a CLI extractor; embedding it from Python would require carving out its DSP modules.

### What soundscope offers

- Rust, MIT, ~175 ★. TUI with LUFS, true peak, frequency spectrum, waveform.
- **No JSON output and no documented BS.1770 revision.** Useful for human verification ("does soundscope's LUFS match ASA's on the same file?") but cannot be wired into ASA tests as an automated oracle.

### Why the plan's premise needs verification

The plan asserts ASA "likely tracks an older BS.1770 rev." Two facts make this less obvious than the assertion:

1. **Essentia's `LoudnessEBUR128`** implements the EBU R128 algorithm, which references BS.1770. The Essentia 2.1b6 docs do not pin a specific BS.1770 revision; the spec it tracks is EBU R128 v3.0 (2014), which is built on BS.1770-3+ with EBU-specific gating. For broadcast-loudness numbers, R128 v3.0 and BS.1770-5 produce values within hundredths of a LU on stereo program material.

2. **Where BS.1770 has actually changed** (`-3` → `-4` → `-5`):
   - `-3` (2012): true-peak metering specified.
   - `-4` (2015): multichannel weighting extended to NHK 22.2.
   - `-5` (2023): primarily editorial clarifications + true-peak measurement refinements.

ASA processes stereo audio. The functional delta between Essentia's `LoudnessEBUR128` and an ITU-R BS.1770-5 reference implementation, *on stereo material*, is likely below the precision ASA reports (`round(integrated, 1)` — one decimal place of a LU, per [`analyze_core.py:216`](../../apps/backend/analyze_core.py)).

This does not mean "do nothing." It means **measure before rewriting**:

- Run ASA on the [EBU R128 test set (Tech 3341 / 3342)](https://tech.ebu.ch/publications/ebu_loudness_test_set).
- Compare `lufsIntegrated` against each track's documented target.
- If ASA's deltas are within ±0.1 LU: the loudness path is *already correct enough*. No port. Add the test set + tolerances as a regression gate (achieves the plan's DoD bullet 4 without any algorithm work).
- If deltas exceed ±0.1 LU: investigate why. Probably an Essentia gating-window or LRA bug, not a revision-of-BS.1770 issue.

### Spectral reassignment — the real opportunity

Reassignment is a distinct concept from BS.1770. It sharpens a spectrogram by relocating each STFT bin to the centroid implied by the local time and frequency derivatives of the analyzing window, yielding much sharper transients than vanilla STFT. **This is a real and visible UX improvement** for ASA's spectral artifacts.

But:

- The user-value bar is **the spectrogram view**, not the measurement layer. PURPOSE.md invariant 1 says Phase 1 measurements are ground truth; reassignment improves the *picture*, not the number that Phase 2 cites. So it pulls criterion 2 ("more accurate or actionable" — yes, for the visual) and criterion 3 ("act on results" — yes, sharper transient location). Both are legitimate.
- Implementation cost is non-trivial. The reassignment formula needs analytic differentiation of the analyzing window. In Python, the cleanest path is **librosa's `librosa.reassigned_spectrogram`** (already a dependency for `spectral_viz.py`) — no porting of openmeters required.
- **Recommendation: skip openmeters entirely for this.** Stand up `librosa.reassigned_spectrogram` as an opt-in mode behind a `?reassign=1` query param on the spectral-artifact endpoints. Costs: ~half a day to wire and gate; no license risk; no new dependency.

### Adopt / Adapt / Reject for Track 1

| Item | Decision | Why |
| --- | --- | --- |
| Port openmeters' BS.1770-5 loudness to Python | **Reject (as written).** | Premise unverified; Essentia is likely close enough. License risk (GPL-3.0). Wrong runtime target (Rust → Python, not Rust → JS). |
| Add EBU R128 test set as a tolerance regression gate | **Adopt.** | Cheap. Verifies the premise. Satisfies the plan's DoD without algorithmic work. Serves PURPOSE.md criterion 1 (accuracy of ground truth). |
| Use soundscope as an automated oracle | **Reject.** | TUI-only; no JSON output to diff against. Can be a manual sanity check, nothing more. |
| Add spectral reassignment via `librosa.reassigned_spectrogram` (not openmeters) | **Adopt as a separate, smaller track.** | Genuine UX improvement on the spectrogram path. Zero license risk. Native to existing dependency. |
| Verify Essentia's BS.1770 revision in our pinned version | **Adopt as the first step.** | Resolves the ambiguity that makes the rest of Track 1 ambiguous. One Read of the Essentia changelog + one note in `analyze_core.py`. |

### Definition of done (revised)

- [ ] Note in `analyze_core.py` documenting which BS.1770 revision Essentia 2.1b6's `LoudnessEBUR128` tracks.
- [ ] EBU R128 test set committed under `apps/backend/tests/fixtures/r128/` with documented target tolerances.
- [ ] A `test_loudness_r128.py` that loads each fixture and asserts `abs(lufsIntegrated - target) < 0.1`.
- [ ] If the test set passes: close Track 1 with no algorithm rewrite. If it fails: triage Essentia, not BS.1770-5.
- [ ] (Independent of the above) `librosa.reassigned_spectrogram` available behind a feature flag for the spectral artifact endpoint.

---

## Track 2 — Result-interchange schema (Partiels)

### Where ASA's schema lives today

- Spec: [`apps/backend/JSON_SCHEMA.md`](../../apps/backend/JSON_SCHEMA.md) — 60+ top-level keys, deeply nested per-domain detail objects.
- Test snapshot: `EXPECTED_TOP_LEVEL_KEYS` at [`tests/test_analyze.py:26-43`](../../apps/backend/tests/test_analyze.py).
- Frontend mirror: [`apps/ui/src/types/measurement.ts`](../../apps/ui/src/types/measurement.ts) — `Phase1Result` and its detail interfaces.
- Time-tagged fields today: `lufsCurve.{shortTerm,momentary}[]` (`{t, lufs}`), `spectralBalanceTimeSeries[]` (`{t, subBass, lowBass, …}`), `rhythmDetail.tempoCurve[]` (`{t, bpm}`), `segmentLoudness`/`segmentSpectral`/`segmentStereo`/`segmentKey` (per-section summary objects, not per-frame).
- Export formats: JSON (over HTTP); MIDI for melody/transcription via `apps/ui/src/services/midi/midiExport.ts`. **No CSV, SDIF, LAB, or REAPER export today.**

### What Partiels exports

From the [Partiels Manual](https://github.com/Ircam-Partiels/Partiels/blob/main/Docs/Partiels-Manual.md):

- **CSV:** Three columns — `time`, `duration`, and either `label` (for markers) or one or more numerical values (for points/matrices). Optional header row.
- **JSON:** Per-track export; optional "Include Extra Description" block describes the processor (Vamp plugin) that produced the data. No documented top-level schema.
- **SDIF:** User configures the frame signature and matrix signature per export. No canonical signatures shipped by Partiels.
- **LAB, CUE, REAPER, MAX, PUREDATA:** Tool-specific marker/event formats — mostly time-anchored events.
- **CLI:** Exists; no flags documented in the manual section provided.

### The framing problem

The plan says: *"ASA's JSON output should be a subset of what serious analysis tools already emit."*

This treats Partiels as a richer, established schema for ASA to mirror. The reality is the opposite. Partiels' export shape is *deliberately thin* because it serves a different purpose: feeding analysis results into music software (Max, PD, REAPER) that just needs `(time, duration, value)` tuples per Vamp track. Partiels' "schema" is essentially **one analysis track per file, with a flat row-per-frame structure** — not a domain schema with named, nested measurements.

ASA's schema is the opposite: **one analysis per audio file, with dozens of named measurement domains** (kickDetail, sidechainDetail, spectralBalance, …), each carefully matched to a Phase 2 prompt obligation. The PURPOSE.md citation chain depends on this naming. Reducing ASA to a Partiels-style flat schema would break the chain of custody (Quality Invariant #2).

### What's actually useful from Partiels

The valuable pattern in Partiels' export model is **the tabular CSV view for time-series fields**. ASA has several `[{t, value}]` arrays today that would interoperate well with Max, REAPER, PD if exposed as CSV. This is the right lift.

A concrete per-field CSV view, modeled on Partiels' `time, duration, value` shape:

| ASA time-series field | CSV columns | Use case |
| --- | --- | --- |
| `lufsCurve.shortTerm` | `time, duration=3.0, lufs` | Pull a R128 short-term curve into REAPER as a track of automation. |
| `lufsCurve.momentary` | `time, duration=0.4, lufs` | Same, for moment-by-moment dynamics. |
| `rhythmDetail.tempoCurve` | `time, duration, bpm` | Match a reference's tempo drift in an Ableton tempo automation lane. |
| `spectralBalanceTimeSeries` | `time, duration, subBass, lowBass, lowMids, mids, upperMids, highs, brilliance` | EQ-curve evolution per section. |
| `rhythmTimeline.beats[]` + `downbeats[]` | `time, label="beat"|"downbeat"` | Beat grid as markers (matches Partiels' marker CSV exactly). |

This adds an export channel without disturbing the JSON contract. The HTTP surface would be:

- `GET /api/analysis-runs/{run_id}/export/csv/{field_path}` — e.g. `…/csv/lufsCurve.shortTerm`. Returns `text/csv`.

### SDIF defer (with the paragraph the plan asked for)

SDIF is IRCAM's binary frame format. The full SDIF spec involves frame/matrix signatures (e.g. `1FQ0` for fundamental frequency, `1STF` for STFT) that have no native equivalent in ASA's domain schema. There is no current user demand for SDIF in the ASA target audience (intermediate Ableton producers), and the cost is real: implementing SDIF means either a dependency on libIRCAM-SDIF or writing a binary serializer.

**Revisit when:** a user requests SDIF *with a concrete downstream use case* (Max patch consumes ASA output, OpenMusic project loads ASA tempograms, etc.), or when ASA grows a domain that overlaps with Vamp's established Vamp/SDIF signatures (e.g. polyphonic transcription producing per-frame fundamentals).

### Adopt / Adapt / Reject for Track 2

| Item | Decision | Why |
| --- | --- | --- |
| Make ASA's JSON "a subset of Partiels' export schemas" | **Reject as written.** | Misreads Partiels' shape. ASA's schema is richer by design; flattening it breaks the chain of custody. |
| Document ASA's JSON shape as an ADR (versioned, frozen contract) | **Adopt.** | JSON_SCHEMA.md exists but doesn't carry an explicit version or stability promise. An ADR ratifies "this is the v1 contract" and defines the compatibility policy. |
| Add a CSV view per time-series field, patterned on Partiels' columns | **Adopt.** | Interop with Max/REAPER/PD without contorting the JSON. New endpoint, additive, no migration cost. |
| Implement SDIF export | **Defer.** | No user demand. Cost real. Revisit when polyphonic transcription stabilizes. |
| Mirror Partiels' "Include Extra Description" idea | **Partially adopt.** | ASA already does this via `diagnostics` (engineVersion, timings, flagsUsed). Document the parallel; no new code. |

### Definition of done (revised)

- [ ] `docs/adr/0001-phase1-json-schema-v1.md` — declares the current schema v1, lists invariants, defines the compatibility policy (additive-only minor bumps; renames are major bumps).
- [ ] `GET /api/analysis-runs/{run_id}/export/csv/{field_path}` endpoint with CSV exporters for: `lufsCurve.shortTerm`, `lufsCurve.momentary`, `rhythmDetail.tempoCurve`, `spectralBalanceTimeSeries`, `rhythmTimeline.beats`, `rhythmTimeline.downbeats`.
- [ ] One round-trip test in `tests/services/csvExport.test.ts` that compares CSV columns to JSON values.
- [ ] SDIF deferral note in this document (above) referenced from `BACKLOG.md`.

---

## Track 3 — REST contract (forever-jukebox)

### Where ASA's API lives today

From the survey of [`server.py`](../../apps/backend/server.py), [`server_phase1.py`](../../apps/backend/server_phase1.py), [`server_phase2.py`](../../apps/backend/server_phase2.py), [`server_upload.py`](../../apps/backend/server_upload.py), and [`analysis_runtime.py`](../../apps/backend/analysis_runtime.py):

**Canonical (run-oriented):**
- `POST /api/analysis-runs` — create run (multipart upload).
- `POST /api/analysis-runs/estimate` — estimate without executing.
- `GET /api/analysis-runs/{run_id}` — snapshot poll (1 s default interval, see `analyzer.ts:16`).
- `POST /api/analysis-runs/{run_id}/interrupt` — cancel.
- `DELETE /api/analysis-runs/{run_id}` — purge.
- `GET /api/analysis-runs/{run_id}/artifacts` and `…/artifacts/{artifact_id}`.
- `POST /api/analysis-runs/{run_id}/spectral-enhancements/{kind}` (CQT, HPSS, onset, chroma).
- `POST /api/analysis-runs/{run_id}/pitch-note-translations`.
- `POST /api/analysis-runs/{run_id}/interpretations`.

**Legacy:** `POST /api/analyze`, `POST /api/analyze/estimate`, `POST /api/phase2` — wrappers kept for compatibility only ([CLAUDE.md](../../CLAUDE.md), "Staged Analysis Runs").

**Error envelope:** Always includes `requestId`, `error.code`, `error.message`, `error.retryable`, `diagnostics`. Stage states: `queued`, `running`, `blocked`, `ready`, `completed`, `failed`, `interrupted`, `not_requested`.

**Upload limit:** 100 MiB raw / 101 MiB request envelope ([`upload_limits.py:7-16`](../../apps/backend/upload_limits.py) — `MAX_UPLOAD_SIZE_BYTES` 104,857,600 + `UPLOAD_REQUEST_SIZE_SLACK_BYTES` 1,048,576 = 105,906,176 bytes = 101 MiB).

### What forever-jukebox exposes

From [`api/README.md`](https://github.com/creightonlinza/forever-jukebox/blob/main/api/README.md):

- `POST /api/upload` (multipart, 20 MB cap, gated by `ALLOW_USER_UPLOAD=true`).
- `POST /api/analysis/youtube` (`{youtube_id}`) — analyze a YouTube ID.
- `POST /api/analysis/url` (`{url}`) — analyze a URL.
- `GET /api/analysis/<id>` — three response shapes: `{status: "downloading|queued|processing", progress}` (HTTP 202), `{status: "complete", result}` (HTTP 200), `{status: "failed", error}` (HTTP 200).
- `GET /api/search/{spotify,youtube}` — search.
- `GET /api/audio/<id>` — stream the source audio.
- `POST /api/plays/<id>` / `PATCH …` — play tracking (admin via `X-Admin-Key`).
- `GET /api/{top,trending,recent}` — discovery.
- `POST|PUT|GET /api/favorites/sync/...` — multi-device sync.
- `GET /api/jobs/by-source/<type>/<id>` / `DELETE /api/jobs/<id>`.
- `GET /api/app-config`.
- Retry: failed jobs auto-reissue on resubmission with the same source.

### Side-by-side: where ASA leads, matches, lags

| Dimension | forever-jukebox | ASA today | Verdict |
| --- | --- | --- | --- |
| Async pattern | Poll `GET /api/analysis/<id>` until status flips | Poll `GET /api/analysis-runs/{run_id}` | **Match.** Pattern-equivalent. |
| State machine (public-facing) | 5 states: `downloading | queued | processing | complete | failed` | 8 states: `queued | running | blocked | ready | completed | failed | interrupted | not_requested` | **ASA over-exposes.** `blocked`, `ready`, `not_requested` are useful internally; they leak run-runtime concepts to clients. Worth collapsing in the public response. |
| Error envelope | Inline `{error}` blob in the response; no documented `requestId` / `retryable` flag | `requestId`, `error.code`, `error.message`, `error.retryable`, `diagnostics` | **ASA leads.** Don't regress. |
| Input methods | Upload + YouTube ID + URL | Upload only | **forever-jukebox leads.** URL ingestion would help producers analyze reference tracks they don't have a local file for. YouTube has TOS hazards; URL is clean. |
| Upload size | 20 MB | 100 MiB | **ASA leads** — and the difference matters for long, full-bit-rate FLAC reference tracks. |
| Job retry | Auto-creates a new job on resubmission of a retryable failure | Client must explicitly recreate the run; `error.retryable` is advisory | **forever-jukebox slightly leads.** ASA's `retryable` flag is informative; turning it into automatic retry on resubmit would close the loop. |
| Discovery (top/trending/recent) | Yes | No | **Out of scope** for ASA's target user — they have a specific reference track, not a feed. |
| Search (Spotify/YouTube) | Yes | No | **Out of scope** for ASA — pulling rights-restricted audio is a separate product question. |
| Admin auth | `X-Admin-Key` header | None at the canonical-API layer ([`auth_context.py`](../../apps/backend/auth_context.py) handles hosted-mode user context but not admin) | **forever-jukebox leads operationally**; ASA has a forward design for hosted auth but no admin-key surface for operator tasks (purge a run, audit a job). Worth filing. |
| Audio re-serve | `GET /api/audio/<id>` | No | **Worth considering** — ASA already persists artifacts; re-serving the original audio at the staged endpoint avoids re-uploading on Phase 2 reruns. |

### Adopt / Adapt / Reject per endpoint

| forever-jukebox endpoint | Decision | Notes |
| --- | --- | --- |
| `POST /api/analysis/url` | **Adopt** | Add `POST /api/analysis-runs` URL-mode variant (multipart with `url` field instead of `file`). Server fetches, stores via `artifact_storage.py`, then runs the same pipeline. Respect `upload_limits.py`. |
| `POST /api/analysis/youtube` | **Reject** | YouTube ToS; would change ASA's risk profile. URL ingestion covers the underlying need for licit sources. |
| Retry on resubmission | **Adapt** | Use ASA's `error.retryable` flag as the signal; if a client POSTs `/api/analysis-runs` with the same `source_hash` and the prior run failed retryably, return the new run's `run_id` (idempotency-style). |
| `GET /api/audio/<id>` | **Adopt** | `GET /api/analysis-runs/{run_id}/source-audio` — serves the original file from `artifact_storage.py`. Removes the need to re-upload for Phase 2 reruns. |
| Collapsed public state machine | **Adapt** | Keep the 8 internal states; expose 5 in the public snapshot. Map `blocked` and `not_requested` to `pending`; map `ready` to `queued`. Document the collapse in JSON_SCHEMA.md. |
| `X-Admin-Key` for admin ops | **Adopt** | Apply to `DELETE /api/analysis-runs/{run_id}` and a forthcoming `GET /api/admin/runs` listing. Gate via existing `auth_context.py`. |
| Search / discovery / favorites / play tracking | **Reject** | Out of scope for the recreation-blueprint mission. PURPOSE.md decision-framework branch 5: "stop and reconsider." |
| Echo Nest-style beats/segments/sections output | **Reject** | ASA emits richer, named domain measurements ([`JSON_SCHEMA.md`](../../apps/backend/JSON_SCHEMA.md)). Adopting Echo Nest's flat segment schema would collapse the citation chain (Quality Invariant #2). |

### Definition of done (revised)

- [ ] Side-by-side endpoint comparison committed (this section is the seed; expand into `docs/api-comparison-2026-05-13.md` if it gets longer).
- [ ] ADR per "adopt" decision: URL input, admin key, audio re-serve, collapsed public state machine.
- [ ] API doc updated (currently lives in [`apps/backend/ARCHITECTURE.md`](../../apps/backend/ARCHITECTURE.md)) — specifically the public state-machine collapse, since it's the only contract-shape change.

---

## Risks & Watch-outs

| Risk | Track | Mitigation |
| --- | --- | --- |
| GPL contamination from reading openmeters/Partiels source | 1, 2 | Read ITU-R BS.1770-5 (PDF, gratis from ITU) and Partiels' user manual instead of source. Document algorithmic provenance per file. |
| BS.1770 revision premise is wrong (Essentia already does -3 to -5 equivalent for stereo) | 1 | Run the verification spike first. Cheapest possible disproof. |
| Spectral-reassignment requires WASM | 1 | False risk — use `librosa.reassigned_spectrogram` server-side. Same dependency family as `spectral_viz.py`. |
| CSV exporter explosion (one endpoint per field path) | 2 | Generic `…/export/csv/{field_path}` resolves a dot-path (e.g. `lufsCurve.shortTerm`) into the snapshot — not JSONPath, just nested-key descent. One endpoint, finite serializers per type. |
| State-machine collapse breaks legacy clients | 3 | The legacy clients are ASA's own UI; map at the server boundary. Bump the `phase1` envelope version if external consumers ever exist. |
| URL ingestion exposes the server to arbitrary network egress | 3 | Limit to a configurable allowlist of hosts in hosted-mode; in local mode, allow all. Reuse `upload_limits.py` to cap downloaded bytes. |

---

## Sequencing

Same order as the plan, different reasons:

1. **Track 2 — schema work, scoped down.** ~2-3 days. ADR + CSV exporters for six time-series fields. SDIF deferred with this document as the rationale.
2. **Track 3 — API audit, targeted lift.** ~2-3 days. URL input + state-machine collapse + admin key + audio re-serve. The Echo Nest schema is left alone.
3. **Track 1 — verification spike first; full rewrite gated.** ~1 day spike. EBU R128 test set + tolerance assertion. If green: close as a regression test addition (no algorithm work). If red: triage Essentia. Spectral reassignment as a separate ~1-day add via `librosa.reassigned_spectrogram`, no openmeters dependency.

**Total estimated effort if all three adopted:** 6-8 working days, dominated by Tracks 2 and 3. This is roughly half of what the plan implies because the most expensive items (porting openmeters, mirroring Partiels' SDIF, full Echo Nest schema parity) are rejected.

---

## What was *not* evaluated

The plan's "Out of scope" list is correct:

- **spleeter-web** — revisit when ASA adds stems beyond Demucs.
- **Olaf** — revisit if cross-take alignment becomes a feature.
- **nightingale** — desktop shell; not relevant until/unless ASA grows a desktop app.
- **ChordMiniApp / chordonomicon / rawl** — harmonic-domain tools; flagged separately in [`BACKLOG.md`](../../BACKLOG.md) as a Harmonia track.

> **Correction (2026-05-22):** "Harmonia" was later verified to be a phantom — no such project exists (`github.com/slittycode/harmonia` 404s; absent from `CLAUDE.md` / `PURPOSE.md` / `BACKLOG.md`). **`BACKLOG.md` has never contained a "Harmonia track"** — this cross-reference was dangling at birth (the line was introduced in the same commit that added `BACKLOG.md` itself). The three named repos are real but were mis-scoped to a non-existent sibling. See the correction banner in [`incorporations/forking-plans-2026-05-14.md`](../../incorporations/forking-plans-2026-05-14.md).

No change to the deferral logic.

---

## Sources

- Anchoring docs in this repo: [PURPOSE.md](../../PURPOSE.md), [CLAUDE.md](../../CLAUDE.md), [apps/backend/JSON_SCHEMA.md](../../apps/backend/JSON_SCHEMA.md), [apps/backend/analyze_core.py](../../apps/backend/analyze_core.py), [apps/backend/upload_limits.py](../../apps/backend/upload_limits.py).
- [openmeters on GitHub](https://github.com/httpsworldview/openmeters) (GPL-3.0).
- [bananaofhappiness/soundscope on GitHub](https://github.com/bananaofhappiness/soundscope) (MIT).
- [Ircam-Partiels/Partiels on GitHub](https://github.com/Ircam-Partiels/Partiels) (GPL-3.0).
- [Partiels Manual](https://github.com/Ircam-Partiels/Partiels/blob/main/Docs/Partiels-Manual.md) — export format documentation.
- [creightonlinza/forever-jukebox on GitHub](https://github.com/creightonlinza/forever-jukebox) (MIT).
- [forever-jukebox API README](https://github.com/creightonlinza/forever-jukebox/blob/main/api/README.md).
- [ITU-R BS.1770-5 (Nov 2023, PDF)](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I!!PDF-E.pdf).
- [EBU R128 test set (EBU Tech 3341/3342)](https://tech.ebu.ch/publications/ebu_loudness_test_set).
- [librosa.reassigned_spectrogram](https://librosa.org/doc/main/generated/librosa.reassigned_spectrogram.html).
