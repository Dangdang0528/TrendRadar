// 与后端 Pydantic schema 对齐的类型定义

export interface UserPublic {
  id: number
  email: string
  nickname: string | null
  timezone: string
  language: string
  email_verified: boolean
  is_active: boolean
  created_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: number
  expires_in: number
}

export type SubType = 'platform' | 'rss' | 'keyword' | 'ai_interest' | 'global_filter'

/** 一个关键词词组,对应 frequency_words.txt 里由空行分隔的一个块 */
export interface KeywordGroupConfig {
  alias: string | null
  words: string[]
  required: string[]
  filters: string[]
  max_count: number
}

export interface Subscription {
  id: number
  user_id: number
  type: SubType
  target: string
  name: string | null
  config: Record<string, unknown>
  enabled: boolean
  created_at: string | null
}

export interface PlatformInfo {
  id: string
  name: string
  enabled: boolean
}

/** 平台多选结果;空列表表示"不限制",即抓取全部平台 */
export interface PlatformSelection {
  platforms: string[]
}

/** 全局过滤词,命中即排除整条新闻 */
export interface GlobalFilterWords {
  words: string[]
}

export type ReportMode = 'daily' | 'current' | 'incremental'

export interface Schedule {
  cron_expr: string
  report_mode: ReportMode
  enable_ai_summary: boolean
  ai_language: string
  ai_max_news: number
  channel_filter: Record<string, unknown> | null
  enabled: boolean
  user_id: number
  next_run_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AIUsageSummary {
  today_count: number
  today_cost_cents: number
  month_count: number
  month_cost_cents: number
}

export type ChannelType = 'feishu' | 'email' | 'telegram' | 'webhook'

export interface Channel {
  id: number
  user_id: number
  channel: ChannelType
  label: string | null
  priority: number
  enabled: boolean
  created_at: string | null
}

export interface ChannelTestResult {
  success: boolean
  message: string
  channel: string
  sent_at: string
}