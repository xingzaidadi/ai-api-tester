#!/usr/bin/env python3
"""Generate HTML dashboard from historical test reports."""

import sys
import io
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def parse_date_from_path(path: Path) -> str:
    """Extract date string from a directory path like '2024-06-01-run1'.

    Walks up parent directories looking for a name that starts with a
    YYYY-MM-DD pattern.  Returns the date portion or the directory name
    as-is when no date pattern is found.
    """
    for parent in [path.parent, path.parent.parent]:
        name = parent.name
        if len(name) >= 10 and name[4] == "-" and name[7] == "-":
            return name[:10]
    return path.parent.name


def load_reports(output_dir: Path):
    """Recursively find and parse all report.json files under *output_dir*.

    Returns a list of dicts, each augmented with ``_date`` and ``_dir``
    keys derived from the file's location on disk.
    """
    reports = []
    for report_path in sorted(output_dir.rglob("report.json")):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            report["_date"] = parse_date_from_path(report_path)
            report["_dir"] = report_path.parent

            # Attempt to load a sibling analysis.json
            analysis_path = report_path.parent / "analysis.json"
            if analysis_path.exists():
                with open(analysis_path, "r", encoding="utf-8") as f:
                    report["_analysis"] = json.load(f)

            reports.append(report)
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"Warning: skipping {report_path}: {exc}", file=sys.stderr)
    return reports


def build_chart_data(reports: list) -> dict:
    """Aggregate *reports* into structures consumed by Chart.js."""

    # ---- summary ----------------------------------------------------------
    total_reports = len(reports)
    total_cases = sum(r.get("total", 0) for r in reports)
    total_passed = sum(r.get("passed", 0) for r in reports)
    apis_tested = len({r.get("api", "unknown") for r in reports})
    overall_pass_rate = round(total_passed / total_cases * 100, 1) if total_cases else 0

    # ---- pass-rate trend (per date) ---------------------------------------
    date_stats = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in reports:
        d = r["_date"]
        date_stats[d]["total"] += r.get("total", 0)
        date_stats[d]["passed"] += r.get("passed", 0)

    sorted_dates = sorted(date_stats.keys())
    trend_dates = sorted_dates
    trend_rates = [
        round(date_stats[d]["passed"] / date_stats[d]["total"] * 100, 1)
        if date_stats[d]["total"] else 0
        for d in sorted_dates
    ]

    # ---- dimension coverage -----------------------------------------------
    dim_pass = defaultdict(int)
    dim_fail = defaultdict(int)
    for r in reports:
        for case in r.get("cases", []):
            dim = case.get("dimension", "unknown")
            if case.get("status") == "pass":
                dim_pass[dim] += 1
            else:
                dim_fail[dim] += 1

    all_dims = sorted(set(dim_pass.keys()) | set(dim_fail.keys()))
    dim_labels = all_dims
    dim_pass_values = [dim_pass[d] for d in all_dims]
    dim_fail_values = [dim_fail[d] for d in all_dims]

    # ---- failure classification -------------------------------------------
    has_analysis = any("_analysis" in r for r in reports)
    if has_analysis:
        classification_counts = defaultdict(int)
        for r in reports:
            analysis = r.get("_analysis")
            if analysis and analysis.get("findings"):
                for finding in analysis["findings"]:
                    cls = finding.get("classification", "unknown")
                    classification_counts[cls] += 1
        class_labels = list(classification_counts.keys()) or ["No data"]
        class_values = list(classification_counts.values()) or [0]
    else:
        class_labels = ["pass", "fail", "error"]
        class_values = [
            total_passed,
            sum(r.get("failed", 0) for r in reports),
            sum(r.get("errored", 0) for r in reports),
        ]

    # ---- high-risk APIs ---------------------------------------------------
    api_stats = defaultdict(lambda: {
        "total": 0, "failed": 0, "last_date": ""
    })
    for r in reports:
        api = r.get("api", "unknown")
        api_stats[api]["total"] += r.get("total", 0)
        api_stats[api]["failed"] += r.get("failed", 0) + r.get("errored", 0)
        if r["_date"] > api_stats[api]["last_date"]:
            api_stats[api]["last_date"] = r["_date"]

    high_risk = sorted(
        api_stats.items(),
        key=lambda x: (x[1]["failed"] / x[1]["total"] if x[1]["total"] else 0),
        reverse=True,
    )[:10]

    high_risk_rows = []
    for api, stats in high_risk:
        rate = round(stats["failed"] / stats["total"] * 100, 1) if stats["total"] else 0
        high_risk_rows.append({
            "api": api,
            "total": stats["total"],
            "failed": stats["failed"],
            "rate": rate,
            "last_tested": stats["last_date"],
        })

    return {
        "summary": {
            "total_reports": total_reports,
            "total_cases": total_cases,
            "overall_pass_rate": overall_pass_rate,
            "apis_tested": apis_tested,
        },
        "trend": {
            "dates": trend_dates,
            "rates": trend_rates,
        },
        "dimensions": {
            "labels": dim_labels,
            "pass": dim_pass_values,
            "fail": dim_fail_values,
        },
        "classification": {
            "labels": class_labels,
            "values": class_values,
        },
        "high_risk": high_risk_rows,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI API Tester - Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:#f0f2f5;color:#1d1d1f;line-height:1.6}
header{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);color:#fff;padding:28px 40px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
header h1{font-size:1.6rem;font-weight:700;letter-spacing:-0.02em}
header .meta{font-size:0.82rem;opacity:0.7}
.dashboard{max-width:1280px;margin:0 auto;padding:28px 20px 60px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px;margin-bottom:28px}
.card{background:#fff;border-radius:12px;padding:24px 28px;box-shadow:0 1px 3px rgba(0,0,0,0.08);text-align:center}
.card .value{font-size:2rem;font-weight:700;color:#0f3460;margin-bottom:4px}
.card .label{font-size:0.85rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:28px}
@media(max-width:860px){.charts{grid-template-columns:1fr}}
.chart-box{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.chart-box h2{font-size:1rem;font-weight:600;margin-bottom:16px;color:#374151}
.chart-box.full-width{grid-column:1/-1}
canvas{width:100%!important;max-height:340px}
.table-section{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.table-section h2{font-size:1rem;font-weight:600;margin-bottom:16px;color:#374151}
table{width:100%;border-collapse:collapse;font-size:0.9rem}
th{text-align:left;padding:10px 14px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600;text-transform:uppercase;font-size:0.78rem;letter-spacing:0.03em}
td{padding:10px 14px;border-bottom:1px solid #f3f4f6}
tr:hover td{background:#f9fafb}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.78rem;font-weight:600}
.badge-high{background:#fef2f2;color:#dc2626}
.badge-med{background:#fffbeb;color:#d97706}
.badge-low{background:#f0fdf4;color:#16a34a}
.empty-state{text-align:center;padding:48px 20px;color:#9ca3af}
</style>
</head>
<body>
<header>
  <h1>AI API Tester &mdash; Dashboard</h1>
  <span class="meta">Generated __TIMESTAMP__</span>
</header>
<div class="dashboard">

  <!-- Summary cards -->
  <div class="cards">
    <div class="card"><div class="value" id="v-reports">-</div><div class="label">Total Reports</div></div>
    <div class="card"><div class="value" id="v-cases">-</div><div class="label">Total Cases</div></div>
    <div class="card"><div class="value" id="v-rate">-</div><div class="label">Overall Pass Rate</div></div>
    <div class="card"><div class="value" id="v-apis">-</div><div class="label">APIs Tested</div></div>
  </div>

  <!-- Charts row -->
  <div class="charts">
    <div class="chart-box full-width">
      <h2>Pass Rate Trend</h2>
      <canvas id="trendChart"></canvas>
    </div>
    <div class="chart-box">
      <h2>Dimension Coverage</h2>
      <canvas id="dimChart"></canvas>
    </div>
    <div class="chart-box">
      <h2>Failure Classification</h2>
      <canvas id="classChart"></canvas>
    </div>
  </div>

  <!-- High-risk table -->
  <div class="table-section">
    <h2>High Risk APIs</h2>
    <div id="risk-table"></div>
  </div>
</div>

<script>
const D = __CHART_DATA__;

// Summary cards
document.getElementById("v-reports").textContent = D.summary.total_reports;
document.getElementById("v-cases").textContent = D.summary.total_cases.toLocaleString();
document.getElementById("v-rate").textContent = D.summary.overall_pass_rate + "%";
document.getElementById("v-apis").textContent = D.summary.apis_tested;

// Colour helpers
const GREEN = "rgba(22,163,74,0.85)";
const GREEN_BG = "rgba(22,163,74,0.15)";
const RED = "rgba(220,38,38,0.85)";
const BLUE = "rgba(15,52,96,0.9)";
const BLUE_BG = "rgba(15,52,96,0.12)";
const DOUGHNUT_COLORS = ["#16a34a","#dc2626","#d97706","#6366f1","#0ea5e9","#f43f5e","#8b5cf6","#14b8a6"];

// --- Trend chart ---
if (D.trend.dates.length) {
  new Chart(document.getElementById("trendChart"), {
    type: "line",
    data: {
      labels: D.trend.dates,
      datasets: [{
        label: "Pass Rate (%)",
        data: D.trend.rates,
        borderColor: BLUE,
        backgroundColor: BLUE_BG,
        fill: true,
        tension: 0.35,
        pointRadius: 4,
        pointBackgroundColor: BLUE
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: v => v + "%" }, grid: { color: "#f3f4f6" } },
        x: { grid: { display: false } }
      }
    }
  });
}

// --- Dimension chart ---
if (D.dimensions.labels.length) {
  new Chart(document.getElementById("dimChart"), {
    type: "bar",
    data: {
      labels: D.dimensions.labels,
      datasets: [
        { label: "Pass", data: D.dimensions.pass, backgroundColor: GREEN },
        { label: "Fail", data: D.dimensions.fail, backgroundColor: RED }
      ]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { stacked: true, grid: { color: "#f3f4f6" } },
        y: { stacked: true, grid: { display: false } }
      }
    }
  });
}

// --- Classification chart ---
if (D.classification.values.some(v => v > 0)) {
  new Chart(document.getElementById("classChart"), {
    type: "doughnut",
    data: {
      labels: D.classification.labels,
      datasets: [{
        data: D.classification.values,
        backgroundColor: DOUGHNUT_COLORS.slice(0, D.classification.labels.length),
        borderWidth: 2,
        borderColor: "#fff"
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "bottom" }
      }
    }
  });
}

// --- High-risk table ---
(function() {
  var container = document.getElementById("risk-table");
  var rows = D.high_risk;
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">No API data available.</div>';
    return;
  }
  function badge(rate) {
    if (rate >= 50) return '<span class="badge badge-high">' + rate + '%</span>';
    if (rate >= 20) return '<span class="badge badge-med">' + rate + '%</span>';
    return '<span class="badge badge-low">' + rate + '%</span>';
  }
  var html = '<table><thead><tr><th>API</th><th>Total Cases</th><th>Failed</th><th>Failure Rate</th><th>Last Tested</th></tr></thead><tbody>';
  rows.forEach(function(r) {
    html += '<tr><td><strong>' + r.api + '</strong></td><td>' + r.total + '</td><td>' + r.failed + '</td><td>' + badge(r.rate) + '</td><td>' + r.last_tested + '</td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
})();
</script>
</body>
</html>"""


def render_html(chart_data: dict) -> str:
    """Inject *chart_data* into the HTML template and return the result."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.replace("__CHART_DATA__", json.dumps(chart_data, ensure_ascii=False))
    html = html.replace("__TIMESTAMP__", timestamp)
    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generate an HTML dashboard from historical test reports."
    )
    parser.add_argument(
        "output_dir",
        help="Path to test-output/ directory containing historical report.json files",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output HTML file path (default: {output_dir}/dashboard.html)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        print(f"Error: directory not found: {output_dir}", file=sys.stderr)
        sys.exit(1)

    reports = load_reports(output_dir)
    if not reports:
        print("No report.json files found under: " + str(output_dir), file=sys.stderr)
        sys.exit(1)

    chart_data = build_chart_data(reports)
    html = render_html(chart_data)

    output_path = Path(args.output) if args.output else output_dir / "dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"Reports processed: {len(reports)}")
    print(f"Dashboard generated: {output_path}")


if __name__ == "__main__":
    main()
