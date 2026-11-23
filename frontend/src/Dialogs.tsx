import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { FlaskConical } from 'lucide-react'
import { ApiError, DEMO_CONTROL, MONITORS, REQUEST_METHODS, request, send, type DemoBehavior, type DemoEndpoint, type Monitor } from './api'
import { ErrorBanner, Modal } from './ui'

function Field({ name, label, error, children }: {
  name: string; label: string; error?: string; children: ReactNode
}) {
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      {children}
      {error && <span className="field-error" id={`${name}-error`}>{error}</span>}
    </div>
  )
}

export function MonitorDialog({ monitor, onClose, onSaved }: {
  monitor?: Monitor; onClose: () => void; onSaved: (result: Monitor) => void
}) {
  const [name, setName] = useState(monitor?.name ?? '')
  const [url, setUrl] = useState(monitor?.url ?? '')
  const [method, setMethod] = useState<Monitor['method']>(monitor?.method ?? 'GET')
  const [headers, setHeaders] = useState('')
  const [body, setBody] = useState('')
  const [replaceHeaders, setReplaceHeaders] = useState(false)
  const [replaceBody, setReplaceBody] = useState(false)
  const [interval, setInterval] = useState(String(monitor?.interval_seconds ?? 60))
  const [timeout, setTimeout] = useState(String(monitor?.timeout_seconds ?? 5))
  const [status, setStatus] = useState(String(monitor?.expected_status ?? 200))
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')

  function field(name: string, hint?: string) {
    return {
      id: name, name,
      'aria-invalid': !!errors[name],
      'aria-describedby': [hint, errors[name] && `${name}-error`].filter(Boolean).join(' ') || undefined,
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    const saveHeaders = replaceHeaders || (!monitor?.has_request_headers && headers.trim() !== '')
    const saveBody = replaceBody || (!monitor?.has_request_body && body !== '')
    const requestHeaders = new Map<string, string>()
    for (const line of saveHeaders ? headers.split('\n') : []) {
      if (!line.trim()) continue
      const separator = line.indexOf(':')
      const name = line.slice(0, separator).trim().toLowerCase()
      if (separator < 1 || !name || requestHeaders.has(name)) {
        setErrors({ request_headers: 'Enter one unique header per line in Name: value format.' })
        return
      }
      requestHeaders.set(name, line.slice(separator + 1).trim())
    }
    setBusy(true)
    setErrors({})
    const editable = {
      name, interval_seconds: Number(interval), timeout_seconds: Number(timeout),
      ...(method !== monitor?.method && { method }),
      ...(saveHeaders && { request_headers: Object.fromEntries(requestHeaders) }),
      ...(saveBody && { request_body: body || null }),
    }
    try {
      const saved = monitor
        ? await send<Monitor>(`${MONITORS}/${monitor.id}`, 'PATCH', editable)
        : await send<Monitor>(MONITORS, 'POST', { ...editable, url, expected_status: Number(status) })
      onSaved(saved)
    } catch (failure) {
      if (failure instanceof ApiError && Object.keys(failure.fields).length) setErrors(failure.fields)
      else setError(failure instanceof Error ? failure.message : 'Could not save the monitor.')
    } finally {
      setBusy(false)
    }
  }

  function useDemo() {
    setName('Demo API')
    setUrl('http://demo:8001/health/primary')
    setMethod('GET')
    setHeaders('')
    setBody('')
    setInterval('5')
    setTimeout('2')
    setStatus('200')
    setErrors({})
  }

  return (
    <Modal title={monitor ? 'Edit monitor' : 'Add monitor'} onClose={onClose}>
      <form className="dialog-body" onSubmit={submit} noValidate>
        {!monitor && <button className="button button-secondary preset" type="button" onClick={useDemo}>
          <FlaskConical size={16} />Use demo endpoint
        </button>}
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <Field name="name" label="Name" error={errors.name}>
          <input {...field('name')} value={name} onChange={event => setName(event.target.value)}
            placeholder="Orders API" required maxLength={100} autoFocus />
        </Field>
        <div className="request-target">
          <Field name="method" label="Method" error={errors.method}>
            <select {...field('method')} value={method} onChange={event => setMethod(event.target.value as Monitor['method'])}>
              {REQUEST_METHODS.map(option => <option key={option}>{option}</option>)}
            </select>
          </Field>
          <Field name="url" label="Endpoint URL" error={errors.url}>
            <input {...field('url')} type="url" value={url} onChange={event => setUrl(event.target.value)}
              placeholder="https://api.example.com/health" required readOnly={!!monitor} />
          </Field>
        </div>
        <div className="field-grid">
          <Field name="interval_seconds" label="Interval (s)" error={errors.interval_seconds}>
            <input {...field('interval_seconds')} type="number" value={interval} min={5} max={3600}
              onChange={event => setInterval(event.target.value)} required />
          </Field>
          <Field name="timeout_seconds" label="Timeout (s)" error={errors.timeout_seconds}>
            <input {...field('timeout_seconds')} type="number" value={timeout} min={0} step="any"
              onChange={event => setTimeout(event.target.value)} required />
          </Field>
          <Field name="expected_status" label="Expected status" error={errors.expected_status}>
            <input {...field('expected_status')} type="number" value={status} min={100} max={599}
              onChange={event => setStatus(event.target.value)} required readOnly={!!monitor} />
          </Field>
        </div>
        {monitor?.has_request_headers && <label className="request-option">
          <input type="checkbox" checked={replaceHeaders} onChange={event => setReplaceHeaders(event.target.checked)} />
          Replace saved headers
        </label>}
        {(!monitor?.has_request_headers || replaceHeaders) &&
          <Field name="request_headers" label="Request headers (optional)" error={errors.request_headers}>
            <textarea {...field('request_headers', 'headers-hint')} rows={2} value={headers}
              onChange={event => setHeaders(event.target.value)} placeholder="Accept: application/json"
              autoComplete="off" spellCheck={false} />
            <span className="muted" id="headers-hint">
              {replaceHeaders ? 'Leave blank to clear saved headers. ' : ''}Use one Name: value pair per line.
            </span>
          </Field>}
        {monitor?.has_request_body && <label className="request-option">
          <input type="checkbox" checked={replaceBody} onChange={event => setReplaceBody(event.target.checked)} />
          Replace saved body
        </label>}
        {(!monitor?.has_request_body || replaceBody) &&
          <Field name="request_body" label="Request body (optional)" error={errors.request_body}>
            <textarea {...field('request_body', 'body-hint')} rows={2} value={body} maxLength={65536}
              onChange={event => setBody(event.target.value)} autoComplete="off" spellCheck={false} />
            <span className="muted" id="body-hint">
              {replaceBody ? 'Leave blank to clear the saved body. ' : ''}Set a Content-Type header if the API requires one.
            </span>
          </Field>}
        <footer className="dialog-actions">
          <button className="button button-secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : monitor ? 'Save changes' : 'Create monitor'}
          </button>
        </footer>
      </form>
    </Modal>
  )
}

const modeLabels: Record<DemoBehavior['mode'], string> = {
  healthy: 'Healthy · 200', unavailable: 'Unavailable · 503', delayed: 'Delayed · 200',
}
const endpoints: DemoEndpoint[] = ['primary', 'secondary']

function DemoEndpointControl({ endpoint, initial }: { endpoint: DemoEndpoint; initial: DemoBehavior }) {
  const [saved, setSaved] = useState(initial)
  const [mode, setMode] = useState(initial.mode)
  const [delay, setDelay] = useState(String(initial.delay_ms))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const label = endpoint === 'primary' ? 'Primary endpoint' : 'Secondary endpoint'

  async function apply(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const behavior = await send<DemoBehavior>(`${DEMO_CONTROL}/${endpoint}`, 'PUT', {
        mode, delay_ms: mode === 'delayed' ? Number(delay) : saved.delay_ms,
      })
      setSaved(behavior)
    } catch (failure) {
      const message = failure instanceof ApiError
        ? Object.values(failure.fields)[0] ?? failure.message
        : 'Could not update the demo endpoint.'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="demo-control" onSubmit={apply} aria-label={label}>
      <h3>{label}</h3>
      <code>http://demo:8001/health/{endpoint}</code>
      <p className="muted" role="status">
        Current mode: {modeLabels[saved.mode]}{saved.mode === 'delayed' ? ` after ${saved.delay_ms} ms` : ''}
      </p>
      <div className="demo-inputs">
        <Field label="Mode" name={`${endpoint}-mode`}>
          <select id={`${endpoint}-mode`} value={mode} onChange={event => setMode(event.target.value as DemoBehavior['mode'])}>
            {Object.entries(modeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        {mode === 'delayed' && <Field label="Delay (ms)" name={`${endpoint}-delay`}>
          <input id={`${endpoint}-delay`} type="number" required min={1} max={30000} value={delay}
            onChange={event => setDelay(event.target.value)} />
        </Field>}
        <button type="submit" disabled={busy} className="button button-primary">{busy ? 'Applying…' : 'Apply'}</button>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </form>
  )
}

export function DemoControls({ onClose }: { onClose: () => void }) {
  const [behaviors, setBehaviors] = useState<Record<DemoEndpoint, DemoBehavior>>()
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    request<Record<DemoEndpoint, DemoBehavior>>(DEMO_CONTROL, { signal: controller.signal })
      .then(setBehaviors)
      .catch(() => { if (!controller.signal.aborted) setError('Unable to reach the demo service.') })
    return () => controller.abort()
  }, [])
  return (
    <Modal title="Demo controls" onClose={onClose}>
      <div className="dialog-body">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {!behaviors && !error && <p className="muted">Loading demo endpoints…</p>}
        {behaviors && endpoints.map(endpoint =>
          <DemoEndpointControl key={endpoint} endpoint={endpoint} initial={behaviors[endpoint]} />)}
      </div>
    </Modal>
  )
}
