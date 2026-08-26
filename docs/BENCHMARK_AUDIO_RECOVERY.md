# Benchmark audio recovery record

Audited 2026-08-26 before local disk cleanup. Benchmark audio is intentionally
not committed because of size and redistribution/licensing constraints.

## GiantSteps Key and Tempo

Recovery is automated by `apps/backend/scripts/fetch_giantsteps.py`:

```bash
cd apps/backend
./scripts/bootstrap.sh
./venv/bin/python scripts/fetch_giantsteps.py
./venv/bin/python scripts/fetch_giantsteps.py --verify-only
```

The fetcher clones the upstream repositories, downloads Beatport previews from
the primary or JKU backup host, and checks every MP3 against the upstream MD5.

| Subset | Local MP3s | Annotations | Upstream repository | Audited upstream commit |
| --- | ---: | ---: | --- | --- |
| Key | 604 | 604 | `GiantSteps/giantsteps-key-dataset` | `6bcd492c825ac9b8597bc650a5f6fd18b6c43d2b` |
| Tempo | 664 | 664 | `GiantSteps/giantsteps-tempo-dataset` | `d51ab2422e76abacfaa86616a57054bc222ec9fd` |

The exact audio identities and MD5 values live in each upstream repository's
`md5/` directory. Preview-host links are old and may rot; re-run the fetcher to
use its fallback host and verify what remains available.

## GTZAN and GTZAN-Rhythm

The local copy contains all 1,000 GTZAN WAV clips (10 genres by 100 clips).
`docs/GTZAN_AUDIO_SHA256.txt` records the SHA-256 of every local WAV so a future
copy can be checked against the exact material used by ASA.

There are 999 local GTZAN-Rhythm `.beats` annotations. The only WAV without a
matching annotation is `reggae.00086`. The annotations can be reacquired from
`TempoBeatDownbeat/gtzan_tempo_beat` and the manifest can be regenerated:

```bash
cd apps/backend
./venv/bin/python scripts/build_beat_manifest.py \
  --root tests/fixtures/beat_tracks \
  --out tests/fixtures/beat_eval_manifest.gtzan.json
```

The old official GTZAN audio host is no longer dependable, and current
`mirdata` supports downloading the annotations and a mini audio subset rather
than the complete audio collection. The hash inventory is an identification
record, not a backup of the audio bytes.

## ASA electronic beat slice

The slice contains 18 copied GiantSteps previews. No hand-made ASA beat
annotations exist yet, so there is no irreplaceable annotation work to save.
The selection algorithm is in `apps/backend/scripts/stage_asa_beat_slice.py`.
This is the exact audited selection:

| Clip ID | Family | Beatport genre |
| --- | --- | --- |
| `1034795.LOFI` | house | house |
| `1198571.LOFI` | house | deep-house |
| `1004923.LOFI` | house | tech-house |
| `1007941.LOFI` | house | electro-house |
| `1017921.LOFI` | house | progressive-house |
| `1026478.LOFI` | techno | techno |
| `1041574.LOFI` | techno | techno |
| `1193612.LOFI` | techno | techno |
| `1009960.LOFI` | techno | minimal |
| `1174239.LOFI` | techno | hardcore-hard-techno |
| `1052744.LOFI` | dnb | drum-and-bass |
| `1068430.LOFI` | dnb | drum-and-bass |
| `1075123.LOFI` | dnb | drum-and-bass |
| `1120171.LOFI` | dnb | drum-and-bass |
| `10089.LOFI` | garage substitute | breaks |
| `1084996.LOFI` | garage substitute | breaks |
| `1092771.LOFI` | garage substitute | dubstep |
| `1171800.LOFI` | garage substitute | dubstep |

The original local `SELECTION.tsv` had SHA-256
`53dfbbc80eb04ec587e9935e80cb4876503c4fc906661df870169bfeccd6af7e`.
