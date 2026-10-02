import { useEffect, useMemo, useState } from 'react'

import { ApiError, api } from '../api/client'
import type { PlatformInfo, SubType, Subscription } from '../api/types'

const TYPE_LABEL: Record<SubType, string> = {
  platform: '平台',
  rss: 'RSS',
  keyword: '关键词',
  ai_interest: 'AI 兴趣',
}

const TYPE_HINT: Record<SubType, string> = {
  platform: '选择 trendradar 内置平台(热榜来源)',
  rss: '填写 RSS / Atom 订阅地址',
  keyword: '命中该关键词的条目才会进入推送',
  ai_interest: '交给 AI 判断相关性的兴趣描述',
}

export default function Subscriptions() {
  const [subs, setSubs] = useState<Subscription[]>([])
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [type, setType] = useState<SubType>('platform')
  const [target, setTarget] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)

  const platformMap = useMemo(() => {
    const m = new Map<string, string>()
    platforms.forEach((p) => m.set(p.id, p.name))
    return m
  }, [platforms])

  async function load() {
    try {
      const [s, p] = await Promise.all([api.listSubs(), api.platforms()])
      setSubs(s)
      setPlatforms(p.platforms)
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
    const t = target.trim()
    if (!t) {
      setErr('请填写目标(平台 / 地址 / 关键词)')
      return
    }
    const displayName = type === 'platform' ? platformMap.get(t) ?? undefined : name.trim() || undefined
    setBusy(true)
    try {
      await api.createSub({ type, target: t, name: displayName })
      setTarget('')
      setName('')
      setOk('已添加订阅')
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(sub: Subscription) {
    try {
      await api.updateSub(sub.id, { enabled: !sub.enabled })
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '更新失败')
    }
  }

  async function remove(sub: Subscription) {
    if (!confirm(`删除订阅「${sub.name || sub.target}」?`)) return
    try {
      await api.deleteSub(sub.id)
      await load()
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '删除失败')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>订阅</h1>
        <p>聚合来源:平台热榜、RSS、关键词与 AI 兴趣。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}
      {ok && <div className="alert alert--ok">{ok}</div>}

      <div className="card">
        <h3 className="card__title">新增订阅</h3>
        <p className="card__hint">{TYPE_HINT[type]}</p>

        <div className="grid-2">
          <div className="field">
            <label htmlFor="type">类型</label>
            <select
              id="type"
              value={type}
              onChange={(e) => {
                setType(e.target.value as SubType)
                setTarget('')
                setName('')
              }}
            >
              {(Object.keys(TYPE_LABEL) as SubType[]).map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="target">{type === 'platform' ? '平台' : '目标'}</label>
            {type === 'platform' ? (
              <select id="target" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">请选择平台…</option>
                {platforms.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="target"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder={type === 'rss' ? 'https://example.com/feed.xml' : '如: 人工智能'}
              />
            )}
          </div>
        </div>

        {type !== 'platform' && (
          <div className="field">
            <label htmlFor="name">备注名(可选)</label>
            <input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="便于识别" />
          </div>
        )}

        <div className="actions">
          <button className="btn btn--primary" onClick={create} disabled={busy}>
            {busy ? '添加中…' : '添加订阅'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3 className="card__title">我的订阅({subs.length})</h3>
        {subs.length === 0 ? (
          <div className="empty">
            <strong>还没有订阅</strong>
            从上面的表单添加一个平台或关键词试试。
          </div>
        ) : (
          <div className="rows">
            {subs.map((s) => (
              <div key={s.id} className={'row' + (s.enabled ? '' : ' is-off')}>
                <div className="row__main">
                  <div className="row__title">
                    {s.name || platformMap.get(s.target) || s.target}
                    <span className="tag tag--accent">{TYPE_LABEL[s.type] ?? s.type}</span>
                    {!s.enabled && <span className="tag tag--off">已停用</span>}
                  </div>
                  <div className="row__sub">{s.target}</div>
                </div>
                <div className="row__actions">
                  <label className="switch">
                    <input type="checkbox" checked={s.enabled} onChange={() => toggle(s)} />
                    <span className="switch__track" />
                  </label>
                  <button className="btn btn--danger" onClick={() => remove(s)}>
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