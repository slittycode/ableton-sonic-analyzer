# RoFormer Separation Bake-off — Research Campaign Plan (2026-07)

**Status:** ACCEPTED (research only — no product change)  
**Accepted:** 2026-07-18  
**Authority:** `PURPOSE.md` > this plan.  
**Companion docs:**
- [`docs/SEPARATION_ROFORMER_PROBE.md`](../docs/SEPARATION_ROFORMER_PROBE.md)
- [`docs/PYPI_AUDIO_ANALYSIS_TOP20.md`](../docs/PYPI_AUDIO_ANALYSIS_TOP20.md) (#2–#5)

**Draft provenance:** Fable draft (`plans/reformerplana.md`, RTF) cleaned and accepted here.

---

## Standing rule — dual-doc pre-registration

Section 9 of this plan and the probe doc's **"What would justify product work later"** bar are **intentionally identical**.

If you edit one during the campaign, **edit both**, or the pre-registration loses its teeth.

**Alignment note at accept (2026-07-18):** the Fable draft stated them as identical, but the probe doc currently reads as "at least one of" (disjunctive) while this plan's promote bar is conjunctive (ears **and** Phase-3 field lift). **This plan is authoritative for the campaign.** When Phase 4 / mid-campaign edits touch the bar, rewrite the probe section to match Section 9 exactly (conjunctive form below) — do not re-soften it.

---

## Summary

ASA's known vocal weakness traces to Hybrid Demucs vocal stems: ghost energy on instrumentals and lead bleed into `other`, which the analyzer already penalizes via `vocalDetail.stemEnergyRatio` and `vocalDetail.stemOtherCorrelation` (`analyze_detection.py:621–853`, `JSON_SCHEMA.md:524`).

This campaign runs a bounded offline bake-off — Demucs baseline vs. at most three RoFormer configs — on a small owned fixture set, using the existing driver `apps/backend/scripts/probe_roformer_separation.py` and a PURPOSE-aligned pass bar: better stems must move Phase-2-citable fields (`vocalDetail` first; `kickDetail`/bass optionally), not just sound cooler.

The product path (`separation_backend.py` → `analyze_audio_io.separate_stems`, `analyze_audio_io.py:200`) stays Demucs-only throughout. Any seam work happens only after promotion, with this campaign's results doc as the recorded-win evidence the 2026-07 trust diet demanded and MSST never had.

---

## 1. Goal + non-goals

**Goal:** Produce a recorded, reproducible answer to: *do RoFormer-class separators fix ASA's vocal-stem pain (and optionally improve kick/bass stems) in a way that would improve Phase-2-citable fields?*

**Non-goals (explicit):**

1. No product default change. `separation_backend_name()` stays `demucs` for the entire campaign.
2. No RoFormer deps in `apps/backend/requirements.txt` or the product venv — eval venv only.
3. No schema changes, no new `stemAnalysis` fields, no UI work.
4. No model-zoo leaderboard. This is a class-level decision (Demucs vs. multi-stem RoFormer vs. vocal-specialist RoFormer), not a 20-model shootout.
5. No re-litigation of the trust diet — the old MSST path stays removed; anything promoted goes through a *new* thin seam with evidence attached.

---

## 2. Hypotheses

- **H1 — Vocals-specialist win:** MelBand Kim produces materially cleaner vocal isolates and near-silent vocals on instrumentals, enough to fix false `hasVocals` and lift `vocalDetail` confidence calibration. Drums/bass unaffected (Demucs stays for those).
- **H2 — Multi-stem win:** BS-RoFormer-SW beats Demucs across drums/bass/other/vocals well enough that a full 4-stem replacement (with 6→4 fold-down) is worth researching, moving `kickDetail`/bass fields too.
- **H3 — Hybrid win (most likely a-priori):** Demucs stays authoritative for drums/bass/other; MelBand supplies only the `vocals` stem. Cheapest promoted shape, smallest dual-authority surface.
- **H0 — Null:** RoFormers sound better in solo but the deltas don't move any citable field, or wins are marginal. Record the null (PENN precedent in `ARCHITECTURE_STRATEGY.md`) and keep Demucs.

---

## 3. Fixture set requirements

Minimum 6, maximum ~8 tracks, all owned/licensed by the owner (personal-use analysis only; never committed to the repo, never redistributed; no PII in filenames — use `track01_vocal_house` style keys):

1. ≥3 **vocal tracks** spanning: a sparse vocal (house/techno topline), a dense full-mix vocal (pop-EDM), and a processed/vocoded or chopped vocal (the hard case for formant heuristics).
2. ≥2 **instrumentals** in ASA's target styles (the ghost-stem / false-`hasVocals` test — this is where `stemEnergyRatio < 0.05` behavior lives).
3. ≥1 **edge case**: vocal chops used as texture, or a synth lead that mimics vocals (the `stemOtherCorrelation > 0.55` misclassification case).

Electronic styles ASA targets; 44.1/48 kHz lossless preferred (FLAC/WAV), 2–5 min each.

Storage: outside the repo (e.g. `/tmp/asa-scratch/bakeoff-fixtures/` or a home-dir folder); probe outputs go to the driver's default `apps/backend/.runtime/separation_probe/`.

---

## 4. Models to run (max 4 configs) — and why not 20

| # | Config | Package | Why this one |
|---|---|---|---|
| 0 | **Demucs baseline** | product venv, `analyze_audio_io.separate_stems` | Ground truth for the comparison; always run |
| 1 | **BS-RoFormer-SW** (default model) | `bs-roformer-infer` | Best multi-stem challenger family (TOP20 #2); tests H2 |
| 2 | **MelBand Kim vocals** (default model) | `melband-roformer-infer` | Vocal specialist (TOP20 #4); tests H1/H3 directly |
| 3 | *(optional)* BS-RoFormer Viperx vocals | `audio-separator` | Second vocal opinion only if #2 is ambiguous; do not run first |

**Why not 20:** each checkpoint is a ~700 MB–1 GB download, each run costs real CPU/MPS minutes per track, and ear time is the true bottleneck (4 configs × 7 tracks × ~4 stems is already ~100 solo auditions). The decision is class-level; a leaderboard is engineering for its own sake (PURPOSE test #5). The `audio-separator` zoo is explicitly a rabbit hole — it enters only as a tiebreaker.

---

## 5. Procedure (phased, checkboxes)

### Phase 0 — Environment + smoke (½ day)

- [ ] Create eval venv at `/tmp/asa-roformer-eval` per `SEPARATION_ROFORMER_PROBE.md`; install `bs-roformer-infer` + `melband-roformer-infer` only (defer `audio-separator`).
- [ ] `bs-roformer-download --list-models` / `melband-roformer-download --list-models`; record exact default model names + checkpoint sizes into the results notes.
- [ ] Smoke: run the probe on **one** vocal track with `--backends demucs,bs_roformer,melband_vocals`; confirm manifest + per-backend folders appear under `.runtime/separation_probe/<track>/`.
- [ ] Record per-backend `elapsedMs` and peak memory impressions (Activity Monitor is fine) — this is the H2 feasibility number.

### Phase 1 — Full fixture runs (½–1 day, mostly unattended)

- [ ] Assemble fixture set (Section 3), write a one-line provenance list (title → source/ownership) in the results notes, not in the repo.
- [ ] Run the probe over all fixtures with the same 3 backends. No per-track tweaking — same defaults everywhere.
- [ ] Note failures honestly in the manifest (the driver already records `ok: false` + error per backend).

### Phase 2 — Ears + crude numbers (1 day)

- [ ] **Listening protocol** (from the probe doc, applied per fixture): vocal tracks — Demucs `vocals` vs MelBand vocals bleed; Demucs `other` residual lead; MelBand instrumental residual cleanliness. Instrumentals — ghost energy in Demucs `vocals` vs MelBand. Multi-stem — kick/snare definition, sub leak, fold-down obviousness. Blind where possible (load stems into Ableton labeled A/B before knowing which backend).
- [ ] Score each item 0/1/2 (worse/parity/clearly better) per track in a small table; "clearly better" requires no squinting.
- [ ] **Crude metrics** (eval-side script, not product code): for each backend's vocals stem, compute (a) RMS(vocals)/RMS(mix) — the `stemEnergyRatio` analogue, mirroring `analyze_detection.py:621–626`; (b) 200 Hz envelope Pearson correlation vocals↔other — the `stemOtherCorrelation` analogue, mirroring `analyze_detection.py:638–672`. On instrumentals, lower (a) is better; on vocal tracks, lower (b) is better. These reuse ASA's own thresholds (0.05 ghost, 0.30/0.55 correlation) so numbers translate directly into predicted `vocalDetail` behavior.
- [ ] Checkpoint against the decision matrix (Section 6). **This is the stop gate.**

### Phase 3 — Field-delta probe (optional, 1 day; only if Phase 2 passes ears)

- [ ] Small offline harness (eval-only) that feeds the RoFormer vocals stem into the existing vocal-detail computation in place of the Demucs stem, and diffs `vocalDetail.hasVocals` / `confidence` / `stemEnergyRatio` / `stemOtherCorrelation` per fixture. This is the "measurable lift on citable fields" evidence the promote bar requires.
- [ ] Optionally the same for `kickDetail`/bass fields with BS-RoFormer drums/bass stems, only if H2 survived Phase 2.

### Phase 4 — Writeup + decision (½ day)

- [ ] Results doc (append to or alongside `SEPARATION_ROFORMER_PROBE.md`): per-track scores, metric tables, timings, model names + licenses, and the matrix row we landed in. Null results get written up with the same care as wins.
- [ ] Owner decision recorded; update `ARCHITECTURE_STRATEGY.md` dependency table only if something is promoted.

---

## 6. Decision matrix

| Ears (vocal tracks) | Ears (instrumentals) | Crude/field metrics | → Decision |
|---|---|---|---|
| MelBand clearly better on ≥3 | Ghost clearly quieter on ≥2 | Metrics agree; Phase 3 shows `vocalDetail` calibration lift | **Promote H3**: vocals-only override research seam (Section 7) |
| BS-RoFormer parity-or-better on vocals | Parity-or-better | Drums/bass clearly better by ear on ≥3 tracks AND fold-down is unambiguous AND Phase 3 moves `kickDetail`/bass | **Promote H2**: full multi-stem research challenger (larger effort; needs its own follow-on plan) |
| RoFormer better by ear | Better by ear | But Phase 3 field deltas ≈ 0 | **Keep Demucs**; record "audible but not citable" result; revisit at next landscape review |
| Marginal / mixed | Marginal | Flat | **Abandon**: record null (PENN precedent); Demucs stays; probe doc updated so the next agent doesn't re-run this |
| MelBand wins vocals; BS-RoFormer only parity elsewhere | — | — | H3 only; do **not** pursue H2 on vibes |

---

## 7. Only-if-promoted: the thin seam (sketch, no code now)

`separation_backend.py` already is the seam — 38 lines, one dispatch function, byte-compatible `{stem_name: wav_path}` return. The promoted H3 shape: a new env-gated value (e.g. `ASA_SEPARATION_BACKEND=demucs+melband_vocals`) where Demucs runs exactly as today and only the `vocals` wav is replaced by a MelBand isolate produced via **subprocess to the eval-venv CLI** (mirroring how the probe driver shells out) — no new product Python deps, unknown values still fall back to `demucs`, default unchanged.

Measurement authority stays single-sourced per stem (Demucs for drums/bass/other, MelBand for vocals) — never two separators feeding the same field.

This does not re-litigate the trust diet: MSST was cut for "no recorded win"; this seam would land *with* the Phase 4 results doc as its recorded win, or not at all.

---

## 8. Risks

1. **Download/disk:** ~700 MB–1 GB per checkpoint into `~/.cache/*-roformer-infer/`; 2–3 models ≈ 2–3 GB. Budget disk before Phase 0.
2. **Mac RAM/speed:** RoFormer inference on arm64 CPU (MPS support varies) may be minutes per track; if a 3-minute track takes >15 min, H2 (full replacement in the product path) is dead on latency alone even if quality wins — record timings in Phase 0.
3. **License:** community UVR/RoFormer checkpoints (Kim, jarredou, Viperx) have murky or non-commercial terms. Fine for offline research; a **blocking gate before any product promotion** — same discipline as `incorporations/msst-separation-licence-gate-2026-06-05.md`.
4. **Dual authority:** mixing separators invites two sources of truth for one stem. Mitigated by the per-stem single-source rule in Section 7; PURPOSE invariant 1 wins over any quality argument.
5. **6-stem→4-stem fold-down:** BS-RoFormer-SW emits up to 6 stems; guitar+piano→`other` summing must preserve energy and not break `stemAnalysis` expectations. If fold-down needs judgment calls, that's evidence against H2's "thin" promotion.
6. **2-stem ≠ 4-stem:** MelBand's residual is *instrumental*, not `other` — it can never replace the multi-stem output; H3 must keep Demucs for the other three stems.
7. **Eval-venv contamination:** `audio-separator`'s numpy pins can fight the product stack — keep it in `/tmp/asa-roformer-eval` only (already the probe doc's rule).
8. **Confirmation bias:** we *want* RoFormer to win (the vocal pain is annoying). Blind A/B labeling and the pre-registered pass bar in Section 9 are the guards.

---

## 9. Stop / promote criteria

**Promote (any path) requires — pre-registered (authoritative; keep in sync with probe doc):**

1. Clear vocal-isolate win on ≥3 real vocal tracks **and** quieter ghost stems on ≥2 instrumentals (ears + crude metrics agreeing), **and**
2. Phase 3 shows a measurable `vocalDetail` improvement (confidence calibration up, or false `hasVocals` down) on the fixture set; for H2 additionally a `kickDetail`/bass field delta.

**Stop immediately when:**

1. Phase 2 lands in matrix rows 3–4 (audible-but-not-citable, or marginal) — do not proceed to Phase 3 "just to check."
2. Cumulative effort exceeds **4 days** without hitting a promote row — write the null and stop.
3. Any config requires per-track parameter fiddling to look good — that's a research toy, not a product candidate.

---

## 10. Open questions for Christian

### Q1 — Fixtures (ANSWERED 2026-07-18) — **gates same-day Phase 0+1**

**Answer: fixtures are NOT assembled. Treat assembly as its own half-day first.**

Inventory at accept:

1. No `/tmp/asa-scratch/bakeoff-fixtures/` (or equivalent bakeoff corpus) exists.
2. No prior `apps/backend/.runtime/separation_probe/` outputs.
3. Repo fixtures under `apps/backend/tests/fixtures/` are synthetic / fundamentals / proxy recommendation material — **not** a Section 3 vocal/instrumental bakeoff set.
4. Loose candidates under `~/Music/` (`DJ Metatron Prompt 1.wav`, `Fuck Around.wav`, `Voice 001.m4a`) are incomplete vs Section 3 and unverified for ownership/style coverage. `Stemify Benchmark Sources/` currently has no usable audio files staged.
5. Nothing in-tree satisfies ≥3 vocal (incl. processed) + ≥2 instrumentals + 1 edge case.

**Schedule implication:**

- **Phase 0** can start after **one** owned vocal track is staged (smoke only).
- **Phase 1** waits on the full Section 3 set + provenance list (results notes only; never committed).
- **Same-day Phase 0 + Phase 1 is not realistic** until fixtures are assembled. Recommended order: fixture assembly half-day → Phase 0 smoke on one vocal → Phase 1 full runs overnight.

### Q2 — Hardware budget (OPEN)

Is this all on the Mac (CPU/MPS), and what's your per-track inference tolerance before H2 is disqualified on latency — 5 min? 15 min?

### Q3 — Product shape (OPEN)

If H3 wins, is a two-separator hybrid (Demucs + MelBand vocals-only override) acceptable to you philosophically, or do you require single-separator purity even at the cost of the vocal win?

### Q4 — License bar (OPEN)

Is a non-commercial-weights model acceptable for the *local-only* product path, or is that a hard no regardless of quality (which would make license the first check, not the last)?

### Q5 — Phase 3 harness timing (OPEN)

Build the `vocalDetail` field-delta harness only after ears pass (as planned), or do you want it built during Phase 1 so numbers and ears land together?

---

## Suggested first commands (Phase 0)

```bash
# From repo root (asa/) — eval venv, NEVER apps/backend/venv
python3.11 -m venv /tmp/asa-roformer-eval
source /tmp/asa-roformer-eval/bin/activate
pip install -U pip
pip install 'bs-roformer-infer>=0.1.5' 'melband-roformer-infer>=0.1.5'
bs-roformer-download --list-models
melband-roformer-download --list-models
deactivate

# Smoke run: product venv drives Demucs; RoFormer CLIs found via PATH
cd apps/backend
export PATH="/tmp/asa-roformer-eval/bin:$PATH"
./venv/bin/python scripts/probe_roformer_separation.py /path/to/vocal_track.flac \
  --backends demucs,bs_roformer,melband_vocals \
  --out .runtime/separation_probe
cat .runtime/separation_probe/vocal_track/manifest.json
```

---

## Campaign start checklist (post-accept)

1. [ ] Christian answers Q2–Q5 (or explicitly defers; defaults: Mac-only, 15 min H2 latency kill, H3 hybrid OK if evidence, license gate before promote, Phase 3 after ears).
2. [ ] Assemble Section 3 fixtures outside the repo; provenance list in private results notes.
3. [ ] Phase 0 eval venv + smoke on one vocal track.
4. [ ] Keep Section 9 ↔ probe "What would justify product work later" bit-identical whenever either moves.
