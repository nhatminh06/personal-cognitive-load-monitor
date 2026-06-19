"""Business logic for cognitive load calculation."""

from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest


def calculate_cognitive_load(request: PredictionRequest) -> CognitiveLoadLevel:
    """
    Calculate cognitive load level based on focus, distraction, tasks, and deadline.

    Args:
        request: PredictionRequest containing focus_minutes, distraction_minutes,
                tasks_due, and hours_to_deadline

    Returns:
        CognitiveLoadLevel: LOW, MEDIUM, or HIGH
    """
    # Calculate focus ratio (focus time / total time)
    total_time = request.focus_minutes + request.distraction_minutes
    if total_time == 0:
        focus_ratio = 0.0
    else:
        focus_ratio = request.focus_minutes / total_time

    # Calculate task pressure (more tasks = higher pressure)
    task_pressure = request.tasks_due * 0.2

    # Calculate deadline pressure (closer deadline = higher pressure)
    # Normalize: 0-24 hours = high pressure, 24-72 hours = medium, 72+ = low
    if request.hours_to_deadline <= 24:
        deadline_pressure = 1.0
    elif request.hours_to_deadline <= 72:
        deadline_pressure = 0.5
    else:
        deadline_pressure = 0.2

    # Calculate distraction impact (higher distraction = higher load)
    if total_time == 0:
        distraction_ratio = 0.0
    else:
        distraction_ratio = request.distraction_minutes / total_time

    # Combine factors into a cognitive load score
    # Lower focus ratio = higher load
    # Higher task pressure = higher load
    # Higher deadline pressure = higher load
    # Higher distraction = higher load
    cognitive_load_score = (
        (1.0 - focus_ratio) * 0.3
        + task_pressure * 0.2
        + deadline_pressure * 0.3
        + distraction_ratio * 0.2
    )

    # Map score to cognitive load level
    if cognitive_load_score < 0.4:
        return CognitiveLoadLevel.LOW
    elif cognitive_load_score < 0.7:
        return CognitiveLoadLevel.MEDIUM
    else:
        return CognitiveLoadLevel.HIGH

