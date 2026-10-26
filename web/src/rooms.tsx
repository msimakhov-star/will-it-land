import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { Cell, LocaliseAllResult, MatrixResult, Ref, Room, Segment, Summary, Verdict } from './types'
import { AGES, AgeStrip, LandBar, ScoreChip, SourceBadge, TONE, TYPE_LABEL, Waterfall, ageLabel, headline, verdictOf } from './ui'
import { utf16Offsets } from './api'

export const CITIES = [
  'London', 'Manchester', 'Leeds', 'Glasgow', 'Edinburgh', 'Birmingham', 'Bristol', 'Liverpool', 'Dublin',
  'New York', 'Los Angeles', 'Chicago', 'Atlanta', 'Houston', 'Dallas', 'Austin', 'St. Louis', 'Miami', 'Seattle',
  'San Francisco', 'Boston', 'Philadelphia', 'Nashville', 'New Orleans', 'Detroit', 'Toronto', 'Vancouver', 'Montreal',
  'Sydney', 'Melbourne', 'Auckland', 'Mumbai', 'Delhi', 'Bangalore', 'Lagos', 'Johannesburg', 'Paris', 'Berlin',
  'Madrid', 'Amsterdam', 'Stockholm', 'Tokyo', 'Seoul', 'Singapore', 'Mexico City', 'Sao Paulo',
  'United States', 'United Kingdom', 'Texas', 'California', 'India', 'Brazil', 'Canada', 'Australia',
]

export type Scoring = 'qloo' | 'ai'
type Model = MatrixResult['model']

export function roomLabel(r: Room, showPlace: boolean) {
  if (r.name) return r.name
  const bits = [r.segment ? r.segment_name : null, r.age ? ageLabel(r.age) : (r.segment ? null : 'Any age'), r.gender === 'male' ? 'men' : r.gender === 'female' ? 'women' : null, showPlace ? r.location : null]
  const s = bits.filter(Boolean).join(', ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const whereLabel = (n: number) => (n === 1 ? 'this room' : n === 2 ? 'both rooms' : 'every room')
const labelOf = (m: MatrixResult, rooms: Room[], j: number, showPlace: boolean) => m.audiences[j]?.label ?? (rooms[j] ? roomLabel(rooms[j], showPlace) : `Room ${j + 1}`)
const refName = (r: Ref) => r.name ?? r.surface

/** The value a cell shows under the current scoring mode. */
export function shown(c: Cell | null, mode: Scoring, m: Model): { v: number | null; verdict: Verdict } {
  if (!c) return { v: null, verdict: 'unknown' }
  if (mode === 'ai') return { v: c.llm_guess ?? null, verdict: c.llm_guess == null ? 'unknown' : verdictOf(c.llm_guess, m.lands, m.misses) }
  return { v: c.score, verdict: c.verdict }
}

/** Room summary that follows the scoring mode, so the headline agrees with the marks. */
export function summaryFor(m: MatrixResult, j: number, mode: Scoring): Summary | undefined {
  const s = m.summaries[j]
  if (!s || mode === 'qloo') return s
  const v = m.cells.map(r => shown(r[j] ?? null, 'ai', m.model).verdict)
  const n = (k: Verdict) => v.filter(x => x === k).length
  return { ...s, lands: n('lands'), risky: n('risky'), misses: n('misses') }
}

const differs = (c: Cell | null | undefined) => c?.llm_guess != null && Math.abs(c.llm_guess - c.score) >= 25

/** How many references the AI alone would have put in a different verdict for room j (needs guesses). */
export function aiDisagrees(m: MatrixResult, j: number): { n: number; of: number } | null {
  const cells = m.cells.map(r => r[j]).filter((c): c is Cell => !!c)
  if (!cells.length || cells.some(c => c.llm_guess == null)) return null
  return { n: cells.filter(c => verdictOf(c.llm_guess, m.model.lands, m.model.misses) !== c.verdict).length, of: cells.length }
}

/** The reference whose score differs most between rooms: the one-line proof that the room matters. */
export function biggestSplit(m: MatrixResult): { ref: number; hi: number; lo: number; gap: number } | null {
  let best: { ref: number; hi: number; lo: number; gap: number } | null = null
  m.cells.forEach((row, i) => {
    const idx = row.map((c, j) => [c?.score, j] as const).filter((x): x is readonly [number, number] => x[0] != null)
    if (idx.length < 2) return
    const hi = idx.reduce((a, b) => (b[0] > a[0] ? b : a)), lo = idx.reduce((a, b) => (b[0] < a[0] ? b : a))
    if (!best || hi[0] - lo[0] > best.gap) best = { ref: i, hi: hi[1], lo: lo[1], gap: hi[0] - lo[0] }
  })
  return best
}

export function Legend(p: { model: Model }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted" role="note" aria-label="How to read the marks">
      <span><span className="mark mark-lands">solid</span> lands ({p.model.lands}+)</span>
      <span><span className="mark mark-risky">dotted</span> risky ({p.model.misses} to {p.model.lands - 1})</span>
      <span><span className="mark mark-misses">wavy</span> likely misses (under {p.model.misses})</span>
      <span><span className="mark mark-unknown">dashed</span> not in Qloo</span>
      <span className="hidden sm:inline">Numbers are the score out of 100. Tap a reference for the evidence.</span>
    </div>
  )
}

export function MarkedText(p: { text: string; refs: Ref[]; cells: (Cell | null)[]; mode: Scoring; model: Model; room: string; active: number | null; flash?: number | null; onPick: (i: number) => void }) {
  const off = useMemo(() => utf16Offsets(p.text), [p.text])
  const order = useMemo(() => p.refs.map((_, i) => i).sort((a, b) => p.refs[a].start - p.refs[b].start), [p.refs])
  const parts: React.ReactNode[] = []
  let pos = 0
  for (const i of order) {
    const r = p.refs[i]
    const s = off[r.start] ?? r.start, e = off[r.end] ?? r.end
    if (s < pos) continue
    parts.push(p.text.slice(pos, s))
    const { v, verdict } = shown(p.cells[i], p.mode, p.model)
    const label = `${refName(r)}, ${p.room}: ${v === null ? 'not in Qloo' : `${Math.round(v)} out of 100, ${TONE[verdict].label}`}. Open evidence.`
    parts.push(
      <span key={i} role="button" tabIndex={0} aria-label={label} title={label} data-ref={i} onClick={() => p.onPick(i)}
        onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); p.onPick(i) } }}
        className={`mark ${TONE[verdict].mark} ${p.active === i ? 'active' : ''} ${p.flash === i ? 'flash' : ''}`}>
        {p.text.slice(s, e)}
      </span>,
      v !== null && <sup key={`s${i}`} aria-hidden className={`ml-0.5 inline-block text-[11px] font-semibold tabular-nums ${TONE[verdict].text}`}>{Math.round(v)}</sup>,
      p.mode === 'ai' && differs(p.cells[i]) && <sup key={`d${i}`} aria-hidden className="ml-0.5 inline-block text-[10px] text-muted">◆</sup>,
    )
    pos = e
  }
  parts.push(p.text.slice(pos))
  return <div className="max-w-[62ch] whitespace-pre-wrap text-[17px] leading-[1.8] [text-wrap:pretty]">{parts}</div>
}

const pretty = (t: string | null) => { const s = (t ?? 'other').split(':').pop()!.replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1) }

export function RoomHeader(p: { room: Room; label: string; showPlace: boolean; segments?: Segment[]; onChange: (r: Room) => void; onRemove?: () => void; compact?: boolean }) {
  const r = p.room
  const groups = useMemo(() => {
    const g = new Map<string, Segment[]>()
    for (const x of p.segments ?? []) g.set(pretty(x.parent), [...(g.get(pretty(x.parent)) ?? []), x])
    return [...g.entries()]
  }, [p.segments])
  const pill = 'rounded-full px-2.5 py-1 text-xs transition pointer-coarse:px-3 pointer-coarse:py-2.5'
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1 pointer-coarse:gap-2" role="group" aria-label={`Age band, ${p.label}`}>
        {AGES.map(([v, l, s]) => (
          <button key={v} onClick={() => p.onChange({ ...r, name: null, age: r.age === v ? null : v })} aria-pressed={r.age === v}
            className={`${pill} ${r.age === v ? 'bg-ink text-paper' : 'bg-white text-ink ring-1 ring-line hover:ring-ink/40'}`}>{p.compact ? s : l}</button>
        ))}
      </div>
      {groups.length > 0 && (
        <select value={r.segment ?? ''} aria-label={`Audience, ${p.label}`}
          onChange={e => { const x = p.segments!.find(s => s.id === e.target.value); p.onChange({ ...r, name: null, segment: x?.id ?? null, segment_name: x?.name ?? null }) }}
          className="w-full rounded-full bg-white px-3 py-1 text-xs ring-1 ring-line outline-none focus:ring-ink/50 pointer-coarse:py-2.5 pointer-coarse:text-base">
          <option value="">Any audience (no Qloo audience segment)</option>
          {groups.map(([g, xs]) => <optgroup key={g} label={g}>{xs.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</optgroup>)}
        </select>
      )}
      <div className={`flex flex-wrap items-center gap-1.5 ${p.compact ? 'flex-col items-stretch' : ''}`}>
        {p.showPlace && (
          <input list="wil-cities" value={r.location ?? ''} placeholder="any place" aria-label={`City or country, ${p.label}`}
            onChange={e => p.onChange({ ...r, name: null, location: e.target.value })}
            className={`min-w-0 rounded-full bg-white px-3 py-1 text-xs ring-1 ring-line outline-none placeholder:text-muted focus:ring-ink/50 pointer-coarse:py-2.5 pointer-coarse:text-base ${p.compact ? 'w-full' : 'flex-1'}`} />
        )}
        <div className={`flex items-center gap-1.5 ${p.compact ? 'justify-between' : ''}`}>
          <div className="flex overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label={`Gender, ${p.label}`}>
            {([['male', 'men'], ['female', 'women']] as const).map(([v, l]) => (
              <button key={v} onClick={() => p.onChange({ ...r, name: null, gender: r.gender === v ? null : v })} aria-pressed={r.gender === v}
                className={`px-2.5 py-1 text-xs pointer-coarse:px-3 pointer-coarse:py-2.5 ${r.gender === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
            ))}
          </div>
          {p.onRemove && <button onClick={p.onRemove} className="rounded-full px-2.5 py-1 text-xs text-muted ring-1 ring-line hover:text-ink pointer-coarse:py-2.5" aria-label={`Remove room ${p.label}`}>Remove room</button>}
        </div>
      </div>
    </div>
  )
}

export function TwoUp(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; segments?: Segment[]; dim: boolean; demo: boolean; active: { ref: number; room: number } | null; flash: { ref: number; room: number } | null; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void; onAiView: () => void }) {
  const [tab, setTab] = useState(0)
  const t = Math.min(tab, p.rooms.length - 1)
  const two = p.rooms.length > 1
  return (
    <>
      {two && (
        <div className="sticky top-0 z-20 -mx-4 flex gap-2 bg-paper/95 px-4 py-2 backdrop-blur lg:hidden" role="tablist" aria-label="Rooms">
          {p.rooms.map((_, j) => {
            const s = summaryFor(p.m, j, p.mode)
            const weak = s ? s.misses + s.risky : 0
            return (
              <button key={j} role="tab" aria-selected={t === j} aria-controls={`room-${j}`} onClick={() => setTab(j)}
                className={`flex min-h-11 flex-1 items-center justify-between gap-2 rounded-xl px-3 text-left text-xs ring-1 ${t === j ? 'bg-ink text-paper ring-ink' : 'bg-white ring-line'}`}>
                <span className="truncate font-semibold">{labelOf(p.m, p.rooms, j, p.showPlace)}</span>
                {s && <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${weak ? 'bg-misses text-white' : 'bg-lands text-white'}`}>{weak ? `${weak} weak` : 'all land'}</span>}
              </button>
            )
          })}
        </div>
      )}
      <div className={`grid gap-4 ${two ? 'lg:grid-cols-2' : ''} transition-opacity ${p.dim ? 'opacity-50' : ''}`} aria-busy={p.dim}>
        {p.rooms.map((room, j) => {
          const cells = p.m.cells.map(row => row[j] ?? null)
          const s = summaryFor(p.m, j, p.mode)
          const label = labelOf(p.m, p.rooms, j, p.showPlace)
          const ai = !p.demo && p.mode === 'qloo' ? aiDisagrees(p.m, j) : null
          return (
            <section key={j} id={`room-${j}`} role={two ? 'tabpanel' : undefined} aria-labelledby={`room-h-${j}`}
              className={`${two && j !== t ? 'hidden lg:block' : ''} rounded-2xl bg-white p-4 shadow-[0_1px_0_rgba(23,21,15,.04),0_8px_24px_-14px_rgba(23,21,15,.18)] ring-1 ring-ink/10 md:p-6`}>
              {s && (
                <div className="space-y-2">
                  <h2 id={`room-h-${j}`} className="font-display text-xl font-semibold leading-snug md:min-h-[2lh] lg:min-h-0 xl:text-2xl">{headline(label, s)}</h2>
                  <LandBar s={s} />
                  {ai && ai.n > 0 && (
                    <button onClick={p.onAiView} className="text-xs text-muted underline decoration-line underline-offset-2 hover:text-ink">
                      AI alone, with no data, would have called {ai.n} of {ai.of} differently. See its guesses
                    </button>
                  )}
                </div>
              )}
              {p.m.audiences[j]?.location_recognised === false && <div className="mt-2 text-xs text-risky">Qloo did not recognise this place, so it is scored without location.</div>}
              <details className="group mt-3">
                <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-full px-2 py-1 text-xs text-muted ring-1 ring-line hover:text-ink pointer-coarse:py-2">
                  <span aria-hidden className="transition group-open:rotate-90">▸</span> Change this room
                </summary>
                <div className="mt-3"><RoomHeader room={room} label={label} showPlace={p.showPlace} segments={p.segments} onChange={r => p.onRoom(j, r)} onRemove={two ? () => p.onRemove(j) : undefined} /></div>
              </details>
              <div className="mt-4 border-t border-line pt-4">
                <MarkedText text={p.text} refs={p.m.references} cells={cells} mode={p.mode} model={p.m.model} room={label}
                  active={p.active?.room === j ? p.active.ref : null} flash={p.flash?.room === j ? p.flash.ref : null} onPick={i => p.onPick(i, j)} />
              </div>
            </section>
          )
        })}
      </div>
    </>
  )
}

export function Grid(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; segments?: Segment[]; dim: boolean; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void }) {
  const off = useMemo(() => utf16Offsets(p.text), [p.text])
  const [scrolled, setScrolled] = useState(false)
  const lineOf = (r: Ref) => {
    const s = off[r.start] ?? r.start
    const a = p.text.lastIndexOf('\n', s - 1) + 1
    const b = p.text.indexOf('\n', s)
    return p.text.slice(a, b < 0 ? undefined : b)
  }
  return (
    <div className="relative">
      <div onScroll={e => setScrolled((e.target as HTMLElement).scrollLeft > 8)}
        className={`relative overflow-x-auto rounded-2xl bg-white shadow-[0_1px_0_rgba(23,21,15,.04),0_8px_24px_-14px_rgba(23,21,15,.18)] ring-1 ring-ink/10 transition-opacity ${p.dim ? 'opacity-50' : ''}`} aria-busy={p.dim}>
        <table className="w-full border-collapse text-sm" style={{ minWidth: 104 + 72 + 112 * p.rooms.length }}>
          <caption className="sr-only">Likely to land, out of 100, for each reference in each room. The second column is the worst room.</caption>
          <thead>
            <tr className="align-top">
              <th scope="col" className="sticky left-0 z-10 w-[104px] min-w-[104px] max-w-[104px] md:max-w-none border-b border-line bg-white p-2 text-left text-xs font-medium uppercase tracking-wide text-muted md:w-[230px] md:p-3">Reference</th>
              <th scope="col" className="sticky left-[104px] z-10 w-[72px] border-b border-l-2 border-ink/80 bg-paper p-2 text-left md:static md:w-[120px] md:p-3">
                <div className="font-display text-sm font-semibold leading-tight md:text-base">Lands everywhere?</div>
                <div className="mt-0.5 hidden text-[11px] font-normal text-muted md:block">score in the worst room</div>
              </th>
              {p.rooms.map((room, j) => {
                const s = summaryFor(p.m, j, p.mode)
                const label = labelOf(p.m, p.rooms, j, p.showPlace)
                return (
                  <th key={j} scope="col" className="min-w-[112px] border-b border-l border-line p-2 text-left font-normal md:min-w-[150px] md:p-3">
                    <div className="font-display text-sm font-semibold leading-tight md:text-base">{label}</div>
                    {s && <div className="mt-1.5"><LandBar s={s} /></div>}
                    {s && <div className="mt-1 text-[11px] text-muted">{s.misses + s.risky ? `${s.misses + s.risky} of ${s.checked} weak` : `all ${s.checked} land`}</div>}
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[11px] text-muted hover:text-ink pointer-coarse:py-2">Change room</summary>
                      <div className="mt-2"><RoomHeader room={room} label={label} compact showPlace={p.showPlace} segments={p.segments} onChange={r => p.onRoom(j, r)} onRemove={p.rooms.length > 1 ? () => p.onRemove(j) : undefined} /></div>
                    </details>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {p.m.references.map((r, i) => {
              const vals = p.rooms.map((_, j) => shown(p.m.cells[i]?.[j] ?? null, p.mode, p.m.model))
              const nums = vals.map(v => v.v).filter((v): v is number => v !== null)
              const min = nums.length === p.rooms.length ? Math.min(...nums) : null
              return (
                <tr key={i} className="align-top hover:bg-paper/40">
                  <th scope="row" className="sticky left-0 z-10 w-[104px] min-w-[104px] max-w-[104px] md:max-w-none border-b border-line bg-white p-2 text-left font-normal md:p-3">
                    <div className="font-medium leading-snug">{refName(r)} <span className="ml-1 hidden rounded-full border border-line px-1.5 text-[10px] text-muted md:inline">{TYPE_LABEL[r.type] ?? r.type}</span></div>
                    <div className="mt-0.5 line-clamp-2 hidden text-xs text-muted md:block">{lineOf(r)}</div>
                  </th>
                  <td className="sticky left-[104px] z-10 border-b border-l-2 border-ink/80 bg-paper p-2 md:static md:p-3">
                    <ScoreChip big={false} score={min} verdict={verdictOf(min, p.m.model.lands, p.m.model.misses)} />
                  </td>
                  {vals.map((v, j) => (
                    <td key={j} className="border-b border-l border-line p-2 md:p-3">
                      <button onClick={() => p.onPick(i, j)} aria-label={`${refName(r)}, ${labelOf(p.m, p.rooms, j, p.showPlace)}: ${v.v === null ? 'not in Qloo' : `${Math.round(v.v)}, ${TONE[v.verdict].label}`}. Open evidence.`}
                        className="rounded-lg p-0.5 pointer-coarse:p-2">
                        <ScoreChip score={v.v} verdict={v.verdict} />
                      </button>
                      {p.mode === 'ai' && differs(p.m.cells[i]?.[j]) && <sup className="ml-0.5 text-[10px] text-muted" aria-label="AI guess differs">◆</sup>}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {!scrolled && p.rooms.length > 2 && (
        <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 flex w-16 items-center justify-end rounded-r-2xl bg-gradient-to-l from-white to-transparent pr-2 text-xs text-muted md:hidden">→</div>
      )}
      {!scrolled && p.rooms.length > 2 && <div className="mt-1 text-xs text-muted md:hidden">Swipe the table for more rooms.</div>}
    </div>
  )
}

/** Word-level diff of two lines (LCS over words); each run of changes becomes one removed block then one added block. */
export function wordDiff(a: string, b: string): { t: 'same' | 'del' | 'ins'; s: string }[] {
  const x = a.split(/\s+/).filter(Boolean), y = b.split(/\s+/).filter(Boolean)
  const n = x.length, m = y.length
  const L = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: { t: 'same' | 'del' | 'ins'; s: string }[] = []
  let dels: string[] = [], ins: string[] = []
  const flush = () => { if (dels.length) out.push({ t: 'del', s: dels.join(' ') }); if (ins.length) out.push({ t: 'ins', s: ins.join(' ') }); dels = []; ins = [] }
  let i = 0, j = 0
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { flush(); out.push({ t: 'same', s: x[i] }); i++; j++ }
    else if (j >= m || (i < n && L[i + 1][j] >= L[i][j + 1])) dels.push(x[i++])
    else ins.push(y[j++])
  }
  flush()
  return out
}

function DiffLine(p: { before: string; after: string }) {
  return (
    <p className="text-[16px] leading-8">
      {wordDiff(p.before, p.after).map((d, k) => (
        <Fragment key={k}>{k > 0 && ' '}{d.t === 'same' ? d.s
          : d.t === 'del' ? <del className="swap-del"><span className="sr-only">Removed: </span>{d.s}</del>
          : <ins className="swap-ins"><span className="sr-only">Added: </span>{d.s}</ins>}</Fragment>
      ))}
    </p>
  )
}

/** The proposed rewrite: word-level suggestions inside each changed line, and why each stand-in fits. */
export function TrackedChanges(p: { r: LocaliseAllResult; rooms: Room[]; showPlace: boolean; demo: boolean; onKeep: () => void; onUndo: () => void }) {
  const head = useRef<HTMLHeadingElement>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    head.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    head.current?.focus({ preventScroll: true })
  }, [p.r])
  const before = p.r.original.split('\n'), after = p.r.text.split('\n')
  const fromQloo = p.r.applied?.from_qloo ?? p.r.swaps.filter(s => s.source === 'qloo').length
  const total = p.r.applied?.total ?? p.r.swaps.length
  const weak = (m: MatrixResult) => m.summaries.map(s => s.misses + s.risky)
  const where = whereLabel(p.rooms.length)
  const allLand = p.r.after.summaries.every(s => s.misses + s.risky === 0)
  const checked = Math.max(...p.r.after.summaries.map(s => s.checked), 0)
  const refFor = (name: string) => p.r.before.references.find(x => refName(x).toLowerCase() === name.toLowerCase())
  const title = p.r.kept
    ? (allLand ? `Proposed rewrite: all ${checked} references would land in ${where}` : `Proposed rewrite: fewer weak references in ${where}`)
    : `No rewrite beat your original in ${where}. Your text is untouched.`
  return (
    <section className="rise scroll-mt-4 rounded-2xl bg-white p-4 shadow-[0_1px_0_rgba(23,21,15,.04),0_8px_24px_-14px_rgba(23,21,15,.18)] ring-1 ring-ink/10 md:p-6" aria-labelledby="fix-h">
      <h2 id="fix-h" ref={head} tabIndex={-1} className="scroll-mt-6 font-display text-xl font-semibold leading-snug outline-none md:text-2xl">{title}</h2>
      {!p.r.kept && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">{p.r.detail ?? 'Every stand-in we tried made one of the rooms worse, so we left your script alone.'}</p>
          <button onClick={p.onUndo} className="min-h-10 rounded-xl px-4 text-sm ring-1 ring-line hover:ring-ink/40">Close</button>
        </div>
      )}
      {p.r.kept && (
        <>
          <p className="mt-1 text-sm text-muted">
            {total > 0 && (p.demo ? `${total} stand-in${total === 1 ? '' : 's'}, each scored on demo data in every room.` : fromQloo > 0 ? `${fromQloo} of ${total} stand-ins came straight from Qloo's taste graph. Every one was scored with Qloo data in every room.` : `Every stand-in was scored with Qloo data in every room.`)}
            {' '}The score measures recognition, not whether it is funny: read each line out loud before you keep it.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {p.rooms.map((_, j) => (
              <div key={j} className="rounded-xl bg-paper/70 px-3 py-2 text-sm">
                <span className="font-medium">{labelOf(p.r.after, p.rooms, j, p.showPlace)}</span>
                <span className="ml-2 text-muted">weak references {weak(p.r.before)[j]} <span aria-hidden>→</span><span className="sr-only">to</span> <span className="font-semibold text-ink">{weak(p.r.after)[j]}</span></span>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-2">
            {after.map((line, i) => before[i] !== line ? (
              <div key={i} className="border-l-[3px] border-lands pl-3"><DiffLine before={before[i] ?? ''} after={line} /></div>
            ) : null)}
          </div>
          <ul className="mt-4 space-y-3 border-t border-line pt-4">
            {p.r.swaps.map((s, i) => {
              const ref = refFor(s.from)
              const lo = Math.round(Math.min(...s.scores_from)), hi = Math.round(Math.min(...s.scores_to))
              return (
                <li key={i} className="text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <del className="swap-del">{ref?.surface ?? s.from}</del><span className="sr-only">replaced by</span><span aria-hidden>→</span><ins className="swap-ins">{s.to}</ins>
                    <SourceBadge source={s.source} why={s.why} demo={p.demo} />
                    <span className="text-xs text-muted" title="The lowest score across your rooms. We pick the stand-in that raises it most.">weakest room {lo} → <span className="font-semibold text-ink">{hi}</span></span>
                  </div>
                  {ref?.role && <div className="mt-0.5 text-xs text-muted">Plays the same part: {ref.role}.</div>}
                </li>
              )
            })}
          </ul>
          <div className="sticky bottom-0 -mx-4 mt-4 flex flex-wrap gap-2 bg-white/95 px-4 py-3 backdrop-blur md:static md:mx-0 md:bg-transparent md:p-0">
            <button onClick={p.onKeep} className="min-h-10 rounded-xl bg-ink px-4 text-sm font-medium text-paper">Keep this version</button>
            <button onClick={p.onUndo} className="min-h-10 rounded-xl px-4 text-sm ring-1 ring-line hover:ring-ink/40">Undo</button>
            <button onClick={() => navigator.clipboard?.writeText(p.r.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})}
              className="min-h-10 rounded-xl px-4 text-sm ring-1 ring-line hover:ring-ink/40">{copied ? 'Copied' : 'Copy revised script'}</button>
          </div>
        </>
      )}
    </section>
  )
}

export function Evidence(p: { m: MatrixResult; ref_: number; room: number; rooms: Room[]; showPlace: boolean; locMeasured: boolean; demo: boolean; onRoom: (j: number) => void; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null)
  const back = useRef<HTMLElement | null>(null)
  useEffect(() => {
    back.current = document.activeElement as HTMLElement | null
    close.current?.focus({ preventScroll: true })
    // on phones, keep the tapped word visible above the sheet
    if (window.matchMedia('(max-width: 767px)').matches) (document.querySelector(`#room-${p.room} [data-ref="${p.ref_}"]`) ?? back.current)?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
    const b = back.current
    return () => { b?.focus?.({ preventScroll: true }) }
  }, [])
  const r = p.m.references[p.ref_]
  const c = p.m.cells[p.ref_]?.[p.room] ?? null
  const room = p.rooms[p.room]
  const label = labelOf(p.m, p.rooms, p.room, p.showPlace)
  const v = c ? c.verdict : 'unknown'
  const sentence = c ? plain(c, room, p.showPlace) : (r.why || 'Qloo has no entity for this, so it is not scored.')
  const others = p.m.cells[p.ref_]?.map((x, j) => (x && j !== p.room ? x.score : null)).filter((x): x is number => x != null) ?? []
  return (
    <>
      <div className="fixed inset-0 z-30 bg-ink/20 md:hidden" onClick={p.onClose} aria-hidden />
      <aside role="dialog" aria-labelledby="ev-h"
        className="rise fixed inset-x-0 bottom-0 z-40 max-h-[62dvh] overflow-y-auto overscroll-contain rounded-t-2xl bg-white p-5 pt-3 shadow-2xl ring-1 ring-line md:inset-x-auto md:bottom-4 md:right-4 md:top-4 md:max-h-none md:w-[380px] md:rounded-2xl md:pt-5">
        <div aria-hidden className="mx-auto mb-3 h-1 w-9 rounded-full bg-line md:hidden" />
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
            <h3 id="ev-h" className="font-display text-2xl font-semibold leading-tight">{refName(r)}</h3>
            <div className="mt-0.5 text-xs text-muted">{TYPE_LABEL[r.type] ?? r.type}{r.name && r.name !== r.surface ? `, written as "${r.surface}"` : ''}{!p.demo && r.trend && r.trend.direction !== 'flat' ? `, ${r.trend.direction} over six months` : ''}</div>
          </div>
          <div className="flex items-center gap-1">
            <ScoreChip big score={c?.score} verdict={v} />
            <button ref={close} onClick={p.onClose} className="grid h-11 w-11 place-items-center rounded-full text-muted hover:bg-paper hover:text-ink" aria-label="Close evidence">✕</button>
          </div>
        </div>
        {p.rooms.length > 1 && (
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Same reference in each room">
            {p.rooms.map((_, j) => {
              const cj = p.m.cells[p.ref_]?.[j]
              return (
                <button key={j} onClick={() => p.onRoom(j)} aria-pressed={j === p.room} className={`inline-flex min-h-9 items-center gap-1.5 rounded-full py-0.5 pl-2.5 pr-0.5 text-xs ring-1 ${j === p.room ? 'bg-paper font-semibold ring-ink/40' : 'ring-line'}`}>
                  <span className="text-muted">{labelOf(p.m, p.rooms, j, p.showPlace)}</span><ScoreChip score={cj?.score} verdict={cj?.verdict ?? 'unknown'} />
                </button>
              )
            })}
          </div>
        )}
        <p className="mt-3 text-[15px]">{sentence}</p>
        {c && others.length > 0 && Math.abs(Math.max(...others) - c.score) >= 25 && (
          <p className="mt-1 text-xs text-muted">Same reference, other rooms: up to {Math.round(Math.max(...others))}. The room changes the answer by {Math.round(Math.abs(Math.max(...others) - c.score))} points.</p>
        )}
        {c && <div className="mt-4"><Waterfall parts={c.parts} showGender={!!room.gender} showPlace={p.showPlace && !!room.location} showSegment={!!room.segment} locMeasured={p.locMeasured} demo={p.demo} /></div>}
        {r.age_skew && (
          <div className="mt-5">
            <div className="mb-1 text-xs font-medium text-muted">Which ages are keener (green) or less keen (red){p.demo ? ', demo data' : ', from Qloo age data'}</div>
            <AgeStrip skew={r.age_skew} selected={room.age} />
          </div>
        )}
        {!p.demo && c && c.llm_guess != null && (
          <div className="mt-5 rounded-xl bg-paper/70 p-3 text-sm">
            <div className="flex items-center justify-between"><span className="text-muted">AI's own guess, no data</span><span className="tabular-nums">{Math.round(c.llm_guess)}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted">Score with Qloo data</span><span className="font-semibold tabular-nums">{Math.round(c.score)}</span></div>
          </div>
        )}
        {r.candidates.length > 1 && (
          <div className="mt-5 text-xs text-muted">
            Matched to <span className="text-ink">{r.name}</span>{r.disambiguation ? ` (${r.disambiguation})` : ''}. Other Qloo entities with this name: {r.candidates.filter(x => x.entity_id !== r.entity_id).map(x => x.name).slice(0, 4).join(', ')}.
          </div>
        )}
        {r.role && <div className="mt-2 text-xs text-muted">Its part in the line: {r.role}.</div>}
      </aside>
    </>
  )
}

function plain(c: Cell, room: Room, showPlace: boolean): string {
  const known = c.parts.base >= 70 ? 'Most people have heard of it' : c.parts.base >= 45 ? 'Plenty of people have heard of it' : 'Not many people have heard of it'
  const who = room.age === '24_and_younger' ? 'under 25s' : room.age === '55_and_older' ? 'people over 55' : room.age ? `people aged ${ageLabel(room.age)}` : ''
  const neg: string[] = [], pos: string[] = []
  if (room.age && Math.abs(c.parts.age) >= 3) (c.parts.age < 0 ? neg : pos).push(`${who} are ${c.parts.age < 0 ? 'less' : 'more'} keen`)
  if (showPlace && room.location && c.location != null && Math.abs(c.parts.location) >= 3) (c.parts.location < 0 ? neg : pos).push(c.parts.location > 0 ? `${room.location} helps` : `it is weak in ${room.location}`)
  if (room.segment && c.segment != null && Math.abs(c.parts.segment ?? 0) >= 3) ((c.parts.segment ?? 0) < 0 ? neg : pos).push((c.parts.segment ?? 0) > 0 ? `${room.segment_name ?? 'this audience'} like it more than most` : `${room.segment_name ?? 'this audience'} are cooler on it`)
  const tail = neg.length ? `, but ${neg.join(' and ')}` : ''
  const plus = pos.length ? `${neg.length ? '. On the plus side, ' : ', and '}${pos.join(' and ')}` : ''
  const s = `${known}${tail}${plus}.`
  return s.charAt(0).toUpperCase() + s.slice(1).replace('. on the plus side', '. On the plus side')
}
