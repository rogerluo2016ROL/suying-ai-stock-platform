import asyncio
from datetime import datetime as RealDatetime

from app import scheduler


def test_fixed_time_job_runs_again_on_next_day(monkeypatch):
    clock = [
        RealDatetime(2026, 7, 14, 14, 30, 0),
        RealDatetime(2026, 7, 14, 14, 31, 0),
        RealDatetime(2026, 7, 15, 14, 30, 0),
    ]
    ticks = 0
    runs = []
    real_sleep = asyncio.sleep

    class FakeDatetime:
        @classmethod
        def now(cls):
            return clock[min(ticks, len(clock) - 1)]

    async def fake_run_job(job):
        runs.append((job["id"], FakeDatetime.now().date().isoformat()))

    async def fake_sleep(_seconds):
        nonlocal ticks
        await real_sleep(0)
        ticks += 1
        if ticks >= len(clock):
            scheduler._running = False

    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "_run_job", fake_run_job)
    monkeypatch.setattr(scheduler.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        scheduler,
        "_jobs",
        [{"id": "daily_1430", "name": "daily", "cron": "30 14 * * 1-5", "fn": lambda: None}],
    )

    asyncio.run(scheduler._scheduler_loop())

    assert runs == [
        ("daily_1430", "2026-07-14"),
        ("daily_1430", "2026-07-15"),
    ]
