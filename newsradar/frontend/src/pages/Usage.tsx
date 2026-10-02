import { useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import type { AIUsageSummary } from '../api/types'

export default function Usage() {
  const [usage, setUsage] = useState<AIUsageSummary | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    ;(async () => {
      try {
        setUsage(await api.aiUsage())
      } catch (ex) {
        setErr(ex instanceof ApiError ? ex.message : '加载失败')
      }
    })()
  }, [])

  const yuan = (cents: number) => (cents / 100).toFixed(2)

  return (
    <>
      <div className="page-head">
        <h1>AI 用量</h1>
        <p>每次 AI 深度总结都会记一条用量;此处统计今日与本月。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}

      <div className="stat-row">
        <div className="stat">
          <div className="stat__label">今日调用</div>
          <div className="stat__value">
            {usage?.today_count ?? 0}
            <span className="stat__unit">次</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">今日费用</div>
          <div className="stat__value">
            ¥{yuan(usage?.today_cost_cents ?? 0)}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">本月调用</div>
          <div className="stat__value">
            {usage?.month_count ?? 0}
            <span className="stat__unit">次</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">本月费用</div>
          <div className="stat__value">¥{yuan(usage?.month_cost_cents ?? 0)}</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card__title">关于计费</h3>
        <p className="card__hint">
          用量按“每用户每次深度总结”计一条记录(模型、token、成本)。当前为 MVP:token 与成本字段先记 0,
          后续接入真实计费后自动填充。若未配置全局 <code>AI_API_KEY</code>,AI 步骤会被自动跳过,不产生用量。
        </p>
      </div>
    </>
  )
}