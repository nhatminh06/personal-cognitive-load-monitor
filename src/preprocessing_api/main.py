"""FastAPI application for cognitive load prediction."""

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from preprocessing_api.schemas import PredictionRequest, PredictionResponse
from preprocessing_api.service import calculate_cognitive_load

app = FastAPI(
    title="Personal Cognitive Load Monitoring API",
    description="API for predicting cognitive load based on focus, distraction, tasks, and deadlines",
    version="1.0.0",
)


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "cognitive-load-monitor"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return an empty favicon response to avoid 404 in logs."""
    return Response(status_code=204)


@app.get("/robots.txt", include_in_schema=False)
def robots():
    """Return a minimal robots.txt to avoid 404 in logs."""
    return Response(content="User-agent: *\nDisallow:\n", media_type="text/plain")


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    """
    Predict cognitive load level based on input metrics.

    Args:
        request: PredictionRequest containing focus_minutes, distraction_minutes,
                tasks_due, and hours_to_deadline

    Returns:
        PredictionResponse with cognitive_load_level
    """
    cognitive_load_level = calculate_cognitive_load(request)
    return PredictionResponse(cognitive_load_level=cognitive_load_level)


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

