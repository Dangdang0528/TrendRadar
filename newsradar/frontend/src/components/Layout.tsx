import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth'

const NAV = [
  { to: '/', label: '概览', icon: 'M3 3h7v7H3zM14 3h7v4h-7zM14 11h7v10h-7zM3 14h7v7H3z', end: true },
  { to: '/subscriptions', label: '订阅', icon: 'M4 6h16M4 12h16M4 18h10', end: false },
  { to: '/schedule', label: '调度与 AI', icon: 'M12 8v4l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', end: false },
  { to: '/channels', label: '投递渠道', icon: 'M4 4h16v16H4zM4 9l8 5 8-5', end: false },
  { to: '/usage', label: 'AI 用量', icon: 'M4 19V5M4 19h16M8 19V9m4 10V13m4 6V7', end: false },
]

function Glyph({ d }: { d: string }) {
  return (
    <svg
      className="nav__ico"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  )
}

export function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">NewsRadar</span>
          <span className="brand__sub">订阅推送</span>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => 'nav__link' + (isActive ? ' is-active' : '')}
            >
              <Glyph d={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__foot">
          <div className="sidebar__user">{user?.nickname || user?.email}</div>
          <button className="sidebar__logout" onClick={logout}>
            退出登录
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}