import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      await login(email.trim(), password)
      nav('/')
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '登录失败,请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="登录"
      subtitle="使用你的邮箱与密码进入控制台"
      footer={
        <>
          还没有账号?<Link to="/register">立即注册</Link>
        </>
      }
    >
      <form onSubmit={submit}>
        {err && <div className="alert alert--error">{err}</div>}
        <div className="field">
          <label htmlFor="email">邮箱</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="field">
          <label htmlFor="password">密码</label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
          />
        </div>
        <button className="btn btn--primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? '登录中…' : '登录'}
        </button>
      </form>
    </AuthShell>
  )
}