// 轻量 API 客户端:JWT 存 localStorage,fetch 封装 + 统一错误

import type {
  AIUsageSummary,
  Channel,
  ChannelTestResult,
  PlatformInfo,
  Schedule,
  Subscription,
  TokenResponse,
  UserPublic,
} from './types'

const BASE = '/api/v1'
const TOKEN_KEY = 'newsradar_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join(';')
  }
  return detail ? JSON.stringify(detail) : '请求失败'
}

async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false) {
    const t = getToken()
    if (t) headers['Authorization'] = `Bearer ${t}`
  }

  const res = await fetch(BASE + path, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })

  if (res.status === 204) return undefined as T

  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const msg = data && 'detail' in data ? formatDetail(data.detail) : `请求失败 (${res.status})`
    throw new ApiError(res.status, msg)
  }
  return data as T
}

export const api = {
  // 认证
  register: (body: { email: string; password: string; nickname?: string }) =>
    request<{ user_id: number; email: string; verify_required: boolean }>('/auth/register', {
      method: 'POST',
      body,
      auth: false,
    }),
  login: (body: { email: string; password: string }) =>
    request<TokenResponse>('/auth/login', { method: 'POST', body, auth: false }),
  me: () => request<UserPublic>('/auth/me'),

  // 订阅
  platforms: () => request<{ platforms: PlatformInfo[]; source: string }>('/subscriptions/platforms'),
  listSubs: () => request<Subscription[]>('/subscriptions'),
  createSub: (body: { type: string; target: string; name?: string; config?: Record<string, unknown> }) =>
    request<Subscription>('/subscriptions', { method: 'POST', body }),
  updateSub: (id: number, body: { name?: string; config?: Record<string, unknown>; enabled?: boolean }) =>
    request<Subscription>(`/subscriptions/${id}`, { method: 'PATCH', body }),
  deleteSub: (id: number) => request<void>(`/subscriptions/${id}`, { method: 'DELETE' }),

  // 调度
  getSchedule: () => request<Schedule>('/schedule'),
  updateSchedule: (body: Partial<Schedule>) =>
    request<Schedule>('/schedule', { method: 'PUT', body }),
  aiUsage: () => request<AIUsageSummary>('/schedule/ai-usage'),

  // 渠道
  listChannels: () => request<Channel[]>('/channels'),
  createChannel: (body: {
    channel: string
    label?: string
    priority?: number
    credential: Record<string, unknown>
  }) => request<Channel>('/channels', { method: 'POST', body }),
  updateChannel: (
    id: number,
    body: { label?: string; credential?: Record<string, unknown>; priority?: number; enabled?: boolean },
  ) => request<Channel>(`/channels/${id}`, { method: 'PATCH', body }),
  deleteChannel: (id: number) => request<void>(`/channels/${id}`, { method: 'DELETE' }),
  testChannel: (id: number) => request<ChannelTestResult>(`/channels/${id}/test`, { method: 'POST' }),
}