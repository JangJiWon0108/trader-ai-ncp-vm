import { NavLink } from 'react-router-dom'
import { theme } from '../theme'
import './Sidebar.css'
import MarketStatusCard from './MarketStatusCard'

const menus = [
  { path: '/', label: '대시보드', icon: '⊞' },
  { path: '/portfolio', label: '포트폴리오 / 잔고', icon: '◈' },
  { path: '/recommendations', label: 'AI 추천 종목', icon: '✦' },
  { path: '/orders', label: '주문 내역', icon: '≡' },
  { path: '/economic', label: '경제 지표', icon: '◉' },
  { path: '/alpha-advantage', label: '알파 어드밴티지', icon: 'α' },
  { path: '/inference-history', label: 'AI 추론 히스토리', icon: '∑' },
  { path: '/admin', label: '관리자', icon: '⚙' },
]

export default function Sidebar() {
  return (
    <aside
      style={{
        width: theme.sidebarWidth,
        minHeight: '100vh',
        background: `linear-gradient(165deg, #0f172a 0%, #020617 48%, #0c1224 100%)`,
        borderRight: `1px solid ${theme.sidebarBorder}`,
        padding: '28px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        flexShrink: 0,
        boxShadow: '8px 0 40px rgba(0, 0, 0, 0.35)',
      }}
    >
      <div
        style={{
          padding: '0 22px 28px',
          fontFamily: theme.fontDisplay,
          fontSize: 22,
          fontWeight: 800,
          letterSpacing: '-0.03em',
          background: `linear-gradient(120deg, #e0e7ff 0%, #38bdf8 45%, #c4b5fd 100%)`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}
      >
        Trader AI
      </div>
      <nav className="sidebar-nav">
        {menus.map(({ path, label, icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => `sidebar-nav-link${isActive ? ' is-active' : ''}`}
          >
            <span className="sidebar-nav-link__icon" aria-hidden>
              {icon}
            </span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div style={{ flex: 1 }} />
      <MarketStatusCard />
    </aside>
  )
}
