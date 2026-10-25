#!/usr/bin/env python3
"""Install, remove and show cron jobs for the project apps.

    python scripts/setup_cron.py --every 5 install sender
    python scripts/setup_cron.py remove [task]
    python scripts/setup_cron.py status [task]

`sender` runs once per tick and exits. The indexers stay running and poll the
database themselves; cron only starts one if it is not already running.
Omitting the task installs or removes `sender`, and `status` then lists every task.
`--every` is minutes: `5` and `5m` both become `*/5 * * * *`.
`1h`, `1d`, `@hourly`, and a five-field cron expression are accepted too.
"""

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from crontab import CronTab

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOGS_DIR = PROJECT_ROOT / "logs"

_CRON_EXPR = re.compile(r"^(\S+\s+){4}\S+$")
_EVERY = re.compile(r"^(\d+)([mhd]?)$", re.IGNORECASE)


@dataclass(frozen=True)
class Task:
    name: str
    comment: str
    module: str
    args: tuple[str, ...]
    log_name: str
    default_every: str
    stays_running: bool


TASKS = {
    "sender": Task(
        name="sender",
        comment="tg-memes-sender",
        module="sender_tg_app",
        args=(),
        log_name="sender_cron.log",
        default_every="30m",
        stays_running=False,
    ),
    "clip-indexer": Task(
        name="clip-indexer",
        comment="tg-memes-clip-indexer",
        module="clip_indexer_app",
        args=(),
        log_name="clip_indexer_cron.log",
        default_every="1m",
        stays_running=True,
    ),
    "ocr-indexer": Task(
        name="ocr-indexer",
        comment="tg-memes-ocr-indexer",
        module="ocr_indexer_app",
        args=(),
        log_name="ocr_indexer_cron.log",
        default_every="1m",
        stays_running=True,
    ),
}


def to_cron(every: str) -> str:
    """Turn minutes, `1h`, `1d`, `@hourly`, or a cron expression into five fields."""
    text = every.strip()
    if text.startswith("@") or _CRON_EXPR.fullmatch(text):
        return text

    match = _EVERY.fullmatch(text)
    if not match:
        raise ValueError(f"interval {every!r} must be minutes, for example 5")

    count = int(match.group(1))
    unit = (match.group(2) or "m").lower()
    if count < 1:
        raise ValueError("interval must be at least 1")
    if unit == "m":
        if count > 59:
            raise ValueError("minutes must be 1..59")
        return "* * * * *" if count == 1 else f"*/{count} * * * *"
    if unit == "h":
        if count > 23:
            raise ValueError("hours must be 1..23")
        return "0 * * * *" if count == 1 else f"0 */{count} * * *"
    if count != 1:
        raise ValueError("days must be 1")
    return "0 0 * * *"


def command_for(task: Task) -> str:
    """One guarded command. `flock -E 0` exits quietly when this task is already running."""
    log_path = LOGS_DIR / task.log_name
    lock_path = LOGS_DIR / f"{task.name}.lock"
    parts = [
        "cd", shlex.quote(str(PROJECT_ROOT)),
        "&&",
        "flock", "-n", "-E", "0", shlex.quote(str(lock_path)),
        shlex.quote(sys.executable), "-m", task.module,
        *(shlex.quote(arg) for arg in task.args),
        ">>", shlex.quote(str(log_path)), "2>&1",
    ]
    return " ".join(parts)


def install(task: Task, every: str) -> int:
    try:
        schedule = to_cron(every)
    except ValueError as exc:
        print(exc)
        return 1

    LOGS_DIR.mkdir(exist_ok=True)
    cron = CronTab(user=True)
    cron.remove_all(comment=task.comment)
    job = cron.new(command=command_for(task), comment=task.comment)
    try:
        job.setall(schedule)
    except (ValueError, KeyError) as exc:
        print(f"Invalid schedule {schedule!r}: {exc}")
        return 1
    if not job.is_valid():
        print(f"Invalid schedule {schedule!r}")
        return 1

    cron.write()
    print(f"Installed {task.name}")
    print(f"  schedule: {schedule}")
    print(f"  log: {LOGS_DIR / task.log_name}")
    print(f"  next run: {job.schedule().get_next()}")
    if task.stays_running:
        print("  the process stays up; this schedule only restarts it if it has stopped")
    return 0


def remove(task: Task) -> int:
    cron = CronTab(user=True)
    removed = cron.remove_all(comment=task.comment)
    if removed:
        cron.write()
        print(f"Removed {removed} {task.name} job(s)")
    else:
        print(f"No {task.name} job installed")
    return 0


def status(tasks: list[Task]) -> int:
    cron = CronTab(user=True)
    for task in tasks:
        jobs = list(cron.find_comment(task.comment))
        if not jobs:
            print(f"{task.name}: not installed")
            continue
        for job in jobs:
            state = "enabled" if job.is_enabled() else "disabled"
            print(f"{task.name}: installed, {state}")
            print(f"  schedule: {job.slices}")
            print(f"  next run: {job.schedule().get_next()}")
            print(f"  command: {job.command}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install, remove and show project cron jobs.")
    parser.add_argument("action", choices=("install", "remove", "status"))
    parser.add_argument(
        "task",
        nargs="?",
        choices=tuple(TASKS),
        help="which app; defaults to sender. status without a task shows all",
    )
    parser.add_argument(
        "--every",
        help="minutes, such as 5 or 30m; also 1h, 1d, @hourly, or a five-field cron expression",
    )
    args = parser.parse_args()
    if args.every and args.action != "install":
        parser.error("--every applies to install only")
    return args


def main() -> int:
    args = parse_args()
    if args.action == "status" and args.task is None:
        return status(list(TASKS.values()))

    task = TASKS[args.task or "sender"]
    if args.action == "install":
        return install(task, args.every or task.default_every)
    if args.action == "remove":
        return remove(task)
    return status([task])


if __name__ == "__main__":
    sys.exit(main())
