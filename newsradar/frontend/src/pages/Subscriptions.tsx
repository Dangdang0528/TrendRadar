import { useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import type { KeywordGroupConfig, PlatformInfo, Subscription, SubType } from '../api/types'

// ── 词组草稿(带可选 id:undefined = 尚未落库)──────────────────────
interface GroupDraft {
  id?: number
  enabled: boolean
  alias: string
  words: string[]
  required: string[]
  filters: string[]
  max_count: number
}

function toDraft(s: Subscription): GroupDraft {
  const c = (s.config || {}) as Partial<KeywordGroupConfig>
  return {
    id: s.id,
    enabled: s.enabled,
    alias: typeof c.alias === 'string' ? c.alias : '',
    words: Array.isArray(c.words) ? c.words : [],
    required: Array.isArray(c.required) ? c.required : [],
    filters: Array.isArray(c.filters) ? c.filters : [],
    max_count: typeof c.max_count === 'number' ? c.max_count : 0,
  }
}

function toConfig(d: GroupDraft): Record<string, unknown> {
  return {
    alias: d.alias.trim() || null,
    words: d.words,
    required: d.required,
    filters: d.filters,
    max_count: Number(d.max_count) || 0,
  }
}

function emptyDraft(): GroupDraft {
  return { enabled: true, alias: '', words: [], required: [], filters: [], max_count: 0 }
}

// ── 词条输入:回车 / 逗号 / 失焦即加入,点 × 移除 ──────────────────
function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  function commit(raw: string) {
    const parts = raw
      .split(/[,,\n]/)
      .map((x) => x.trim())
      .filter(Boolean)
    if (!parts.length) return
    const next = [...value]
    for (const p of parts) if (!next.includes(p)) next.push(p)
    onChange(next)
  }

  return (
    <div className="chips">
      {value.map((w) => (
        <span key={w} className="chip">
          {w}
          <button
            type="button"
            className="chip__x"
            aria-label={`移除 ${w}`}
            onClick={() => onChange(value.filter((x) => x !== w))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="chips__input"
        value={draft}
        placeholder={value.length ? '' : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',' || e.key === '，') {
            e.preventDefault()
            commit(draft)
            setDraft('')
          } else if (e.key === 'Backspace' && !draft && value.length) {
            onChange(value.slice(0, -1))
          }
        }}
        onBlur={() => {
          commit(draft)
          setDraft('')
        }}
      />
    </div>
  )
}

export default function Subscriptions() {
  const [catalog, setCatalog] = useState<PlatformInfo[]>([])
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [groups, setGroups] = useState<GroupDraft[]>([])
  const [globalFilters, setGlobalFilters] = useState<string[]>([])
  const [others, setOthers] = useState<Subscription[]>([])
  const [platformDirty, setPlatformDirty] = useState(false)
  const [gfDirty, setGfDirty] = useState(false)

  // 其他来源(RSS / AI 兴趣)的新增表单
  const [otherType, setOtherType] = useState<Exclude<SubType, 'platform' | 'keyword' | 'global_filter'>>('rss')
  const [otherTarget, setOtherTarget] = useState('')

  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState<string>('')

  async function load() {
    try {
      const [subs, p, gf] = await Promise.all([
        api.listSubs(),
        api.platforms(),
        api.getGlobalFilters(),
      ])
      setCatalog(p.platforms)
      setSelectedPlatforms(subs.filter((s) => s.type === 'platform').map((s) => s.target))
      setGroups(subs.filter((s) => s.type === 'keyword').map(toDraft))
      setOthers(subs.filter((s) => s.type === 'rss' || s.type === 'ai_interest'))
      setGlobalFilters(gf.words)
      setPlatformDirty(false)
      setGfDirty(false)
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : '加载失败')
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function flash(msg: string) {
    setErr('')
    setOk(msg)
  }
  function fail(ex: unknown, fallback: string) {
    setOk('')
    setErr(ex instanceof ApiError ? ex.message : fallback)
  }

  // ── 平台多选 ────────────────────────────────────────────
  function togglePlatform(id: string) {
    setPlatformDirty(true)
    setSelectedPlatforms((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function savePlatforms() {
    setBusy('platforms')
    try {
      const r = await api.putPlatforms(selectedPlatforms)
      setSelectedPlatforms(r.platforms)
      setPlatformDirty(false)
      flash(r.platforms.length ? `已限定 ${r.platforms.length} 个平台` : '已设为抓取全部平台')
    } catch (ex) {
      fail(ex, '保存平台失败')
    } finally {
      setBusy('')
    }
  }

  // ── 关键词组 ────────────────────────────────────────────
  function patchGroup(i: number, patch: Partial<GroupDraft>) {
    setGroups((prev) => prev.map((g, idx) => (idx === i ? { ...g, ...patch } : g)))
  }

  async function saveGroup(i: number) {
    const d = groups[i]
    if (!d.words.length && !d.required.length) {
      setOk('')
      setErr('词组至少要有一个普通词或必须词,否则不会匹配任何新闻')
      return
    }
    setBusy(`group-${i}`)
    try {
      if (d.id) {
        await api.updateSub(d.id, { config: toConfig(d) })
      } else {
        await api.createSub({ type: 'keyword', target: '', config: toConfig(d) })
      }
      await load()
      flash('词组已保存')
    } catch (ex) {
      fail(ex, '保存词组失败')
    } finally {
      setBusy('')
    }
  }

  async function toggleGroup(i: number) {
    const d = groups[i]
    if (!d.id) {
      patchGroup(i, { enabled: !d.enabled })
      return
    }
    try {
      await api.updateSub(d.id, { enabled: !d.enabled })
      patchGroup(i, { enabled: !d.enabled })
    } catch (ex) {
      fail(ex, '更新失败')
    }
  }

  async function removeGroup(i: number) {
    const d = groups[i]
    if (!d.id) {
      setGroups((prev) => prev.filter((_, idx) => idx !== i))
      return
    }
    if (!confirm(`删除词组「${d.alias || d.words.join('、') || d.id}」?`)) return
    try {
      await api.deleteSub(d.id)
      await load()
      flash('词组已删除')
    } catch (ex) {
      fail(ex, '删除失败')
    }
  }

  // ── 全局过滤词 ──────────────────────────────────────────
  async function saveGlobalFilters() {
    setBusy('gf')
    try {
      const r = await api.putGlobalFilters(globalFilters)
      setGlobalFilters(r.words)
      setGfDirty(false)
      flash(r.words.length ? `已保存 ${r.words.length} 个全局过滤词` : '已清空全局过滤词')
    } catch (ex) {
      fail(ex, '保存全局过滤词失败')
    } finally {
      setBusy('')
    }
  }

  // ── 其他来源 ────────────────────────────────────────────
  async function addOther() {
    const t = otherTarget.trim()
    if (!t) {
      setOk('')
      setErr('请填写目标')
      return
    }
    setBusy('other')
    try {
      await api.createSub({ type: otherType, target: t })
      setOtherTarget('')
      await load()
      flash('已添加')
    } catch (ex) {
      fail(ex, '添加失败')
    } finally {
      setBusy('')
    }
  }

  async function toggleOther(s: Subscription) {
    try {
      await api.updateSub(s.id, { enabled: !s.enabled })
      await load()
    } catch (ex) {
      fail(ex, '更新失败')
    }
  }

  async function removeOther(s: Subscription) {
    if (!confirm(`删除「${s.name || s.target}」?`)) return
    try {
      await api.deleteSub(s.id)
      await load()
      flash('已删除')
    } catch (ex) {
      fail(ex, '删除失败')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>订阅</h1>
        <p>用关键词组筛选真正关心的内容;来源平台默认覆盖全部,也可按需限定。</p>
      </div>

      {err && <div className="alert alert--error">{err}</div>}
      {ok && <div className="alert alert--ok">{ok}</div>}

      {/* ── 平台来源 ─────────────────────────────────── */}
      <div className="card">
        <h3 className="card__title">来源平台</h3>
        <p className="card__hint">
          多选热榜平台。不勾选任何平台 = 不限制,将抓取全部可用平台。
        </p>

        {catalog.length === 0 ? (
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>未读取到平台清单。</p>
        ) : (
          <div className="check-grid">
            {catalog.map((p) => {
              const on = selectedPlatforms.includes(p.id)
              return (
                <label key={p.id} className={'check' + (on ? ' is-on' : '')}>
                  <input type="checkbox" checked={on} onChange={() => togglePlatform(p.id)} />
                  <span className="check__name">{p.name}</span>
                  <code className="check__id">{p.id}</code>
                </label>
              )
            })}
          </div>
        )}

        <div className="actions">
          <button
            className="btn btn--primary"
            onClick={savePlatforms}
            disabled={busy === 'platforms' || !platformDirty}
          >
            {busy === 'platforms' ? '保存中…' : '保存平台选择'}
          </button>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setSelectedPlatforms(catalog.map((p) => p.id))
              setPlatformDirty(true)
            }}
          >
            全选
          </button>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setSelectedPlatforms([])
              setPlatformDirty(true)
            }}
          >
            清空(用全部)
          </button>
          <span className="muted-note">
            当前:{selectedPlatforms.length ? `${selectedPlatforms.length} 个平台` : '全部平台'}
          </span>
        </div>
      </div>

      {/* ── 关键词组 ─────────────────────────────────── */}
      <div className="card">
        <h3 className="card__title">关键词组</h3>
        <p className="card__hint">
          对应 frequency_words.txt 的一组关键词。普通词之间是「或」,必须词需全部命中,
          排除词命中即剔除该条;正则写成 /pattern/ 或 /pattern/i。
        </p>

        {groups.length === 0 && (
          <div className="empty">
            <strong>还没有关键词组</strong>
            不配置时抓取全部新闻;新增词组后只推送命中关键词的内容。
          </div>
        )}

        {groups.map((g, i) => (
          <div key={g.id ?? `new-${i}`} className="kw">
            <div className="kw__head">
              <input
                className="kw__alias"
                value={g.alias}
                onChange={(e) => patchGroup(i, { alias: e.target.value })}
                placeholder="组别名(可选),如:华为"
              />
              <label className="switch" title="启用该词组">
                <input type="checkbox" checked={g.enabled} onChange={() => toggleGroup(i)} />
                <span className="switch__track" />
              </label>
              <button className="btn btn--danger btn--sm" onClick={() => removeGroup(i)}>
                删除
              </button>
            </div>

            <div className="field">
              <label>普通词(任一命中即可)</label>
              <TagInput
                value={g.words}
                onChange={(v) => patchGroup(i, { words: v })}
                placeholder="输入后回车,如:华为、鸿蒙"
              />
            </div>

            <div className="grid-2">
              <div className="field">
                <label>必须词(需全部命中)</label>
                <TagInput
                  value={g.required}
                  onChange={(v) => patchGroup(i, { required: v })}
                  placeholder="回车添加"
                />
              </div>
              <div className="field">
                <label>排除词(命中即排除)</label>
                <TagInput
                  value={g.filters}
                  onChange={(v) => patchGroup(i, { filters: v })}
                  placeholder="回车添加"
                />
              </div>
            </div>

            <div className="kw__foot">
              <div className="field" style={{ margin: 0, maxWidth: 200 }}>
                <label htmlFor={`max-${g.id ?? i}`}>该组最多推送条数</label>
                <input
                  id={`max-${g.id ?? i}`}
                  type="number"
                  min={0}
                  max={200}
                  value={g.max_count || ''}
                  placeholder="0 = 不限"
                  onChange={(e) => patchGroup(i, { max_count: Number(e.target.value) || 0 })}
                />
              </div>
              <button
                className="btn btn--primary btn--sm"
                onClick={() => saveGroup(i)}
                disabled={busy === `group-${i}`}
              >
                {busy === `group-${i}` ? '保存中…' : g.id ? '保存词组' : '添加词组'}
              </button>
            </div>
          </div>
        ))}

        <div className="actions">
          <button className="btn btn--ghost" onClick={() => setGroups((prev) => [...prev, emptyDraft()])}>
            + 新增词组
          </button>
        </div>
      </div>

      {/* ── 全局过滤词 ───────────────────────────────── */}
      <div className="card">
        <h3 className="card__title">全局过滤词</h3>
        <p className="card__hint">
          命中任一过滤词的新闻会被整条剔除(对所有词组生效,不支持正则)。
        </p>
        <TagInput
          value={globalFilters}
          onChange={(v) => {
            setGlobalFilters(v)
            setGfDirty(true)
          }}
          placeholder="输入后回车,如:广告、招聘"
        />
        <div className="actions">
          <button className="btn btn--primary" onClick={saveGlobalFilters} disabled={busy === 'gf' || !gfDirty}>
            {busy === 'gf' ? '保存中…' : '保存过滤词'}
          </button>
        </div>
      </div>

      {/* ── 其他来源 ─────────────────────────────────── */}
      <div className="card">
        <h3 className="card__title">其他来源</h3>
        <p className="card__hint">RSS 源与交给 AI 判断的兴趣描述。</p>

        <div className="grid-2">
          <div className="field">
            <label htmlFor="otherType">类型</label>
            <select
              id="otherType"
              value={otherType}
              onChange={(e) => setOtherType(e.target.value as typeof otherType)}
            >
              <option value="rss">RSS</option>
              <option value="ai_interest">AI 兴趣</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="otherTarget">{otherType === 'rss' ? 'RSS 地址' : '兴趣描述'}</label>
            <input
              id="otherTarget"
              value={otherTarget}
              onChange={(e) => setOtherTarget(e.target.value)}
              placeholder={otherType === 'rss' ? 'https://example.com/feed.xml' : '如:关注国产大模型进展'}
            />
          </div>
        </div>
        <div className="actions">
          <button className="btn btn--primary" onClick={addOther} disabled={busy === 'other'}>
            {busy === 'other' ? '添加中…' : '添加'}
          </button>
        </div>

        {others.length > 0 && (
          <div className="rows" style={{ marginTop: 12 }}>
            {others.map((s) => (
              <div key={s.id} className={'row' + (s.enabled ? '' : ' is-off')}>
                <div className="row__main">
                  <div className="row__title">
                    {s.name || s.target}
                    <span className="tag tag--accent">{s.type === 'rss' ? 'RSS' : 'AI 兴趣'}</span>
                  </div>
                  <div className="row__sub">{s.target}</div>
                </div>
                <div className="row__actions">
                  <label className="switch">
                    <input type="checkbox" checked={s.enabled} onChange={() => toggleOther(s)} />
                    <span className="switch__track" />
                  </label>
                  <button className="btn btn--danger" onClick={() => removeOther(s)}>
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