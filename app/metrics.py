"""Prometheus metrics with multiprocess aggregation (K5b).

Metrics never use payload_id, text, phone, name, or free-form values as labels
(requirements N01, research-architecture). Multiprocess mode aggregates across
workers via a shared directory; the directory must be cleaned before workers
start (handled in the Docker entrypoint).

Exposed:
- alfagen_http_requests_total{route, direction, status}
- alfagen_process_latency_seconds{stage} (histogram)
- alfagen_pairs_created_total
- alfagen_pairs_completed_total
- alfagen_errors_total{kind}
- alfagen_detected_total{type}
- alfagen_masked_total{type}
"""

from __future__ import annotations

import os

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    multiprocess,
)

# Multiprocess mode requires a shared directory and a registry that aggregates
# across worker processes. Set PROMETHEUS_MULTIPROC_DIR before importing.
_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

if _MULTIPROC_DIR:
    os.makedirs(_MULTIPROC_DIR, exist_ok=True)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
else:
    registry = CollectorRegistry()

http_requests = Counter(
    "alfagen_http_requests_total",
    "HTTP requests completed",
    ["route", "direction", "status"],
    registry=registry,
)

process_latency = Histogram(
    "alfagen_process_latency_seconds",
    "Latency of processing stages",
    ["stage"],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

pairs_created = Counter(
    "alfagen_pairs_created_total",
    "Pairs created (new payload_id)",
    registry=registry,
)

pairs_completed = Counter(
    "alfagen_pairs_completed_total",
    "Pairs completed (repeat or demask)",
    registry=registry,
)

errors = Counter(
    "alfagen_errors_total",
    "Controlled errors by kind",
    ["kind"],
    registry=registry,
)

detected = Counter(
    "alfagen_detected_total",
    "PII spans detected by type",
    ["type"],
    registry=registry,
)

masked = Counter(
    "alfagen_masked_total",
    "PII spans masked by type",
    ["type"],
    registry=registry,
)


def generate_latest() -> bytes:
    """Return the aggregated metrics in Prometheus text format."""
    from prometheus_client import generate_latest as _generate_latest

    return _generate_latest(registry)