import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth'
import { Layout } from './components/Layout'
import Channels from './pages/Channels'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Register from './pages/Register'
import SchedulePage from './pages/SchedulePage'
import Subscriptions from './pages/Subscriptions'
import Usage from './pages/Usage'

export function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="empty" style={{ paddingTop: 120 }}>
        正在加载…
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/" replace /> : <Register />} />
      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route index element={<Dashboard />} />
        <Route path="subscriptions" element={<Subscriptions />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="channels" element={<Channels />} />
        <Route path="usage" element={<Usage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}