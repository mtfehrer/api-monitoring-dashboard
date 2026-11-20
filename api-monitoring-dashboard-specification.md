# API Monitoring Dashboard

## What the project does

A developer registers a health endpoint and chooses how often to check it. The application sends HTTP requests on that schedule, records each outcome, and displays response times and availability. When failures persist, it opens an incident. The developer can see when the trouble started, inspect the individual failures, and see when the endpoint recovered.

The portfolio demo should answer three questions from real, locally generated data: **Which endpoint needs attention? What did the monitor observe? Has the service recovered?** A small demo API with switchable behavior makes the whole sequence reproducible from a clean checkout.

## First release

Build a single-user application that runs with Docker Compose. It includes monitor configuration, scheduled HTTP GET checks, a React dashboard, incident history, and in-app notifications. The implementation choices below are defaults for the first release. Hosted deployment, authentication, email or webhook delivery, and multi-region checks can follow independently.

### 1. Configure a monitor

| Field | First-release behavior |
| --- | --- |
| Name | Required display name, such as `Orders API`. |
| URL | Absolute HTTP or HTTPS URL for a health endpoint. A locally configured list of permitted hosts includes the demo service. |
| Check interval | Seconds between scheduled starts. Default 60. Allow 5–3,600 so a live demo can run quickly. |
| Expected status | One HTTP status code. Default 200. A different code counts as a failure. |
| Timeout | Total request deadline in seconds. Default 5 and require it to be shorter than the interval. |
| Enabled | Enabled on creation. Pausing preserves check results and incidents. Resuming schedules a fresh check immediately. |

A new monitor is due immediately. Users can edit its name, interval, and timeout. To track a different URL or expected status, create a separate monitor so the original history keeps its meaning. Reject invalid settings before saving them and identify the field that needs correction.

### 2. Run checks and record observations

A single scheduler reads enabled monitors whose `next_run_at` is due in PostgreSQL. An asynchronous worker uses HTTPX to issue one GET per scheduled check, with bounded concurrency across monitors and at most one active check per monitor. Disable redirect following so the result reflects the configured endpoint. A 503, timeout, or connection failure produces one failed observation. The worker waits for the next interval before probing again.

For each completed attempt, record the monitor, scheduled time, start and finish times, elapsed milliseconds, outcome, HTTP status if received, and a short failure reason where applicable. Measure elapsed time through receipt of response headers. Discard the body. Store timestamps in UTC.

Schedule the next future slot from the previous scheduled time so slow checks do not shift the cadence. If the checker was offline, resume with one current check and skip elapsed slots. Gaps in monitoring remain visible. A service restart must preserve completed checks, incidents, and configuration. An interrupted request can leave a gap.

### 3. Detect incidents and recovery

Evaluate completed checks for each monitor in scheduled order. Persist a check and its effects on incident state together. Reprocessing the same scheduled observation must have no additional effect.

| Condition | Recorded event and dashboard behavior |
| --- | --- |
| First or second consecutive failure | Show the failed check and reason. Keep the incident count unchanged. |
| Third consecutive failure | Open one incident and create one in-app outage notification. Record both the first failure in the streak and the time the third failure confirmed the outage. |
| Further failures during an open incident | Append the checks to history. The same incident stays open. |
| First success during an open incident | Show the successful check and mark recovery as awaiting confirmation. An intervening failure resets the recovery count. |
| Second consecutive success | Resolve the incident at the completion time of this check and create one recovery notification. A later outage gets a new incident. |

A success resets a pending failure streak. Pausing a monitor resets pending streaks and leaves any open incident visible. After resumption, two fresh successes are required to resolve it. A missed scheduled slot provides no evidence about the endpoint and breaks a pending streak.

### 4. Display health and history

**Overview.** Show one row per monitor with its name, latest check outcome and HTTP status or error, last check time, last response time if available, and any open incident. Distinguish pending and paused monitors. Mark an enabled monitor as overdue when a scheduled check is more than one full interval late without a completed result. Link each row to its detail view. Show outage and recovery notifications with their timestamps and links to the affected incident.

**Monitor detail.** Show a latency chart, availability and response-time summaries, a newest-first check table, and an incident timeline. Offer 1-hour, 24-hour, and 7-day windows, defaulting to 24 hours. Display each incident's first observed failure, confirmation time, and resolution time or “Ongoing.” Poll the API every five seconds during the demo so that changes appear without a manual refresh.

| Measurement | Definition |
| --- | --- |
| Observed availability | Successful completed checks divided by all completed checks in the window, expressed as a percentage. Show the counts, for example 18/20 = 90%. Missed or paused slots are excluded. |
| Mean and p95 response time | Use elapsed milliseconds for checks that received HTTP response headers, including error responses. Compute p95 using the nearest-rank method. Timeouts and connection failures have no response-time sample. |
| Chart | Plot response time against check time, mark failures, and break the line across observation gaps. Show timeouts in history with their elapsed wait and reason. |
| Empty window | Show “No checks in this period.” If checks exist but none received a response, show availability and leave response-time statistics unavailable. |

## Implementation

Use **FastAPI, SQLAlchemy, Alembic, and PostgreSQL** for the API and persistence, **Python asyncio and HTTPX** for scheduled checks, and **React, TypeScript, and Recharts** for the dashboard. Compose runs the API, checker, database, frontend, and demo endpoint. The checker can contain the scheduler and workers in one process. A single checker instance keeps the first release small enough to explain and test.

| PostgreSQL table | Records and integrity rules |
| --- | --- |
| `monitors` | Configuration, enabled flag, and next scheduled time. Index enabled monitors by due time. |
| `check_results` | Observations with a unique key on monitor ID and scheduled time. Index monitor ID and check time for window queries. |
| `incidents` | Monitor ID, first failure time, confirmation time, and nullable resolution time. A partial unique index allows one unresolved incident per monitor. |
| `notifications` | Incident ID, event type, timestamp, and message. Enforce uniqueness on incident ID and event type. |

Advance the schedule in a short database transaction and perform HTTP I/O outside it. On completion, lock the monitor row while recording the outcome and incident transition. If the insert hits the scheduled-check uniqueness constraint, treat it as already processed. A pause that takes effect during a request may retain the observation for history, but that request must not advance an incident streak across the pause.

| REST endpoint | Purpose |
| --- | --- |
| `POST /api/monitors` | Validate and create a monitor. Return the new monitor with HTTP 201. |
| `GET /api/monitors` | List monitors with the current summary needed for the overview. |
| `GET /api/monitors/{id}` | Read configuration, latest observation, and current incident. |
| `PATCH /api/monitors/{id}` | Edit settings, pause, or resume. |
| `GET /api/monitors/{id}/checks` | Read paginated check history for a time window. |
| `GET /api/monitors/{id}/metrics` | Return window totals, mean and p95 response times, and chart data. |
| `GET /api/monitors/{id}/incidents` | Read incident history, including open incidents. |
| `GET /api/notifications` | Read recent outage and recovery events. |

Use a consistent half-open time window (`from <= started_at < to`) for checks and metrics. Use UTC timestamps with an explicit offset in API responses. Return HTTP 404 for an unknown monitor and HTTP 422 for invalid configuration or an invalid window.

## Build order

1. **Make one endpoint observable.** Bring up PostgreSQL, FastAPI, the checker, and a demo endpoint. Create a monitor through the API and retrieve its first persisted check.
2. **Make the history useful.** Build the overview and detail screens. Add a second monitor and a slow-response mode to demonstrate the difference between degraded response time and a failed check.
3. **Make outages reproducible.** Implement incident transitions and in-app notifications. Give the local demo endpoint healthy (200), unavailable (503), and delayed-response modes that the presenter can switch on demand.
4. **Verify and package the demo.** Use Pytest for transition and metric tests and PostgreSQL integration tests for persistence and deduplication. Run tests in GitHub Actions. Include startup instructions, outage controls, and a screenshot or short recording in the repository README.

## Acceptance checks

| Scenario | Passing result |
| --- | --- |
| Clean checkout | Following the README starts the stack locally and produces a real check without cloud credentials. |
| Outage and recovery | Starting healthy, feed 503, 503, 503, 503, 200, 503, 200, 200. One incident opens on check 3 and resolves on check 8. The dashboard shows exactly one outage notification and one recovery notification. |
| Short disruption | Two failures followed by a success remain visible in history and produce zero incidents. |
| Timeout | Delay a response beyond the monitor deadline. The check records a timeout, contributes to the availability denominator, and adds no latency sample. Another due monitor continues to receive checks. |
| Metric fixture | For successful responses at 100 and 200 ms, a 503 at 300 ms, and one timeout, the detail page shows 2/4 availability (50%), 200 ms mean, and 300 ms p95. |
| Pause and restart | Paused monitors accumulate no scheduled checks. Restarting the checker preserves history, skips missed slots, and creates no duplicate incidents or notifications. |
| Replayed result | Process the third failing check twice. The database contains one result for that slot, one open incident, and one outage notification. |

For the portfolio walkthrough, register the demo endpoint with a five-second interval and a two-second timeout. Show one successful check, switch the endpoint to 503, wait for the incident, then restore 200 and watch recovery. Finish on the incident timeline so a reviewer can trace both notifications back to the checks that triggered them.
