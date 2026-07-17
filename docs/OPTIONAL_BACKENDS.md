# Optional / Frozen Backends

> **Status after 2026-07 trust diet (Waves 2–3).** This document records subsystems that are default-off, non-authoritative, or frozen. See `plans/trust-diet-2026-07.md` for the full decision record.

## Frozen (default-off / non-goal; do not expand)

These remain in the tree because they are threaded through nucleus files or CI-run tests. Excision would be multi-file surgery. They carry `FROZEN 2026-07` banners.

- **MT3 polyphonic transcription** (`mt3_transcription.py`, `ASA_ENABLE_MT3`, run-level `mt3_mode=enabled`): gated, additive only. See `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`.
- **Phase 3 sample generation** (`server_samples.py`, `sample_*.py`): on-demand, user-facing but unvalidated as value. See `docs/SAMPLE_GENERATION.md`.
- **PatchSmith** (`src/services/patchSmith.ts`, `PatchSmithPanel.tsx`): Vital preset generator, zero validation corpus. See header in `patchSmith.ts`.
- **Hosted runtime profile** (`runtime_profile.py`, `auth_context.py`, `worker.py`): speculative deployment infrastructure with no deployment. Local is the product. See `docs/SETUP.md`.

## Removed (Waves 2+3)

- **MOSS** — permanent licence dead-end (501 stub). Sidecar, provider arm, eval harness, and `ASA_MOSS_*` vars removed. See `docs/PHASE2_PROVIDER.md`.
- **MSST / BS-RoFormer separation** — research-only licence gate; no recorded win over Demucs. `separation_backend.py` is now Demucs-only thin seam. See `incorporations/msst-separation-licence-gate-2026-06-05.md`.
- **WASM loudness package** (`packages/loudness-spectro-wasm/`) — archived (real EBU work but unwired on both seams). Backend `loudness_backend.py` degrades to Essentia when binary absent. See archive branch `archive/loudness-spectro-wasm`.

## Non-authoritative (proxy-scored)

- `apps/backend/NEEDS.md` and `apps/backend/RECOMMENDATION_VERDICT.md` carry `NON-AUTHORITATIVE (proxy-scored)` banners. Campaign paused pending real Live 12 renders; do not cite numbers as settled.
- `apps/ui/src/data/recommendationVerification.ts` and `RecommendationVerificationBadge.tsx` are frozen: never regenerate from proxy data.

## Environment Variables for Optional Paths

Product vars live in `CLAUDE.md` "Environment Variables". The following are tied to frozen/removed subsystems and are documented here only:

- `ASA_ENABLE_MT3`, `ASA_LOUDNESS_BACKEND`, `ASA_MEASURE_CLI`, `ASA_PHASE2_PROVIDER`, `ASA_CLAUDE_*` — see frozen sections above and `docs/PHASE2_PROVIDER.md`.
- `VITE_BROWSER_LOUDNESS_WASM_URL` — off-by-default WASM loader (see `src/services/browserLoudness/`).

All optional paths must flow through the same parse / citation / catalogue validators as the product path. Phase 1 stays authoritative (PURPOSE.md invariant #1).
