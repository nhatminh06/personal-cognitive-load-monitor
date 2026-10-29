"""Isolated FastAPI application with strict focus-model startup validation."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from preprocessing_api.security import SecurityMiddleware

from .api import get_focus_runtime, reset_focus_runtime, router


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_focus_runtime()  # Fail process startup before accepting inference.
    yield
    reset_focus_runtime()


app = FastAPI(
    title="CogniFlow Local Focus Inference",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(SecurityMiddleware)
app.include_router(router)
