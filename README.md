# API Monitoring Dashboard

Monitor HTTP health endpoints from a local React dashboard. The checker records real requests, opens an incident after three consecutive failures, and confirms recovery after two consecutive successes.

![Monitoring overview showing an outage on Orders API and a slow, healthy Catalog API](docs/overview.png)

## Start locally

Install Docker with Compose, then run from the repository root.

```sh
docker compose up --build --wait
```

Open the [dashboard](http://127.0.0.1:8080). In **Add monitor**, choose **Use demo endpoint** and then **Create monitor**. The preset checks `http://demo:8001/health/primary` every five seconds with a two-second timeout. The first check is due immediately, and the dashboard refreshes every five seconds.

The [API reference](http://127.0.0.1:8000/docs) and [demo endpoint controls](http://127.0.0.1:8001/docs) are also available on loopback. Run `docker compose down` to stop the stack. PostgreSQL stores monitors, observations, incidents, and notifications in the `monitoring-data` volume.

## Walk through an outage

1. Wait for the first passing check on the primary demo endpoint.
2. Open **Demo controls**. For **Primary endpoint**, select **Unavailable · 503** and click **Apply**. The first two failures appear in check history. The third opens an incident and posts an outage notification.
3. Set the endpoint back to **Healthy · 200**. The first success leaves recovery awaiting confirmation, and the second resolves the incident and posts a recovery notification.
4. Follow either notification to the incident timeline to see the first observed failure, the confirmation time, and the resolution time. The check history underneath shows the individual requests.

For a second monitor, use `http://demo:8001/health/secondary`, a five-second interval, and a two-second timeout. A delay of **500 ms** still returns HTTP 200 and raises response times. A delay of **3,000 ms** records a timeout with a two-second elapsed wait. That check counts toward availability and has no response-time sample. The other endpoint continues on its own schedule.

You can also control the demo from the command line. Each endpoint's mode can be set independently to `healthy`, `unavailable`, or `delayed`. Demo modes start healthy when the demo service restarts.

```sh
curl -fsS -X PUT http://127.0.0.1:8001/control/primary \
  -H 'Content-Type: application/json' -d '{"mode":"unavailable"}'

curl -fsS -X PUT http://127.0.0.1:8001/control/primary \
  -H 'Content-Type: application/json' -d '{"mode":"healthy"}'
```

![Monitor detail showing failed checks, a timeout, and a resolved incident](docs/monitor-detail.png)

## Configuration and history

- The API and checker accept exact hostnames from `ALLOWED_MONITOR_HOSTS`. To permit another endpoint, set a comma-separated list in the Compose `.env`, for example `ALLOWED_MONITOR_HOSTS=demo,health.example.com`. Use hostnames reachable from the checker container. The default allowlist is `demo`.
- Use `DASHBOARD_PORT`, `API_PORT`, and `DEMO_PORT` to change the loopback ports. `CHECKER_CONCURRENCY` defaults to eight. Run a single checker instance.
- You can edit a monitor's name, interval, and timeout. Editing the interval uses the pending scheduled slot as the cadence anchor. Create a separate monitor to change the URL or expected status.
- Pausing clears pending failure and recovery streaks. Resuming schedules a fresh check. Scheduler downtime skips elapsed slots and breaks streaks. A request already in flight during a pause can appear in history without affecting the incident.
- Checks and metrics share the half-open window `from <= started_at < to`. Use offset-bearing timestamps for `from` and `to`. The default is the preceding 24 hours. Checks are newest first and accept `page` and `page_size`. API timestamps use UTC.

## Tests

GitHub Actions runs Pytest against PostgreSQL 17, checks the Alembic schema, and builds the frontend. To run the same checks locally, start a disposable PostgreSQL database and point the tests at it. The integration suite creates its own temporary schema.

```sh
docker run --rm -d --name api-monitoring-test-db -p 127.0.0.1:55432:5432 \
  -e POSTGRES_DB=monitoring -e POSTGRES_USER=monitor -e POSTGRES_PASSWORD=monitor \
  postgres:17-alpine
until docker exec api-monitoring-test-db pg_isready -h 127.0.0.1 -U monitor -d monitoring; do sleep 1; done

python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
export TEST_DATABASE_URL=postgresql+psycopg://monitor:monitor@127.0.0.1:55432/monitoring
(cd backend && DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head &&
  DATABASE_URL="$TEST_DATABASE_URL" alembic check && python -m pytest)
docker stop api-monitoring-test-db

(cd frontend && npm ci && npm run build)
```

## How it fits together

FastAPI serves monitor configuration and history. An asyncio checker claims due slots in PostgreSQL, sends one streaming HTTPX GET per slot, and measures time to the response headers. The checker writes each result, incident transition, and notification in one transaction. PostgreSQL constraints deduplicate replays and enforce one open incident per monitor. Nginx serves the React dashboard and proxies its API requests. Recharts plots HTTP response samples and shows interruptions in the series.

[Original specification](api-monitoring-dashboard-specification.md)
