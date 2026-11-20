import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/manrope/wght.css'
import { StrictMode, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Frame } from './Frame'
import { Empty } from './ui'
import { Overview } from './Overview'
import './styles.css'

const MonitorDetail = lazy(() => import('./MonitorDetail'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Frame>
        <Suspense fallback={<Empty>Loading monitor…</Empty>}>
          <Routes>
            <Route index element={<Overview />} />
            <Route path="monitors/:id" element={<MonitorDetail />} />
            <Route path="*" element={<Empty>Page not found.</Empty>} />
          </Routes>
        </Suspense>
      </Frame>
    </BrowserRouter>
  </StrictMode>,
)
