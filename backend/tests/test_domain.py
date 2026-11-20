from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from monitoring.domain import Streak, next_streak, schedule_slot, window_statistics


@pytest.mark.parametrize(("checks", "events"), [
    ([False, False, False, False, True, False, True, True], [(3, "outage"), (8, "recovery")]),
    ([False, False, True], []),
    ([False, False, False, True, True, False, False, False], [
        (3, "outage"), (5, "recovery"), (8, "outage"),
    ]),
])
def test_incident_transitions(checks, events):
    state = Streak(0, None, 0)
    incident_open = False
    observed = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for position, success in enumerate(checks, 1):
        state = next_streak(
            state, incident_open=incident_open, success=success,
            finished_at=start + timedelta(seconds=5 * position),
        )
        if state.event:
            incident_open = state.event == "outage"
            observed.append((position, state.event))
    assert observed == events


def test_schedule_keeps_its_cadence():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    scheduled, next_run = schedule_slot(start, start + timedelta(seconds=19.9), 5)
    assert scheduled == start + timedelta(seconds=15)
    assert next_run == start + timedelta(seconds=20)
    assert schedule_slot(next_run, next_run, 5)[0] == next_run


@dataclass
class Sample:
    success: bool
    elapsed_ms: int
    http_status: int | None


def test_metric_fixture():
    samples = [
        Sample(True, 100, 200), Sample(True, 200, 200), Sample(False, 300, 503),
        Sample(False, 2000, None),
    ]
    assert window_statistics(samples) == {
        "total_checks": 4, "successful_checks": 2, "availability_percent": 50.0,
        "response_samples": 3, "mean_ms": 200.0, "p95_ms": 300,
    }


def test_nearest_rank_and_missing_samples():
    samples = [Sample(True, index, 200) for index in range(1, 21)]
    assert window_statistics(samples)["p95_ms"] == 19
    assert window_statistics([])["availability_percent"] is None
    stats = window_statistics([Sample(False, 5000, None)])
    assert stats["availability_percent"] == 0
    assert stats["mean_ms"] is stats["p95_ms"] is None
