"""Behavior clarified by organizers in docs/sources/qa.txt, including span boundaries."""

import pytest
from app.core import TOKEN_RE, restore
from app.engine import MaskingEngine


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Паспорт серия 45 09 номер 123456",
            "Паспорт серия <PASSPORT> номер <PASSPORT>",
        ),
        (
            "ВУ серия 77 12 номер 345678",
            "ВУ серия <DRIVING_LICENSE> номер <DRIVING_LICENSE>",
        ),
        ("Дата рождения 15 марта 1990 года", "Дата рождения <BIRTH_DATE> года"),
        ("Дата выдачи 20 апреля 2015 года", "Дата выдачи <ISSUE_DATE> года"),
        (
            "Адрес: г. Москва, ул. Ленина, д. 5",
            "Адрес: г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>",
        ),
        ("Родился в г. Москва", "Родился в г. <BIRTH_PLACE>"),
        ("Иванов Иван Иванович", "<PERSON>"),
        ("  ИВАНОВ ИВАН ИВАНОВИЧ  ", "  <PERSON>  "),
        ("иванов иван иванович", "<PERSON>"),
        ("Сидорова Анна Петровна.", "<PERSON>."),
        # Explicitly labelled series is masked even without the number.
        ("Паспорт серия 45 09 номер", "Паспорт серия <PASSPORT> номер"),
        # Standalone structured address is masked without the "Адрес:" label.
        (
            "г. Москва, ул. Маросейка, д. 5",
            "г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>",
        ),
    ],
)
def test_qa_exact_boundaries_and_restoration(text, expected):
    result = MaskingEngine().mask(text)
    readable = TOKEN_RE.sub(
        lambda m: "<" + m.group()[2:].split(":")[0] + ">", result.masked_text
    )
    assert readable == expected
    assert restore(result.masked_text, result.mapping) == text


@pytest.mark.parametrize(
    "text", ["Поэт Александр Пушкин", "обычный тестовый текст", "Писатель Лев Толстой"]
)
def test_bare_name_support_does_not_mask_unrelated_three_words(text):
    assert MaskingEngine().mask(text).masked_text == text


def test_qa_ramp_has_declared_mean_peak_and_balanced_pair_arrivals():
    from benchmarks.load_test import arrival_schedule

    arrivals = list(arrival_schedule(1000, 100, "qa-ramp"))
    assert len(arrivals) * 2 / 100 == pytest.approx(327.5)
    assert all(0 < a < 100 for a in arrivals)
    assert arrivals == sorted(arrivals)
    assert len(list(arrival_schedule(500, 10, "constant"))) == 2500


def test_load_report_separates_429_from_errors():
    import asyncio
    from aiohttp import web
    from benchmarks.load_test import run

    async def scenario():
        calls = 0

        async def process(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return web.json_response({"detail": "too_many_requests"}, status=429)
            return web.json_response({"result": (await request.json())["payload"]})

        application = web.Application()
        application.router.add_post("/process", process)
        runner = web.AppRunner(application)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        try:
            host, port = runner.addresses[0]
            return await run(f"http://{host}:{port}", 100, 0.04, 4, "unique")
        finally:
            await runner.cleanup()

    report = asyncio.run(scenario())
    assert report["throttled_http"] == 1
    assert report["errors"] == {}
    assert report["completed_pairs"] == 1
    assert report["latency_seconds"]["all"]["mean"] > 0
