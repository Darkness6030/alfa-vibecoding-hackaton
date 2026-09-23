"""Bounded ASGI transport without private request fields or task-group overhead."""

import logging
import time

from fastapi.responses import JSONResponse
from app.metrics import errors, http_requests, process_latency

logger = logging.getLogger("alfagen")
_ROUTES = frozenset(("/process", "/proxy", "/health", "/ready", "/metrics", "/"))
_LIMITED = frozenset(("/process", "/proxy"))


async def bounded_body(receive, limit):
    """Buffer at most limit bytes before allowing any request processing."""
    chunks, size = [], 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            raise BodyTooLarge
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


class BodyTooLarge(Exception):
    """The incoming stream exceeded the configured byte budget."""


class BoundaryMiddleware:
    """Admission, bounded input, safe errors and low-cardinality observations."""

    def __init__(self, app, semaphore, body_limit):
        self.app = app
        self.semaphore = semaphore
        self.body_limit = body_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route = scope["path"] if scope["path"] in _ROUTES else "other"
        gate = self.semaphore() if route in _LIMITED else None
        acquired = gate is not None and gate.acquire(blocking=False)
        started, status = time.perf_counter(), 500
        response_started = False

        async def observe_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                ]
            await send(message)

        try:
            if gate is not None and not acquired:
                errors.labels(kind="overload").inc()
                response = JSONResponse(
                    {"detail": "too_many_requests"},
                    status_code=429,
                    headers={"Retry-After": "1"},
                )
                await response(scope, receive, observe_send)
            else:
                await self._dispatch(scope, receive, observe_send, route)
        except Exception:
            # This final transport barrier deliberately hides arbitrary dependency errors.
            logger.error("request_failed route=%s", route)
            errors.labels(kind="internal").inc()
            if not response_started:
                await JSONResponse({"detail": "internal_error"}, status_code=500)(
                    scope, receive, observe_send
                )
        finally:
            if acquired:
                gate.release()
            self._observe(scope, route, status, started)

    async def _dispatch(self, scope, receive, send, route):
        if route not in _LIMITED:
            await self.app(scope, receive, send)
            return
        try:
            body = await bounded_body(receive, self.body_limit())
        except BodyTooLarge:
            await JSONResponse({"detail": "request_too_large"}, status_code=413)(
                scope, receive, send
            )
            return
        if body is None:
            return

        async def replay():
            nonlocal body
            if body is None:
                return await receive()
            message = {"type": "http.request", "body": body, "more_body": False}
            body = None
            return message

        await self.app(scope, replay, send)

    @staticmethod
    def _observe(scope, route, status, started):
        elapsed = time.perf_counter() - started
        direction = scope.get("state", {}).get("direction", "in")
        http_requests.labels(route=route, direction=direction, status=str(status)).inc()
        if route in _LIMITED:
            process_latency.labels(stage=route[1:]).observe(elapsed)
            logger.info(
                "request route=%s direction=%s status=%s latency_ms=%.2f",
                route,
                direction,
                status,
                elapsed * 1000,
            )
