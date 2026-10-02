import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { AIUsageSummary, Channel, Schedule, Subscription } from '../api/types'

const MODE_LABEL: Record<string, string> = {
  daily: '当日汇总',
  current: '当前榜单',
  incremental: '增量(仅新增)',
}

export default function Dashboard() {
  const [subs, setSubs] = useState<Subscription[]>([])
  const [chans, setChans] = useState<Channel[]>([])
  const [sched, setSched] = useState<Schedule | null>(null)
  const [usage, setUsage] = useState<AIUsageSummary | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    ;(async () => {
      try {
        const [s, c, sch, u] = await Promise.all([
          api.listSubs(),
          api.listChannels(),
          api.getSchedule(),
          api.aiUsage(),
        ])
        setSubs(s)
        setChans(c)
        setSched(sch)
        setUsage(u)
      } catch (ex) {
        setErr(ex instanceof ApiError ? ex.message : '加载失败')
      }
    })()
  }, [])

  const activeSubs = subs.filter((s) => s.enabled).length
  const activeChans = chans.filter((c) => c.enabled).length

  return (
    <>
      <div className="page-head">
        <h1>概览</h1>
        <p>你的订阅、投递与 AI 总结状态一览。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}

      <div className="stat-row">
        <div className="stat">
          <div className="stat__label">订阅</div>
          <div className="stat__value">
            {activeSubs}
            <span className="stat__unit">/ {subs.length} 启用</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">投递渠道</div>
          <div className="stat__value">
            {activeChans}
            <span className="stat__unit">/ {chans.length} 启用</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">AI 深度总结</div>
          <div className="stat__value" style={{ fontSize: 22 }}>
            {sched?.enable_ai_summary ? '已开启' : '未开启'}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">今日 AI 调用</div>
          <div className="stat__value">
            {usage?.today_count ?? 0}
            <span className="stat__unit">次</span>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card__title">推送计划</h3>
        <p className="card__hint">
          由前端提交后写入调度;实际触发由后台 worker 按 cron 执行(worker 在后续阶段接入)。
        </p>
        {sched ? (
          <div className="rows">
            <div className="row">
              <div className="row__main">
                <div className="row__title">触发时间</div>
                <div className="row__sub">
                  cron <code>{sched.cron_expr}</code>
                </div>
              </div>
              <span className={'tag ' + (sched.enabled ? 'tag--ok' : 'tag--off')}>
                {sched.enabled ? '已启用' : '已暂停'}
              </span>
            </div>
            <div className="row">
              <div className="row__main">
                <div className="row__title">报告模式</div>
                <div className="row__sub">{MODE_LABEL[sched.report_mode] ?? sched.report_mode}</div>
              </div>
            </div>
            <div className="row">
              <div className="row__main">
                <div className="row__title">下一次运行</div>
                <div className="row__sub">
                  {sched.next_run_at ? new Date(sched.next_run_at).toLocaleString() : '待调度器计算'}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="empty">正在读取调度…</div>
        )}
      </div>

      <div className="card">
        <h3 className="card__title">下一步</h3>
        <p className="card__hint">
          {subs.length === 0
            ? '还没有任何订阅。先添加几个平台关键词,再绑定投递渠道。'
            : activeChans === 0
              ? '已有订阅,但还没绑定投递渠道——去配置飞书或邮箱。'
              : '配置看起来完整,等待调度器按计划触发即可。'}
        </p>
        <div className="actions">
          <Link className="btn btn--primary" to="/subscriptions">
            管理订阅
          </Link>
          <Link className="btn btn--ghost" to="/channels">
            投递渠道
          </Link>
          <Link className="btn btn--ghost" to="/schedule">
            调度与 AI
          </Link>
        </div>
      </div>
    </>
  )
}