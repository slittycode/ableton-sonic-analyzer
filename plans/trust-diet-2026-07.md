# ASA Trust Diet — 2026-07 (ruthless revision)

> Canonical artifact: written verbatim to `plans/trust-diet-2026-07.md` in the repo as execution step 1. Repo root for all paths/commands: `~/code/projects/ableton-sonic-analyzer/asa`. Plan only — nothing here has been executed.

## Context and stance

The owner vibe-coded much of this repo with agents and wants to keep only what is **good and works**. Blunt assessment of the areas, per the no-fake-balance rule:

1. **The nucleus is real.** `analyze_*.py` on Essentia/Demucs/torchcrepe, the schema/contract gates, the golden fixture, and the fundamentals CI gate are verified working product (owner-assessment 2026-06-10; accuracy-baseline 2026-07-03 reproduces). The genre-generalization program (PRs #210–#216, merged) is real measured improvement (0/93 → 51/93 genre top-1 on real clips).
2. **The recommendation-proof campaign is one real component wrapped in proxy theater.** The scorer (`recommendation_evaluation.py`, CI-tested, moves correctly on injected-bad input) is real. The "ALL FOUR SUB-GOALS MECHANICALLY COMPLETE" status, the 0.227-vs-0.000 verdict, and the badge confidence bands all rest on synthetic numpy proxy renders. Documented ≠ true; green on proxies ≠ ear-true. **Demote, label, stop citing as settled.**
3. **The optional-experiment layer is mostly slop with licence dead-ends.** MOSS: permanent 501 stub (modeling code has no effective licence) — can never ship. MSST: research-only licence gate, no recorded win over Demucs. WASM package: real DSP with real EBU conformance, but unwired into the product on both seams. Hosted profile: speculative April infrastructure for a deployment that doesn't exist.
4. **The doc layer is a museum of prior agent sessions.** `docs/history/` (13 MB, 4,871 md lines + pptx/png/node debris), three May nightly "audits," a 1,004-line forking plan, `.superpowers/` brainstorm server debris (6 files accidentally tracked), 57 branches, 8 worktrees. Three copies of the same backend file map (CLAUDE.md + backend AGENTS.md + ARCHITECTURE.md).

**The load-bearing CI fact** (verified): `ci.yml` runs `unittest discover -s tests` over ALL of `apps/backend/tests/` and `npm run verify` over all `apps/ui/tests/{services,smoke}/`. So any code DELETE must remove its tests **in the same commit** — that is routine, not a reason to keep dead ends. The rule applied below: *if no call site, test, or CI job needs it for the nucleus, it gets no benefit of the doubt; if it is threaded through nucleus files, FREEZE beats surgery.*

---

## 0. Preconditions (Wave 0 — restore / clean baseline)

Dirty state verified 2026-07-17, main @ `0ed792ff` (PR #216):

| Item | What it is | Action |
|---|---|---|
| `CHANGELOG.md` (+6 lines) | Records the merged genre PRs #210–#216 | **Commit** (real record of merged work — do NOT discard) |
| `.poll_fable.sh` (untracked) | Dead session-polling debris | Delete |
| `apps/backend/tests/fixtures/beat_eval_manifest.gtzan{,.asarelevant}.json` (untracked) | Locally generated GTZAN beat-eval manifests (machine-local paths) | Keep on disk, gitignore |

```bash
cd ~/code/projects/ableton-sonic-analyzer/asa
git checkout main && git pull
git add CHANGELOG.md && git commit -m "docs(changelog): record genre-generalization program (PRs #210–#216)"
rm .poll_fable.sh
printf 'apps/backend/tests/fixtures/beat_eval_manifest.gtzan*.json\n' >> .gitignore
git add .gitignore && git commit -m "chore: ignore locally generated GTZAN beat-eval manifests"
```

**Baseline verification (must be green before any wave):**

```bash
git status --short                                                   # empty
cd apps/backend && ./venv/bin/python -m unittest discover -s tests   # full backend suite
cd ../ui && npm run verify                                           # lint+style+unit+build+smoke
git rev-parse HEAD                                                   # record as BASELINE_SHA
```

Recovery point for every DELETE/ARCHIVE below:

```bash
git tag archive/pre-trust-diet-2026-07 && git push origin archive/pre-trust-diet-2026-07
```

Universal restore path: `git checkout archive/pre-trust-diet-2026-07 -- <path>`.

---

## 1. Decision table

Risk key: product (request path), eval (measurement/proof signal), UI (frontend). Every row decided — no "review later."

### A. Museum / hygiene

**A1. `docs/history/**`** — **ARCHIVE**
1. Why: 13 MB agent-session museum; zero imports, zero CI references (verified — only stale comment strings in `csv_export.py:5`, `dsp_bandbank.py:10`, `scripts/calibrate_confidence.py:35`, `tests/test_loudness_r128.py` docstrings, which stay harmlessly).
2. Risk: none. 3. Verify: both suites green; `grep -rn "docs/history" apps/ scripts/ .github/` → only the known comments. 4. History: YES — tag; `git rm -r docs/history`; leave a 5-line `docs/history/README.md` stub pointing at the tag.

**A2. `audits/` — split**
- **ARCHIVE**: `nightly-2026-05-{14,16,19}.md` (agent nightly theater, superseded), `full-review-2026-05-30.md` (point-in-time snapshot superseded by owner-assessment). Verify: `grep -rn "nightly-2026-05\|full-review-2026-05-30" --include="*.py" --include="*.ts" apps/ scripts/` → 0. History: tag.
- **KEEP** (current, labeled): `owner-assessment-2026-06-10.md` (verdict of record), `accuracy-baseline-2026-07-03.md` (reproducible baseline w/ commands), `genre-coverage-2026-07-13.md`, `genre-target-sourcing-2026-07-13.md` (feed the merged genre program), `phase2-recommendation-surface-2026-05-24.md` (GOAL.md's live Tier-2/3 backlog source). Add a 6-line `audits/README.md` index: current vs archived-by-tag.

**A3. `.superpowers/` + `docs/superpowers/`** — **DELETE**
1. Paths: 6 tracked pid/log debris files under `.superpowers/brainstorm/55385-*/` (tracked despite `.gitignore:6`); the rest is ignored local brainstorm HTML + one stale local plan doc.
2. Why: ephemeral tool output; pure museum. 3. Risk: none. 4. Verify: `git ls-files .superpowers | wc -l` → 0. 5. History: git retains the 6 tracked files; `git rm -r --cached .superpowers` + local `rm -rf .superpowers docs/superpowers`.

**A4. Worktrees & branches** — **DELETE (tag unmerged tips first)**
1. Facts (verified): 5 clean detached codex worktrees (`~/.codex/worktrees/{1701,455d,8061,9010,fe47}/asa`); 2 in-repo worktrees with **uncommitted WIP** — `.worktrees/link-based-music-analysis` (14 files: a link-analysis feature — `audio_source_providers.py`, intake clients, smoke spec) and `.worktrees/phase1-contract` (5 files: golden/parity fixture WIP); 57 local branches (13 merged, 30 with gone upstreams).
2. Action: commit each in-repo worktree's WIP as a `wip:` snapshot on its branch and push, THEN `git worktree remove` all 7 + `git worktree prune`. Delete merged branches (`git branch -d`); for every unmerged tip `git tag archive/branch/<name> <sha> && git branch -D <name>` (incl. `backup/local-state-2026-07-05`); push tags.
3. Risk: losing the two WIPs if order violated — wip-commit-then-remove is mandatory. 4. Verify: `git worktree list` → 1; `git branch | wc -l` ≤ ~5; tag count matches deletions. 5. History: YES via pushed wip commits + `archive/branch/*` tags.

**A5. `experiments/`, `advisory/`** — **DELETE** (local `.DS_Store` shells; nothing tracked). Verify: dirs gone.

**A6. `incorporations/forking-plans-2026-05-14.md`** — **ARCHIVE** (1,004-line superseded planning pile). **KEEP** the three pre-registrations (`beat-this-measurement-gate`, `msst-separation-licence-gate`, `key-ensemble-decision`) — referenced from code (`separation_backend.py:70`) and the accuracy program. Verify: grep filename in apps/scripts → 0 code hits. History: tag.

### B. Unwired / dead-end experiments — no benefit of the doubt

**B1. MOSS — `apps/backend/moss_sidecar/**` + provider arm** — **DELETE**
1. Paths (one commit): `moss_sidecar/` entirely; `MossSidecarProvider` (`phase2_provider.py:130-232`), `"moss"` registry entry (`:47`) and dispatch (`:470-471`); moss cases in `tests/test_phase2_provider.py`; `phase2_provider_evaluation.py` + `scripts/evaluate_phase2_providers.py` (moss-centric harness — imports `moss_sidecar.mock_interpreter`; its real job died with the licence gate); `ASA_MOSS_*` env-var docs in CLAUDE.md/AGENTS.md; `docs/PHASE2_PROVIDER.md` moss sections collapse to a 3-line tombstone (licence finding preserved).
2. Why: permanent licence dead-end — the real-model path is a designed-in 501 stub that can never be promoted; only a mock exists. Nothing in the nucleus needs it. This is the textbook "looks like progress" artifact.
3. Risk: product low (default-off `ASA_PHASE2_PROVIDER=gemini`; gemini/claude paths untouched — **the provider seam and the `claude` provider stay**: `gen_claude_phase2.py` + `evaluate_recommendations.py --source claude` are the free real-scoring path and are used).
4. Verify: `unittest discover` green; `grep -rin "moss" apps/ scripts/ --include="*.py" --include="*.ts"` → 0 functional hits; server starts and Gemini interpretation smoke passes (`test_server.py` contract tests cover routing).
5. History: YES — tag restores everything.

**B2. MSST separation path + A/B harness** — **DELETE**
1. Paths (one commit): `_separate_via_msst_subprocess` + model registry + msst branch in `separation_backend.py` (keep the file as the thin backend seam, demucs-only); `scripts/msst_separate_runner.py`; `separation_ab.py` + `scripts/ab_separation_backends.py`; `requirements-msst.txt`; msst cases in `tests/test_separation_backend.py`; `tests/test_separation_ab.py`; `ASA_MSST_*`/`ASA_SEPARATION_BACKEND=msst` env docs.
2. Why: research-only licence gate, needs an external MSST-WebUI checkout + its own venv, and no recorded evidence it beats Demucs for ASA. The A/B harness was built to answer that and never produced a decisive kept result. Wired-but-optional + unproven + heavy = cut.
3. Risk: product medium-low — `separate_stems_backend` is called from `analyze.py`'s three separation sites, so the demucs default path through the trimmed seam must stay intact; existing `test_separation_backend.py` demucs cases gate it.
4. Verify: `unittest discover` green; `./venv/bin/python analyze.py <fixture> --separate --yes` produces the 4-stem contract; `grep -rin "msst\|roformer" apps/ scripts/` → 0 functional hits.
5. History: YES — tag; the licence pre-registration doc (`incorporations/msst-separation-licence-gate-2026-06-05.md`) stays as the record of why.

**B3. WASM package — `packages/loudness-spectro-wasm/**`** — **ARCHIVE**
1. Paths: the whole package (own Cargo workspace) + the `loudness-wasm` job in `ci.yml:60-75`.
2. Why: real work (EBU 3341/3342 conformance is genuine ground truth, not proxy) but **unwired on both seams** — backend `ASA_LOUDNESS_BACKEND` defaults to essentia and merely shells to a binary that won't exist; frontend loader is URL-gated off and the pkg is not a build dependency. "Might be useful someday" vs context tax today → archive. Because it's good-but-dormant (not slop), ARCHIVE with a clean restore path rather than plain delete.
3. Risk: eval low — `loudness_backend.py` degrades to essentia when the binary is absent (that IS its contract); `test_loudness_backend.py` and `browserLoudness/loader.test.ts` mock, they don't build the package. One known reference to check: `scripts/evaluate_giantsteps.py` mentions the package — confirm it's an optional path before the rm.
4. Verify: both suites green with the package gone; `ci.yml` has 2 jobs (frontend, backend); grep `loudness-spectro-wasm` → only doc mentions + the degrading default path in `loudness_backend.py:59-95`.
5. History: YES — additionally `git branch archive/loudness-spectro-wasm main` before the rm (belt and braces for a package someone may resurrect), then `git rm -r packages/loudness-spectro-wasm` + drop the CI job. `loudness_backend.py` itself is **KEEP** (imported unconditionally by `analyze.py:101`; nucleus seam).

### C. Wired-in options — FREEZE (surgery would cut nucleus files)

**Frozen means, operationally:** default-off / non-authoritative stays as-is; **no agent may expand it** (no new fields, params, endpoints, panels, models, or docs beyond the freeze banner); PRs touching it require the owner naming it explicitly; code stays because it is threaded through nucleus files and/or CI-run tests, and excision would be nucleus surgery this plan forbids.

**C1. MT3** — **FREEZE**
1. Paths: `mt3_transcription.py`, `requirements-mt3.txt`, hooks inside `analyze.py:1185-1239,1374-1418,1874-1900`, `analyze_estimate.py:66,124-138`, `server.py:1459-1660,2386-2408,3505-3547`, `analysis_runtime.py` (mt3_attempts lifecycle), `server_phase2.py:797-846,2670-2708`; frontend `mt3Client.ts`, `Mt3TranscriptionPanel.tsx` + wiring; tests across `test_analyze/server/analysis_runtime/cleanup/phase2_citation_paths` + frontend unit/smoke.
2. Why frozen not deleted: triple-gated off (`ASA_ENABLE_MT3=0`, `mt3_mode=off`, `VITE_ENABLE_MT3`) but threaded THROUGH `analyze.py`/`server.py`/`analysis_runtime.py` — excision is a multi-file nucleus surgery with UI+smoke fallout. Unproven value, so: banner + do-not-expand now; a documented excision PR is a separate owner decision (cut list = the paths above).
3. Risk if wrong: product (hooks live in nucleus files). 4. Verify: no code change → suites green. 5. History: n/a.

**C2. Phase 3 sample generation** — **FREEZE (demoted to toy)**
1. Paths: `server_samples.py`, `sample_{generation,theory,synthesis,drums}.py`; frontend `SamplePlayback.tsx`, `sampleGenerationClient.ts`; `docs/SAMPLE_GENERATION.md`; 4 CI-run backend test files.
2. Why: shipped and user-facing but unvalidated as value; notably the only optional subsystem that is **effectively default-ON** (no flag; panel renders whenever a run exists). Freeze = banner + do-not-expand. Adding an off-flag is a later owner option, not this plan (UI code change).
3. Risk: UI (mounted from `AnalysisResults.tsx:727`). 4. Verify: no change → green. 5. History: n/a.

**C3. PatchSmith** — **FREEZE (demoted to toy)**
1. Paths: `apps/ui/src/services/patchSmith.ts`, `components/PatchSmithPanel.tsx` (mounted `AnalysisResults.tsx:725`), CI-run `tests/services/patchSmith.test.ts`.
2. Why: frontend-only Vital preset generator, cited/hedged but zero validation corpus. Cheap to keep frozen; deleting is a candidate for the later excision PR alongside MT3 if the owner wants the panels gone.
3. Risk: UI. 4. Verify: `npm run verify`. 5. History: n/a.

**C4. Hosted profile** — **FREEZE (declared non-goal)**
1. Paths: `runtime_profile.py`, `auth_context.py`, `worker.py`, hosted branches in `server.py:343-355,410-411` + `artifact_storage.py`; frontend `config.ts:35-52`, `httpClient.ts`.
2. Why: speculative deployment infrastructure with no deployment; but the seams are load-bearing for local mode and woven through core tests (`test_server.py`, `test_cleanup.py`, …). Excision = the `server.py` refactor this plan explicitly does not do. Freeze = "hosted is a non-goal; local is the product; do not expand."
3. Risk: product (seams serve local mode). 4. Verify: no change → green. 5. History: n/a.

### D. Proxy-truth artifacts — demote, don't protect

**D1. Recommendation-proof campaign status (GOAL.md §status, `NEEDS.md`, `RECOMMENDATION_VERDICT.md`)** — **FREEZE + LABEL non-authoritative**
1. Why: "mechanically complete" is proxy theater — sub-goals 1/3/4 rest on numpy renders; the one real deliverable is the scorer. The campaign is **paused pending real renders**, not complete.
2. Action (docs only): banner atop `NEEDS.md` and reinforce `RECOMMENDATION_VERDICT.md`'s existing banner: `> **NON-AUTHORITATIVE (proxy-scored).** Campaign paused pending real Live 12 renders; do not cite these numbers as settled.` Append "(PROXY-SCORED — non-authoritative)" to every pointer: `AGENTS.md:22-23`, CLAUDE.md companion-docs §item 4. GOAL.md body untouched (no rewrite), but it drops out of the always-mandated read chain (E2).
3. Risk: none (prose). 4. Verify: grep "PROXY-SCORED" hits all pointer sites. 5. History: n/a.

**D2. Verification badges** — **FREEZE + LABEL**
1. Paths: generated `apps/ui/src/data/recommendationVerification.ts`, `services/recommendationVerification.ts`, `RecommendationVerificationBadge.tsx` (rendered from `PatchFrameworkSection.tsx:124`, `MixChainSection.tsx:146`).
2. Why: bands derive from the proxy corpus; currently honest `NONE`/dormant. Freeze = never regenerate from proxy data again — only the real-render intake (`recommendation_fixture_intake.py`) may regenerate the artifact. Header comment in the generated file states this.
3. Risk: UI (leave mounted code alone). 4. Verify: `npm run verify`. 5. History: n/a.

**D3. Proxy fixtures (`tests/fixtures/recommendation_tracks/`, `synth_fixtures.py`)** — **KEEP (labeled)**
Why: the scorer's only corpus until renders land, and the scorer is real + CI-tested. The fixture READMEs/manifests already mark proxy provenance; D1's banners cover interpretation. Risk: eval if deleted. Verify: backend suite green.

### E. Agent-doc surface — collapse the duplicates

**E1. Root `CLAUDE.md` (461 ln, ~10.2k tok)** — **KEEP + SHRINK to ≤ 200 lines**
1. Why: the single largest always-loaded item; its backend/frontend file inventories exist in THREE places (here + backend AGENTS.md + ARCHITECTURE.md).
2. Keep verbatim: purpose recap + invariants, commands, the one-request trace + two load-bearing contracts, **all 10 tripwires**, change map, debugging recipes. Move out: the 25-item backend file inventory and 19-item frontend service inventory → `apps/backend/ARCHITECTURE.md` / new `apps/ui/ARCHITECTURE.md` (read-on-demand); env-var table trimmed to product vars + one pointer line at a new short `docs/OPTIONAL_BACKENDS.md` for frozen-experiment vars (much of that table dies with B1/B2 anyway).
3. Risk: losing a tripwire/contract nuance — mitigate: **move, never summarize away**; grep-verify every removed sentence exists in its new home.
4. Verify: `wc -l CLAUDE.md` ≤ 200; suites green; fresh-agent smoke ("where do I change what gets measured?" resolves via change map). 5. History: tag.

**E2. Smaller agent load set** — **decision**
Always-load: slim `CLAUDE.md` + `PURPOSE.md` (unchanged). Load-on-task: per-app `AGENTS.md`, `GOAL.md`+`NEEDS.md` (recommendation work only, with their non-authoritative banners), `ARCHITECTURE_STRATEGY.md` (structural work), ADRs (schema work). Always-on drop: ~12.3k → ~7k tokens; mandated chain ~21k → ~11k.

**E3. `apps/backend/AGENTS.md` (256 ln) / `apps/ui/AGENTS.md` (193 ln)** — **KEEP + COLLAPSE**
Drop the duplicated file maps (pointer to ARCHITECTURE docs instead); keep setup, testing contract, change checklists. Root `AGENTS.md` (25 ln) stays; its `docs/history` line updates to the archive tag. Verify: line counts roughly halve; no unique fact deleted (grep check).

**E4. `PURPOSE.md` / `GOAL.md` bodies** — **KEEP untouched** (no multi-DAW/marketing rewrite; Strudel/Logic/multi-coat out of scope).

**E5. `.claude/skills/asa-*` (5 skills) + `.claude/hooks/contract_guard.py`** — **KEEP** (load-on-demand, small, and the hook guards real contracts).

---

## 2. Ordered waves

### Wave 0 — Restore (no approval; do first)
§0 verbatim. Rollback: `git reset --hard BASELINE_SHA`. Done when: clean tree, both suites green, tag pushed.

### Wave 1 — Zero-risk archive (docs/git only; nothing executable changes)
Prereq: Wave 0. One commit + worktree/branch ops:
1. Write this plan to `plans/trust-diet-2026-07.md`.
2. `git rm -r docs/history` (+stub README); `git rm` the 4 stale audits + `forking-plans-2026-05-14.md`; add `audits/README.md` index; `git rm -r --cached .superpowers`.
3. Worktrees: wip-commit + push both in-repo worktrees' WIP, then remove all 7 worktrees; prune.
4. Branches: delete 13 merged; tag-then-delete every unmerged stale tip; push tags.
5. Local: `rm -rf experiments advisory .superpowers docs/superpowers`.
- Verify: both suites green (proves nothing executable moved); `git worktree list`=1; grep checks per rows A1/A2/A6.
- Rollback: revert commit; tags/wip commits restore branches/worktrees.
- Done when: no museum dirs, 4 stale audits gone, 1 worktree, ≤5 branches, suites green.

### Wave 2 — Cut the dead ends (OWNER APPROVAL — deletes product-adjacent code)
Prereq: Wave 1 merged green. Three independent single-subsystem commits, each suite-verified before the next:
1. **B1 MOSS delete** (sidecar + provider arm + moss tests + moss eval harness + env docs; keep gemini/claude provider seam).
2. **B2 MSST delete** (msst branch of `separation_backend.py` + runner + A/B harness + tests + reqs; demucs seam intact).
3. **B3 WASM archive** (`git branch archive/loudness-spectro-wasm main`; `git rm -r packages/loudness-spectro-wasm`; remove `loudness-wasm` CI job; pre-check the `evaluate_giantsteps.py` reference is optional).
- Verify after each: `unittest discover` + `npm run verify` green; subsystem grep → 0 functional hits; `analyze.py --separate` stem contract after B2; server Gemini-route contract tests after B1.
- Rollback: revert the single commit; tag restores files.
- Done when: `grep -rin "moss\|msst\|roformer" apps/ scripts/` → 0 functional hits, ci.yml has frontend+backend jobs only, suites green.

### Wave 3 — Freeze + demote labels (OWNER APPROVAL — constrains future agent work)
Prereq: Wave 2 (so labels reference what's left). One commit:
1. FROZEN banners (uniform text): MT3 (`docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`, `mt3_transcription.py` module docstring), samples (`docs/SAMPLE_GENERATION.md`), PatchSmith (`patchSmith.ts` header), hosted (`runtime_profile.py` docstring + SETUP.md note). Banner: `FROZEN 2026-07 (trust diet): default-off/non-goal. Do not expand without the owner naming this subsystem. See plans/trust-diet-2026-07.md.`
2. Non-authoritative banners per D1/D2 (NEEDS.md, verdict pointers in AGENTS.md/CLAUDE.md, badge artifact header).
- Verify: suites green; `grep -rln "FROZEN 2026-07"` ≥ 5; `grep -rln "NON-AUTHORITATIVE"` covers NEEDS/verdict/badge artifact.
- Rollback: revert commit. Done when: every frozen/demoted item carries exactly one marker.

### Wave 4 — Agent-context diet (OWNER APPROVAL — judgment-heavy doc moves)
Prereq: Wave 3. Execute E1/E3: relocate file inventories to ARCHITECTURE docs, trim env table (smaller after Wave 2), collapse per-app AGENTS.md, fix archived-path pointers, add `docs/OPTIONAL_BACKENDS.md` (short). PURPOSE.md/GOAL.md bodies untouched.
- Verify: `wc -l CLAUDE.md` ≤ 200; every moved sentence greps in its new home; suites green; fresh-agent smoke question resolves.
- Rollback: revert; tag holds the old text. Done when: always-on load ≈ 7k tokens, zero information deleted (only relocated or killed with its subsystem).

### Explicit DO NOT CUT list
1. **Phase 1 DSP nucleus**: `analyze.py` + all `analyze_*.py`, `dsp_bandbank.py`, `dsp_utils.py`, `spectral_viz.py`, `key_ensemble_gate.py`, `loudness_backend.py` (unconditional import at `analyze.py:101`; wasm branch degrades to essentia), `separation_backend.py` (demucs seam, post-B2).
2. **Schema/contract gates**: `schemas/{recommendations.v1,phase2-export.v1}.schema.json`, `recommendations_contract.py`, `phase2_catalogue_gates.py`, `phase2_export.py`, `live12_catalogue.py` + `data/live12_catalogue.*`, `upload_limits.py`, `audio_mime.py` ↔ `audioFile.ts` mirror, golden `tests/fixtures/golden/phase1_default.json`.
3. **CI gates + all remaining tests**: `ci.yml` frontend/backend jobs, the fundamentals gate (`build_synthetic_corpus.py` + `evaluate_fundamentals.py --fail-on-skip`), everything under `apps/backend/tests/` and `apps/ui/tests/{services,smoke}/` that survives Wave 2 (deleted subsystems take their tests with them, same commit).
4. **Real eval harnesses** (score real measurement quality — never silent rm): `fundamentals_evaluation.py`+`fundamentals_quality.py`, `beat_evaluation.py`/`evaluate_beats.py`+manifest tooling, `giantsteps_evaluation.py`/`evaluate_giantsteps.py`/`fetch_giantsteps.py`, `phase1_evaluation.py`, `recommendation_evaluation.py`+`recommendation_fixture_intake.py`+`gen_claude_phase2.py`, fixtures `tests/fixtures/{recommendation_tracks,fundamentals_tracks,transcription_tracks,polyphonic_tracks,beat_tracks,ground_truth}/`, local corpora/venvs (GiantSteps, GTZAN, venv-eval, Demucs weights — staged locally; don't refetch).
5. **Current record**: the 5 KEEP audits, `plans/{genre-generalization-program,owner-actions-*}.md`, the 3 KEEP incorporations, `docs/adr/*`, `docs/{ARCHITECTURE_STRATEGY,SETUP,ASA_ABLETON_BOUNDARY}.md`.
6. **`PURPOSE.md`, `GOAL.md`** bodies; `.claude/` skills + contract-guard hook.

---

## 3. Recommended first execution + approvals

**Execute now: Wave 0 + Wave 1.** Mechanically safe (nothing executable changes — the green suites prove it), fully reversible via tags/pushed-wip, and they deliver the museum-ectomy: 13 MB + ~6k doc lines out, 57 branches/8 worktrees → 1 clean checkout.

**Owner must approve before Wave 2+:**
1. Wave 2's three deletes (MOSS, MSST, WASM-archive) — product-adjacent code with tests removed in-commit.
2. Wave 3 freeze semantics — constrains future agent sessions.
3. Wave 4 CLAUDE.md target shape.
4. Deferred, named, not in these waves: MT3/PatchSmith excision PR (cut lists documented in C1/C3), an off-flag for Phase 3 samples (C2), any hosted-profile removal (needs the forbidden `server.py` refactor).

**Biggest wins:** agent hits signal first — always-on context ~12.3k → ~7k tokens; the tree contains only nucleus, labeled-frozen options, and current records; ~3 dead-end subsystems and their theater gone.
**Biggest risks:** (1) losing the two uncommitted worktree WIPs — wip-commit-then-remove is mandatory order; (2) B2 trims a seam (`separation_backend.py`) the nucleus calls — the demucs-path tests and a manual `--separate` run gate it; (3) over-trimming CLAUDE.md — move-don't-summarize + grep verification.

## The center of gravity that remains

**An accurate Phase 1 measurement engine and the harnesses that prove it on real audio** — `analyze_*.py` + schema/golden/CI gates, the fundamentals/beat/GiantSteps/GTZAN evals, and one honest proof loop for recommendations (the real scorer + the real-render intake) waiting on the owner's five Live 12 renders. Everything else is either frozen with a label saying so, or gone.
