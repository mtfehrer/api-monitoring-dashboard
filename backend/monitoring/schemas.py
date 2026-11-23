import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, field_validator

from .config import validate_target

UTCDateTime = Annotated[
    datetime, PlainSerializer(lambda value: value.astimezone(UTC).isoformat(), return_type=str)
]
MonitorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Interval = Annotated[int, Field(strict=True, ge=5, le=3600)]
Timeout = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
StatusCode = Annotated[int, Field(strict=True, ge=100, le=599)]
RequestMethod = Literal["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
HEADER_VALUE = re.compile(r"[\t\x20-\x7e]*")
MANAGED_HEADERS = {
    "connection", "content-length", "expect", "host", "keep-alive", "proxy-authorization",
    "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
}


def validate_headers(headers: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for name, value in headers.items():
        if not HEADER_NAME.fullmatch(name):
            raise ValueError("Enter valid HTTP header names.")
        name = name.lower()
        if name in MANAGED_HEADERS:
            raise ValueError(f"The checker manages the {name} header.")
        if name in normalized:
            raise ValueError("Each header name can be used once.")
        if not HEADER_VALUE.fullmatch(value):
            raise ValueError("Header values must use ASCII and fit on one line.")
        normalized[name] = value.strip(" \t")
    return normalized


def validate_body(body: str) -> str:
    try:
        body.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Enter a UTF-8 text body.") from exc
    if "\x00" in body:
        raise ValueError("Request body cannot contain null characters.")
    return body


RequestHeaders = Annotated[dict[str, str], Field(max_length=50), AfterValidator(validate_headers)]
RequestBody = Annotated[str, StringConstraints(max_length=65536), AfterValidator(validate_body)]


class MonitorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: MonitorName
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    method: RequestMethod = "GET"
    request_headers: RequestHeaders = Field(default_factory=dict, repr=False)
    request_body: RequestBody | None = Field(default=None, repr=False)
    interval_seconds: Interval = 60
    expected_status: StatusCode = 200
    timeout_seconds: Timeout = 5

    validate_url = field_validator("url")(validate_target)


class MonitorEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: MonitorName | None = None
    method: RequestMethod | None = None
    request_headers: RequestHeaders | None = Field(default=None, repr=False)
    request_body: RequestBody | None = Field(default=None, repr=False)
    interval_seconds: Interval | None = None
    timeout_seconds: Timeout | None = None
    enabled: Annotated[bool, Field(strict=True)] | None = None

    @field_validator("name", "method", "request_headers", "interval_seconds", "timeout_seconds", "enabled")
    @classmethod
    def disallow_null(cls, value):
        if value is None:
            raise ValueError("Provide a value for this field.")
        return value


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Check(Record):
    id: int
    monitor_id: int
    scheduled_at: UTCDateTime
    started_at: UTCDateTime
    finished_at: UTCDateTime
    elapsed_ms: int
    success: bool
    http_status: int | None
    failure_reason: str | None
    gap_before: bool


class IncidentView(Record):
    id: int
    first_failure_at: UTCDateTime
    confirmed_at: UTCDateTime
    resolved_at: UTCDateTime | None


class MonitorView(Record):
    id: int
    name: str
    url: str
    method: RequestMethod
    has_request_headers: bool
    has_request_body: bool
    interval_seconds: int
    expected_status: int
    timeout_seconds: float
    enabled: bool
    created_at: UTCDateTime
    next_run_at: UTCDateTime | None
    latest_check: Check | None = None
    open_incident: IncidentView | None = None
    awaiting_recovery: bool = False
    overdue: bool = False


class CheckPage(BaseModel):
    items: list[Check]
    page: int
    page_size: int
    has_more: bool


class ChartPoint(BaseModel):
    started_at: UTCDateTime
    response_ms: int | None
    success: bool
    gap_before: bool


class Metrics(BaseModel):
    total_checks: int
    successful_checks: int
    availability_percent: float | None
    response_samples: int
    mean_ms: float | None
    p95_ms: int | None
    points: list[ChartPoint]


class NotificationView(Record):
    id: int
    incident_id: int
    monitor_id: int
    monitor_name: str
    event_type: Literal["outage", "recovery"]
    created_at: UTCDateTime
    message: str
