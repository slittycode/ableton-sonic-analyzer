"""Per-segment analysis — loudness, stereo, spectral, key, and chords."""

import functools
import sys
from collections import Counter

import librosa
import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import (
    _compute_bark_db,
    _compute_stereo_metrics,
    _safe_db,
    _slice_segments,
    _to_finite_float,
)


# ---- Phase 1.D #2 chord-timeline helpers (Viterbi engine) -----------------
#
# Vocabulary: 25 states = 12 major triads + 12 minor triads + 1 no-chord ("N").
# Short-form labels use Essentia's flat convention so chordTimeline[].label
# matches dominantChords (e.g. "Eb" not "D#"). Long-form labels are emitted
# alongside as labelLong for readability. _normalize_chord_label_for_compare
# is used ONLY for the agreement comparison against Essentia; it maps
# enharmonic sharps to flats so "D#m" and "Ebm" compare equal.

_PITCH_CLASS_NAMES_FLAT = (
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
)
_ENHARMONIC_MAP = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}


@functools.lru_cache(maxsize=1)
def _chord_templates_25() -> np.ndarray:
    """Return a (25, 12) chord-template matrix, L1-normalized per row.

    Rows 0-11: major triads at pitch classes 0-11 (root, +4 semitones, +7).
    Rows 12-23: minor triads at pitch classes 0-11 (root, +3 semitones, +7).
    Row 24: "N" no-chord template — uniform 1/12 across pitch classes,
    matching what a flat chroma profile produces on percussive/silent frames.
    """
    templates = np.zeros((25, 12), dtype=np.float64)
    major_mask = np.zeros(12)
    major_mask[[0, 4, 7]] = 1.0
    minor_mask = np.zeros(12)
    minor_mask[[0, 3, 7]] = 1.0
    for pc in range(12):
        templates[pc] = np.roll(major_mask, pc)
        templates[12 + pc] = np.roll(minor_mask, pc)
    templates[24] = np.full(12, 1.0 / 12.0)
    row_sums = templates.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    templates /= row_sums
    return templates


def _state_label_short(state_idx: int) -> str:
    """Short-form label for a Viterbi state index: 'Cm', 'Eb', 'N'."""
    if state_idx == 24:
        return "N"
    if state_idx < 12:
        return _PITCH_CLASS_NAMES_FLAT[state_idx]
    return _PITCH_CLASS_NAMES_FLAT[state_idx - 12] + "m"


def _state_label_long(state_idx: int) -> str:
    """Long-form label for a Viterbi state index: 'C major', 'Eb minor', 'N'."""
    if state_idx == 24:
        return "N"
    if state_idx < 12:
        return f"{_PITCH_CLASS_NAMES_FLAT[state_idx]} major"
    return f"{_PITCH_CLASS_NAMES_FLAT[state_idx - 12]} minor"


def _normalize_chord_label_for_compare(label: str) -> str:
    """Normalize a chord label to 'root:quality' form for agreement comparison.

    Handles both Essentia short form ('Cm', 'Eb', 'F#m') and Viterbi long form
    ('C minor', 'Eb major', 'F# minor'). Enharmonic sharps are mapped to flats
    so 'D#m' and 'Ebm' produce identical normalized strings. Returns the input
    unchanged for 'N' or non-string input.
    """
    if not isinstance(label, str):
        return ""
    s = label.strip()
    if not s or s == "N":
        return s
    quality = "maj"
    if s.endswith(" minor"):
        quality = "min"
        s = s[: -len(" minor")]
    elif s.endswith(" major"):
        quality = "maj"
        s = s[: -len(" major")]
    elif s.endswith("m") and len(s) > 1 and s[-2] != "m":
        # Short form: trailing 'm' marks minor (Cm, F#m, Ebm). "Em" matches;
        # "maj"-style suffixes never appear in our 25-state vocab.
        quality = "min"
        s = s[:-1]
    s = s.strip()
    root = _ENHARMONIC_MAP.get(s, s)
    return f"{root}:{quality}"


def _viterbi_chord_timeline(
    chroma: np.ndarray,
    hop_seconds: float,
    min_segment_sec: float = 0.25,
    p_stay: float = 0.9,
) -> list[dict]:
    """Decode a chord timeline via Viterbi over the 25-state HMM.

    Parameters
    ----------
    chroma
        (12, T) numpy array — per-frame chroma vectors (librosa convention).
    hop_seconds
        Seconds per frame.
    min_segment_sec
        Drop merged segments shorter than this (250 ms by default — chord
        changes faster than a sixteenth note at 240 BPM are almost always
        decoder noise, not real harmonic events).
    p_stay
        Self-transition probability for the 25-state HMM. 0.9 is a standard
        default for chord HMMs; higher values produce longer / more stable
        segments at the cost of missing fast progressions.

    Returns
    -------
    list of {"startSec", "endSec", "label", "labelLong", "confidence"}.
    Empty list on empty input.
    """
    if chroma.ndim != 2 or chroma.shape[0] != 12:
        return []
    n_frames = chroma.shape[1]
    if n_frames == 0:
        return []

    templates = _chord_templates_25()  # (25, 12) — already L1-normalized per row.

    # L1-normalize chroma columns so the dot product with L1-normalized
    # templates is a directly-comparable mass-overlap score. (L2 normalization
    # of both sides would over-amplify the uniform "N" template on dense
    # electronic tracks where the chroma is broadly distributed; the mass-
    # overlap form is N-safe.)
    chroma_norm = chroma.astype(np.float64)
    col_sums = chroma_norm.sum(axis=0, keepdims=True)
    col_sums[col_sums == 0] = 1.0
    chroma_norm = chroma_norm / col_sums

    emission_scores = templates @ chroma_norm  # (25, T) — Viterbi emission.

    # Softmax with temperature 0.1 turns mass-overlap scores into log-probs
    # for the Viterbi DP. The temperature sharpens preferred state without
    # collapsing the posterior to a delta function.
    temperature = 0.1
    scaled = emission_scores / temperature
    scaled -= scaled.max(axis=0, keepdims=True)
    exp_scaled = np.exp(scaled)
    posterior = exp_scaled / exp_scaled.sum(axis=0, keepdims=True)  # (25, T)
    log_emission = np.log(posterior + 1e-9)

    # Per-frame confidence as L2 cosine similarity between the chroma column
    # and each state's template. Bounded [0, 1] and producer-intuitive: 1.0
    # = perfect chord match, ~0.7 = strong triadic match with leakage, ~0.5
    # = roughly half-matched, ~0.3 = noise. This is more interpretable than
    # the Viterbi softmax posterior, which caps around 0.3 even for perfect
    # chords because the 25 closely-overlapping state templates split the
    # probability mass (e.g., C major and A minor share C+E pitch classes).
    chroma_l2 = chroma.astype(np.float64)
    chroma_l2_norms = np.linalg.norm(chroma_l2, axis=0, keepdims=True)
    chroma_l2_norms[chroma_l2_norms == 0] = 1.0
    chroma_l2 = chroma_l2 / chroma_l2_norms
    templates_l2_norms = np.linalg.norm(templates, axis=1, keepdims=True)
    templates_l2_norms[templates_l2_norms == 0] = 1.0
    templates_l2 = templates / templates_l2_norms
    per_frame_cos_sim = templates_l2 @ chroma_l2  # (25, T) in [0, 1].

    # Log transition matrix.
    n_states = 25
    log_p_stay = np.log(p_stay)
    log_p_move = np.log((1.0 - p_stay) / (n_states - 1))
    log_trans = np.full((n_states, n_states), log_p_move)
    np.fill_diagonal(log_trans, log_p_stay)

    # Viterbi forward pass.
    log_uniform_init = -np.log(n_states)
    delta_matrix = np.full((n_states, n_frames), -np.inf, dtype=np.float64)
    backpointers = np.zeros((n_states, n_frames), dtype=np.int32)
    delta_matrix[:, 0] = log_uniform_init + log_emission[:, 0]
    for t in range(1, n_frames):
        candidate = delta_matrix[:, t - 1][:, None] + log_trans  # (i, j)
        best_src = np.argmax(candidate, axis=0)
        delta_matrix[:, t] = candidate[best_src, np.arange(n_states)] + log_emission[:, t]
        backpointers[:, t] = best_src

    # Viterbi backtrace.
    state_path = np.zeros(n_frames, dtype=np.int32)
    state_path[-1] = int(np.argmax(delta_matrix[:, -1]))
    for t in range(n_frames - 2, -1, -1):
        state_path[t] = backpointers[state_path[t + 1], t + 1]

    # Merge consecutive identical states into segments. Confidence is the
    # mean cosine similarity between chroma and the winning state's template
    # across the segment's frames — bounded [0, 1], higher = better match.
    def _emit(seg_state: int, seg_start: int, seg_end: int) -> dict:
        seg_conf = float(np.mean(per_frame_cos_sim[seg_state, seg_start:seg_end]))
        seg_conf = float(np.clip(seg_conf, 0.0, 1.0))
        return {
            "startSec": round(seg_start * hop_seconds, 3),
            "endSec": round(seg_end * hop_seconds, 3),
            "label": _state_label_short(seg_state),
            "labelLong": _state_label_long(seg_state),
            "confidence": round(seg_conf, 4),
        }

    segments: list[dict] = []
    seg_start = 0
    for t in range(1, n_frames):
        if state_path[t] != state_path[seg_start]:
            segments.append(_emit(int(state_path[seg_start]), seg_start, t))
            seg_start = t
    segments.append(_emit(int(state_path[seg_start]), seg_start, n_frames))

    # Drop short segments (chord changes faster than min_segment_sec are noise).
    segments = [
        seg for seg in segments
        if (seg["endSec"] - seg["startSec"]) >= min_segment_sec
    ]
    # Drop low-confidence "N" segments — those tend to be transition artifacts
    # rather than real "no chord" spans.
    segments = [
        seg for seg in segments
        if seg["label"] != "N" or seg["confidence"] >= 0.4
    ]

    # Cap at 64 segments — keep the 64 longest by duration, then re-sort
    # by start time. Matches the existing payload-cap policy.
    if len(segments) > 64:
        segments.sort(key=lambda s: s["endSec"] - s["startSec"], reverse=True)
        segments = sorted(segments[:64], key=lambda s: s["startSec"])

    return segments


def analyze_segment_loudness(
    structure_data: dict | None,
    stereo: np.ndarray | None,
    sample_rate: int = 44100,
) -> dict:
    """Compute LUFS/LRA per structure segment using LoudnessEBUR128."""
    try:
        if structure_data is None or stereo is None:
            return {"segmentLoudness": None}

        stereo_arr = np.asarray(stereo, dtype=np.float32)
        if stereo_arr.ndim == 1:
            stereo_arr = stereo_arr[:, np.newaxis]
        if stereo_arr.ndim != 2 or stereo_arr.shape[0] == 0:
            return {"segmentLoudness": None}

        segment_slices = _slice_segments(
            structure_data, int(stereo_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentLoudness": None}

        out = []

        for segment in segment_slices:
            start = float(segment["start"])
            end = float(segment["end"])
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])
            lufs = None
            lra = None
            if end_idx > start_idx:
                try:
                    segment_audio = stereo_arr[start_idx:end_idx]
                    _m, _s, integrated, loudness_range = es.LoudnessEBUR128(
                        sampleRate=sample_rate
                    )(segment_audio)
                    if np.isfinite(integrated):
                        lufs = round(float(integrated), 1)
                    if np.isfinite(loudness_range):
                        lra = round(float(loudness_range), 1)
                except Exception:
                    lufs = None
                    lra = None

            out.append(
                {
                    "segmentIndex": index,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "lufs": lufs,
                    "lra": lra,
                }
            )

        return {"segmentLoudness": out}
    except Exception as e:
        print(f"[warn] Segment loudness analysis failed: {e}", file=sys.stderr)
        return {"segmentLoudness": None}


def analyze_segment_stereo(
    structure_data: dict | None,
    stereo: np.ndarray | None,
    sample_rate: int = 44100,
) -> dict:
    """Compute stereo metrics per segment using shared segment slicing."""
    try:
        if structure_data is None or stereo is None:
            return {"segmentStereo": None}

        stereo_arr = np.asarray(stereo, dtype=np.float64)
        if stereo_arr.ndim != 2 or stereo_arr.shape[0] == 0:
            return {"segmentStereo": None}

        segment_slices = _slice_segments(
            structure_data, int(stereo_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentStereo": None}

        if stereo_arr.shape[1] < 2:
            left_all = stereo_arr[:, 0]
            right_all = stereo_arr[:, 0]
        else:
            left_all = stereo_arr[:, 0]
            right_all = stereo_arr[:, 1]

        out = []
        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            if end_idx - start_idx < 2:
                metrics = {"stereoWidth": None, "stereoCorrelation": None}
            else:
                metrics = _compute_stereo_metrics(
                    left_all[start_idx:end_idx], right_all[start_idx:end_idx]
                )

            out.append(
                {
                    "segmentIndex": index,
                    "stereoWidth": metrics.get("stereoWidth"),
                    "stereoCorrelation": metrics.get("stereoCorrelation"),
                }
            )

        return {"segmentStereo": out}
    except Exception as e:
        print(f"[warn] Segment stereo analysis failed: {e}", file=sys.stderr)
        return {"segmentStereo": None}


def analyze_segment_spectral(
    structure_data: dict | None,
    mono: np.ndarray,
    segment_stereo_data: list[dict] | None = None,
    sample_rate: int = 44100,
) -> dict:
    """Compute Bark, centroid/rolloff, and stereo metrics per segment."""
    try:
        if structure_data is None:
            return {"segmentSpectral": None}

        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size == 0:
            return {"segmentSpectral": None}

        segment_slices = _slice_segments(
            structure_data, int(mono_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentSpectral": None}

        stereo_map = {}
        if isinstance(segment_stereo_data, list):
            for item in segment_stereo_data:
                try:
                    stereo_map[int(item.get("segmentIndex"))] = {
                        "stereoWidth": item.get("stereoWidth"),
                        "stereoCorrelation": item.get("stereoCorrelation"),
                    }
                except Exception:
                    continue

        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        centroid_algo = es.SpectralCentroidTime(sampleRate=sample_rate)
        rolloff_algo = es.RollOff(sampleRate=sample_rate)

        out = []

        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            bark_bands = None
            if end_idx > start_idx:
                bark_bands = _compute_bark_db(
                    mono_arr[start_idx:end_idx],
                    sample_rate=sample_rate,
                    frame_size=2048,
                    hop_size=1024,
                    number_bands=24,
                )
            if bark_bands is None:
                bark_bands = [-100.0] * 24

            spectral_centroid = None
            spectral_rolloff = None
            if end_idx > start_idx:
                seg_audio = mono_arr[start_idx:end_idx]
                if seg_audio.size < frame_size:
                    seg_audio = np.pad(seg_audio, (0, frame_size - seg_audio.size))
                centroid_vals = []
                rolloff_vals = []
                for frame in es.FrameGenerator(
                    seg_audio, frameSize=frame_size, hopSize=hop_size
                ):
                    try:
                        spec = spectrum(window(frame))
                        centroid_vals.append(float(centroid_algo(frame)))
                        rolloff_vals.append(float(rolloff_algo(spec)))
                    except Exception:
                        continue
                if len(centroid_vals) > 0:
                    spectral_centroid = round(float(np.mean(centroid_vals)), 1)
                if len(rolloff_vals) > 0:
                    spectral_rolloff = round(float(np.mean(rolloff_vals)), 1)

            stereo_item = stereo_map.get(index, {})
            out.append(
                {
                    "segmentIndex": index,
                    "barkBands": bark_bands,
                    "spectralCentroid": spectral_centroid,
                    "spectralRolloff": spectral_rolloff,
                    "stereoWidth": stereo_item.get("stereoWidth"),
                    "stereoCorrelation": stereo_item.get("stereoCorrelation"),
                }
            )

        return {"segmentSpectral": out}
    except Exception as e:
        print(f"[warn] Segment spectral analysis failed: {e}", file=sys.stderr)
        return {"segmentSpectral": None}


def analyze_segment_key(
    structure_data: dict | None,
    mono: np.ndarray,
    sample_rate: int = 44100,
    *,
    harmonic_mono: np.ndarray | None = None,
) -> dict:
    """Compute key and confidence per segment using KeyExtractor.

    When ``harmonic_mono`` (bass-removed stem mix) is provided, per-segment
    key runs on it instead of the full mix — same harmonic-isolation rationale
    as ``analyze_chords``. Each entry records its ``source``. Falls back to the
    full mix (bit-identical) when stems are unavailable.
    """
    source = "harmonic_stems" if harmonic_mono is not None else "full_mix"
    try:
        if structure_data is None:
            return {"segmentKey": None}

        mono_arr = np.asarray(
            harmonic_mono if harmonic_mono is not None else mono, dtype=np.float32
        )
        if mono_arr.ndim != 1 or mono_arr.size == 0:
            return {"segmentKey": None}

        segment_slices = _slice_segments(
            structure_data, int(mono_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentKey": None}

        key_extractor = es.KeyExtractor(profileType="edma")
        out = []
        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            key_value = None
            key_confidence = None
            if end_idx - start_idx >= 2:
                seg_audio = mono_arr[start_idx:end_idx]
                try:
                    key, scale, strength = key_extractor(seg_audio)
                    key_value = f"{key} {scale.capitalize()}"
                    if np.isfinite(strength):
                        key_confidence = round(float(strength), 2)
                except Exception:
                    key_value = None
                    key_confidence = None

            out.append(
                {
                    "segmentIndex": index,
                    "key": key_value,
                    "keyConfidence": key_confidence,
                    "source": source,
                }
            )

        return {"segmentKey": out}
    except Exception as e:
        print(f"[warn] Segment key analysis failed: {e}", file=sys.stderr)
        return {"segmentKey": None}


def _empty_chord_detail(source: str) -> dict:
    return {
        "chordDetail": {
            "chordSequence": [],
            "chordStrength": 0.0,
            "progression": [],
            "dominantChords": [],
            "chordTimeline": [],
            "chordChangeCount": 0,
            "chordTimelineSource": "librosa_viterbi",
            "chordTimelineAgreement": None,
            "chordSource": source,
        }
    }


def analyze_chords(
    mono: np.ndarray,
    sample_rate: int = 44100,
    *,
    harmonic_mono: np.ndarray | None = None,
) -> dict:
    """Frame-wise HPCP analysis and chord detection via ChordsDetection.

    When ``harmonic_mono`` is provided (a bass-removed stem mix), chroma runs
    on it instead of the full mix — the bassline is the biggest polluter of
    full-mix chroma, so harmonic-source isolation lifts chord accuracy on
    dense material. Falls back to the full mix (bit-identical to before) when
    stems are unavailable. ``chordSource`` records which path ran.
    """
    source = "harmonic_stems" if harmonic_mono is not None else "full_mix"
    try:
        analysis_mono = harmonic_mono if harmonic_mono is not None else mono
        hp_filter = es.HighPass(cutoffFrequency=120, sampleRate=sample_rate)
        mono_filtered = hp_filter(analysis_mono)

        frame_size = 4096
        hop_size = 2048
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=60,
            sampleRate=sample_rate,
        )
        hpcp_algo = es.HPCP(sampleRate=sample_rate)
        chords_algo = es.ChordsDetection(sampleRate=sample_rate, hopSize=hop_size)

        hpcp_sequence = []
        for frame in es.FrameGenerator(
            mono_filtered, frameSize=frame_size, hopSize=hop_size
        ):
            spec = spectrum(window(frame))
            try:
                freqs, mags = spectral_peaks(spec)
                if len(freqs) > 0:
                    hpcp = hpcp_algo(freqs, mags)
                    hpcp_sequence.append(np.asarray(hpcp, dtype=np.float32))
            except Exception:
                continue

        if len(hpcp_sequence) == 0:
            return _empty_chord_detail(source)

        chords, strength = chords_algo(np.asarray(hpcp_sequence, dtype=np.float32))
        chords = [str(c) for c in chords]
        strength = np.asarray(strength, dtype=np.float64)

        if len(chords) == 0:
            return _empty_chord_detail(source)

        # Keep payload manageable.
        if len(chords) > 32:
            indices = np.linspace(0, len(chords) - 1, 32, dtype=int)
            chord_sequence = [chords[i] for i in indices]
        else:
            chord_sequence = chords

        chord_strength = (
            round(float(np.mean(strength)), 4) if strength.size > 0 else 0.0
        )

        progression = []
        for chord in chords:
            if not progression or progression[-1] != chord:
                progression.append(chord)
            if len(progression) >= 16:
                break

        dominant_chords = [label for label, _count in Counter(chords).most_common(4)]

        # Phase 1.D #2 — temporal chord timeline via librosa chroma_cqt +
        # 25-state (12 major + 12 minor + N) Viterbi. Replaces the earlier
        # 5-frame median-filter smoothing of Essentia's per-frame labels.
        # The HMM self-loop prior produces fewer, more confident segments on
        # hard material (electronic, modal) and exposes a per-segment posterior
        # we can hedge against in Phase 2. Same hop_size as the Essentia path
        # so frame indices remain comparable between the two engines.
        chroma = librosa.feature.chroma_cqt(
            y=mono_filtered, sr=sample_rate, hop_length=hop_size
        )
        chord_timeline = _viterbi_chord_timeline(
            chroma, hop_seconds=float(hop_size) / float(sample_rate),
        )

        # chordChangeCount is recomputed from the new timeline (same definition
        # as before — count of label transitions across the segment list).
        chord_change_count = sum(
            1 for i in range(1, len(chord_timeline))
            if chord_timeline[i]["label"] != chord_timeline[i - 1]["label"]
        )

        # Cross-cite against Essentia: does the most-frequent Viterbi label
        # (excluding "N") agree with Essentia's top dominantChord after
        # enharmonic normalization? Disagreement is a strong hedging signal
        # — Phase 2 should describe the harmony as uncertain when this is False.
        viterbi_labels_non_n = [
            seg["label"] for seg in chord_timeline if seg["label"] != "N"
        ]
        chord_timeline_agreement: bool | None
        if viterbi_labels_non_n and dominant_chords:
            top_viterbi = Counter(viterbi_labels_non_n).most_common(1)[0][0]
            top_essentia = dominant_chords[0]
            chord_timeline_agreement = (
                _normalize_chord_label_for_compare(top_viterbi)
                == _normalize_chord_label_for_compare(top_essentia)
            )
        else:
            chord_timeline_agreement = None

        return {
            "chordDetail": {
                "chordSequence": chord_sequence,
                "chordStrength": chord_strength,
                "progression": progression,
                "dominantChords": dominant_chords,
                "chordTimeline": chord_timeline,
                "chordChangeCount": chord_change_count,
                "chordTimelineSource": "librosa_viterbi",
                "chordTimelineAgreement": chord_timeline_agreement,
                "chordSource": source,
            }
        }
    except Exception as e:
        print(f"[warn] Chord analysis failed: {e}", file=sys.stderr)
        return {"chordDetail": None}




