"""Helpers for the Phase 3 audition-sample HTTP routes.

The thin `@app.post / @app.get` wrappers live in `server.py` to match the
existing house style. All business logic — payload extraction, generation,
artifact registration, manifest decoration — lives here.

These endpoints are on-demand: nothing in the staged-execution loop runs them
automatically. The user (or UI) explicitly POSTs to
`/api/analysis-runs/{run_id}/samples` after Phase 2 is complete.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import sample_generation
from analysis_runtime import AnalysisRuntime

logger = logging.getLogger(__name__)

SAMPLE_AUDIO_KIND_PREFIX = "sample_audio"
SAMPLE_MIDI_KIND_PREFIX = "sample_midi"
SAMPLE_MANIFEST_KIND = "sample_manifest"


class SamplesPreconditionError(Exception):
    """The run isn't in a state where samples can be generated yet."""

    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _extract_phase1_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    stages = snapshot.get("stages") or {}
    measurement = stages.get("measurement") or {}
    if measurement.get("status") != "completed":
        return None
    result = measurement.get("result")
    return result if isinstance(result, dict) else None


def _extract_phase2_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the preferred Phase 2 result if one has completed.

    Returns None if interpretation never ran or didn't complete — sample
    generation still proceeds from Phase 1 alone in that case. Any non-
    "completed" status reaches that path through the isinstance gate below,
    since stages without a completed attempt carry a `null` result anyway.
    """
    stages = snapshot.get("stages") or {}
    interpretation = stages.get("interpretation") or {}
    if interpretation.get("status") != "completed":
        return None
    result = interpretation.get("result")
    return result if isinstance(result, dict) else None


def generate_and_register_samples(
    *,
    runtime: AnalysisRuntime,
    run_id: str,
    snapshot: dict[str, Any],
    force: bool = False,
    allow_soundfont_backends: bool = True,
) -> dict[str, Any]:
    """Run the orchestrator, persist artifacts, return a decorated manifest.

    The decorated manifest is the same shape the orchestrator emits, with
    each sample augmented by `artifactId` so the frontend can construct
    download URLs without a second round-trip.
    """
    phase1 = _extract_phase1_from_snapshot(snapshot)
    if phase1 is None:
        raise SamplesPreconditionError(
            code="MEASUREMENT_NOT_COMPLETED",
            message=(
                "Audition samples require a completed Phase 1 measurement. "
                "Wait for the measurement stage to finish before requesting samples."
            ),
            status_code=409,
        )

    phase2 = _extract_phase2_from_snapshot(snapshot)

    if not force:
        existing = runtime.get_internal_artifacts_by_kind(run_id, SAMPLE_MANIFEST_KIND)
        if existing:
            raise SamplesPreconditionError(
                code="SAMPLES_ALREADY_GENERATED",
                message=(
                    "An audition-sample manifest already exists for this run. "
                    "Pass ?force=true to regenerate."
                ),
                status_code=409,
            )

    with tempfile.TemporaryDirectory(prefix=f"asa-samples-{run_id}-") as tmp_root:
        tmp_dir = Path(tmp_root)
        result = sample_generation.generate_samples(
            run_id=run_id,
            phase1=phase1,
            phase2=phase2,
            output_dir=tmp_dir,
            pitch_note_hints=None,  # Pitch/note translation hints are a follow-up.
            allow_soundfont_backends=allow_soundfont_backends,
        )

        # Persist each WAV/MIDI as a run artifact. The artifact kind names the
        # sample so the GET-by-kind endpoint can filter just sample artifacts
        # without including spectral or stem outputs.
        sample_artifact_ids: dict[str, str] = {}
        midi_artifact_ids: dict[str, str] = {}
        for sample_id, wav_path in result.artifact_paths.items():
            record = runtime.record_artifact(
                run_id,
                kind=f"{SAMPLE_AUDIO_KIND_PREFIX}:{sample_id}",
                source_path=str(wav_path),
                filename=wav_path.name,
                mime_type="audio/wav",
                provenance={
                    "sampleId": sample_id,
                    "schemaVersion": result.manifest["schemaVersion"],
                },
            )
            sample_artifact_ids[sample_id] = record["artifactId"]
        for sample_id, mid_path in result.midi_paths.items():
            record = runtime.record_artifact(
                run_id,
                kind=f"{SAMPLE_MIDI_KIND_PREFIX}:{sample_id}",
                source_path=str(mid_path),
                filename=mid_path.name,
                mime_type="audio/midi",
                provenance={
                    "sampleId": sample_id,
                    "schemaVersion": result.manifest["schemaVersion"],
                },
            )
            midi_artifact_ids[sample_id] = record["artifactId"]

        # And persist the manifest itself. Future GETs read this back to
        # decorate the response identically.
        manifest_record = runtime.record_artifact(
            run_id,
            kind=SAMPLE_MANIFEST_KIND,
            source_path=str(result.manifest_path),
            filename=result.manifest_path.name,
            mime_type="application/json",
            provenance={
                "schemaVersion": result.manifest["schemaVersion"],
                "sampleArtifactIds": sample_artifact_ids,
                "midiArtifactIds": midi_artifact_ids,
            },
        )

    decorated = _decorate_manifest(
        result.manifest, sample_artifact_ids, midi_artifact_ids
    )
    decorated["manifestArtifactId"] = manifest_record["artifactId"]
    return decorated


def fetch_existing_manifest(
    *,
    runtime: AnalysisRuntime,
    run_id: str,
) -> dict[str, Any] | None:
    """Reconstruct the decorated manifest from previously-persisted artifacts.

    Returns None if no manifest has been generated yet — caller can decide
    whether that's a 404 or a different signal.
    """
    manifests = runtime.get_internal_artifacts_by_kind(run_id, SAMPLE_MANIFEST_KIND)
    if not manifests:
        return None
    # get_internal_artifacts_by_kind returns rows ordered by created_at ASC,
    # so the latest is the tail. (force=true paths create multiple rows.)
    latest = manifests[-1]

    manifest_path = runtime.resolve_artifact_local_path(latest.get("path"))
    if manifest_path is None or not manifest_path.is_file():
        return None
    raw = json.loads(manifest_path.read_text())
    provenance = latest.get("provenance") or {}
    decorated = _decorate_manifest(
        raw,
        provenance.get("sampleArtifactIds") or {},
        provenance.get("midiArtifactIds") or {},
    )
    decorated["manifestArtifactId"] = latest["artifactId"]
    return decorated


def _decorate_manifest(
    manifest: dict[str, Any],
    sample_artifact_ids: dict[str, str],
    midi_artifact_ids: dict[str, str],
) -> dict[str, Any]:
    """Attach artifactId fields to each sample so the UI can build URLs."""
    decorated = dict(manifest)
    decorated_samples: list[dict[str, Any]] = []
    for sample in manifest.get("samples", []):
        copy = dict(sample)
        sample_id = sample.get("id")
        if sample_id in sample_artifact_ids:
            copy["artifactId"] = sample_artifact_ids[sample_id]
        if sample_id in midi_artifact_ids:
            copy["midiArtifactId"] = midi_artifact_ids[sample_id]
        decorated_samples.append(copy)
    decorated["samples"] = decorated_samples
    return decorated
