"""Render the Phase 1 evaluation report as a standalone HTML page.

The HTML report is the milestone-audit deliverable from Track 2 of the depth
plan. It surfaces synthetic-fixture and real-track results side-by-side, marks
skipped real tracks with their reason, and stays self-contained (no external
CSS or JS) so it can be opened directly from `.runtime/reports/`.

Confidence-calibration analytics — "% wrong above threshold X" — are intentionally
deferred to a follow-up; this first render keeps to the data the harness already
produces, plus a clearly-flagged TODO for the calibration sub-report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ASA Phase 1 Accuracy Report — {{ generated_at }}</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #14181d;
      --surface: #1c2229;
      --border: #2a323c;
      --text: #e6ecf2;
      --muted: #95a3b3;
      --pass: #5ad481;
      --fail: #ff6b6b;
      --skip: #f7c948;
      --accent: #6aa9ff;
      --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace;
    }
    * { box-sizing: border-box; }
    html, body { background: var(--bg); color: var(--text); }
    body {
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 32px 24px 64px;
    }
    .wrap { max-width: 1100px; margin: 0 auto; }
    h1 { font-size: 22px; margin: 0 0 4px; }
    h2 { font-size: 17px; margin: 32px 0 12px; color: var(--accent); }
    h3 { font-size: 14px; margin: 16px 0 8px; }
    .meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
    .meta code { font-family: var(--mono); }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .summary-cell {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px 14px;
    }
    .summary-cell .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
    .summary-cell .value { font-size: 22px; font-weight: 600; margin-top: 4px; font-family: var(--mono); }
    .verdict { padding: 10px 14px; border-radius: 6px; font-weight: 600; display: inline-block; }
    .verdict.pass { background: rgba(90, 212, 129, 0.12); color: var(--pass); }
    .verdict.fail { background: rgba(255, 107, 107, 0.14); color: var(--fail); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
    td.mono, code { font-family: var(--mono); font-size: 12px; }
    .status { font-weight: 600; font-family: var(--mono); }
    .status.pass { color: var(--pass); }
    .status.fail { color: var(--fail); }
    .status.skip { color: var(--skip); }
    .fixture-block, .track-block {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 14px 18px;
      margin-bottom: 16px;
    }
    .fixture-block h3, .track-block h3 { margin-top: 0; }
    .skip-note {
      background: rgba(247, 201, 72, 0.08);
      border-left: 3px solid var(--skip);
      padding: 8px 12px;
      margin: 8px 0;
      font-family: var(--mono);
      font-size: 12px;
      color: var(--skip);
    }
    .empty { color: var(--muted); font-style: italic; padding: 12px 0; }
    .footer { color: var(--muted); font-size: 12px; margin-top: 48px; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>ASA Phase 1 Accuracy Report</h1>
      <div class="meta">
        Generated <code>{{ generated_at }}</code> ·
        Manifest <code>{{ manifest_path }}</code> ·
        Runs per fixture: <code>{{ runs_per_fixture }}</code>
        {% if include_real %} · Real-tracks dir: <code>{{ real_tracks_dir }}</code>{% endif %}
      </div>
    </header>

    <section>
      <span class="verdict {% if summary.allPassed %}pass{% else %}fail{% endif %}">
        {% if summary.allPassed %}ALL CHECKS PASSED{% else %}REGRESSIONS DETECTED{% endif %}
      </span>
    </section>

    <section>
      <h2>Summary</h2>
      <div class="summary-grid">
        <div class="summary-cell">
          <div class="label">Synthetic fixtures</div>
          <div class="value">{{ summary.fixtures }}</div>
        </div>
        <div class="summary-cell">
          <div class="label">Real tracks evaluated</div>
          <div class="value">{{ summary.realTracksEvaluated }}</div>
        </div>
        <div class="summary-cell">
          <div class="label">Real tracks skipped</div>
          <div class="value">{{ summary.realTracksSkipped }}</div>
        </div>
        <div class="summary-cell">
          <div class="label">analyze.py failures</div>
          <div class="value">{{ summary.realTracksAnalyzeFailed }}</div>
        </div>
        <div class="summary-cell">
          <div class="label">Checks passed</div>
          <div class="value">{{ summary.checksPassed }}</div>
        </div>
        <div class="summary-cell">
          <div class="label">Checks failed</div>
          <div class="value">{{ summary.checksFailed }}</div>
        </div>
      </div>
    </section>

    <section>
      <h2>Synthetic fixtures</h2>
      {% for fixture in fixtures %}
        <div class="fixture-block">
          <h3>
            <code>{{ fixture.id }}</code>
            <span class="status {% if fixture.allPassed %}pass{% else %}fail{% endif %}">
              {{ "PASS" if fixture.allPassed else "FAIL" }}
            </span>
          </h3>
          <table>
            <thead>
              <tr><th>Check</th><th>Result</th><th>Message</th></tr>
            </thead>
            <tbody>
              {% for check in fixture.checks %}
                <tr>
                  <td class="mono">{{ check.name }}</td>
                  <td><span class="status {% if check.passed %}pass{% else %}fail{% endif %}">
                    {{ "PASS" if check.passed else "FAIL" }}
                  </span></td>
                  <td class="mono">{{ check.message }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      {% endfor %}
    </section>

    {% if include_real %}
    <section>
      <h2>Real tracks</h2>
      {% if real_tracks %}
        {% for track in real_tracks %}
          <div class="track-block">
            <h3>
              <code>{{ track.id }}</code>
              {% if track.category %}<span class="meta">· {{ track.category }}</span>{% endif %}
              <span class="status
                {% if track.status == 'evaluated' and track.allPassed %}pass
                {% elif track.status == 'skipped_audio_missing' %}skip
                {% else %}fail{% endif %}">
                {% if track.status == 'evaluated' %}
                  {{ "PASS" if track.allPassed else "FAIL" }}
                {% elif track.status == 'skipped_audio_missing' %}
                  SKIP
                {% else %}
                  ANALYZE FAILED
                {% endif %}
              </span>
            </h3>
            {% if track.description %}<p class="meta">{{ track.description }}</p>{% endif %}
            {% if track.skipReason %}
              <div class="skip-note">{{ track.skipReason }}</div>
            {% endif %}
            {% if track.checks %}
              <table>
                <thead>
                  <tr><th>Check</th><th>Result</th><th>Message</th></tr>
                </thead>
                <tbody>
                  {% for check in track.checks %}
                    <tr>
                      <td class="mono">{{ check.name }}</td>
                      <td><span class="status {% if check.passed %}pass{% else %}fail{% endif %}">
                        {{ "PASS" if check.passed else "FAIL" }}
                      </span></td>
                      <td class="mono">{{ check.message }}</td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            {% endif %}
          </div>
        {% endfor %}
      {% else %}
        <p class="empty">No real-track entries in the manifest yet. See <code>bench_tracks/README.md</code> for how to register tracks.</p>
      {% endif %}
    </section>
    {% endif %}

    <footer class="footer">
      Phase 1 accuracy bench · {{ now_local }} ·
      Confidence-calibration sub-report (% wrong above threshold X) is a planned follow-up.
    </footer>
  </div>
</body>
</html>
"""


def render_html_report(report: dict[str, Any], output_path: Path) -> Path:
    """Render an evaluation report dict into a standalone HTML file.

    `report` is the dict returned by `run_phase1_evaluation`. `output_path` is
    the absolute path to write — its parent is created if missing.
    """
    env = jinja2.Environment(
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.from_string(_TEMPLATE)
    html = template.render(
        generated_at=report.get("generatedAt", ""),
        manifest_path=report.get("manifestPath", ""),
        runs_per_fixture=report.get("runsPerFixture", 1),
        include_real=bool(report.get("includeReal", False)),
        real_tracks_dir=report.get("realTracksDir") or "",
        summary=report.get("summary", {}),
        fixtures=report.get("fixtures", []),
        real_tracks=report.get("realTracks", []),
        now_local=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def default_html_report_path(reports_dir: Path) -> Path:
    """Return the conventional dated HTML report path under `reports_dir`."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return reports_dir / f"accuracy_{stamp}.html"
