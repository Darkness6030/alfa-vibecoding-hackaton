"""K9 load test: pairs, RPS, latency, errors.

Sends POST /process requests with unique payload_ids (mask direction) and
measures offered/success RPS, latency percentiles, and errors. Supports
unique vs repeated texts and configurable concurrency/duration.

Usage:
    python benchmarks/load_test.py --url http://127.0.0.1:8000 \
        --rps 100 --duration 30 --concurrency 20 --mode unique
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

TEXTS = [
    "Клиент Иван Петров, почта ivan@example.com, телефон +7 912 345-67-89",
    "Дата рождения 15.03.1990, паспорт 4509 123456, ИНН 7707083893",
    "Карта 4111111111111111, cvv 123, пин 1234, держатель Иван Петров",
    "Адрес: г. Москва, ул. Ленина, д. 5, почта a@b.com",
]


async def worker(
    client: httpx.AsyncClient,
    url: str,
    mode: str,
    counter: dict,
    lock: asyncio.Lock,
    stop: asyncio.Event,
) -> None:
    i = 0
    while not stop.is_set():
        text = TEXTS[i % len(TEXTS)]
        if mode == "unique":
            payload_id = f"load-{time.time_ns()}-{i}"
        else:
            payload_id = f"repeat-{i % 100}"
        t0 = time.perf_counter()
        try:
            r = await client.post(
                f"{url}/process",
                json={"payload": text, "payload_id": payload_id},
                timeout=10.0,
            )
            latency = time.perf_counter() - t0
            async with lock:
                counter["total"] += 1
                counter["latencies"].append(latency)
                if r.status_code == 200:
                    counter["success"] += 1
                else:
                    counter["errors"][r.status_code] = counter["errors"].get(r.status_code, 0) + 1
        except Exception:
            async with lock:
                counter["total"] += 1
                counter["errors"]["conn"] = counter["errors"].get("conn", 0) + 1
        i += 1


async def run(url: str, rps: int, duration: int, concurrency: int, mode: str) -> dict:
    counter = {"total": 0, "success": 0, "latencies": [], "errors": {}}
    lock = asyncio.Lock()
    stop = asyncio.Event()

    async with httpx.AsyncClient() as client:
        workers = [asyncio.create_task(worker(client, url, mode, counter, lock, stop)) for _ in range(concurrency)]
        await asyncio.sleep(duration)
        stop.set()
        await asyncio.gather(*workers, return_exceptions=True)

    lat = sorted(counter["latencies"])
    n = len(lat)
    pct = lambda p: lat[min(n - 1, int(p * n))] if n else 0.0
    return {
        "mode": mode,
        "duration": duration,
        "total": counter["total"],
        "success": counter["success"],
        "offered_rps": rps,
        "success_rps": counter["success"] / duration,
        "errors": counter["errors"],
        "p50": pct(0.50),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": lat[-1] if lat else 0.0,
        "avg": statistics.mean(lat) if lat else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--rps", type=int, default=100)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--mode", choices=["unique", "repeat"], default="unique")
    args = ap.parse_args()

    result = asyncio.run(run(args.url, args.rps, args.duration, args.concurrency, args.mode))
    print(f"mode={result['mode']} duration={result['duration']}s")
    print(f"offered_rps={result['offered_rps']} success_rps={result['success_rps']:.1f}")
    print(f"total={result['total']} success={result['success']} errors={result['errors']}")
    print(f"latency p50={result['p50']*1000:.1f}ms p95={result['p95']*1000:.1f}ms "
          f"p99={result['p99']*1000:.1f}ms max={result['max']*1000:.1f}ms avg={result['avg']*1000:.1f}ms")


if __name__ == "__main__":
    main()