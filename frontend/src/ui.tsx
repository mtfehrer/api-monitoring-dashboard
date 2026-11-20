import {
  CircleAlert, X, type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import type { Monitor } from './api'

export const monitorLink = (id: number) => `/monitors/${id}`
export const incidentLink = (id: number, incident: number) => `${monitorLink(id)}#incident-${incident}`

const dateFormat = new Intl.DateTimeFormat(undefined, {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit',
})
export const timeLabel = (value: string) => dateFormat.format(new Date(value))
export const ms = (value: number | null) =>
  value === null ? '—' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`

export function Timestamp({ value }: { value: string }) {
  return <time dateTime={value} title={value}>{timeLabel(value)}</time>
}

export function monitorStatus(monitor: Monitor) {
  if (!monitor.enabled) return ['Paused', 'neutral'] as const
  if (monitor.overdue) return ['Overdue', 'amber'] as const
  if (!monitor.latest_check) return ['Pending', 'neutral'] as const
  return monitor.latest_check.success ? ['Healthy', 'green'] as const : ['Failing', 'red'] as const
}

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}><span className="status-dot" />{children}</span>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return <div className="error-banner" role="alert"><CircleAlert size={17} />{children}</div>
}

export function MetricCard({ label, value, caption, tone, icon: Icon }: {
  label: string; value: ReactNode; caption: string; tone: string; icon: LucideIcon
}) {
  return (
    <div className="metric-card">
      <span className={`icon-tile ${tone}`}><Icon size={19} strokeWidth={2} /></span>
      <div className="metric-copy">
        <h2>{label}</h2>
        <div className="metric-value">{value}</div>
        <p>{caption}</p>
      </div>
    </div>
  )
}

export function Modal({ title, onClose, children }: {
  title: string; onClose: () => void; children: ReactNode
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current!
    element.showModal()
    return () => element.close()
  }, [])
  return (
    <dialog ref={dialog} aria-labelledby="dialog-title" onCancel={event => {
      event.preventDefault()
      onClose()
    }}>
      <header className="dialog-header">
        <h2 id="dialog-title">{title}</h2>
        <button className="icon-button" type="button" aria-label="Close dialog" onClick={onClose}><X size={20} /></button>
      </header>
      {children}
    </dialog>
  )
}

