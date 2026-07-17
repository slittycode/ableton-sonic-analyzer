# Phase 2 Provider — tombstone (MOSS removed)

The MOSS-Audio sidecar experiment was a permanent licence dead-end: weights were Apache-2.0, but the modeling code had no effective licence, so the real-model path was a designed-in 501 stub that could never ship. Removed in the 2026-07 trust diet (`plans/trust-diet-2026-07.md`, Wave 2 B1).

**What remains:** `ASA_PHASE2_PROVIDER=gemini` (product default) or `claude` (local CLI, text-only). See `apps/backend/phase2_provider.py`. Restore the old analysis + sidecar from tag `archive/pre-trust-diet-2026-07` if needed.
