"""Redis-backed state store implementing the D05 mapping table.

Key: ``alfagen:{namespace}:{consumer}:{payload_id}``.

Record (JSON):
    h_original:  sha256 of the original text (for repeat detection, no PII)
    h_masked:    sha256 of the masked text (for demask detection, no PII)
    original_enc: Fernet-encrypted original text
    masked_enc:  Fernet-encrypted masked text
    mapping_enc: {token: Fernet-encrypted original value}

D05 behaviour:
- New id + original text: mask, atomically publish the pair (SET NX EX), then
  return the mask. The mask is never returned before the mapping is saved.
- Known id + original text matching: return the stored mask.
- Known id + mask matching: return the stored original (demasking).
- Known id + different text: ConflictError (409), no state/source leak.
- Original == mask (no PII): store and return the same string on repeats.
- Storage unavailable: StorageError (503), never a 200 with the original.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from cryptography.fernet import Fernet

from app.core import MaskResult
from app.policy import AccessDeniedError


class ConflictError(Exception):
    """Known payload_id with different text (HTTP 409)."""


class StorageError(Exception):
    """State store unavailable or record too large (HTTP 503)."""


@dataclass(frozen=True)
class ProcessOutcome:
    result: str
    created: bool


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_encryption_key(configured: str) -> str:
    """Return a valid Fernet key.

    Uses the configured key when provided (must be shared across workers).
    Otherwise generates an ephemeral key (dev only: mappings are lost on
    restart and not shared between processes).
    """
    if configured:
        return configured
    return Fernet.generate_key().decode("utf-8")


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
        self._fernet = Fernet(encryption_key.encode("utf-8"))

    def _key(self, payload_id: str) -> str:
        return f"alfagen:{self._namespace}:{self._consumer}:{payload_id}"

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    def _build_record(self, original: str, masked: str, mapping: dict[str, str]) -> str:
        # mapping_enc is reserved for K6 (demasking a modified LLM response,
        # where tokens are embedded in changed text). The /process pair contract
        # restores via original_enc/masked_enc only.
        mapping_enc = {token: self._encrypt(value) for token, value in mapping.items()}
        record = {
            "h_original": _sha256(original),
            "h_masked": _sha256(masked),
            "original_enc": self._encrypt(original),
            "masked_enc": self._encrypt(masked),
            "mapping_enc": mapping_enc,
        }
        return json.dumps(record, ensure_ascii=False)

    def _parse_record(self, raw: str) -> dict:
        return json.loads(raw)

    def process(
        self,
        payload_id: str,
        payload: str,
        mask_fn: Callable[[str], MaskResult],
        demask_allowed: Callable[[], bool] | None = None,
    ) -> ProcessOutcome:
        """Apply the D05 state machine for one payload_id.

        ``demask_allowed`` is a callback re-checked on every request before a
        demask is returned, so revoking demask access takes effect immediately
        even for already-created pairs (D05).
        """
        if len(payload.encode("utf-8")) > self._max_record_bytes:
            raise StorageError("payload exceeds configured record size limit")

        key = self._key(payload_id)
        try:
            # Atomic create: only the first writer publishes the pair.
            created = self._try_create(key, payload, mask_fn)
            if created is not None:
                return created

            # Key exists: read published state and apply the same mapping.
            raw = self._redis.get(key)
            if raw is None:
                # Lost between NX and get (e.g. TTL expired): treat as storage
                # inconsistency, never return the original as a success.
                raise StorageError("state disappeared during request")
            record = self._parse_record(raw)
            return self._match_existing(record, payload, demask_allowed)
        except (AccessDeniedError, ConflictError, StorageError):
            raise
        except Exception as exc:  # Redis connection errors etc.
            import logging

            logging.getLogger("alfagen").error("state store error type=%s", type(exc).__name__)
            raise StorageError("state store unavailable") from exc

    def _try_create(
        self, key: str, payload: str, mask_fn: Callable[[str], MaskResult]
    ) -> ProcessOutcome | None:
        res = mask_fn(payload)
        record = self._build_record(payload, res.masked_text, res.mapping)
        # SET NX EX: atomic publish only if the key does not exist yet.
        ok = self._redis.set(key, record, nx=True, ex=self._ttl)
        if ok:
            return ProcessOutcome(result=res.masked_text, created=True)
        return None

    def _match_existing(
        self,
        record: dict,
        payload: str,
        demask_allowed: Callable[[], bool] | None = None,
    ) -> ProcessOutcome:
        h_payload = _sha256(payload)
        if h_payload == record["h_original"]:
            # Repeat of the original: return the stored mask.
            return ProcessOutcome(result=self._decrypt(record["masked_enc"]), created=False)
        if h_payload == record["h_masked"]:
            # Demask: return the stored original, but only if demasking is
            # currently allowed for this system (re-checked per request).
            if demask_allowed is not None and not demask_allowed():
                raise AccessDeniedError("demasking not allowed for system")
            return ProcessOutcome(result=self._decrypt(record["original_enc"]), created=False)
        raise ConflictError("payload_id already used with different content")