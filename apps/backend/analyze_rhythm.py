"""Rhythm analysis — beat loudness, groove, melody, onset detection, and timeline."""

import math
import os
import sys
from collections import Counter
from typing import Any

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import _compute_tempo_curve_from_ticks


def _extract_beat_loudness_data(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
) -> dict | None:
    """Shared beat/band loudness extraction for groove and sidechain analyses."""
    try:
        if rhythm_data is None:
            return None

        ticks = np.asarray(rhythm_data.get("ticks", []), dtype=np.float64)
        if ticks.size < 2:
            return None

        frequency_bands = [20, 200, 200, 4000, 4000, 20000]

        beat_loudness_cls = getattr(es, "BeatLoudness", None)
        use_ratio_output = False
        if beat_loudness_cls is None:
            beat_loudness_cls = getattr(es, "BeatsLoudness", None)
            use_ratio_output = True
        if beat_loudness_cls is None:
            return None

        beat_loudness_algo = beat_loudness_cls(
            beats=ticks.tolist(),
            sampleRate=sample_rate,
            frequencyBands=frequency_bands,
        )
        beat_loudness, band_loudness = beat_loudness_algo(mono)

        beat_loudness = np.asarray(beat_loudness, dtype=np.float64)
        band_loudness = np.asarray(band_loudness, dtype=np.float64)
        if band_loudness.ndim != 2 or band_loudness.shape[0] == 0:
            return None

        if use_ratio_output:
            if beat_loudness.size != band_loudness.shape[0]:
                return None
            band_loudness = band_loudness * beat_loudness[:, np.newaxis]

        low_band = band_loudness[:, 0]
        # Phase 1.C #3: surface the middle band (200-4000 Hz) so analyze_groove
        # can compute per-drum-group swing for the snare separately from kick
        # and hi-hat. The BeatLoudness algorithm already computes this — we
        # were just discarding it.
        mid_band = (
            band_loudness[:, 1]
            if band_loudness.shape[1] >= 3
            else np.zeros(band_loudness.shape[0], dtype=np.float64)
        )
        high_band = band_loudness[:, -1]
        count = min(
            ticks.size,
            beat_loudness.size,
            band_loudness.shape[0],
            low_band.size,
            high_band.size,
        )
        if count < 2:
            return None

        beats = ticks[:count]
        beat_loudness = beat_loudness[:count]
        band_loudness = band_loudness[:count, :]
        low_band = low_band[:count]
        mid_band = mid_band[:count]
        high_band = high_band[:count]

        return {
            "beats": beats,
            "beatLoudness": beat_loudness,
            "bandLoudness": band_loudness,
            "lowBand": low_band,
            "midBand": mid_band,
            "highBand": high_band,
        }
    except Exception:
        return None


def _detect_onset_times(
    mono: np.ndarray,
    sample_rate: int,
    frame_size: int = 1024,
    hop_size: int = 512,
) -> np.ndarray:
    """Detect onset times from audio frames using Essentia onset tools."""
    mono_arr = np.asarray(mono, dtype=np.float32)
    if mono_arr.ndim != 1 or mono_arr.size < frame_size:
        return np.asarray([], dtype=np.float64)

    window = es.Windowing(type="hann", size=frame_size)
    spectrum = es.Spectrum(size=frame_size)
    onset_detection = es.OnsetDetection(method="hfc", sampleRate=sample_rate)
    onset_values = []

    for frame in es.FrameGenerator(
        mono_arr,
        frameSize=frame_size,
        hopSize=hop_size,
    ):
        spec = spectrum(window(frame))
        onset_value = None
        try:
            onset_value = float(onset_detection(spec))
        except Exception:
            try:
                onset_value = float(
                    onset_detection(spec, np.zeros_like(spec, dtype=np.float32)),
                )
            except Exception:
                onset_value = None

        if onset_value is not None and np.isfinite(onset_value):
            onset_values.append(onset_value)

    if len(onset_values) == 0:
        return np.asarray([], dtype=np.float64)

    onset_times = es.Onsets(
        frameRate=float(sample_rate) / float(hop_size),
    )(
        np.asarray([onset_values], dtype=np.float32),
        np.asarray([1.0], dtype=np.float32),
    )
    onset_times = np.asarray(onset_times, dtype=np.float64)
    return onset_times[np.isfinite(onset_times)]


def analyze_rhythm_detail(
    mono: np.ndarray,
    sample_rate: int,
    rhythm_data: dict | None,
) -> dict:
    """Onset rate, beat positions, and groove amount from shared rhythm data."""
    try:
        if rhythm_data is None:
            return {"rhythmDetail": None}

        ticks = np.asarray(rhythm_data["ticks"], dtype=np.float64)

        duration_seconds = (
            float(len(np.asarray(mono, dtype=np.float32)) / sample_rate)
            if sample_rate > 0
            else 0.0
        )
        onset_times = _detect_onset_times(mono, sample_rate)
        onset_rate = (
            float(onset_times.size) / duration_seconds
            if duration_seconds > 0 and onset_times.size > 0
            else 0.0
        )

        beat_grid = [round(float(t), 3) for t in ticks]
        beat_positions = [((index % 4) + 1) for index in range(len(beat_grid))]
        downbeats = beat_grid[::4]

        # Groove amount: stdev of beat interval diffs, normalized by mean interval
        if len(ticks) >= 3:
            intervals = np.diff(ticks.astype(np.float64))
            mean_interval = float(np.mean(intervals))
            if mean_interval > 0:
                groove = float(np.std(intervals) / mean_interval)
            else:
                groove = 0.0
        else:
            groove = 0.0

        # Tempo stability: 1.0 = metronomic, 0.0 = arrhythmic
        tempo_stability = round(float(np.clip(1.0 - groove, 0.0, 1.0)), 4)

        # Phrase grid: group downbeats into 4-bar, 8-bar, 16-bar phrases
        phrase_grid = None
        if len(downbeats) >= 2:
            phrases_4bar = [downbeats[i] for i in range(0, len(downbeats), 4)]
            phrases_8bar = [downbeats[i] for i in range(0, len(downbeats), 8)]
            phrases_16bar = [downbeats[i] for i in range(0, len(downbeats), 16)]
            phrase_grid = {
                "phrases4Bar": phrases_4bar,
                "phrases8Bar": phrases_8bar,
                "phrases16Bar": phrases_16bar,
                "totalBars": len(downbeats),
                "totalPhrases8Bar": len(phrases_8bar),
            }

        # Instantaneous-BPM curve from beat ticks, smoothed with a 4-beat
        # rolling median. Surfaces deliberate ritardando/accelerando and
        # DJ-tool transitions that the single mean BPM scalar conflates away.
        tempo_curve = _compute_tempo_curve_from_ticks(ticks)

        return {
            "rhythmDetail": {
                "onsetRate": round(onset_rate, 2),
                "beatGrid": beat_grid,
                "downbeats": downbeats,
                "beatPositions": beat_positions,
                "grooveAmount": round(groove, 4),
                "tempoStability": tempo_stability,
                "phraseGrid": phrase_grid,
                "tempoCurve": tempo_curve,
            }
        }
    except Exception as e:
        print(f"[warn] Rhythm detail analysis failed: {e}", file=sys.stderr)
        return {"rhythmDetail": None}


def analyze_melody(
    audio_path: str,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    stems: dict | None = None,
) -> dict:
    """Melody extraction with contour segmentation and optional MIDI export."""
    try:
        source_path = audio_path
        source_separated = False
        if stems is not None:
            other_path = stems.get("other")
            if isinstance(other_path, str) and os.path.exists(other_path):
                source_path = other_path
                source_separated = True

        loader = es.EqloudLoader(filename=source_path, sampleRate=sample_rate)
        audio_eq = loader()

        pitch_extractor = es.PredominantPitchMelodia(frameSize=2048, hopSize=128)
        pitch_values, pitch_confidence = pitch_extractor(audio_eq)
        pitch_values = np.asarray(pitch_values, dtype=np.float64)
        pitch_confidence = np.asarray(pitch_confidence, dtype=np.float64)
        mean_conf = (
            float(np.mean(pitch_confidence)) if pitch_confidence.size > 0 else 0.0
        )
        vibrato_metrics = {
            "vibratoPresent": False,
            "vibratoExtent": 0.0,
            "vibratoRate": 0.0,
            "vibratoConfidence": 0.0,
        }

        # Reuse existing pitch contour (do not re-run Melodia) for vibrato extraction.
        try:
            pitch_frame_rate = float(sample_rate) / 128.0 if sample_rate > 0 else 0.0
            min_pitch_frames = (
                int(np.ceil((2.0 * pitch_frame_rate) / 4.0))
                if pitch_frame_rate > 0
                else 0
            )
            voiced_pitch = pitch_values[
                np.isfinite(pitch_values) & (pitch_values > 0.0)
            ]

            if min_pitch_frames > 0 and voiced_pitch.size >= min_pitch_frames:
                vibrato_algo = es.Vibrato(
                    sampleRate=pitch_frame_rate,
                    minFrequency=4.0,
                    maxFrequency=8.0,
                    minExtend=50.0,
                    maxExtend=250.0,
                )
                vibrato_frequency, vibrato_extend = vibrato_algo(
                    np.asarray(voiced_pitch, dtype=np.float32)
                )
                vibrato_frequency = np.asarray(vibrato_frequency, dtype=np.float64)
                vibrato_extend = np.asarray(vibrato_extend, dtype=np.float64)

                valid = (
                    np.isfinite(vibrato_frequency)
                    & np.isfinite(vibrato_extend)
                    & (vibrato_frequency > 0.0)
                    & (vibrato_extend > 0.0)
                )
                if vibrato_extend.size > 0:
                    confidence = float(np.sum(valid)) / float(vibrato_extend.size)
                else:
                    confidence = 0.0

                extent = float(np.mean(vibrato_extend[valid])) if np.any(valid) else 0.0
                rate = (
                    float(np.mean(vibrato_frequency[valid])) if np.any(valid) else 0.0
                )
                vibrato_metrics = {
                    "vibratoPresent": bool(extent > 50.0),
                    "vibratoExtent": round(extent, 4),
                    "vibratoRate": round(rate, 4),
                    "vibratoConfidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
                }
        except Exception:
            vibrato_metrics = {
                "vibratoPresent": False,
                "vibratoExtent": 0.0,
                "vibratoRate": 0.0,
                "vibratoConfidence": 0.0,
            }

        contour_segmenter = es.PitchContourSegmentation(
            hopSize=128, sampleRate=sample_rate
        )
        onsets, durations, notes = contour_segmenter(pitch_values, audio_eq)

        onsets = np.asarray(onsets, dtype=np.float64)
        durations = np.asarray(durations, dtype=np.float64)
        notes = np.asarray(notes, dtype=np.float64)

        count = min(onsets.size, durations.size, notes.size)
        if count == 0:
            return {
                "melodyDetail": {
                    "noteCount": 0,
                    "notes": [],
                    "dominantNotes": [],
                    "pitchRange": {"min": None, "max": None},
                    "pitchConfidence": round(mean_conf, 4),
                    "midiFile": None,
                    "sourceSeparated": source_separated,
                    "vibratoPresent": vibrato_metrics["vibratoPresent"],
                    "vibratoExtent": vibrato_metrics["vibratoExtent"],
                    "vibratoRate": vibrato_metrics["vibratoRate"],
                    "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
                }
            }

        note_events = []
        midi_values = []
        for i in range(count):
            onset = float(onsets[i])
            duration = float(durations[i])
            midi_note = int(np.rint(notes[i]))
            if duration <= 0:
                continue
            midi_note = int(np.clip(midi_note, 0, 127))
            note_events.append((onset, duration, midi_note))
            midi_values.append(midi_note)

        if len(note_events) == 0:
            return {
                "melodyDetail": {
                    "noteCount": 0,
                    "notes": [],
                    "dominantNotes": [],
                    "pitchRange": {"min": None, "max": None},
                    "pitchConfidence": round(mean_conf, 4),
                    "midiFile": None,
                    "sourceSeparated": source_separated,
                    "vibratoPresent": vibrato_metrics["vibratoPresent"],
                    "vibratoExtent": vibrato_metrics["vibratoExtent"],
                    "vibratoRate": vibrato_metrics["vibratoRate"],
                    "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
                }
            }

        note_objects = [
            {
                "midi": int(m),
                "onset": round(float(o), 3),
                "duration": round(float(d), 3),
            }
            for (o, d, m) in note_events
        ]
        if len(note_objects) > 64:
            indices = np.linspace(0, len(note_objects) - 1, 64, dtype=int)
            sampled_notes = [note_objects[i] for i in indices]
        else:
            sampled_notes = note_objects

        dominant_notes = [
            label for label, _count in Counter(midi_values).most_common(5)
        ]
        pitch_range = {"min": int(min(midi_values)), "max": int(max(midi_values))}

        midi_file_path = None
        try:
            import mido

            bpm = 120.0
            if rhythm_data is not None and rhythm_data.get("bpm") is not None:
                bpm = float(rhythm_data["bpm"])
            if not np.isfinite(bpm) or bpm <= 0:
                bpm = 120.0

            ppq = 96
            ticks_per_second = (ppq * bpm) / 60.0
            midi_out = mido.MidiFile(ticks_per_beat=ppq)
            track = mido.MidiTrack()
            midi_out.tracks.append(track)
            track.append(
                mido.MetaMessage("set_tempo", tempo=int(mido.bpm2tempo(bpm)), time=0)
            )

            events = []
            for onset, duration, midi_note in note_events:
                start_tick = max(0, int(round(onset * ticks_per_second)))
                end_tick = max(
                    start_tick + 1, int(round((onset + duration) * ticks_per_second))
                )
                events.append((start_tick, 1, midi_note))
                events.append((end_tick, 0, midi_note))
            events.sort(key=lambda e: (e[0], e[1]))

            prev_tick = 0
            for tick, is_note_on, midi_note in events:
                delta = max(0, tick - prev_tick)
                if is_note_on == 1:
                    track.append(
                        mido.Message("note_on", note=midi_note, velocity=90, time=delta)
                    )
                else:
                    track.append(
                        mido.Message("note_off", note=midi_note, velocity=0, time=delta)
                    )
                prev_tick = tick

            output_dir = os.path.dirname(audio_path)
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            midi_file_path = os.path.join(output_dir, f"{base_name}_melody.mid")
            midi_out.save(midi_file_path)
        except Exception as e:
            print(f"[warn] Melody MIDI export failed: {e}", file=sys.stderr)
            midi_file_path = None

        return {
            "melodyDetail": {
                "noteCount": len(note_events),
                "notes": sampled_notes,
                "dominantNotes": dominant_notes,
                "pitchRange": pitch_range,
                "pitchConfidence": round(mean_conf, 4),
                "midiFile": midi_file_path,
                "sourceSeparated": source_separated,
                "vibratoPresent": vibrato_metrics["vibratoPresent"],
                "vibratoExtent": vibrato_metrics["vibratoExtent"],
                "vibratoRate": vibrato_metrics["vibratoRate"],
                "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
            }
        }
    except Exception as e:
        print(f"[warn] Melody analysis failed: {e}", file=sys.stderr)
        return {"melodyDetail": None}


def analyze_groove(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Per-beat groove detail from beat-synchronous band loudness."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"grooveDetail": None}

        beats = np.asarray(beat_data.get("beats", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        mid_band = np.asarray(beat_data.get("midBand", []), dtype=np.float64)
        high_band = np.asarray(beat_data.get("highBand", []), dtype=np.float64)
        if beats.size < 2 or low_band.size < 2 or high_band.size < 2:
            return {"grooveDetail": None}

        # Swing: stdev(intervals between beats above mean), normalized by mean interval.
        def calc_swing(band_values: np.ndarray, beat_positions: np.ndarray) -> float:
            if band_values.size < 2 or beat_positions.size < 2:
                return 0.0

            mean_val = float(np.mean(band_values))
            selected_beats = beat_positions[band_values > mean_val]
            if selected_beats.size < 2:
                return 0.0

            intervals = np.diff(selected_beats)
            mean_interval = float(np.mean(intervals))
            if mean_interval <= 0:
                return 0.0
            return float(np.std(intervals) / mean_interval)

        def sample_accents(values: np.ndarray, max_points: int = 16) -> list[float]:
            if values.size == 0:
                return []
            if values.size > max_points:
                indices = np.linspace(0, values.size - 1, max_points, dtype=int)
                values = values[indices]
            return [round(float(v), 4) for v in values]

        raw_kick_swing = calc_swing(low_band, beats)
        raw_snare_swing = (
            calc_swing(mid_band, beats) if mid_band.size >= 2 else 0.0
        )
        raw_hihat_swing = calc_swing(high_band, beats)
        # Normalize to 0-1 scale using tanh compression
        kick_swing = round(math.tanh(raw_kick_swing * 0.5), 4)
        snare_swing = round(math.tanh(raw_snare_swing * 0.5), 4)
        hihat_swing = round(math.tanh(raw_hihat_swing * 0.5), 4)
        kick_accent = sample_accents(low_band, 16)
        hihat_accent = sample_accents(high_band, 16)

        # Phase 1.C #3: per-drum-group swing object — derived from the three
        # beat-loudness bands (kick: 20-200 Hz, snare: 200-4000 Hz, hi-hat:
        # 4000-20000 Hz). When `stems.drums` is present the per-stem drum
        # analyzers (snareDetail, hihatDetail) give more accurate event timing;
        # but this object is computed on the same loudness signal used for
        # kickSwing/hihatSwing, so it's available even when stems are absent.
        per_drum_swing = {
            "kick": kick_swing,
            "snare": snare_swing,
            "hihat": hihat_swing,
        }

        return {
            "grooveDetail": {
                "kickSwing": kick_swing,
                "hihatSwing": hihat_swing,
                "kickAccent": kick_accent,
                "hihatAccent": hihat_accent,
                "perDrumSwing": per_drum_swing,
            }
        }
    except Exception as e:
        print(f"[warn] Groove analysis failed: {e}", file=sys.stderr)
        return {"grooveDetail": None}


def _build_bar_position_pattern(values: np.ndarray, count: int) -> list[float]:
    if values.size == 0 or count <= 0:
        return [0.0] * max(count, 0)

    sums = np.zeros(count, dtype=np.float64)
    counts = np.zeros(count, dtype=np.float64)
    for index, value in enumerate(values):
        position = index % count
        sums[position] += float(value)
        counts[position] += 1.0

    averages = []
    for position in range(count):
        if counts[position] > 0:
            averages.append(float(sums[position] / counts[position]))
        else:
            averages.append(0.0)

    max_value = max(averages, default=0.0)
    if max_value <= 0:
        return [0.0] * count
    return [round(value / max_value, 4) for value in averages]


def analyze_rhythm_timeline(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Build a representative multi-bar sequencer timeline from DSP timing and band energy."""
    try:
        beats_per_bar = 4
        steps_per_beat = 4
        steps_per_bar = beats_per_bar * steps_per_beat

        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)

        beats = np.asarray(
            beat_data.get("beats", []) if isinstance(beat_data, dict) else [],
            dtype=np.float64,
        )
        beats = beats[np.isfinite(beats)]
        if beats.size < beats_per_bar:
            return {"rhythmTimeline": None}

        if beats.size >= 2:
            beat_intervals = np.diff(beats)
            finite_intervals = beat_intervals[np.isfinite(beat_intervals) & (beat_intervals > 0)]
            median_beat_interval = (
                float(np.median(finite_intervals)) if finite_intervals.size > 0 else None
            )
        else:
            median_beat_interval = None
        if median_beat_interval is None or median_beat_interval <= 0:
            return {"rhythmTimeline": None}

        mono_arr = np.asarray(mono, dtype=np.float32)
        total_samples = int(mono_arr.size)
        if total_samples < 8 or sample_rate <= 0:
            return {"rhythmTimeline": None}

        low_steps: list[float] = []
        mid_steps: list[float] = []
        high_steps: list[float] = []
        overall_steps: list[float] = []
        valid_beats = 0

        for beat_index, start in enumerate(beats):
            end = (
                float(beats[beat_index + 1])
                if beat_index + 1 < beats.size
                else float(start + median_beat_interval)
            )
            if not np.isfinite(start) or not np.isfinite(end) or end <= start:
                continue

            beat_start_sample = max(0, int(round(start * sample_rate)))
            beat_end_sample = min(total_samples, int(round(end * sample_rate)))
            if beat_end_sample - beat_start_sample < 8:
                continue

            step_length = (beat_end_sample - beat_start_sample) / float(steps_per_beat)
            if step_length <= 0:
                continue

            for step_index in range(steps_per_beat):
                step_start = beat_start_sample + int(round(step_index * step_length))
                step_end = beat_start_sample + int(round((step_index + 1) * step_length))
                step_start = max(0, min(total_samples - 1, step_start))
                step_end = max(step_start + 1, min(total_samples, step_end))
                segment = mono_arr[step_start:step_end]
                if segment.size < 8:
                    low_steps.append(0.0)
                    mid_steps.append(0.0)
                    high_steps.append(0.0)
                    overall_steps.append(0.0)
                    continue

                window = np.hanning(segment.size).astype(np.float32)
                spectrum = np.fft.rfft(segment * window)
                freqs = np.fft.rfftfreq(segment.size, d=1.0 / sample_rate)
                power = np.abs(spectrum) ** 2

                low_mask = (freqs >= 20.0) & (freqs < 200.0)
                mid_mask = (freqs >= 200.0) & (freqs < 4000.0)
                high_mask = freqs >= 4000.0

                low_energy = float(np.sum(power[low_mask])) if np.any(low_mask) else 0.0
                mid_energy = float(np.sum(power[mid_mask])) if np.any(mid_mask) else 0.0
                high_energy = float(np.sum(power[high_mask])) if np.any(high_mask) else 0.0
                total_energy = low_energy + mid_energy + high_energy

                low_steps.append(low_energy)
                mid_steps.append(mid_energy)
                high_steps.append(high_energy)
                overall_steps.append(total_energy)

            valid_beats += 1

        available_bars = valid_beats // beats_per_bar
        if available_bars <= 0:
            return {"rhythmTimeline": None}

        usable_step_count = available_bars * steps_per_bar

        def _normalize_step_series(values: list[float]) -> np.ndarray:
            series = np.asarray(values[:usable_step_count], dtype=np.float64)
            if series.size == 0:
                return series
            max_value = float(np.max(series))
            if max_value <= 0 or not np.isfinite(max_value):
                return np.zeros_like(series)
            return np.clip(series / max_value, 0.0, 1.0)

        low_series = _normalize_step_series(low_steps)
        mid_series = _normalize_step_series(mid_steps)
        high_series = _normalize_step_series(high_steps)
        overall_series = _normalize_step_series(overall_steps)

        low_bars = low_series.reshape(available_bars, steps_per_bar)
        mid_bars = mid_series.reshape(available_bars, steps_per_bar)
        high_bars = high_series.reshape(available_bars, steps_per_bar)
        overall_bars = overall_series.reshape(available_bars, steps_per_bar)

        def _window_similarity(window: np.ndarray) -> float:
            if window.shape[0] < 2:
                return 1.0
            diffs = np.mean(np.abs(np.diff(window, axis=0)), axis=1)
            return float(np.mean(1.0 - np.clip(diffs, 0.0, 1.0)))

        def _best_window_start(bar_count: int) -> int:
            if available_bars <= bar_count:
                return 0
            best_index = 0
            best_score = -1.0
            for start_index in range(0, available_bars - bar_count + 1):
                window = overall_bars[start_index : start_index + bar_count]
                activity = float(np.mean(window))
                consistency = _window_similarity(window)
                score = activity * 0.65 + consistency * 0.35
                if score > best_score + 1e-9:
                    best_index = start_index
                    best_score = score
            return best_index

        def _emit_window(start_bar_index: int, bar_count: int) -> dict[str, Any]:
            start_step = start_bar_index * steps_per_bar
            end_step = start_step + bar_count * steps_per_bar
            return {
                "bars": int(bar_count),
                "startBar": int(start_bar_index + 1),
                "endBar": int(start_bar_index + bar_count),
                "lowBandSteps": [round(float(value), 4) for value in low_series[start_step:end_step]],
                "midBandSteps": [round(float(value), 4) for value in mid_series[start_step:end_step]],
                "highBandSteps": [round(float(value), 4) for value in high_series[start_step:end_step]],
                "overallSteps": [round(float(value), 4) for value in overall_series[start_step:end_step]],
            }

        primary_bars = 8 if available_bars >= 8 else available_bars
        primary_start = _best_window_start(primary_bars)
        windows = [_emit_window(primary_start, primary_bars)]

        if available_bars >= 16:
            extended_start = min(max(primary_start, 0), available_bars - 16)
            windows.append(_emit_window(extended_start, 16))

        return {
            "rhythmTimeline": {
                "beatsPerBar": beats_per_bar,
                "stepsPerBeat": steps_per_beat,
                "availableBars": int(available_bars),
                "selectionMethod": "representative_dsp_window",
                "windows": windows,
            }
        }
    except Exception as e:
        print(f"[warn] Rhythm timeline analysis failed: {e}", file=sys.stderr)
        return {"rhythmTimeline": None}


def analyze_beats_loudness(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Beat-synchronous loudness summary with band dominance and accent pattern."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"beatsLoudness": None}

        beat_loudness = np.asarray(beat_data.get("beatLoudness", []), dtype=np.float64)
        band_loudness = np.asarray(beat_data.get("bandLoudness", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        high_band = np.asarray(beat_data.get("highBand", []), dtype=np.float64)

        if beat_loudness.size < 2 or band_loudness.ndim != 2 or band_loudness.shape[0] < 2:
            return {"beatsLoudness": None}

        mean_total = float(np.mean(beat_loudness))
        if mean_total <= 0:
            return {"beatsLoudness": None}

        # Band dominance ratios
        mean_low = float(np.mean(low_band)) if low_band.size > 0 else 0.0
        mean_high = float(np.mean(high_band)) if high_band.size > 0 else 0.0
        # Mid band is column 1 of bandLoudness (200-4000 Hz)
        mid_band = band_loudness[:, 1] if band_loudness.shape[1] > 1 else np.zeros(band_loudness.shape[0])
        mean_mid = float(np.mean(mid_band))

        kick_dominant_ratio = round(float(np.clip(mean_low / mean_total, 0.0, 1.0)), 4)
        mid_dominant_ratio = round(float(np.clip(mean_mid / mean_total, 0.0, 1.0)), 4)
        high_dominant_ratio = round(float(np.clip(mean_high / mean_total, 0.0, 1.0)), 4)

        beats_per_bar = 4
        low_band_pattern = _build_bar_position_pattern(low_band, beats_per_bar)
        mid_band_pattern = _build_bar_position_pattern(mid_band, beats_per_bar)
        high_band_pattern = _build_bar_position_pattern(high_band, beats_per_bar)
        overall_pattern = _build_bar_position_pattern(beat_loudness, beats_per_bar)

        # Summary stats
        n_beats = beat_loudness.size
        std_total = float(np.std(beat_loudness))
        beat_loudness_variation = round(std_total / mean_total, 4) if mean_total > 0 else 0.0

        result = {
            "beatsLoudness": {
                "kickDominantRatio": kick_dominant_ratio,
                "midDominantRatio": mid_dominant_ratio,
                "highDominantRatio": high_dominant_ratio,
                "patternBeatsPerBar": beats_per_bar,
                "lowBandAccentPattern": low_band_pattern,
                "midBandAccentPattern": mid_band_pattern,
                "highBandAccentPattern": high_band_pattern,
                "overallAccentPattern": overall_pattern,
                "accentPattern": overall_pattern,
                "meanBeatLoudness": round(mean_total, 4),
                "beatLoudnessVariation": beat_loudness_variation,
                "beatCount": int(n_beats),
            }
        }

        # Raw matrix behind debug env var only
        if os.environ.get("ASA_DEBUG_BEATS_LOUDNESS") == "1":
            result["beatsLoudness"]["rawBeatLoudness"] = [round(float(v), 4) for v in beat_loudness]
            result["beatsLoudness"]["rawLowBand"] = [round(float(v), 4) for v in low_band]
            result["beatsLoudness"]["rawHighBand"] = [round(float(v), 4) for v in high_band]

        return result
    except Exception as e:
        print(f"[warn] Beat loudness analysis failed: {e}", file=sys.stderr)
        return {"beatsLoudness": None}

