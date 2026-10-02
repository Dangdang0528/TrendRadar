import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'

export default function Register() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (password.length < 8) {
      setErr('密码至少 8 位')
      return
    }
    setErr('')
    setBusy(true)
    try {
      await register(email.trim(), password, nickname.trim() || undefined)
      nav('/')
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '注册失败,请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="创建账号"
      subtitle="注册后即可订阅热榜,并配置推送时间"
      footer={
        <>
          已经有账号?<Link to="/login">前往登录</Link>
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
          <label htmlFor="nickname">昵称(可选)</label>
          <input
            id="nickname"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="怎么称呼你"
          />
        </div>
        <div className="field">
          <label htmlFor="password">密码</label>
          <input
            id="password"
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 8 位"
          />
          <span className="hint">至少 8 位字符</span>
        </div>
        <button className="btn btn--primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? '创建中…' : '创建账号'}
        </button>
      </form>
    </AuthShell>
  )
}