"""Generate sample data for development and testing."""

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from preprocessing_api.schemas import PredictionRequest  # noqa: E402
from preprocessing_api.service import calculate_cognitive_load  # noqa: E402


def generate_sample_data(n_samples: int = 100, output_path: Path = None, seed: int = 42):
    """
    Generate sample cognitive load monitoring data.

    Args:
        n_samples: Number of samples to generate
        output_path: Path to save the CSV file. Defaults to data/raw/sample_data.csv
        seed: Random seed for reproducibility
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "raw" / "sample_data.csv"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    # Generate realistic data
    data = []
    for i in range(n_samples):
        # Simulate a day's worth of monitoring
        date = datetime.now() - timedelta(days=random.randint(0, 30))

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


if __name__ == "__main__":
    generate_sample_data(n_samples=500)

