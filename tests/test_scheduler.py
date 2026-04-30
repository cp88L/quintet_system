import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, time
from unittest import TestCase
from zoneinfo import ZoneInfo

from quintet import scheduler
from quintet.scheduler import (
    build_run_command,
    configured_run_time,
    next_run_at,
    parse_run_time,
    run_scheduled_once,
)


class SchedulerTests(TestCase):
    def test_parse_run_time(self) -> None:
        self.assertEqual(parse_run_time("16:30"), time(16, 30))

    def test_configured_run_time_uses_env_override(self) -> None:
        old_value = os.environ.get("QUINTET_SCHEDULE_TIME")
        try:
            os.environ["QUINTET_SCHEDULE_TIME"] = "15:45"
            self.assertEqual(configured_run_time(), time(15, 45))
            self.assertEqual(configured_run_time("16:30"), time(16, 30))
        finally:
            if old_value is None:
                os.environ.pop("QUINTET_SCHEDULE_TIME", None)
            else:
                os.environ["QUINTET_SCHEDULE_TIME"] = old_value

    def test_next_run_uses_today_when_time_is_ahead(self) -> None:
        tz = ZoneInfo("America/Chicago")
        now = datetime(2026, 4, 30, 15, 0, tzinfo=tz)

        self.assertEqual(
            next_run_at(
                now=now,
                run_time=time(16, 30),
                timezone=tz,
                weekdays=(0, 1, 2, 3, 4),
            ),
            datetime(2026, 4, 30, 16, 30, tzinfo=tz),
        )

    def test_next_run_uses_current_minute(self) -> None:
        tz = ZoneInfo("America/Chicago")
        now = datetime(2026, 4, 30, 16, 30, 30, tzinfo=tz)

        self.assertEqual(
            next_run_at(
                now=now,
                run_time=time(16, 30),
                timezone=tz,
                weekdays=(0, 1, 2, 3, 4),
            ),
            datetime(2026, 4, 30, 16, 30, tzinfo=tz),
        )

    def test_next_run_skips_weekend_after_friday_run_time(self) -> None:
        tz = ZoneInfo("America/Chicago")
        now = datetime(2026, 5, 1, 17, 0, tzinfo=tz)

        self.assertEqual(
            next_run_at(
                now=now,
                run_time=time(16, 30),
                timezone=tz,
                weekdays=(0, 1, 2, 3, 4),
            ),
            datetime(2026, 5, 4, 16, 30, tzinfo=tz),
        )

    def test_build_run_command_uses_existing_runner(self) -> None:
        self.assertEqual(
            build_run_command(mode="live", extra_args=("--no-fetch",)),
            [sys.executable, "-m", "quintet.run", "--live", "--no-fetch"],
        )

    def test_build_run_command_can_force_tau(self) -> None:
        self.assertEqual(
            build_run_command(
                mode="live",
                extra_args=("--no-fetch",),
                force_tau=True,
            ),
            [
                sys.executable,
                "-m",
                "quintet.run",
                "--live",
                "--force-tau",
                "--no-fetch",
            ],
        )

    def test_shutdown_computer_uses_quartet_shutdown_command(self) -> None:
        calls: list[list[str]] = []
        old_run = scheduler.subprocess.run

        class FakeResult:
            returncode = 0

        try:
            scheduler.subprocess.run = lambda cmd: calls.append(cmd) or FakeResult()
            with redirect_stdout(io.StringIO()):
                scheduler.shutdown_computer()
        finally:
            scheduler.subprocess.run = old_run

        self.assertEqual(calls, [["shutdown", "+1"]])

    def test_run_scheduled_once_sleeps_and_runs_one_time(self) -> None:
        tz = ZoneInfo("America/Chicago")
        calls: list[tuple] = []
        old_datetime = scheduler.datetime
        old_sleep = scheduler.time_module.sleep
        old_run_once = scheduler.run_once

        class FakeDatetime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 4, 30, 16, 0, tzinfo=tz)

            @classmethod
            def combine(cls, *args, **kwargs):
                return datetime.combine(*args, **kwargs)

        try:
            scheduler.datetime = FakeDatetime
            scheduler.time_module.sleep = lambda seconds: calls.append(("sleep", seconds))

            def fake_run_once(*, mode, extra_args=(), force_tau=False):
                calls.append(("run", mode, extra_args, force_tau))
                return 0

            scheduler.run_once = fake_run_once

            with redirect_stdout(io.StringIO()):
                code = run_scheduled_once(
                    run_time=time(16, 30),
                    timezone=tz,
                    weekdays=(0, 1, 2, 3, 4),
                    mode="live",
                    extra_args=("--no-fetch",),
                    force_tau=True,
                )
        finally:
            scheduler.datetime = old_datetime
            scheduler.time_module.sleep = old_sleep
            scheduler.run_once = old_run_once

        self.assertEqual(code, 0)
        self.assertEqual(
            calls,
            [("sleep", 1800.0), ("run", "live", ("--no-fetch",), True)],
        )
