# MOSS-Audio Phase 2 Sidecar

A standalone FastAPI service that emits the **identical `Phase2Result` schema** as
the Gemini Phase 2 path, fed the same inputs (built prompt + audio + authoritative
Phase 1 JSON + `response_schema`). The ASA backend reaches it via
[`phase2_provider.py`](../phase2_provider.py) when `ASA_PHASE2_PROVIDER=moss`.

**Default-off research experiment.** Gemini stays the product default. This sidecar
runs in its **own venv**, isolated from the product venv (mirrors the MSST
separation runner) so its dependencies never touch `analyze.py`'s contract.

## ⚠️ Licence status (STEP ONE gate)

- **Weights** (`OpenMOSS-Team/MOSS-Audio-*` on HuggingFace): **Apache-2.0** — clean,
  permits self-host + derivative + commercial use.
- **Modeling code** (the forward pass you must run): **no effective licence.** The
  `OpenMOSS/MOSS-Audio` GitHub repo has no `LICENSE` file; its `pyproject.toml`
  declares `license = { file = "LICENSE" }` — a dangling reference to a file that
  does not exist. The HF weights repo has no `modeling_*.py` and its `auto_map` has
  no `AutoModel` entry, so you cannot run the model without the GitHub `src/` code.

Consequence: **this sidecar ships no OpenMOSS code.** The real-model path
(`ASA_MOSS_SIDECAR_MODE=model`) is a 501 stub. Only the deterministic `mock` mode
runs. See [`docs/PHASE2_PROVIDER.md`](../../../docs/PHASE2_PROVIDER.md) and the
`asa-moss-audio-licence-gate` memory. Promotion is unblocked only when OpenMOSS
publishes the missing LICENSE (or `moss_audio` is upstreamed into Apache-2.0
`transformers`), or a cleanly-licensed runtime can serve the Apache-2.0 weights for
audio-in inference.

## Run (mock mode)

```bash
# From apps/backend (own venv — NOT the product venv):
python3.11 -m venv moss_sidecar/.venv
moss_sidecar/.venv/bin/pip install -r moss_sidecar/requirements.txt
moss_sidecar/.venv/bin/python -m moss_sidecar.app          # serves 127.0.0.1:8200
```

Then point the backend at it:

```bash
ASA_PHASE2_PROVIDER=moss ASA_MOSS_SIDECAR_URL=http://127.0.0.1:8200 \
  <start the ASA backend>   # producer_summary interpretations now route to MOSS
```

`stem_summary` interpretations stay on Gemini; only the recommendation-emitting
`producer_summary` profile routes to MOSS.

## Contract

`POST /v1/phase2`

```jsonc
{
  "prompt": "<full Phase 2 system prompt, already embeds Phase 1 + device catalogue>",
  "response_schema": { /* the Phase2Result schema server.py would hand Gemini */ },
  "phase1": { /* authoritative measurement JSON, for citation grounding */ },
  "model": "moss-audio-4b-instruct",
  "audio": { "filename": "x.flac", "mime_type": "audio/flac", "base64": "..." }  // or null
}
```

→ `{ "result": <Phase2Result> | null, "provider": "moss-mock" | "moss", "warnings": [] }`

`GET /healthz` → `{ "status": "ok", "mode": "mock", "provider": "moss-mock" }`

The backend re-serialises `result` and runs it through the **same** parse +
`_validate_phase2_citation_paths` + `apply_live12_catalogue_gates` path as Gemini,
so the schema and the chain-of-custody contract are enforced identically.

## Eval

[`scripts/evaluate_phase2_providers.py`](../scripts/evaluate_phase2_providers.py)
scores citation accuracy across providers on the fixed
`tests/fixtures/recommendation_tracks/` corpus. The mock's citation accuracy is
~1.0 **by construction** (it cites only resolving paths) — it proves the pipeline
and scorer, not the real model's quality. Live MOSS-vs-Gemini numbers are blocked
(no Gemini key locally, no audio renders in the corpus, model not runnable under
the licence gate); see the eval's `--help` and `docs/PHASE2_PROVIDER.md`.
