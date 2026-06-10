# Owner Actions for Recommendation Proof

**Goal:** complete the few steps that require the owner's credentials or Ableton Live,
then establish Claude as a no-additional-cost Phase 2 option alongside Gemini. Gemini
remains available and remains the default; the Claude route allows the owner to run ASA
without paying for Gemini API calls.

**Date:** 2026-06-10

## Verified Starting Point

- PR #153 is mergeable. Backend, frontend, Chromatic, and Loudness WASM checks pass.
  CI ran 1,200 backend tests successfully. The only failure is the optional Claude
  review job, which received `401 Invalid authentication credentials`.
- The Claude provider is default-off, text-only, schema-enforced, and uses the same
  citation/catalogue/contract validation path as Gemini. Its 42 focused tests pass.
- Claude's saved real-track output contains 28 raw recommendation cards, all cited.
  The Gate alpha export independently reproduces 11/11 applied values, passes structural
  checks, and reports a 60.7% skip rate.
- The `asa-ableton` branch is local only. Its 66 tests pass and it includes the tracked
  real VTSS fixture, Gate alpha receipt, and Gate beta generator.
- Ableton Live is not installed on this Mac.
- All five recommendation fixtures still use fingerprints marked `_synthetic: true`.
  No real `audio.flac` render exists yet.

## Important Correction

PR #153 does **not** replace Gemini. Provider selection is:

- `ASA_PHASE2_PROVIDER=gemini`: existing product default.
- `ASA_PHASE2_PROVIDER=claude`: optional text-only route using the owner's Claude
  subscription and no Gemini API credits.
- `ASA_PHASE2_PROVIDER=moss`: existing default-off research route.

Only one provider produces a given interpretation; PR #153 does not run Gemini and Claude
together as an ensemble or automatically fall back between them.

The present evidence is sufficient to establish Claude as a useful no-Gemini-cost option:
it produced fully cited advice on two real tracks and passed the shared validation path.
A same-corpus comparison remains valuable research, but it is not a condition for keeping
or using the Claude option, and it must not require Gemini spending the owner cannot fund.

## Owner Actions

### 1. Clear and merge PR #153

Preferred route:

1. Run `claude setup-token` locally.
2. In GitHub, replace the repository Actions secret
   `CLAUDE_CODE_OAUTH_TOKEN` with the new token.
3. Re-run the failed `Claude Code Review` job for PR #153.
4. When it is green, squash-merge PR #153.

Do not paste the token into chat, a commit, or a shell command argument.

Fallback: the `main` branch has no protection rule, so the PR can be merged past the
advisory review failure. Use that only if token rotation cannot be completed; all four
product CI gates are already green.

**Done when:** PR #153 is merged into `main`.

### 2. Publish the `asa-ableton` gate branch

From `/Users/christiansmith/code/projects/asa-ableton`:

```bash
git push -u origin feat/track-ii-gate-tooling
```

Open a pull request for that branch after the push. Before merging it, an agent should
correct the stale first-line status in `docs/GATE_ALPHA.md` and clarify the wording around
28 raw cards versus the normalized recommendation count.

**Done when:** the branch is on GitHub and its pull request contains the real Gate alpha
receipt.

### 3. Use one Ableton session for Gate beta and the fixture renders

Use a Mac with Ableton Live 12. Pull both repositories and the published
`feat/track-ii-gate-tooling` branch.

Before building anything, confirm that house, techno, melodic techno, drum and bass,
and acid techno are useful test genres for your work. If one is irrelevant, stop and
have an agent re-author that fixture first.

#### 3a. Run Gate beta first

Generate the probe set:

```bash
cd /path/to/asa-ableton
python3 scripts/gate_beta_probes.py
```

Open `.runtime/gate_beta/gate_beta_probes.als` in Live. Fill in
`.runtime/gate_beta/gate_beta_worksheet.md`, starting with the four Auto Filter
frequency tracks.

Record each device as:

- `verified`
- `corrected: expected -> actual`
- `still uncertain`

**Stop condition:** if Auto Filter does not display approximately 100, 200, 1,000,
and 5,000 Hz, record the actual readings and stop Gate beta. An agent must correct the
mapping and regenerate the probes before Track III proceeds.

#### 3b. Pilot one fixture before building all five

Start with `techno_rumble_130`, the smallest spec:

1. Open its `manifest.json` and README.
2. Build the listed device chains and values exactly.
3. Use the included `audio_melody.mid` where applicable.
4. Set Live to 48 kHz and export at 24-bit.
5. Export the 16-second loop with normalization off as `audio.flac`.

Return that single render to:

`apps/backend/tests/fixtures/recommendation_tracks/techno_rumble_130/audio.flac`

An agent should ingest and validate this pilot before the remaining four are built.
This catches unclear instructions or an invalid measurement target before more manual
work is spent.

#### 3c. Render the remaining fixtures

After the pilot passes, render:

1. `dnb_reese_174`
2. `acid_303_128`
3. `house_sidechain_pluck_124`
4. `melodic_techno_arp_124`

Each render is a 16-second, 48 kHz, 24-bit FLAC with normalization off. Save the Live
sets for traceability, but do not commit the audio files; the corpus intentionally
gitignores them.

Keep `melodic_techno_arp_124` as the held-out fixture. Agents may tune against the other
four, but the final score must include this untouched stress test.

**Done when:** all five real `audio.flac` files are back in their exact fixture folders
and the completed Gate beta worksheet is available.

### 4. Confirm the intended provider policy

After PR #153 is merged, document and verify this operating policy:

- Gemini remains available and remains the default for users who configure its API key.
- The owner can select Claude explicitly and run the complete advice path without a
  Gemini key or Gemini API credits.
- Missing Gemini funds must not block fixture ingestion, Claude evaluation, Gate alpha,
  Gate beta, or recommendation-quality work.
- There is no automatic fallback or dual-provider review unless that is designed as a
  separate future feature.

If Gemini funds become available later, a controlled same-render comparison can be run:
five calls, one per fixture, plus at most one retry. Until then, use recorded historical
Gemini outputs where comparable and mark the direct comparison as deferred, not blocked.

**Done when:** the documentation clearly presents Claude as an additional selectable
provider and no required step depends on buying Gemini credits.

## Agent Work After Owner Handoff

The agent should then:

1. Replace each proxy fingerprint with Phase 1 output from the real render and confirm
   `_synthetic` is absent.
2. Validate each fingerprint against the fixture's measurable intent.
3. Generate Claude recommendations for every fixture at no Gemini cost.
4. Score Claude, deterministic, and baseline outputs using the same scorer.
5. Report aggregate and per-domain setting accuracy, citation validity, catalogue
   warnings, completeness, latency, and failures.
6. Compare against recorded Gemini evidence where the input is genuinely comparable.
   Do not infer provider superiority from different tracks or different card counts.
7. When Gemini funds become available, optionally run the controlled same-render
   comparison. This is research evidence, not a gate on the Claude provider.
8. Keep deployment separate from quality: the current Claude route depends on a locally
   logged-in CLI, so it cannot yet replace an API-backed provider for other users.
9. Regenerate the UI verification data only from real-render results.
10. Implement the catalogue-alias cleanup for recurring spellings; this is agent work,
   not an owner task.
11. Update `RECOMMENDATION_VERDICT.md`, `NEEDS.md`, the owner assessment, and the
    `asa-ableton` gate documents with one consistent final verdict.

## Provider Policy

- Keep Gemini implemented and available.
- Keep Gemini as the default unless a separate product decision changes it.
- Keep Claude as an explicit no-Gemini-cost option for the owner's local workflow.
- Do not make Claude contingent on proving it better than Gemini.
- Do not claim that Claude and Gemini jointly review each result; the current design is
  selectable providers, one at a time.
- If a future dual-review mode is wanted, design it separately with clear handling for
  disagreements, extra latency, and Gemini cost.

## Completion Checklist

- [ ] PR #153 merged.
- [ ] `feat/track-ii-gate-tooling` pushed and reviewed.
- [ ] Gate beta has a recorded verdict for all six built devices.
- [ ] Five real Ableton fixture renders exist.
- [ ] Five real Phase 1 fingerprints replace the proxy fingerprints.
- [ ] Claude is scored on all five real fixtures without Gemini spending.
- [ ] Documentation presents Gemini and Claude as coexisting selectable providers.
- [ ] Optional Gemini comparison is clearly deferred until funds are available.
- [ ] UI verification badges are regenerated from real evidence.
