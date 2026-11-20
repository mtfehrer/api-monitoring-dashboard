import { Activity, Bell, CircleAlert, CircleCheck, CirclePause, Layers3, Plus, Radar } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { MONITORS, request, type Event, type Monitor } from './api'
import { MonitorDialog } from './Dialogs'
import { Badge, Empty, ErrorBanner, MetricCard, Timestamp, incidentLink, monitorLink, monitorStatus, ms } from './ui'
import { usePolling } from './usePolling'

const loadMonitors = (signal: AbortSignal) => request<Monitor[]>(MONITORS, { signal })
const loadEvents = (signal: AbortSignal) => request<Event[]>('/api/notifications', { signal })

export function Overview() {
  const [creating, setCreating] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const monitors = usePolling('monitors', loadMonitors)
  const events = usePolling('notifications', loadEvents)
  const list = monitors.data ?? []
  const counts = monitors.data ? {
    total: list.length,
    healthy: list.filter(monitor => monitorStatus(monitor)[0] === 'Healthy' && !monitor.open_incident).length,
    open: list.filter(monitor => monitor.open_incident).length,
    paused: list.filter(monitor => !monitor.enabled).length,
  } : undefined

  useEffect(() => {
    if (location.hash === '#notifications') document.getElementById('notifications')?.scrollIntoView()
  }, [location.hash])

  return (
    <>
      <header className="page-heading">
        <div>
          <h1>Monitoring overview</h1>
          <p>Endpoint health, response times, and recent incidents.</p>
        </div>
        <button className="button button-primary" onClick={() => setCreating(true)}><Plus size={18} />Add monitor</button>
      </header>
      <div className="metric-grid overview-metrics">
        <MetricCard label="Monitors" value={counts?.total ?? '—'} caption="Configured endpoints" tone="blue" icon={Layers3} />
        <MetricCard label="Healthy" value={counts?.healthy ?? '—'} caption="Passing, with no open incident" tone="green" icon={CircleCheck} />
        <MetricCard label="Open incidents" value={counts?.open ?? '—'} caption="Confirmed outages" tone="red" icon={CircleAlert} />
        <MetricCard label="Paused" value={counts?.paused ?? '—'} caption="Scheduled checks paused" tone="neutral" icon={CirclePause} />
      </div>
      <div className="overview-grid">
        <section className="panel" aria-labelledby="monitors-heading">
          <header className="panel-header">
            <div><h2 id="monitors-heading">Endpoint monitors</h2><p>Latest observation for each endpoint</p></div>
            {monitors.updated && <span className={`poll-state ${monitors.error ? 'stale' : ''}`}>
              <span className="status-dot" />{monitors.error ? 'Updates interrupted' : 'Live'}
            </span>}
          </header>
          {monitors.error && <ErrorBanner>Could not refresh monitors. {monitors.error}</ErrorBanner>}
          {!monitors.data && !monitors.error && <Empty>Loading monitors…</Empty>}
          {monitors.data?.length === 0 && <Empty>
            <span className="icon-tile blue"><Radar size={23} /></span>
            <strong>No monitors yet</strong>
            <p>Add a health endpoint to start recording checks.</p>
            <button className="button button-secondary" onClick={() => setCreating(true)}>Add monitor</button>
          </Empty>}
          {list.length > 0 && <div className="table-scroll" role="region" aria-label="Endpoint monitor table" tabIndex={0}><table>
            <thead><tr><th>Endpoint</th><th>Status</th><th>Last check</th><th>Response</th><th>Incident</th></tr></thead>
            <tbody>{list.map(monitor => {
              const check = monitor.latest_check
              const [label, tone] = monitorStatus(monitor)
              return <tr key={monitor.id}>
                <td>
                  <Link className="row-link" to={monitorLink(monitor.id)}>
                    <span className="endpoint-icon"><Activity size={17} /></span>
                    <span className="endpoint-name"><strong>{monitor.name}</strong><code title={monitor.url}>{monitor.url}</code></span>
                  </Link>
                </td>
                <td><Badge tone={tone}>{label}</Badge>
                  {check && <div className="cell-note" title={check.failure_reason ?? undefined}>
                    {(!monitor.enabled || monitor.overdue) && (check.success ? 'Passed · ' : 'Failed · ')}
                    {check.http_status === null ? check.failure_reason : `HTTP ${check.http_status}`}
                  </div>}
                </td>
                <td>{check ? <Timestamp value={check.started_at} /> : '—'}</td>
                <td className="numeric">{check?.http_status != null ? ms(check.elapsed_ms) : '—'}</td>
                <td>{monitor.open_incident
                  ? <Link className={`text-link ${monitor.awaiting_recovery ? 'amber-text' : 'red-text'}`}
                      to={incidentLink(monitor.id, monitor.open_incident.id)}>
                      {monitor.awaiting_recovery ? 'Awaiting recovery' : 'Ongoing'}
                    </Link>
                  : '—'}</td>
              </tr>
            })}</tbody>
          </table></div>}
        </section>
        <section className="panel notifications" id="notifications" aria-labelledby="notifications-heading">
          <header className="panel-header">
            <div><h2 id="notifications-heading">Notifications</h2><p>Outages and recoveries</p></div>
            <span className="icon-tile neutral"><Bell size={18} /></span>
          </header>
          {events.error && <ErrorBanner>Could not refresh notifications. {events.error}</ErrorBanner>}
          {!events.data && !events.error && <Empty>Loading notifications…</Empty>}
          {events.data?.length === 0 && <Empty><strong>No notifications yet</strong><p>Outages and recoveries will appear here.</p></Empty>}
          {!!events.data?.length && <ul className="notification-list">
            {events.data.map(event => {
              const recovery = event.event_type === 'recovery'
              const Icon = recovery ? CircleCheck : CircleAlert
              return <li key={event.id}>
                <Link className="notification" to={incidentLink(event.monitor_id, event.incident_id)}>
                  <span className={`icon-tile ${recovery ? 'green' : 'red'}`}><Icon size={18} /></span>
                  <span><strong>{event.message}</strong><Timestamp value={event.created_at} /></span>
                </Link>
              </li>
            })}
          </ul>}
        </section>
      </div>
      {creating && <MonitorDialog onClose={() => setCreating(false)} onSaved={monitor => {
        setCreating(false)
        navigate(monitorLink(monitor.id))
      }} />}
    </>
  )
}
