import {
  Activity, ChevronLeft, CircleAlert, CircleCheck, Clock3, Gauge, History, Pause, Pencil, Play, Timer,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { MONITORS, request, send, type CheckPage, type Incident, type Metrics, type Monitor } from './api'
import { MonitorDialog } from './Dialogs'
import LatencyChart from './LatencyChart'
import { Badge, Empty, ErrorBanner, MetricCard, Timestamp, monitorStatus, ms } from './ui'
import { usePolling } from './usePolling'

const ranges = { '1h': 1, '24h': 24, '7d': 168 } as const
type Range = keyof typeof ranges

function IncidentTimeline({ incidents, monitor }: { incidents: Incident[]; monitor?: Monitor }) {
  const { hash } = useLocation()
  const target = incidents.find(incident => hash === `#incident-${incident.id}`)?.id
  useEffect(() => {
    if (target) {
      const article = document.getElementById(`incident-${target}`)
      article?.scrollIntoView({ block: 'nearest' })
      article?.focus({ preventScroll: true })
    }
  }, [target])

  if (!incidents.length) return <Empty>No incidents recorded.</Empty>
  return <ol className="incident-list">
    {incidents.map(incident => {
      const resolved = !!incident.resolved_at
      const recovering = !resolved && monitor?.awaiting_recovery
      const Icon = resolved ? CircleCheck : CircleAlert
      return <li key={incident.id} className="incident-item" id={`incident-${incident.id}`} tabIndex={-1}>
        <span className={`icon-tile ${resolved ? 'green' : recovering ? 'amber' : 'red'}`}><Icon size={17} /></span>
        <div className="incident-content">
          <div className="incident-title">
            <h3>Incident #{incident.id}</h3>
            <Badge tone={resolved ? 'green' : recovering ? 'amber' : 'red'}>
              {resolved ? 'Resolved' : recovering ? 'Awaiting confirmation' : 'Ongoing'}
            </Badge>
          </div>
          <dl className="incident-dates">
            <div><dt>First observed failure</dt><dd><Timestamp value={incident.first_failure_at} /></dd></div>
            <div><dt>Outage confirmed</dt><dd><Timestamp value={incident.confirmed_at} /></dd></div>
            <div><dt>Resolution</dt><dd>{incident.resolved_at ? <Timestamp value={incident.resolved_at} /> : 'Ongoing'}</dd></div>
          </dl>
        </div>
      </li>
    })}
  </ol>
}

function CheckHistory({ checks, onPage }: { checks: CheckPage; onPage: (page: number) => void }) {
  return <>
    {checks.items.length ? <div className="table-scroll" role="region" aria-label="Check history table" tabIndex={0}><table className="checks-table">
      <thead><tr><th>Started</th><th>Outcome</th><th>HTTP status</th><th>Elapsed</th><th>Observation</th></tr></thead>
      <tbody>{checks.items.map(check => (
        <tr key={check.id}>
          <td><Timestamp value={check.started_at} />{check.gap_before && <div className="cell-note">Gap before this check</div>}</td>
          <td><Badge tone={check.success ? 'green' : 'red'}>{check.success ? 'Passed' : 'Failed'}</Badge></td>
          <td className="numeric">{check.http_status ?? '—'}</td>
          <td className="numeric">{ms(check.elapsed_ms)}</td>
          <td>{check.failure_reason ?? '—'}</td>
        </tr>
      ))}</tbody>
    </table></div> : <Empty>No checks in this period.</Empty>}
    {(checks.page > 1 || checks.has_more) && <footer className="pagination">
      <span>Page {checks.page}</span>
      <button className="button button-secondary" disabled={checks.page === 1} onClick={() => onPage(checks.page - 1)}>Previous</button>
      <button className="button button-secondary" disabled={!checks.has_more} onClick={() => onPage(checks.page + 1)}>Next</button>
    </footer>}
  </>
}

function Detail({ id }: { id: string }) {
  const path = `${MONITORS}/${id}`
  const [range, setRange] = useState<Range>('24h')
  const [page, setPage] = useState(1)
  const [snapshot, setSnapshot] = useState<number>()
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const loadMonitor = useCallback((signal: AbortSignal) => request<Monitor>(path, { signal }), [path])
  const loadIncidents = useCallback((signal: AbortSignal) => request<Incident[]>(`${path}/incidents`, { signal }), [path])
  const loadWindow = useCallback(async (signal: AbortSignal) => {
    const end = snapshot ?? Date.now()
    const start = end - ranges[range] * 3600000
    const query = new URLSearchParams({ from: new Date(start).toISOString(), to: new Date(end).toISOString() })
    const [metrics, checks] = await Promise.all([
      request<Metrics>(`${path}/metrics?${query}`, { signal }),
      request<CheckPage>(`${path}/checks?${query}&page=${page}`, { signal }),
    ])
    return { metrics, checks, end }
  }, [path, range, page, snapshot])
  const { data: monitor, error, updated } = usePolling(path, loadMonitor, revision)
  const incidents = usePolling(`${path}/incidents`, loadIncidents)
  const history = usePolling(`${path}/${range}/${page}`, loadWindow)
  const metrics = history.data?.metrics
  const status = monitor && monitorStatus(monitor)

  function goToPage(next: number) {
    setSnapshot(next === 1 ? undefined : history.data?.end)
    setPage(next)
  }

  async function toggleEnabled() {
    if (!monitor) return
    setBusy(true)
    setActionError('')
    try {
      await send<Monitor>(path, 'PATCH', { enabled: !monitor.enabled })
      setRevision(value => value + 1)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not update the monitor.')
    } finally {
      setBusy(false)
    }
  }

  return <>
    <Link className="back-link text-link" to="/"><ChevronLeft size={17} />All monitors</Link>
    {!monitor && <div className="panel">{error ? <ErrorBanner>{error}</ErrorBanner> : <Empty>Loading monitor…</Empty>}</div>}
    {monitor && <>
      <header className="page-heading detail-heading">
        <div className="detail-title">
          <div className="title-line"><h1>{monitor.name}</h1>{status && <Badge tone={status[1]}>{status[0]}</Badge>}</div>
          <p><code>{monitor.url}</code></p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" disabled={busy} onClick={toggleEnabled}>
            {monitor.enabled ? <Pause size={16} /> : <Play size={16} />}{monitor.enabled ? 'Pause' : 'Resume'}
          </button>
          <button className="button button-primary" onClick={() => setEditing(true)}><Pencil size={16} />Edit monitor</button>
        </div>
      </header>
      {error && <ErrorBanner>Could not refresh monitor. {error}</ErrorBanner>}
      {actionError && <ErrorBanner>{actionError}</ErrorBanner>}
      <div className="config-strip">
        <span><Clock3 size={16} />Every {monitor.interval_seconds} s</span>
        <span><Timer size={16} />{monitor.timeout_seconds} s timeout</span>
        <span><Activity size={16} />Expects HTTP {monitor.expected_status}</span>
        {updated && <span className={`poll-state ${error ? 'stale' : ''}`}><span className="status-dot" />{error ? 'Updates interrupted' : 'Live'}</span>}
      </div>
      <div className="period-head">
        <h2>Performance</h2>
        <div className="segmented" role="group" aria-label="Time window">
          {(Object.keys(ranges) as Range[]).map(option => <button type="button" key={option}
            aria-pressed={option === range} onClick={() => {
              setRange(option)
              setPage(1)
              setSnapshot(undefined)
            }}>{option}</button>)}
        </div>
      </div>
      {history.error && <ErrorBanner>Could not refresh check history. {history.error}</ErrorBanner>}
      <div className="metric-grid detail-metrics">
        <MetricCard label="Observed availability" tone="green" icon={CircleCheck}
          value={metrics?.availability_percent != null
            ? `${metrics.availability_percent.toLocaleString(undefined, { maximumFractionDigits: 2 })}%` : '—'}
          caption={metrics ? `${metrics.successful_checks}/${metrics.total_checks} checks passed` : 'Completed checks'} />
        <MetricCard label="Mean response time" tone="blue" icon={Gauge} value={ms(metrics?.mean_ms ?? null)}
          caption={metrics ? `${metrics.response_samples} HTTP response samples` : 'HTTP response samples'} />
        <MetricCard label="P95 response time" tone="purple" icon={Timer} value={ms(metrics?.p95_ms ?? null)}
          caption="95th percentile · nearest rank" />
      </div>
      <div className="detail-grid">
        <section className="panel" aria-labelledby="latency-heading">
          <header className="panel-header"><div><h2 id="latency-heading">Response time</h2><p>Elapsed time to HTTP response headers</p></div></header>
          {metrics ? <LatencyChart points={metrics.points} /> : !history.error && <Empty>Loading response times…</Empty>}
        </section>
        <section className="panel timeline" aria-labelledby="incident-heading">
          <header className="panel-header">
            <div><h2 id="incident-heading">Incident timeline</h2><p>All recorded incidents</p></div>
            <span className="icon-tile neutral"><History size={18} /></span>
          </header>
          {incidents.error && <ErrorBanner>Could not refresh incidents. {incidents.error}</ErrorBanner>}
          {incidents.data ? <IncidentTimeline incidents={incidents.data} monitor={monitor} /> : !incidents.error && <Empty>Loading incidents…</Empty>}
        </section>
      </div>
      <section className="panel check-panel" aria-labelledby="checks-heading">
        <header className="panel-header">
          <div><h2 id="checks-heading">Check history</h2><p>Completed checks, newest first</p></div>
          {page > 1 && <button type="button" className="button button-secondary" onClick={() => goToPage(1)}>Latest checks</button>}
        </header>
        {history.data ? <CheckHistory checks={history.data.checks} onPage={goToPage} /> : !history.error && <Empty>Loading checks…</Empty>}
      </section>
      {editing && <MonitorDialog monitor={monitor} onClose={() => setEditing(false)} onSaved={() => {
        setEditing(false)
        setRevision(value => value + 1)
      }} />}
    </>}
  </>
}

export default function MonitorDetail() {
  const { id = '' } = useParams()
  return /^\d+$/.test(id) ? <Detail id={id} key={id} /> : <Empty>Monitor not found.</Empty>
}
