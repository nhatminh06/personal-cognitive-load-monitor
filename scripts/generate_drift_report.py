"""Generate an Evidently data drift dashboard.

The script uses Evidently when available. If the installed Evidently API changes,
it still writes a simple HTML drift summary so the pipeline has a stable artifact.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default="data/processed/train.csv")
    parser.add_argument("--current", default="data/processed/test.csv")
    parser.add_argument("--output", default="reports/evidently/data_drift.html")
    return parser.parse_args()


def fallback_report(reference: pd.DataFrame, current: pd.DataFrame, output: Path) -> None:
    rows = []
    for column in reference.select_dtypes(include="number").columns:
        ref_mean = reference[column].mean()
        cur_mean = current[column].mean()
        diff = cur_mean - ref_mean
        rows.append(
            f"<tr><td>{column}</td><td>{ref_mean:.4f}</td><td>{cur_mean:.4f}</td><td>{diff:.4f}</td></tr>"
        )
    html = """
    <html><head><title>Cognitive Load Drift Report</title></head><body>
    <h1>Data Drift Dashboard</h1>
    <p>Fallback report generated when Evidently dashboard rendering is unavailable.</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Feature</th><th>Reference Mean</th><th>Current Mean</th><th>Difference</th></tr>
      {rows}
    </table>
    </body></html>
    """.format(rows="\n".join(rows))
    output.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    reference_path = Path(args.reference)
    current_path = Path(args.current)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference = pd.read_csv(reference_path)
    current = pd.read_csv(current_path)

    try:
        try:
            # Evidently >=0.4.16 (this project's pin) resolves to the current
            # major version today, which moved these under evidently/evidently.presets
            # and made Report.run() return the result instead of mutating in place.
            from evidently import Report
            from evidently.presets import DataDriftPreset

            report = Report(metrics=[DataDriftPreset()])
            result = report.run(reference_data=reference, current_data=current)
            result.save_html(str(output_path))
        except ImportError:
            # Older Evidently (<0.4) API, kept for pinned older installs.
            from evidently.metric_preset import DataDriftPreset as LegacyDataDriftPreset
            from evidently.report import Report as LegacyReport

            report = LegacyReport(metrics=[LegacyDataDriftPreset()])
            report.run(reference_data=reference, current_data=current)
            report.save_html(str(output_path))
    except Exception as exc:
        print(f"WARNING: Evidently rendering failed, writing fallback dashboard: {exc}")
        fallback_report(reference, current, output_path)

    print(f"Wrote drift report to {output_path}")


if __name__ == "__main__":
    main()
