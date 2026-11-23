from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from sqlalchemy import select, text, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .db import session, utcnow
from .domain import window_statistics
from .models import CheckResult, Incident, Monitor, Notification
from .schemas import (
    ChartPoint, Check, CheckPage, IncidentView, Metrics, MonitorCreate, MonitorEdit,
    MonitorView, NotificationView,
)

app = FastAPI(title="API Monitoring Dashboard")
DB = Annotated[AsyncSession, Depends(session)]
REQUEST_FIELDS = ("method", "request_headers", "request_body")


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError):
    # Validation inputs can contain values such as Infinity that JSON cannot serialize.
    details = [
        {key: error[key] for key in ("loc", "msg", "type")}
        for error in exc.errors()
    ]
    return JSONResponse({"detail": details}, status_code=422)


def invalid(location: str, field: str, message: str):
    raise HTTPException(422, detail=[{
        "loc": [location, field], "msg": message, "type": "value_error",
    }])


def validate_timeout(timeout: float, interval: int):
    if timeout >= interval:
        invalid("body", "timeout_seconds", "Timeout must be shorter than the check interval.")


def window(
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> tuple[datetime, datetime]:
    end = end if end is not None else utcnow()
    if start is None:
        try:
            start = end - timedelta(hours=24)
        except OverflowError:
            invalid("query", "to", "Provide an end time that allows a 24-hour window.")
    if start >= end:
        invalid("query", "from", "Window start must precede its end.")
    return start, end


Window = Annotated[tuple[datetime, datetime], Depends(window)]


def summary_statement():
    latest = aliased(CheckResult, (
        select(CheckResult)
        .where(CheckResult.monitor_id == Monitor.id)
        .correlate(Monitor)
        .order_by(CheckResult.scheduled_at.desc())
        .limit(1)
        .lateral()
    ))
    return (
        select(Monitor, latest, Incident)
        .select_from(Monitor)
        .outerjoin(latest, true())
        .outerjoin(Incident, (Incident.monitor_id == Monitor.id) & Incident.resolved_at.is_(None))
    )


def summarize(monitor: Monitor, latest: CheckResult | None, incident: Incident | None) -> MonitorView:
    due = monitor.awaiting_since or monitor.next_run_at
    overdue = bool(
        monitor.enabled and due and utcnow() > due + timedelta(seconds=monitor.interval_seconds)
    )
    return MonitorView.model_validate(monitor).model_copy(update={
        "latest_check": Check.model_validate(latest) if latest is not None else None,
        "open_incident": IncidentView.model_validate(incident) if incident is not None else None,
        "overdue": overdue,
        "awaiting_recovery": bool(incident and monitor.enabled and not overdue and monitor.recovery_streak),
    })


async def require_monitor(db: AsyncSession, monitor_id: int, *, lock: bool = False) -> Monitor:
    if not -(2**31) <= monitor_id < 2**31:
        raise HTTPException(404, "Monitor not found.")
    monitor = await db.get(Monitor, monitor_id, with_for_update=lock)
    if monitor is None:
        raise HTTPException(404, "Monitor not found.")
    return monitor


@app.get("/api/health", include_in_schema=False)
async def health(db: DB):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/monitors", status_code=201, response_model=MonitorView)
async def create_monitor(payload: MonitorCreate, db: DB):
    validate_timeout(payload.timeout_seconds, payload.interval_seconds)
    now = utcnow()
    monitor = Monitor(**payload.model_dump(), created_at=now, next_run_at=now)
    async with db.begin():
        db.add(monitor)
    return monitor


@app.get("/api/monitors", response_model=list[MonitorView])
async def list_monitors(db: DB):
    rows = await db.execute(summary_statement().order_by(Monitor.id))
    return [summarize(*row) for row in rows]


@app.get("/api/monitors/{monitor_id}", response_model=MonitorView)
async def get_monitor(monitor_id: int, db: DB):
    await require_monitor(db, monitor_id)
    row = (await db.execute(summary_statement().where(Monitor.id == monitor_id))).one()
    return summarize(*row)


@app.patch("/api/monitors/{monitor_id}", response_model=MonitorView)
async def edit_monitor(monitor_id: int, payload: MonitorEdit, db: DB):
    async with db.begin():
        monitor = await require_monitor(db, monitor_id, lock=True)
        changes = payload.model_dump(exclude_unset=True)
        validate_timeout(
            changes.get("timeout_seconds", monitor.timeout_seconds),
            changes.get("interval_seconds", monitor.interval_seconds),
        )
        toggled = "enabled" in changes and monitor.enabled != changes["enabled"]
        request_changed = any(
            field in changes and changes[field] != getattr(monitor, field) for field in REQUEST_FIELDS
        )
        if toggled:
            monitor.next_run_at = utcnow() if changes["enabled"] else None
        if toggled or request_changed:
            monitor.generation += 1
            monitor.awaiting_since = None
            monitor.failure_streak = monitor.recovery_streak = 0
            monitor.first_failure_at = None
        for field, value in changes.items():
            setattr(monitor, field, value)
        await db.flush()
        row = (await db.execute(summary_statement().where(Monitor.id == monitor_id))).one()
        return summarize(*row)


def window_checks(monitor_id: int, bounds: tuple[datetime, datetime]):
    start, end = bounds
    return (
        CheckResult.monitor_id == monitor_id,
        CheckResult.started_at >= start,
        CheckResult.started_at < end,
    )


@app.get("/api/monitors/{monitor_id}/checks", response_model=CheckPage)
async def list_checks(
    monitor_id: int, bounds: Window, db: DB,
    page: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    await require_monitor(db, monitor_id)
    results = (
        await db.scalars(
            select(CheckResult)
            .where(*window_checks(monitor_id, bounds))
            .order_by(CheckResult.started_at.desc(), CheckResult.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size + 1)
        )
    ).all()
    return {"items": results[:page_size], "page": page, "page_size": page_size, "has_more": len(results) > page_size}


@app.get("/api/monitors/{monitor_id}/metrics", response_model=Metrics)
async def get_metrics(monitor_id: int, bounds: Window, db: DB):
    await require_monitor(db, monitor_id)
    checks = (await db.execute(
        select(
            CheckResult.started_at, CheckResult.elapsed_ms, CheckResult.http_status,
            CheckResult.success, CheckResult.gap_before,
        )
        .where(*window_checks(monitor_id, bounds))
        .order_by(CheckResult.started_at, CheckResult.id)
    )).all()
    return {
        **window_statistics(checks),
        "points": [ChartPoint(
            started_at=check.started_at, response_ms=check.elapsed_ms if check.http_status is not None else None,
            success=check.success, gap_before=check.gap_before,
        ) for check in checks],
    }


@app.get("/api/monitors/{monitor_id}/incidents", response_model=list[IncidentView])
async def list_incidents(monitor_id: int, db: DB):
    await require_monitor(db, monitor_id)
    return (await db.scalars(
        select(Incident)
        .where(Incident.monitor_id == monitor_id)
        .order_by(Incident.confirmed_at.desc(), Incident.id.desc())
    )).all()


@app.get("/api/notifications", response_model=list[NotificationView])
async def list_notifications(db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    rows = await db.execute(
        select(
            Notification.id, Notification.incident_id, Notification.event_type,
            Notification.created_at, Notification.message,
            Monitor.id.label("monitor_id"), Monitor.name.label("monitor_name"),
        )
        .join(Incident, Incident.id == Notification.incident_id)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    return rows.mappings().all()
