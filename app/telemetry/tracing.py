"""Minimal OpenTelemetry tracing; opt-in console spans for local validation.

No raw prompts, tokens, response bodies or tool arguments are span attributes.
"""
from __future__ import annotations

import os

_INITIALIZED = False


def configure_tracing() -> None:
    global _INITIALIZED
    if _INITIALIZED or os.getenv("OTEL_TRACES_EXPORTER", "none") != "console":
        return
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    provider = TracerProvider(resource=Resource.create({"service.name": "acme-copilot-web"}))
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _INITIALIZED = True


def tracer():
    from opentelemetry import trace
    return trace.get_tracer("acme.agent", "1.0")
