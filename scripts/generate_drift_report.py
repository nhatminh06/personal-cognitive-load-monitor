"""Generate a genuine Evidently data-drift report and machine-readable summary."""

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


def main() -> None:
    args = parse_args()
    reference_path = Path(args.reference)
    current_path = Path(args.current)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference = pd.read_csv(reference_path)
    current = pd.read_csv(current_path)

    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset

        report = Report(metrics=[DataDriftPreset()])
        result = report.run(reference_data=reference, current_data=current)
        result.save_html(str(output_path))
    except ImportError:
        from evidently.metric_preset import DataDriftPreset as LegacyDataDriftPreset
        from evidently.report import Report as LegacyReport

        report = LegacyReport(metrics=[LegacyDataDriftPreset()])
        report.run(reference_data=reference, current_data=current)
        report.save_html(str(output_path))
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    print(f"Wrote drift report to {output_path}")


if __name__ == "__main__":
    main()
