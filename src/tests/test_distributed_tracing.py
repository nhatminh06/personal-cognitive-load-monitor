"""Focused W3C propagation checks for the API-to-KServe HTTP boundary."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_httpx_injects_traceparent_and_creates_child_span() -> None:
    provider, exporter = _provider()
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            captured["traceparent"] = self.headers.get("traceparent")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, format, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    instrumentor = HTTPXClientInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        tracer = provider.get_tracer(__name__)
        with tracer.start_as_current_span("api-request") as parent:
            parent_context = parent.get_span_context()

            async def request() -> None:
                async with httpx.AsyncClient(trust_env=False) as client:
                    url = f"http://127.0.0.1:{server.server_port}/predict"
                    assert (await client.get(url)).status_code == 200

            asyncio.run(request())
    finally:
        instrumentor.uninstrument()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    spans = exporter.get_finished_spans()
    client = next(span for span in spans if span.kind is trace.SpanKind.CLIENT)
    assert captured["traceparent"].startswith(f"00-{parent_context.trace_id:032x}-")
    assert client.context.trace_id == parent_context.trace_id
    assert client.parent.span_id == parent_context.span_id


def test_fastapi_extracts_remote_parent_and_concurrent_requests_are_isolated() -> None:
    provider, exporter = _provider()
    app = FastAPI()

    @app.get("/predict")
    async def predict() -> dict[str, bool]:
        return {"ok": True}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    try:
        trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        parent_id = 0x1234567890ABCDEF
        header = f"00-{trace_id:032x}-{parent_id:016x}-01"
        with TestClient(app) as client:
            assert client.get("/predict", headers={"traceparent": header}).status_code == 200
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: client.get("/predict"), range(2)))
            assert all(response.status_code == 200 for response in responses)
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    server_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.kind is trace.SpanKind.SERVER and span.name.endswith("/predict")
    ]
    remote = next(span for span in server_spans if span.context.trace_id == trace_id)
    assert remote.parent.span_id == parent_id
    local_trace_ids = {span.context.trace_id for span in server_spans if span is not remote}
    assert len(local_trace_ids) == 2
    assert trace_id not in local_trace_ids
