# Trust Diet Closeout — 2026-07-18

Executed record for `plans/trust-diet-2026-07.md` (Waves 0–4 + hygiene). Verified at closeout:
backend `unittest discover` 1344 OK (3 skipped), `npm run verify` 51 smoke passed. A fresh agent
needs only `PURPOSE.md` + `CLAUDE.md` + this file.

## KEEP (the product)

- **Phase 1 DSP nucleus**: `analyze.py` + `analyze_*.py`, schema/golden/contract gates, `ci.yml` (frontend + backend jobs only).
- **Real eval harnesses**: fundamentals, beat (GTZAN), GiantSteps key, phase1, recommendation scorer + real-render intake. Corpora/venvs/Demucs weights staged locally — don't refetch.
- **Phase 2 Gemini path** (coat #1 = Ableton Live 12): Vertex AI + ADC preferred (`ASA_GEMINI_BACKEND=vertex`, auto when `GOOGLE_CLOUD_PROJECT`/`ASA_GCP_PROJECT` set), AI Studio `GEMINI_API_KEY` legacy. The `claude` provider seam stays (`gen_claude_phase2.py` — free real-scoring path).
- **Current record**: 5 audits in `audits/`, 3 licence/gate pre-registrations in `incorporations/`, `docs/adr/*`.

## FREEZE (in-tree, default-off, do-not-expand — banners in place)

MT3 · Phase 3 samples · PatchSmith · hosted profile. See `docs/OPTIONAL_BACKENDS.md`.
Non-authoritative (proxy-scored, do not cite as settled): `apps/backend/NEEDS.md`,
`RECOMMENDATION_VERDICT.md`, verification badges (never regenerate from proxy data).
`GOAL.md` retired 2026-07-18 by owner decision (recover via git history); code/docstring
references to "GOAL.md" are historical context for the scorer's design.

## PARKED

- **Strudel / multi-coat renderers** — Ableton is coat #1; nothing else until it's proven.
- **MT3/PatchSmith excision PR** — cut lists in trust-diet plan C1/C3; owner-named work only.
- **Remote branch backlog** — 20 stale `origin/*` branches (accuracy/*, claude/*, codex/*, feat/notable-findings-triage) listed, NOT deleted; local tips preserved as `archive/branch/*` tags (46 pushed).

## CUT (what's gone, and how to get it back)

| Cut | Restore |
|---|---|
| `docs/history/` museum, stale audits, forking plan, `.superpowers/` | tag `archive/pre-trust-diet-2026-07` |
| MOSS sidecar + provider arm (licence dead-end) | same tag |
| MSST separation + A/B harness (licence gate, no win over Demucs) | same tag |
| WASM loudness package | branch `archive/loudness-spectro-wasm` |
| 55 local branches / 7 worktrees | tags `archive/branch/<name>` + pushed `wip:` commits |

## NEXT — human proof steps (the only path to authoritative claims)

1. Analyze ~5 real reference tracks you know by ear; check BPM/key/LUFS against your own metering (Phase 1 trust).
2. Render 5 recommendation blueprints in real Ableton Live 12; feed captures through `recommendation_fixture_intake.py`.
3. Re-run `recommendation_evaluation.py` on real renders — only then unfreeze badges/verdict language.
4. ~~Vertex smoke~~ **DONE 2026-07-18**: full pipeline on a real track (VTSS "Cant Catch Me": 144.9 BPM,
   C minor 0.93 conf, -7.5 LUFS, +0.7 dBTP) with `ASA_GEMINI_BACKEND=vertex` + ADC on project
   `sonic-analysis` — measurement + interpretation completed, measurement-cited recommendations
   returned (`flagsUsed: vertex:us-central1`). Required fix: Vertex rejects role-less `contents`;
   both `generate_content` sites now send `role: "user"`. Note: the `files-api` path
   (>20MB uploads) uses the AI Studio Files API and is untested on Vertex.
