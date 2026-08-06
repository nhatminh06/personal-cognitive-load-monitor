"""Generate synthetic sample data for development, testing, and DVC/CI training.

All fields are synthetically generated, not collected from real users. See
docs/data-card.md for the full generation method and its limitations.
"""

import csv
import random
import sys
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from preprocessing_api.schemas import PredictionRequest  # noqa: E402
from preprocessing_api.service import calculate_cognitive_load  # noqa: E402

# Used only when the caller does not pass reference_date. datetime.now() makes
# the "date" column (a descriptive field, not a model feature) change on every
# run, which is fine for ad-hoc local use but breaks DVC reproducibility: two
# `dvc repro` runs on different days would report the raw dataset as changed
# even with an identical seed. The DVC pipeline and CI always pass an explicit
# reference_date (from params.yaml) so pipeline runs are byte-for-byte stable.
_DEFAULT_REFERENCE_DATE = datetime.now()


def generate_sample_data(
    n_samples: int = 100,
    output_path: Path = None,
    seed: int = 42,
    reference_date: str | date_cls | None = None,
):
    """
    Generate synthetic cognitive load monitoring data.

    Args:
        n_samples: Number of samples to generate
        output_path: Path to save the CSV file. Defaults to data/raw/sample_data.csv
        seed: Random seed for reproducibility
        reference_date: Fixed date (YYYY-MM-DD string or date) that the "date"
            column counts backward from. Pass an explicit value for
            reproducible pipeline runs; omit only for ad-hoc local generation
            where an approximate recent date is acceptable.
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "raw" / "sample_data.csv"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if reference_date is None:
        reference_datetime = _DEFAULT_REFERENCE_DATE
    elif isinstance(reference_date, str):
        reference_datetime = datetime.strptime(reference_date, "%Y-%m-%d")
    else:
        reference_datetime = datetime.combine(reference_date, datetime.min.time())

    random.seed(seed)

    # Generate realistic data
    data = []
    for i in range(n_samples):
        # Simulate a day's worth of monitoring
        date = reference_datetime - timedelta(days=random.randint(0, 30))

        # Focus and distraction minutes (should sum to a reasonable work day)
        total_minutes = random.randint(240, 480)  # 4-8 hours
        focus_minutes = random.randint(int(total_minutes * 0.3), int(total_minutes * 0.9))
        distraction_minutes = total_minutes - focus_minutes

        # Tasks due (0-10)
        tasks_due = random.randint(0, 10)

        # Hours to deadline (0-168 hours = 0-7 days)
        hours_to_deadline = random.uniform(0.5, 168.0)

        # Ground-truth label uses the same rule engine as the API's fallback path
        # (preprocessing_api.service.calculate_cognitive_load) so there is one
        # source of truth for the scoring formula.
        cognitive_load_level = calculate_cognitive_load(
            PredictionRequest(
                focus_minutes=focus_minutes,
                distraction_minutes=distraction_minutes,
                tasks_due=tasks_due,
                hours_to_deadline=round(hours_to_deadline, 4),
            )
        ).value

        data.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "focus_minutes": focus_minutes,
                "distraction_minutes": distraction_minutes,
                "tasks_due": tasks_due,
                "hours_to_deadline": round(hours_to_deadline, 2),
                "cognitive_load_level": cognitive_load_level,
            }
        )

    # Write to CSV
    fieldnames = [
        "date",
        "focus_minutes",
        "distraction_minutes",
        "tasks_due",
        "hours_to_deadline",
        "cognitive_load_level",
    ]
    with open(output_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"Generated {n_samples} samples and saved to {output_path}")
    return output_path


def _load_params() -> dict:
    """Read params.yaml's data: section, if present, for reproducible CLI runs."""

    import yaml

    params_path = Path(__file__).resolve().parent.parent / "params.yaml"
    if not params_path.exists():
        return {}
    params = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    return params.get("data", {})


if __name__ == "__main__":
    _params = _load_params()
    generate_sample_data(
        n_samples=_params.get("n_samples", 500),
        seed=_params.get("seed", 42),
        reference_date=_params.get("reference_date"),
    )

