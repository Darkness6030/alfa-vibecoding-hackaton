"""Open-loop paired load: fixed pair arrivals, exact reverse checks and bounded work."""

from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import json
import math
import time
import uuid
from pathlib import Path
import aiohttp

TEXTS = [
    "Клиент Иван Петров, почта ivan@example.com, телефон +7 912 345-67-89",
    "Дата рождения 15 марта 1990 года, паспорт серия 45 09 номер 123456, ИНН 7707083893",
    "Карта 4111111111111111, cvv 123, пин 1234, держатель IVAN PETROV",
    "Адрес: г. Москва, ул. Ленина, д. 5, почта a@b.com",
]


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * p))] if values else 0


def arrival_schedule(rps, duration, profile):
    """Pair arrivals; QA ramp is an explicit local approximation, not the stand."""
    points = (
        [(0, 1), (1, 1)]
        if profile == "constant"
        else [(0, 0), (0.2, 0.3), (0.75, 0.3), (0.8, 1), (1, 0)]
    )
    cumulative = 0.0
    next_pair = 0.5
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        width = (x1 - x0) * duration
        rate0, rate1 = rps * y0 / 2, rps * y1 / 2
        slope = (rate1 - rate0) / width
        area = (rate0 + rate1) * width / 2
        while next_pair < cumulative + area:
            target = next_pair - cumulative
            delta = (
                target / rate0
                if abs(slope) < 1e-12
                else 2
                * target
                / (rate0 + math.sqrt(max(0, rate0**2 + 2 * slope * target)))
            )
            yield x0 * duration + delta
            next_pair += 1
        cumulative += area


def valid_response(body):
    return (
        isinstance(body, dict)
        and set(body) == {"result"}
        and isinstance(body["result"], str)
    )


async def dispatch_pairs(pair, rps, duration, profile, concurrency, start):
    active = set()
    scheduled = dropped = delayed_arrivals = max_active_pairs = 0
    max_arrival_lag = 0.0
    for i, arrival in enumerate(arrival_schedule(rps, duration, profile)):
        target = start + arrival
        delay = target - time.perf_counter()
        # Yield even when overdue so response callbacks can release slots.
        await asyncio.sleep(max(0, delay))
        lag = max(0.0, time.perf_counter() - target)
        max_arrival_lag = max(max_arrival_lag, lag)
        delayed_arrivals += lag > 0.01
        scheduled += 1
        if len(active) >= concurrency:
            dropped += 1
            continue
        task = asyncio.create_task(pair(i))
        active.add(task)
        max_active_pairs = max(max_active_pairs, len(active))
        task.add_done_callback(active.discard)
    schedule_end = start + duration
    await asyncio.sleep(max(0, schedule_end - time.perf_counter()))
    await asyncio.gather(*list(active))
    return {
        "scheduled_pairs": scheduled,
        "dropped_pairs": dropped,
        "max_arrival_lag_seconds": max_arrival_lag,
        "arrivals_delayed_over_10ms": delayed_arrivals,
        "max_active_pairs": max_active_pairs,
    }


async def run(
    url: str,
    rps: int,
    duration: float,
    concurrency: int,
    mode: str,
    profile: str = "constant",
) -> dict:
    errors, directions = Counter(), {"mask": [], "demask": []}
    success = attempts = completed = bad_restore = throttled = 0
    run_id = uuid.uuid4().hex
    start = time.perf_counter()
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector, timeout=aiohttp.ClientTimeout(total=10)
    ) as client:

        async def pair(i):
            nonlocal success, attempts, completed, bad_restore, throttled
            original = TEXTS[i % len(TEXTS)]
            if mode == "unique":
                original += f". Тестовый запрос {i}."
            payload = original
            for direction in ("mask", "demask"):
                t = time.perf_counter()
                attempts += 1
                try:
                    response = await client.post(
                        url.rstrip("/") + "/process",
                        json={"payload": payload, "payload_id": f"{run_id}-{i}"},
                    )
                    raw = await response.read()
                    response.release()
                    directions[direction].append(time.perf_counter() - t)
                    if response.status == 429:
                        throttled += 1
                        return
                    if response.status != 200:
                        errors[str(response.status)] += 1
                        return
                    body = json.loads(raw)
                    if not valid_response(body):
                        errors["schema"] += 1
                        return
                    payload = body["result"]
                    success += 1
                except Exception as exc:
                    errors[type(exc).__name__] += 1
                    return
            if payload != original:
                bad_restore += 1
            else:
                completed += 1

        schedule = await dispatch_pairs(pair, rps, duration, profile, concurrency, start)
    elapsed = time.perf_counter() - start
    all_lat = directions["mask"] + directions["demask"]
    return {
        "run_id": run_id,
        "client": "aiohttp " + aiohttp.__version__,
        "corpus_size": len(TEXTS),
        "corpus_max_bytes": max(len(t.encode()) for t in TEXTS),
        "mode": mode,
        "profile": profile,
        "throttled_http": throttled,
        "offered_mean_http_rps": schedule["scheduled_pairs"] * 2 / duration,
        "target_http_rps": rps,
        "arrival_model": "open-loop pairs; --rps is constant rate or ramp peak",
        "schedule_seconds": duration,
        "elapsed_seconds": elapsed,
        "concurrency_pairs": concurrency,
        **schedule,
        "attempted_http": attempts,
        "successful_http": success,
        "successful_http_rps": success / elapsed,
        "completed_pairs": completed,
        "round_trip_failures": bad_restore,
        "errors": dict(errors),
        "latency_seconds": {
            name: {
                "mean": sum(v) / len(v) if v else 0,
                "p50": percentile(v, 0.5),
                "p95": percentile(v, 0.95),
                "p99": percentile(v, 0.99),
                "max": max(v, default=0),
            }
            for name, v in {**directions, "all": all_lat}.items()
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18000")
    ap.add_argument("--rps", type=int, default=100)
    ap.add_argument("--duration", type=float, default=30)
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--mode", choices=["unique", "repeat"], default="unique")
    ap.add_argument("--profile", choices=["constant", "qa-ramp"], default="constant")
    ap.add_argument("--output")
    ap.add_argument("--corpus", help="JSON list of synthetic strings")
    args = ap.parse_args()
    if args.corpus:
        texts = json.loads(Path(args.corpus).read_text())
        if not texts or not all(isinstance(t, str) for t in texts):
            ap.error("corpus must be a nonempty JSON list of strings")
        TEXTS[:] = texts
    if args.rps <= 0 or args.duration <= 0 or args.concurrency <= 0:
        ap.error("positive limits required")
    result = asyncio.run(
        run(
            args.url, args.rps, args.duration, args.concurrency, args.mode, args.profile
        )
    )
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
