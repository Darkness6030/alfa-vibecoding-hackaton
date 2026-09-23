"""Atomic, encrypted and tenant-isolated short-lived request pairs."""

from __future__ import annotations
import hashlib
import hmac
import json
from dataclasses import dataclass
from collections.abc import Callable
from cryptography.fernet import Fernet
from app.core import MaskResult, TOKEN_RE
from app.policy import AccessDeniedError
from app.metrics import measured


class ConflictError(Exception):
    pass


class StorageError(Exception):
    pass


class ExpiredStateError(ConflictError):
    pass


@dataclass(frozen=True)
class ProcessOutcome:
    result: str
    created: bool
    direction: str = "mask"
    types: tuple[str, ...] = ()


def make_encryption_key(configured: str) -> str:
    if configured:
        Fernet(configured.encode("ascii"))
        return configured
    return Fernet.generate_key().decode("ascii")


class StateStore:
    def __init__(
        self,
        redis,
        namespace: str,
        consumer: str,
        ttl_seconds: int,
        max_record_bytes: int,
        encryption_key: str,
    ) -> None:
        self._redis = redis
        self._namespace = namespace
        self._consumer = consumer
        self._ttl = ttl_seconds
        self._max_record_bytes = max_record_bytes
        self._fernet = Fernet(encryption_key.encode("ascii"))
        self._hash_key = encryption_key.encode("ascii")

    def ping(self) -> None:
        """Check storage without exposing its client to the transport layer."""
        from redis.exceptions import RedisError

        try:
            self._redis.ping()
        except (RedisError, OSError):
            raise StorageError("redis unavailable") from None

    def _digest(self, value: str) -> str:
        return hmac.new(
            self._hash_key, value.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _key(self, payload_id: str, consumer: str | None = None) -> str:
        # Hash the structured identity: no ID disclosure or delimiter collisions.
        identity = json.dumps([self._namespace, consumer or self._consumer, payload_id])
        return "alfagen:pair:" + self._digest(identity)

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")

    def process(
        self,
        payload_id: str,
        payload: str,
        mask_fn: Callable[[str], MaskResult],
        demask_allowed: Callable[[], bool] | None = None,
        consumer: str | None = None,
    ) -> ProcessOutcome:
        if len(payload.encode("utf-8")) > self._max_record_bytes:
            raise StorageError("payload too large")
        key = self._key(payload_id, consumer)
        try:
            # Crucial: retries and reverse calls do not rerun detection/encryption.
            with measured("state_read"):
                raw = self._redis.get(key)
            if raw is not None:
                return self._match_existing(
                    json.loads(self._decrypt(raw)), payload, demask_allowed
                )
            if TOKEN_RE.search(payload):
                raise ExpiredStateError("mapping absent")
            return self._publish(key, payload, mask_fn(payload), demask_allowed)
        except (AccessDeniedError, ConflictError, StorageError):
            raise
        except Exception as exc:
            # Never include dependency exception messages or input in the response.
            raise StorageError("state unavailable") from exc

    def _publish(self, key, payload, result, demask_allowed):
        """Publish once; a race loser uses the winner's immutable pair."""
        record = {
            "original": payload,
            "masked": result.masked_text,
            "types": sorted(result.detected_types),
        }
        raw = self._encrypt(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        )
        if len(raw.encode("ascii")) > self._max_record_bytes:
            raise StorageError("encrypted record too large")
        with measured("state_write"):
            created = self._redis.set(key, raw, nx=True, ex=self._ttl)
        if created:
            return ProcessOutcome(
                result.masked_text,
                created=True,
                direction="mask",
                types=tuple(record["types"]),
            )
        raw = self._redis.get(key)
        if raw is None:
            raise StorageError("state disappeared")
        return self._match_existing(
            json.loads(self._decrypt(raw)), payload, demask_allowed
        )

    def _match_existing(
        self, record: dict, payload: str, demask_allowed: Callable[[], bool] | None
    ) -> ProcessOutcome:
        types = tuple(record.get("types", ()))
        if payload == record["original"]:
            return ProcessOutcome(record["masked"], False, "repeat", types)
        if payload == record["masked"]:
            if demask_allowed is not None and not demask_allowed():
                raise AccessDeniedError("demasking denied")
            return ProcessOutcome(record["original"], False, "demask", types)
        raise ConflictError("conflicting content")
