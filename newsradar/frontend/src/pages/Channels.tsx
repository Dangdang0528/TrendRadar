import { useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import type { Channel, ChannelType } from '../api/types'

const CHANNEL_LABEL: Record<ChannelType, string> = {
  feishu: '飞书',
  email: '邮箱',
  telegram: 'Telegram',
  webhook: 'Webhook',
}

// 每种渠道需要的凭证字段(与后端 ChannelCreate 校验一致)
const CRED_FIELDS: Record<ChannelType, { key: string; label: string; placeholder: string; optional?: boolean }[]> = {
  feishu: [
    {
      key: 'webhook_url',
      label: 'Webhook 地址',
      placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxxx',
    },
  ],
  email: [
    { key: 'to_email', label: '收件邮箱', placeholder: 'you@example.com' },
    { key: 'smtp_user', label: 'SMTP 账号(可选)', placeholder: '留空则用服务端全局 SMTP', optional: true },
    { key: 'smtp_pass', label: 'SMTP 授权码(可选)', placeholder: '留空则用服务端全局 SMTP', optional: true },
  ],
  telegram: [
    { key: 'bot_token', label: 'Bot Token', placeholder: '123456:ABC-DEF...' },
    { key: 'chat_id', label: 'Chat ID', placeholder: '-1001234567890' },
  ],
  webhook: [{ key: 'url', label: '目标 URL', placeholder: 'https://your-endpoint/hook' }],
}

export default function Channels() {
  const [chans, setChans] = useState<Channel[]>([])
  const [type, setType] = useState<ChannelType>('feishu')
  const [label, setLabel] = useState('')
  const [cred, setCred] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      setChans(await api.listChannels())
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '加载失败')
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function create() {
    setErr('')
    setOk('')
    const fields = CRED_FIELDS[type]
    const payload: Record<string, unknown> = {}
    for (const f of fields) {
      const v = (cred[f.key] ?? '').trim()
      if (!v && !f.optional) {
        setErr(`请填写「${f.label}」`)
        return
      }
      if (v) payload[f.key] = v
    }
    setBusy(true)
    try {
      await api.createChannel({ channel: type, label: label.trim() || undefined, credential: payload })
      setLabel('')
      setCred({})
      setOk('已添加渠道')
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(ch: Channel) {
    try {
      await api.updateChannel(ch.id, { enabled: !ch.enabled })
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '更新失败')
    }
  }

  async function test(ch: Channel) {
    setErr('')
    setOk('')
    try {
      const r = await api.testChannel(ch.id)
      r.success ? setOk(`测试成功:${r.message}`) : setErr(`测试失败:${r.message}`)
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '测试失败')
    }
  }

  async function remove(ch: Channel) {
    if (!confirm(`删除渠道「${ch.label || CHANNEL_LABEL[ch.channel]}」?`)) return
    try {
      await api.deleteChannel(ch.id)
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '删除失败')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>投递渠道</h1>
        <p>绑定飞书、邮箱或 Webhook,报告会推送到这些渠道。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}
      {ok && <div className="alert alert--ok">{ok}</div>}

      <div className="card">
        <h3 className="card__title">新增渠道</h3>
        <p className="card__hint">凭证将加密存储,接口返回不会回显。</p>

        <div className="grid-2">
          <div className="field">
            <label htmlFor="ch">渠道类型</label>
            <select
              id="ch"
              value={type}
              onChange={(e) => {
                setType(e.target.value as ChannelType)
                setCred({})
              }}
            >
              {(Object.keys(CHANNEL_LABEL) as ChannelType[]).map((t) => (
                <option key={t} value={t}>
                  {CHANNEL_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="label">备注名(可选)</label>
            <input id="label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="如: 工作飞书群" />
          </div>
        </div>

        {CRED_FIELDS[type].map((f) => (
          <div className="field" key={f.key}>
            <label htmlFor={f.key}>{f.label}</label>
            <input
              id={f.key}
              value={cred[f.key] ?? ''}
              onChange={(e) => setCred((c) => ({ ...c, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              type={f.key.includes('pass') || f.key.includes('token') ? 'password' : 'text'}
            />
          </div>
        ))}

        <div className="actions">
          <button className="btn btn--primary" onClick={create} disabled={busy}>
            {busy ? '添加中…' : '添加渠道'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3 className="card__title">我的渠道({chans.length})</h3>
        {chans.length === 0 ? (
          <div className="empty">
            <strong>还没有投递渠道</strong>
            没有渠道,报告就没有去处——先添加一个飞书或邮箱。
          </div>
        ) : (
          <div className="rows">
            {chans.map((ch) => (
              <div key={ch.id} className={'row' + (ch.enabled ? '' : ' is-off')}>
                <div className="row__main">
                  <div className="row__title">
                    {ch.label || CHANNEL_LABEL[ch.channel]}
                    <span className="tag tag--accent">{CHANNEL_LABEL[ch.channel] ?? ch.channel}</span>
                    {!ch.enabled && <span className="tag tag--off">已停用</span>}
                  </div>
                  <div className="row__sub">优先级 {ch.priority}</div>
                </div>
                <div className="row__actions">
                  <button className="btn btn--ghost btn--sm" onClick={() => test(ch)}>
                    测试
                  </button>
                  <label className="switch">
                    <input type="checkbox" checked={ch.enabled} onChange={() => toggle(ch)} />
                    <span className="switch__track" />
                  </label>
                  <button className="btn btn--danger" onClick={() => remove(ch)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}