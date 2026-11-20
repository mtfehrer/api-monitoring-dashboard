from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Literal, Protocol


@dataclass
class Streak:
    failures: int
    first_failure_at: datetime | None
    recoveries: int
    event: Literal["outage", "recovery"] | None = None


def next_streak(
    current: Streak, *, incident_open: bool, success: bool, finished_at: datetime
) -> Streak:
    if incident_open:
        recoveries = current.recoveries + 1 if success else 0
        if recoveries == 2:
            return Streak(0, None, 0, "recovery")
        return Streak(0, None, recoveries)
    if success:
        return Streak(0, None, 0)
    failures = current.failures + 1
    first_failure_at = current.first_failure_at or finished_at
    return Streak(failures, first_failure_at, 0, "outage" if failures == 3 else None)


def schedule_slot(due: datetime, now: datetime, interval: int) -> tuple[datetime, datetime]:
    step = timedelta(seconds=interval)
    scheduled_at = due + ((now - due) // step) * step
    return scheduled_at, scheduled_at + step


class MetricSample(Protocol):
    success: bool
    elapsed_ms: int
    http_status: int | None


def window_statistics(checks: list[MetricSample]) -> dict:
    total = len(checks)
    successful = sum(check.success for check in checks)
    samples = sorted(check.elapsed_ms for check in checks if check.http_status is not None)
    return {
        "total_checks": total,
        "successful_checks": successful,
        "availability_percent": successful / total * 100 if total else None,
        "response_samples": len(samples),
        "mean_ms": sum(samples) / len(samples) if samples else None,
        "p95_ms": samples[ceil(0.95 * len(samples)) - 1] if samples else None,
    }
