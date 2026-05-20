"""Render a beat_evaluation.py report dict into a standalone HTML page.

Research-only companion to beat_evaluation.py; forks the Jinja2/dark-theme
pattern of phase1_report_html.py. Best-effort — the JSON report is the source
of truth.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2

_METRIC_COLUMNS = [
    ("beatF1", "Beat F1"),
    ("beatCMLt", "CMLt"),
    ("beatAMLt", "AMLt"),
    ("downbeatF1Strict", "Downbeat F1 (strict)"),
    ("downbeatF1Tolerant", "Downbeat F1 (phase-tol)"),
    ("tempoAcc1", "Tempo acc1"),
    ("tempoAcc2", "Tempo acc2"),
]

_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Beat measurement gate</title>
<style>
 body{background:#0b0d12;color:#e6e9ef;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;}
 h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:1.8rem;color:#9fb4d6}
 table{border-collapse:collapse;margin:.6rem 0;width:100%}
 th,td{border:1px solid #232a36;padding:.35rem .55rem;text-align:right}
 th:first-child,td:first-child{text-align:left}
 .verdict{padding:.7rem 1rem;border-radius:8px;font-weight:600;display:inline-block}
 .adopt_pending_asa_slice{background:#143d2a;color:#7ee0a8}
 .keep_heuristic{background:#3d2a14;color:#e0b87e}
 .underpowered,.pending_beat_this{background:#2a2f3d;color:#9fb4d6}
 .muted{color:#7c8aa0}
</style></head><body>
<h1>Beat / downbeat measurement gate</h1>
<p class="muted">{{ generated_at }} · dataset: {{ dataset_name }} · metrics: <b>{{ metrics_backend }}</b>
 · meter source: {{ "annotated" if use_annotated_meter else "ASA-detected (product-faithful)" }}</p>
<p><span class="verdict {{ gate.productRecommendation }}">VERDICT: {{ gate.productRecommendation }}</span>
 &nbsp; downbeat gain (beat_this − best non-neural) = <b>{{ gate.downbeatGain }}</b> (bar: ≥ {{ gate.adoptMargin }})
 &nbsp; on {{ gate.asaRelevantClipCount }} asaRelevant clips</p>

<h2>Method summary — asaRelevant subset (the pass-bar surface)</h2>
{{ asa_table }}
<h2>Method summary — full set (context)</h2>
{{ full_table }}

<h2>Meter detection ({{ meter.clips }} clips)</h2>
<p>exact-match rate <b>{{ meter.exactMatchRate }}</b> · non-4/4 exact-match
 <b>{{ meter.nonFourFourExactMatchRate }}</b> over {{ meter.nonFourFourClips }} non-4/4 clips</p>

<h2>Per-genre downbeat F1 (strict)</h2>
{{ genre_table }}
<p class="muted">Research-only. Source of truth: {{ report_path }}</p>
</body></html>"""


def _method_table(summaries: dict[str, Any]) -> str:
    head = "<tr><th>method</th><th>clips</th>" + "".join(f"<th>{label}</th>" for _, label in _METRIC_COLUMNS) + "</tr>"
    rows = [head]
    for method, summary in summaries.items():
        cells = "".join(f"<td>{_fmt(summary.get(key))}</td>" for key, _ in _METRIC_COLUMNS)
        rows.append(f"<tr><td>{method}</td><td>{summary.get('clipsScored', 0)}</td>{cells}</tr>")
    return f"<table>{''.join(rows)}</table>"


def _genre_table(report: dict[str, Any]) -> str:
    methods = report.get("config", {}).get("methods", [])
    by_genre: dict[str, dict[str, list[float]]] = {}
    for clip in report.get("clips", []):
        if clip.get("status") != "evaluated":
            continue
        genre = clip.get("genre") or "?"
        for method, block in clip.get("methods", {}).items():
            metrics = block.get("metrics")
            if metrics and metrics.get("downbeatF1Strict") is not None:
                by_genre.setdefault(genre, {}).setdefault(method, []).append(metrics["downbeatF1Strict"])
    head = "<tr><th>genre</th>" + "".join(f"<th>{m}</th>" for m in methods) + "</tr>"
    rows = [head]
    for genre in sorted(by_genre):
        cells = "".join(
            f"<td>{_fmt(_avg(by_genre[genre].get(m)))}</td>" for m in methods
        )
        rows.append(f"<tr><td>{genre}</td>{cells}</tr>")
    return f"<table>{''.join(rows)}</table>"


def _avg(values: list[float] | None) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _fmt(value: Any) -> str:
    return "—" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))


def render_beat_report(report: dict[str, Any], output_path: Path) -> Path:
    env = jinja2.Environment(autoescape=True, trim_blocks=True, lstrip_blocks=True)
    html = env.from_string(_TEMPLATE).render(
        generated_at=report.get("generatedAt", ""),
        dataset_name=report.get("datasetName", ""),
        metrics_backend=report.get("metricsBackend", ""),
        use_annotated_meter=report.get("config", {}).get("useAnnotatedMeter", False),
        gate=report.get("gate", {}),
        meter=report.get("meterDetection", {}),
        asa_table=_method_table(report.get("methodSummariesAsaRelevant", {})),
        full_table=_method_table(report.get("methodSummariesFull", {})),
        genre_table=_genre_table(report),
        report_path=report.get("reportPath", ""),
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def default_html_report_path(reports_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return Path(reports_dir) / f"beat_eval_{stamp}.html"
