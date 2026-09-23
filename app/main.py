"""Transport, access control and safe observability for the demo and stand."""

from __future__ import annotations
import logging
import threading
from functools import lru_cache
from pathlib import Path
import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from app.boundary import BoundaryMiddleware
from app.config import settings
from app.engine import MaskingEngine
from app.llm import MockLLM
from app.metrics import (
    errors,
    generate_latest,
    pairs_completed,
    pairs_created,
    input_tokens,
)
from app.policy import (
    ALL_TYPES,
    AccessDeniedError,
    UnauthorizedError,
    credentials_match,
    load_policy,
)
from app.proxy import ProxyError, ProxyService
from app.schemas import HealthResponse, ProcessRequest, ProcessResponse
from app.state import ConflictError, StateStore, StorageError, make_encryption_key
from app.tokenizer import count_tokens

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("alfagen")
app = FastAPI(title=settings.app_name, version="0.4.4")
policy = load_policy(settings.policy_file, settings.profile)
if not settings.encryption_key:
    raise RuntimeError(
        "ALFAGEN_ENCRYPTION_KEY is required; generate demo secrets before starting"
    )
_redis = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    max_connections=settings.max_concurrency + 8,
)
store = StateStore(
    _redis,
    settings.state_namespace,
    settings.state_consumer,
    settings.state_ttl_seconds,
    settings.state_max_record_bytes,
    make_encryption_key(settings.encryption_key),
)
_concurrency_limit = settings.max_concurrency
_semaphore = threading.BoundedSemaphore(_concurrency_limit)
_policy_lock = threading.Lock()
_policy_stamp = (
    Path(settings.policy_file).stat().st_mtime_ns if settings.policy_file else None
)
_DEMO_HTML = (Path(__file__).parent / "static" / "demo.html").read_text()


def _refresh_policy():
    global policy, _policy_stamp
    if settings.policy_file:
        with _policy_lock:
            try:
                stamp = Path(settings.policy_file).stat().st_mtime_ns
                if stamp != _policy_stamp:
                    policy = load_policy(settings.policy_file, settings.profile)
                    _policy_stamp = stamp
            except (OSError, ValueError, TypeError, KeyError):
                raise StorageError("invalid policy configuration") from None


def _authenticate(request: Request, *, allow_open: bool = True) -> str:
    _refresh_policy()
    system = policy.authenticate(
        request.headers.get("X-API-Key"), allow_open=allow_open
    )
    policy.check_enabled(system)
    return system


def _engine(system: str) -> MaskingEngine:
    return _configured_engine(
        policy.get(system), policy.custom_patterns, settings.ner_enabled
    )


@lru_cache(maxsize=64)
def _configured_engine(p, custom_patterns, ner_enabled):
    return MaskingEngine(
        ner_enabled=ner_enabled,
        mask_types=set(p.mask_types),
        detect_types=set(p.detect_types),
        masking_enabled=p.masking_enabled,
        mask_mode=p.mask_mode,
        combinations=p.combinations,
        custom_patterns=custom_patterns,
    )


app.add_middleware(
    BoundaryMiddleware,
    semaphore=lambda: _semaphore,
    body_limit=lambda: settings.max_body_bytes,
)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", profile=settings.profile, engine_stub=False)


@app.get("/ready")
def ready():
    store.ping()
    return {"status": "ready"}


@app.get("/metrics")
def metrics(request: Request):
    key = request.headers.get("X-Metrics-Key", "")
    if not settings.metrics_api_key or not credentials_match(
        settings.metrics_api_key, key
    ):
        _authenticate(request, allow_open=False)
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/", response_class=HTMLResponse)
def demo_page():
    return HTMLResponse(_DEMO_HTML, headers={"Cache-Control": "no-store"})


@app.post("/proxy")
def proxy(req: ProcessRequest, request: Request):
    system = _authenticate(request, allow_open=False)
    policy.check_demask(system)
    p = policy.get(system)
    # Do not send deliberately unprotected configurations over the LLM boundary.
    if (
        not p.masking_enabled
        or p.mask_mode != "token"
        or p.combinations
        or not p.detect_types.issuperset(ALL_TYPES)
        or not p.detect_types.issubset(p.mask_types)
    ):
        raise AccessDeniedError("unsafe proxy policy")
    result = ProxyService(_engine(system), MockLLM()).run(req.payload)
    input_tokens.labels(route="/proxy").inc(count_tokens(req.payload))
    _refresh_policy()
    policy.check_demask(system)
    return {
        "masked_input": result.masked_input,
        "llm_response": result.llm_response,
        "restored_response": result.restored_response,
        "llm_mode": "mock",
        "warnings": list(result.warnings),
    }


@app.post("/process", response_model=ProcessResponse)
def process(req: ProcessRequest, request: Request):
    system = _authenticate(request)

    def can_demask():
        _refresh_policy()
        policy.check_demask(system)
        return True

    outcome = store.process(
        req.payload_id,
        req.payload,
        lambda text: _engine(system).mask(text),
        demask_allowed=can_demask,
        consumer=system,
    )
    request.state.direction = outcome.direction
    input_tokens.labels(route="/process").inc(count_tokens(req.payload))
    if outcome.created:
        pairs_created.inc()
    if outcome.direction == "demask":
        pairs_completed.inc()
    logger.info(
        "stage=transform system=%s direction=%s types=%s",
        system,
        outcome.direction,
        ",".join(outcome.types),
    )
    return ProcessResponse(result=outcome.result)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request, _exc):
    errors.labels(kind="validation").inc()
    return JSONResponse(status_code=422, content={"detail": "invalid_request"})


def safe_error(_request, exc):
    if isinstance(exc, UnauthorizedError):
        code, kind = 401, "unauthorized"
    elif isinstance(exc, AccessDeniedError):
        code, kind = 403, "forbidden"
    elif isinstance(exc, ConflictError):
        code, kind = 409, "conflict"
    elif isinstance(exc, ProxyError):
        code, kind = 502, "llm_unavailable"
    else:
        code, kind = 503, "storage_unavailable"
    errors.labels(kind=kind).inc()
    return JSONResponse(status_code=code, content={"detail": kind})


for error_type in (
    UnauthorizedError,
    AccessDeniedError,
    ConflictError,
    StorageError,
    ProxyError,
):
    app.add_exception_handler(error_type, safe_error)
