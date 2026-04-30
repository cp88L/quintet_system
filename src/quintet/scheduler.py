"""One-shot scheduler for the Quintet daily run.

Waits until 4:30 PM Chicago time, runs the pipeline, then exits.
Must be started manually each day you want it to run.

Usage:
    python -m quintet.scheduler              # Wait for 4:30 PM, run, exit
    python -m quintet.scheduler --shutdown   # Same, but shutdown computer after
    python -m quintet.scheduler --now        # Run immediately and exit
    python -m quintet.scheduler --force-tau  # Force tau rebuild during run step

Environment variables:
    QUINTET_SCHEDULE_TIME=16:30    # Override schedule time (24h format)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time as time_module
from collections.abc import Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from quintet import config


VALID_MODES = {"live", "dry-run"}
SCHEDULE_ENV_VAR = "QUINTET_SCHEDULE_TIME"


def parse_run_time(value: str) -> time:
    """Parse configured HH:MM scheduler time."""
    try:
        hour_s, minute_s = value.split(":", maxsplit=1)
        return time(hour=int(hour_s), minute=int(minute_s))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid scheduler run time: {value!r}") from exc


def configured_run_time(override: str | None = None) -> time:
    """Return the CLI, env, or config scheduler time."""
    value = override or os.environ.get(SCHEDULE_ENV_VAR, config.SCHEDULER_RUN_TIME)
    return parse_run_time(value)


def next_run_at(
    *,
    now: datetime,
    run_time: time,
    timezone: ZoneInfo,
    weekdays: Sequence[int],
) -> datetime:
    """Return the next configured run datetime."""
    local_now = now.astimezone(timezone)
    current_minute = local_now.replace(second=0, microsecond=0)
    allowed = set(weekdays)
    for offset in range(8):
        candidate_date = local_now.date() + timedelta(days=offset)
        if candidate_date.weekday() not in allowed:
            continue
        candidate = datetime.combine(candidate_date, run_time, tzinfo=timezone)
        if candidate >= current_minute:
            return candidate
    raise ValueError("No scheduler weekday configured")


def build_run_command(
    *,
    mode: str,
    extra_args: Sequence[str] = (),
    force_tau: bool = False,
) -> list[str]:
    """Build the existing daily-run command the scheduler executes."""
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid scheduler mode: {mode!r}")
    command = [sys.executable, "-m", "quintet.run", f"--{mode}"]
    if force_tau:
        command.append("--force-tau")
    command.extend(extra_args)
    return command


def run_once(
    *,
    mode: str,
    extra_args: Sequence[str] = (),
    force_tau: bool = False,
) -> int:
    """Run the daily pipeline once and return its process exit code."""
    command = build_run_command(
        mode=mode,
        extra_args=extra_args,
        force_tau=force_tau,
    )
    timezone = ZoneInfo(config.SCHEDULER_TIMEZONE)
    print(f"[{datetime.now(timezone)}] Starting pipeline...", flush=True)
    result = subprocess.run(command)
    print(
        f"[{datetime.now(timezone)}] Pipeline finished with code {result.returncode}",
        flush=True,
    )
    return result.returncode


def shutdown_computer() -> None:
    """Schedule host shutdown one minute after the pipeline finishes."""
    print("Shutting down computer in 60 seconds...", flush=True)
    subprocess.run(["shutdown", "+1"])


def run_scheduled_once(
    *,
    run_time: time,
    timezone: ZoneInfo,
    weekdays: Sequence[int],
    mode: str,
    extra_args: Sequence[str] = (),
    force_tau: bool = False,
) -> int:
    """Wait for the next configured time, run once, then exit."""
    target = next_run_at(
        now=datetime.now(tz=timezone),
        run_time=run_time,
        timezone=timezone,
        weekdays=weekdays,
    )
    now = datetime.now(tz=timezone)
    seconds = max(0.0, (target - now).total_seconds())
    print(f"Next Quintet {mode} run: {target.isoformat()}", flush=True)
    time_module.sleep(seconds)
    return run_once(mode=mode, extra_args=extra_args, force_tau=force_tau)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quintet daily-run scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run immediately once instead of waiting for the configured time.",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run immediately once instead of waiting for the configured time.",
    )
    parser.add_argument(
        "--shutdown",
        action="store_true",
        help="Shutdown the computer after the pipeline completes.",
    )
    parser.add_argument(
        "--force-tau",
        action="store_true",
        help="Force tau/lookback rebuild during the scheduled run.",
    )
    parser.add_argument(
        "--show-next",
        action="store_true",
        help="Print the next configured run time and exit.",
    )
    parser.add_argument(
        "--time",
        default=None,
        help=(
            "Daily run time in HH:MM. Defaults to QUINTET_SCHEDULE_TIME "
            f"or config.SCHEDULER_RUN_TIME ({config.SCHEDULER_RUN_TIME})."
        ),
    )
    parser.add_argument(
        "--timezone",
        default=config.SCHEDULER_TIMEZONE,
        help=f"IANA timezone, default {config.SCHEDULER_TIMEZONE}.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--live", action="store_true", help="Schedule live runs.")
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Schedule dry-run reports only.",
    )
    return parser.parse_args()


def _mode_from_args(args: argparse.Namespace) -> str:
    if args.live:
        return "live"
    if args.dry_run:
        return "dry-run"
    mode = config.SCHEDULER_MODE
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid config.SCHEDULER_MODE: {mode!r}")
    return mode


def main() -> int:
    args = _parse_args()
    timezone = ZoneInfo(args.timezone)
    run_time = configured_run_time(args.time)
    mode = _mode_from_args(args)
    extra_args = tuple(config.SCHEDULER_EXTRA_ARGS)

    if args.show_next:
        target = next_run_at(
            now=datetime.now(tz=timezone),
            run_time=run_time,
            timezone=timezone,
            weekdays=config.SCHEDULER_WEEKDAYS,
        )
        print(target.isoformat())
        return 0

    try:
        if args.once or args.now:
            result = run_once(
                mode=mode,
                extra_args=extra_args,
                force_tau=args.force_tau,
            )
        else:
            result = run_scheduled_once(
                run_time=run_time,
                timezone=timezone,
                weekdays=config.SCHEDULER_WEEKDAYS,
                mode=mode,
                extra_args=extra_args,
                force_tau=args.force_tau,
            )
    except KeyboardInterrupt:
        return 130

    if args.shutdown:
        shutdown_computer()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
