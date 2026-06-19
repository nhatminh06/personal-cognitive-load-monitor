"""Generate sample data for development and testing."""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


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

        # Calculate expected cognitive load (for ground truth)
        # This matches the logic in service.py
        total_time = focus_minutes + distraction_minutes
        if total_time == 0:
            focus_ratio = 0.0
            distraction_ratio = 0.0
        else:
            focus_ratio = focus_minutes / total_time
            distraction_ratio = distraction_minutes / total_time

        task_pressure = tasks_due * 0.2

        if hours_to_deadline <= 24:
            deadline_pressure = 1.0
        elif hours_to_deadline <= 72:
            deadline_pressure = 0.5
        else:
            deadline_pressure = 0.2

        cognitive_load_score = (
            (1.0 - focus_ratio) * 0.3
            + task_pressure * 0.2
            + deadline_pressure * 0.3
            + distraction_ratio * 0.2
        )

        if cognitive_load_score < 0.4:
            cognitive_load_level = "LOW"
        elif cognitive_load_score < 0.7:
            cognitive_load_level = "MEDIUM"
        else:
            cognitive_load_level = "HIGH"

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

