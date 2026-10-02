import { useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import type { ChannelType, ReportMode, Schedule } from '../api/types'

const CRON_PRESETS: { label: string; value: string }[] = [
  { label: '每天 09:00', value: '0 9 * * *' },
  { label: '每天 12:00', value: '0 12 * * *' },
  { label: '每天 18:00', value: '0 18 * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '工作日 09:00', value: '0 9 * * 1-5' },
]

const MODES: { value: ReportMode; label: string; desc: string }[] = [
  { value: 'daily', label: '当日汇总', desc: '一天内累积的全部相关新闻' },
  { value: 'current', label: '当前榜单', desc: '仅最新一次抓取的榜单' },
  { value: 'incremental', label: '增量', desc: '仅推送上次之后新增的条目' },
]

const CHANNEL_LABELS: Record<ChannelType, string> = {
  feishu: '飞书',
  email: '邮箱',
  telegram: 'Telegram',
  webhook: 'Webhook',
}

/** 与后端 delivery.selected_channels 同规则:解析出本次要投递的渠道 */
function resolveSelected(
  filter: Record<string, unknown> | null,
  available: ChannelType[],
): ChannelType[] {
  if (!filter) return available
  const pick = (key: string): string[] =>
    Array.isArray(filter[key])
      ? (filter[key] as unknown[]).map((x) => String(x).trim().toLowerCase())
      : []
  const include = pick('include')
  const exclude = pick('exclude')
  if (!include.length && !exclude.length) return available
  return available.filter(
    (c) => (!include.length || include.includes(c)) && !exclude.includes(c),
  )
}

export default function SchedulePage() {
  const [sched, setSched] = useState<Schedule | null>(null)
  const [cron, setCron] = useState('0 9 * * *')
  const [mode, setMode] = useState<ReportMode>('incremental')
  const [enabled, setEnabled] = useState(true)
  const [ai, setAi] = useState(false)
  const [aiMax, setAiMax] = useState(30)
  const [aiLang, setAiLang] = useState('zh')
  const [channels, setChannels] = useState<ChannelType[]>([])
  const [picked, setPicked] = useState<ChannelType[]>([])
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const [s, chs] = await Promise.all([api.getSchedule(), api.listChannels()])
        setSched(s)
        setCron(s.cron_expr)
        setMode(s.report_mode)
        setEnabled(s.enabled)
        setAi(s.enable_ai_summary)
        setAiMax(s.ai_max_news)
        setAiLang(s.ai_language)

        const avail = [...new Set(chs.filter((c) => c.enabled).map((c) => c.channel))]
        setChannels(avail)
        setPicked(resolveSelected(s.channel_filter, avail))
      } catch (ex) {
        setErr(ex instanceof ApiError ? ex.message : '加载失败')
      }
    })()
  }, [])

  function toggleChannel(c: ChannelType) {
    setPicked((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  }

  /** 全选 → {} 表示不过滤;部分选择 → include 白名单 */
  function buildChannelFilter(): Record<string, string[]> | null {
    if (!channels.length) return {}
    if (picked.length === 0) return null
    if (picked.length === channels.length) return {}
    return { include: picked }
  }

  async function save() {
    setErr('')
    setOk('')

    const channelFilter = buildChannelFilter()
    if (channelFilter === null) {
      setErr('至少选择一个投递渠道,否则报告无处可发')
      return
    }

    setBusy(true)
    try {
      const s = await api.updateSchedule({
        cron_expr: cron.trim(),
        report_mode: mode,
        enable_ai_summary: ai,
        ai_language: aiLang,
        ai_max_news: aiMax,
        channel_filter: channelFilter,
        enabled,
      })
      setSched(s)
      setOk('已保存')
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>调度与 AI</h1>
        <p>设定推送时间与报告口径,并按需开启 AI 深度总结。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}
      {ok && <div className="alert alert--ok">{ok}</div>}

      <div className="card">
        <h3 className="card__title">推送时间</h3>
        <p className="card__hint">使用 5 段 unix cron(分 时 日 月 周)。</p>

        <div className="field">
          <label>快捷选择</label>
          <div className="actions" style={{ flexWrap: 'wrap' }}>
            {CRON_PRESETS.map((p) => (
              <button
                key={p.value}
                className={'btn btn--sm ' + (cron === p.value ? 'btn--primary' : 'btn--ghost')}
                onClick={() => setCron(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <div className="field">
            <label htmlFor="cron">cron 表达式</label>
            <input
              id="cron"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 9 * * *"
              style={{ fontFamily: 'var(--font-mono)' }}
            />
          </div>
          <div className="field" style={{ justifyContent: 'center' }}>
            <label>启用调度</label>
            <label className="switch">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              <span className="switch__track" />
              <span>{enabled ? '按计划推送' : '已暂停'}</span>
            </label>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card__title">报告模式</h3>
        <p className="card__hint">决定每次推送包含哪些条目。</p>
        <div className="rows">
          {MODES.map((m) => (
            <label key={m.value} className="row" style={{ cursor: 'pointer' }}>
              <input
                type="radio"
                name="mode"
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
                style={{ width: 'auto', marginRight: 4 }}
              />
              <div className="row__main">
                <div className="row__title">{m.label}</div>
                <div className="row__sub">{m.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 className="card__title">投递渠道</h3>
        <p className="card__hint">
          选择这条推送要发往哪些渠道;全部勾选等同于不限制。未勾选的渠道本次不会收到报告。
        </p>

        {channels.length === 0 ? (
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>
            还没有已启用的投递渠道,先到「投递渠道」页添加。
          </p>
        ) : (
          <div className="rows">
            {channels.map((c) => {
              const on = picked.includes(c)
              return (
                <label key={c} className="row" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggleChannel(c)}
                    style={{ width: 'auto', marginRight: 4 }}
                  />
                  <div className="row__main">
                    <div className="row__title">{CHANNEL_LABELS[c]}</div>
                    <div className="row__sub">{on ? '本次推送会发送' : '本次推送跳过'}</div>
                  </div>
                </label>
              )
            })}
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card__title">AI 深度总结</h3>
        <p className="card__hint">
          开启后,会对 Top-N 条目抓取正文,交由 AI 做正文级解读(需服务端配置全局 AI Key)。
        </p>

        <label className="switch" style={{ marginBottom: 16 }}>
          <input type="checkbox" checked={ai} onChange={(e) => setAi(e.target.checked)} />
          <span className="switch__track" />
          <span>{ai ? '已开启' : '关闭'}</span>
        </label>

        <div className="grid-2">
          <div className="field">
            <label htmlFor="aiMax">参与分析的条数(1–200)</label>
            <input
              id="aiMax"
              type="number"
              min={1}
              max={200}
              value={aiMax}
              onChange={(e) => setAiMax(Number(e.target.value))}
              disabled={!ai}
            />
          </div>
          <div className="field">
            <label htmlFor="aiLang">输出语言</label>
            <select id="aiLang" value={aiLang} onChange={(e) => setAiLang(e.target.value)} disabled={!ai}>
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </div>
        </div>
      </div>

      <div className="actions">
        <button className="btn btn--primary" onClick={save} disabled={busy}>
          {busy ? '保存中…' : '保存设置'}
        </button>
        {sched?.next_run_at && (
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>
            下一次运行:{new Date(sched.next_run_at).toLocaleString()}
          </span>
        )}
      </div>
    </>
  )
}