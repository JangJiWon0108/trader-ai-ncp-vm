import type { CSSProperties } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import GlobalErrorBoundary from './components/GlobalErrorBoundary'
import Dashboard from './pages/dashboard'
import Portfolio from './pages/portfolio'
import Recommendations from './pages/ai-recommendations'
import Orders from './pages/orders'
import Economic from './pages/economic'
import AlphaAdvantage from './pages/alpha-advantage'
import InferenceHistory from './pages/inference-history'
import Admin from './pages/admin'
import { theme } from './theme'
import { CurrencyProvider } from './contexts/CurrencyContext'
import { AlertProvider } from './contexts/AlertContext'

const shell: CSSProperties = {
  display: 'flex',
  minHeight: '100vh',
  backgroundColor: theme.bgBase,
  backgroundImage: `
    radial-gradient(ellipse 90% 55% at 0% -10%, ${theme.bgAccentA}, transparent 55%),
    radial-gradient(ellipse 70% 45% at 100% 0%, ${theme.bgAccentB}, transparent 50%),
    radial-gradient(ellipse 50% 35% at 80% 100%, ${theme.bgAccentC}, transparent 45%)
  `,
}

export default function App() {
  return (
    <CurrencyProvider>
      <AlertProvider>
        <GlobalErrorBoundary>
          <BrowserRouter>
            <div style={shell}>
              <Sidebar />
              <main className="trader-scroll" style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/portfolio" element={<Portfolio />} />
                  <Route path="/recommendations" element={<Recommendations />} />
                  <Route path="/orders" element={<Orders />} />
                  <Route path="/economic" element={<Economic />} />
                  <Route path="/alpha-advantage" element={<AlphaAdvantage />} />
                  <Route path="/inference-history" element={<InferenceHistory />} />
                  <Route path="/admin" element={<Admin />} />
                </Routes>
              </main>
            </div>
          </BrowserRouter>
        </GlobalErrorBoundary>
      </AlertProvider>
    </CurrencyProvider>
  )
}
