import { Activity, Bell, FlaskConical, LayoutDashboard } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { DemoControls } from './Dialogs'

export function Frame({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [demo, setDemo] = useState(false)
  const inDetail = location.pathname.startsWith('/monitors/')
  const inNotifications = location.hash === '#notifications'
  useEffect(() => {
    if (!location.hash) window.scrollTo({ top: 0 })
  }, [location.pathname, location.hash])

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <span className="brand-mark"><Activity size={24} strokeWidth={2.5} /></span>
          <span>API Monitor</span>
        </Link>
        <nav aria-label="Main navigation">
          <Link to="/" className={!inNotifications ? 'nav-link active' : 'nav-link'}
            aria-current={location.pathname === '/' && !inNotifications ? 'page' : undefined}>
            <LayoutDashboard size={18} />Overview
          </Link>
          <Link to="/#notifications" className={inNotifications ? 'nav-link active' : 'nav-link'}
            aria-current={inNotifications ? 'location' : undefined}>
            <Bell size={18} />Notifications
          </Link>
        </nav>
        <button className="nav-link demo-link" type="button" onClick={() => setDemo(true)}>
          <FlaskConical size={18} />Demo controls
        </button>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-inner">
            <span>{inDetail ? 'Monitor detail' : 'Overview'}</span>
            <span className="timezone">Times shown locally</span>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
      {demo && <DemoControls onClose={() => setDemo(false)} />}
    </div>
  )
}
