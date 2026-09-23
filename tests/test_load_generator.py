"""A delayed producer must give completed requests time to release their slots."""

import asyncio
import json
import time

from benchmarks import load_test


class ImmediateResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def read(self):
        return json.dumps({"result": self.payload}).encode()

    def release(self):
        pass


class PausingClient:
    def __init__(self):
        self.paused = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, _url, *, json):
        if not self.paused:
            self.paused = True
            time.sleep(0.04)
        return ImmediateResponse(json["payload"])


def test_overdue_arrivals_do_not_starve_completed_pairs(monkeypatch):
    monkeypatch.setattr(load_test.aiohttp, "TCPConnector", lambda **_: None)
    monkeypatch.setattr(load_test.aiohttp, "ClientSession", lambda **_: PausingClient())
    result = asyncio.run(load_test.run("http://synthetic.invalid", 1000, 0.12, 8, "unique"))
    assert result["dropped_pairs"] == 0
    assert result["completed_pairs"] == result["scheduled_pairs"]
    assert result["round_trip_failures"] == 0
    assert result["max_arrival_lag_seconds"] >= 0.02
