import { useState } from 'react'

import { ApiError, api } from '../api/client'
import type { ExtractResult, HotlistItem } from '../api/types'

export default function ExtractPreview() {
  const [manual, setManual] = useState('')
  const [force, setForce] = useState(false)

  const [hotlist, setHotlist] = useState<HotlistItem[]>([])
  const [hotlistDate, setHotlistDate] = useState('')
  const [dates, setDates] = useState<string[]>([])
  const [picked, setPicked] = useState<string[]>([])
  const [loadingHotlist, setLoadingHotlist] = useState(false)

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ExtractResult | null>(null)
  const [err, setErr] = useState('')

  const manualUrls = manual
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
  const targets = Array.from(new Set([...picked, ...manualUrls]))

  const toggle = (url: string) =>
    setPicked((prev) => (prev.includes(url) ? prev.filter((u) => u !== url) : [...prev, url]))

  async function loadHotlist(date?: string) {
    setLoadingHotlist(true)
    setErr('')
    try {
      const data = await api.hotlist(date, 15)
      setHotlist(data.items)
      setHotlistDate(data.date)
      setDates(data.dates)
      setPicked(data.items.slice(0, 3).map((i) => i.url))
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '热榜加载失败')
    } finally {
      setLoadingHotlist(false)
    }
  }

  async function run() {
    if (targets.length === 0) {
      setErr('请至少选择一个链接')
      return
    }
    setRunning(true)
    setErr('')
    setResult(null)
    try {
      setResult(await api.extract(targets, force))
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '试抓失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>试抓正文</h1>
        <p>
          选择链接直接跑一遍正文抓取,查看抓到的正文质量与字数。只抓正文、不调用 AI、不产生费用。
          仅后端 DEBUG 模式可用。
        </p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}

      <div className="card">
        <h3 className="card__title">1. 选择链接</h3>
        <p className="card__hint">
          可从最近一次热榜里勾选,也可手动粘贴链接(每行一个)。单次最多 20 条。
        </p>

        <div className="actions" style={{ marginBottom: 12 }}>
          <button className="btn btn--ghost" onClick={() => loadHotlist()} disabled={loadingHotlist}>
            {loadingHotlist ? '加载中…' : '载入最新热榜'}
          </button>
          {dates.length > 1 && (
            <select
              value={hotlistDate}
              onChange={(e) => loadHotlist(e.target.value)}
              style={{ width: 'auto' }}
              aria-label="热榜日期"
            >
              {dates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          )}
          {hotlistDate && (
            <span className="muted-note">已选中 {picked.length} 条</span>
          )}
        </div>

        {hotlist.length > 0 && (
          <div className="rows" style={{ marginBottom: 16 }}>
            {hotlist.map((it) => {
              const on = picked.includes(it.url)
              return (
                <label key={it.url} className="row" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggle(it.url)}
                    style={{ width: 'auto', flex: 'none', accentColor: 'var(--accent)' }}
                  />
                  <div className="row__main">
                    <div className="row__title">{it.title || it.url}</div>
                    <div className="row__sub">
                      {it.source} · {it.url}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
        )}

        <div className="field">
          <label htmlFor="manual">手动输入链接</label>
          <textarea
            id="manual"
            rows={3}
            placeholder={'https://news.ifeng.com/c/xxxx\nhttps://www.cls.cn/detail/xxxx'}
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
          />
        </div>

        <div className="actions">
          <label className="switch">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
            <span className="switch__track" />
            忽略缓存重新抓取
          </label>
          <button className="btn btn--primary" onClick={run} disabled={running}>
            {running ? '抓取中…' : `开始试抓（${targets.length}）`}
          </button>
          {result && (
            <span className="muted-note">
              成功 {result.ok_count}/{result.total}
            </span>
          )}
        </div>
      </div>

      {result && (
        <div className="card">
          <h3 className="card__title">2. 抓取结果</h3>
          <p className="card__hint">正文按配置截断,下方展示前 600 字。</p>
          {result.results.map((r) => (
            <div className="result" key={r.url}>
              <div className="result__head">
                <span className={'tag ' + (r.ok ? 'tag--ok' : 'tag--off')}>
                  {r.ok ? `${r.length} 字` : '未抓到'}
                </span>
                {r.from_cache && <span className="tag">来自缓存</span>}
                <span className="result__url">{r.url}</span>
              </div>
              {r.ok ? (
                <div className="result__body">{r.content}</div>
              ) : (
                <div className="empty" style={{ padding: '12px 0' }}>
                  未能提取正文,可能是 JS 渲染、反爬限制或页面结构不匹配
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}