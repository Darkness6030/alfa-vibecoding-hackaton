"""FastAPI application entrypoint.

K5b: safe staged logging (no input values), Prometheus metrics with
multiprocess aggregation, controlled 429 with Retry-After on overload, and
policy-based access control.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import redis
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import settings
from app.engine import MaskingEngine
from app.llm import MockLLM
from app.metrics import (
    errors,
    generate_latest,
    http_requests,
    pairs_completed,
    pairs_created,
    process_latency,
)
from app.policy import (
    AccessDeniedError,
    PolicyConfig,
    UnauthorizedError,
    build_demo_secure,
    build_evaluation_open,
)
from app.proxy import ProxyError, ProxyService
from app.schemas import HealthResponse, ProcessRequest, ProcessResponse
from app.state import ConflictError, StateStore, StorageError, make_encryption_key

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("alfagen")

app = FastAPI(title=settings.app_name, version="0.1.0")

# Profile selection (D07): evaluation-open for the stand, demo-secure for the
# security demonstration with two authenticated systems.
if settings.profile == "demo-secure":
    policy = build_demo_secure()
else:
    policy = build_evaluation_open()

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
store = StateStore(
    redis=_redis,
    namespace=settings.state_namespace,
    consumer=settings.state_consumer,
    ttl_seconds=settings.state_ttl_seconds,
    max_record_bytes=settings.state_max_record_bytes,
    encryption_key=make_encryption_key(settings.encryption_key),
)

# Concurrency limiter: when the semaphore is exhausted, return 429.
_concurrency_limit = settings.max_concurrency
_semaphore = threading.BoundedSemaphore(_concurrency_limit)

# Demo proxy (K6): same core, explicit mock LLM.
_proxy = ProxyService(engine=MaskingEngine(), llm=MockLLM())
_DEMO_HTML = (Path(__file__).parent / "static" / "demo.html").read_text(encoding="utf-8")


def _authenticate(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    system = policy.authenticate(api_key)
    policy.check_enabled(system)
    return system


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        profile=settings.profile,
        engine_stub=settings.engine_stub,
    )


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(content=_DEMO_HTML)


@app.post("/proxy")
def proxy(req: ProcessRequest, request: Request) -> JSONResponse:
    # The demo proxy is protected: only demo-secure systems may use it.
    system = _authenticate(request)
    sys_policy = policy.get(system)
    if not sys_policy.demask_allowed:
        raise AccessDeniedError("proxy requires demask access")
    try:
        result = _proxy.run(req.payload)
    except ProxyError:
        errors.labels(kind="llm").inc()
        http_requests.labels(route="/proxy", direction="in", status="502").inc()
        # Never leak the source text on LLM failure.
        return JSONResponse(status_code=502, content={"detail": "llm_unavailable"})
    http_requests.labels(route="/proxy", direction="in", status="200").inc()
    return JSONResponse(
        content={
            "masked_input": result.masked_input,
            "llm_response": result.llm_response,
            "restored_response": result.restored_response,
        }
    )


@app.post("/process", response_model=ProcessResponse)
def process(req: ProcessRequest, request: Request) -> ProcessResponse:
    if not _semaphore.acquire(blocking=False):
        errors.labels(kind="overload").inc()
        http_requests.labels(route="/process", direction="in", status="429").inc()
        return JSONResponse(
            status_code=429,
            content={"detail": "too_many_requests"},
            headers={"Retry-After": "1"},
        )
    try:
        t0 = time.perf_counter()
        system = _authenticate(request)
        sys_policy = policy.get(system)
        engine = MaskingEngine(mask_types=set(sys_policy.mask_types))
        outcome = store.process(
            req.payload_id,
            req.payload,
            engine.mask,
            demask_allowed=lambda: sys_policy.demask_allowed,
        )
        latency = time.perf_counter() - t0
        process_latency.labels(stage="process").observe(latency)
        if outcome.created:
            pairs_created.inc()
        else:
            pairs_completed.inc()
        # Safe staged log: no payload, no payload_id, no original values.
        logger.info(
            "process profile=%s system=%s created=%s latency_ms=%.1f",
            settings.profile,
            system,
            outcome.created,
            latency * 1000,
        )
        http_requests.labels(route="/process", direction="in", status="200").inc()
        return ProcessResponse(result=outcome.result)
    finally:
        _semaphore.release()


@app.exception_handler(ConflictError)
async def conflict_handler(_request: Request, _exc: ConflictError) -> JSONResponse:
    errors.labels(kind="conflict").inc()
    http_requests.labels(route="/process", direction="in", status="409").inc()
    return JSONResponse(status_code=409, content={"detail": "conflict"})


@app.exception_handler(StorageError)
async def storage_handler(_request: Request, _exc: StorageError) -> JSONResponse:
    logger.error("storage error: %s", _exc)
    errors.labels(kind="storage").inc()
    http_requests.labels(route="/process", direction="in", status="503").inc()
    return JSONResponse(status_code=503, content={"detail": "storage_unavailable"})


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(_request: Request, _exc: UnauthorizedError) -> JSONResponse:
    errors.labels(kind="unauthorized").inc()
    http_requests.labels(route="/process", direction="in", status="401").inc()
    return JSONResponse(status_code=401, content={"detail": "unauthorized"})


@app.exception_handler(AccessDeniedError)
async def access_denied_handler(_request: Request, _exc: AccessDeniedError) -> JSONResponse:
    errors.labels(kind="forbidden").inc()
    http_requests.labels(route="/process", direction="in", status="403").inc()
    return JSONResponse(status_code=403, content={"detail": "forbidden"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    # Never leak payload or sensitive values in error bodies or logs.
    logger.error("unhandled error type=%s", type(exc).__name__)
    errors.labels(kind="internal").inc()
    http_requests.labels(route="/process", direction="in", status="500").inc()
    return JSONResponse(status_code=500, content={"detail": "internal_error"})