import { useMemo, useState } from 'react'
import type { Cell, LocaliseAllResult, MatrixResult, Ref, Room, Summary, Verdict } from './types'
import { AGES, AgeStrip, LandBar, ScoreChip, SourceBadge, TONE, TYPE_LABEL, Waterfall, ageLabel, cellTitle, headline, verdictOf } from './ui'
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

export function roomLabel(r: Room, showPlace: boolean) {
  if (r.name) return r.name
  const bits = [r.age ? ageLabel(r.age) : 'Any age', r.gender === 'male' ? 'men' : r.gender === 'female' ? 'women' : null, showPlace ? r.location : null]
  const s = bits.filter(Boolean).join(', ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const whereLabel = (n: number) => (n === 1 ? 'this room' : n === 2 ? 'both rooms' : 'every room')

/** The value a cell shows under the current scoring mode. */
export function shown(c: Cell | null, mode: Scoring, m: MatrixResult['model']): { v: number | null; verdict: Verdict } {
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

export function MarkedText(p: { text: string; refs: Ref[]; cells: (Cell | null)[]; mode: Scoring; model: MatrixResult['model']; active: number | null; onPick: (i: number) => void }) {
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
    const label = `${r.name ?? r.surface}: ${v === null ? 'not in Qloo' : `${Math.round(v)} out of 100, ${TONE[verdict].label}`}. Open evidence.`
    parts.push(
      <span key={i} role="button" tabIndex={0} aria-label={label} title={label} onClick={() => p.onPick(i)}
        onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); p.onPick(i) } }}
        className={`mark ${TONE[verdict].mark} ${p.active === i ? 'active' : ''}`}>
        {p.text.slice(s, e)}
      </span>,
      v !== null && <sup key={`s${i}`} aria-hidden className={`ml-0.5 inline-block text-[10px] font-semibold tabular-nums ${TONE[verdict].text}`}>{Math.round(v)}</sup>,
      p.mode === 'ai' && differs(p.cells[i]) && <sup key={`d${i}`} aria-hidden className="ml-0.5 inline-block text-[9px] text-muted">◆</sup>,
    )
    pos = e
  }
  parts.push(p.text.slice(pos))
  return <div className="whitespace-pre-wrap text-[16.5px] leading-[1.9]">{parts}</div>
}

export function RoomHeader(p: { room: Room; showPlace: boolean; onChange: (r: Room) => void; onRemove?: () => void; compact?: boolean; recognised?: boolean | null }) {
  const r = p.room
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1" role="group" aria-label="Age band">
        {AGES.map(([v, l, s]) => (
          <button key={v} onClick={() => p.onChange({ ...r, name: null, age: r.age === v ? null : v })} aria-pressed={r.age === v}
            className={`rounded-full px-2.5 py-1 text-xs transition ${r.age === v ? 'bg-ink text-paper' : 'bg-white text-ink ring-1 ring-line hover:ring-ink/40'}`}>{p.compact ? s : l}</button>
        ))}
      </div>
      <div className={`flex flex-wrap items-center gap-1.5 ${p.compact ? 'flex-col items-stretch' : ''}`}>
        {p.showPlace && (
          <input list="wil-cities" value={r.location ?? ''} placeholder="any place" aria-label="City or country"
            onChange={e => p.onChange({ ...r, name: null, location: e.target.value })}
            className={`min-w-0 rounded-full bg-white px-3 py-1 text-xs ring-1 ring-line outline-none focus:ring-ink/50 ${p.compact ? 'w-full' : 'flex-1'}`} />
        )}
        <div className={`flex items-center gap-1.5 ${p.compact ? 'justify-between' : ''}`}>
          <div className="flex overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label="Gender">
            {([['male', 'men'], ['female', 'women']] as const).map(([v, l]) => (
              <button key={v} onClick={() => p.onChange({ ...r, name: null, gender: r.gender === v ? null : v })} aria-pressed={r.gender === v}
                className={`px-2.5 py-1 text-xs ${r.gender === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
            ))}
          </div>
          {p.onRemove && <button onClick={p.onRemove} className="rounded-full px-2 py-1 text-xs text-muted hover:text-ink" aria-label="Remove room">remove</button>}
        </div>
      </div>
      {p.recognised === false && <div className="text-xs text-risky">Qloo did not recognise this place, so it is scored without location.</div>}
    </div>
  )
}

export function TwoUp(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; dim: boolean; active: { ref: number; room: number } | null; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void }) {
  const [tab, setTab] = useState(0)
  const t = Math.min(tab, p.rooms.length - 1)
  return (
    <>
      {p.rooms.length > 1 && (
        <div className="sticky top-0 z-20 -mx-4 grid grid-cols-2 gap-2 bg-paper/95 px-4 py-2 md:hidden">
          {p.rooms.map((room, j) => {
            const s = summaryFor(p.m, j, p.mode)
            return s && (
              <button key={j} onClick={() => setTab(j)} aria-pressed={t === j} className={`rounded-xl p-2 text-left text-xs ring-1 ${t === j ? 'bg-ink text-paper ring-ink' : 'bg-white ring-line'}`}>
                <div className="font-semibold leading-snug">{headline(p.m.audiences[j]?.label ?? roomLabel(room, p.showPlace), s)}</div>
                <div className="mt-1"><LandBar s={s} /></div>
              </button>
            )
          })}
        </div>
      )}
      <div className={`grid gap-4 ${p.rooms.length > 1 ? 'md:grid-cols-2' : ''} ${p.dim ? 'opacity-50' : ''}`}>
        {p.rooms.map((room, j) => {
          const cells = p.m.cells.map(row => row[j] ?? null)
          const s = summaryFor(p.m, j, p.mode)
          const label = p.m.audiences[j]?.label ?? roomLabel(room, p.showPlace)
          return (
            <section key={j} className={`${p.rooms.length > 1 && j !== t ? 'hidden md:block' : ''} rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line md:p-5`}>
              <RoomHeader room={room} showPlace={p.showPlace} onChange={r => p.onRoom(j, r)} onRemove={p.rooms.length > 1 ? () => p.onRemove(j) : undefined} recognised={p.m.audiences[j]?.location_recognised} />
              {s && (
                <div className="mt-4 space-y-2">
                  <h2 className="font-display text-xl font-semibold leading-snug md:text-2xl">{headline(label, s)}</h2>
                  <LandBar s={s} />
                </div>
              )}
              <div className="mt-4 border-t border-line pt-4">
                <MarkedText text={p.text} refs={p.m.references} cells={cells} mode={p.mode} model={p.m.model} active={p.active?.room === j ? p.active.ref : null} onPick={i => p.onPick(i, j)} />
              </div>
            </section>
          )
        })}
      </div>
    </>
  )
}

export function Grid(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; dim: boolean; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void }) {
  const off = useMemo(() => utf16Offsets(p.text), [p.text])
  const lineOf = (r: Ref) => {
    const s = off[r.start] ?? r.start
    const a = p.text.lastIndexOf('\n', s - 1) + 1
    const b = p.text.indexOf('\n', s)
    return p.text.slice(a, b < 0 ? undefined : b)
  }
  return (
    <div className={`overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-line ${p.dim ? 'opacity-50' : ''}`}>
      <table className="w-full border-collapse text-sm" style={{ minWidth: 140 + 120 + 150 * p.rooms.length }}>
        <thead>
          <tr className="align-top">
            <th className="sticky left-0 z-10 w-[140px] border-b border-line bg-white p-3 text-left text-xs font-medium uppercase tracking-wide text-muted md:w-[230px]">Reference</th>
            <th className="w-[120px] border-b border-l border-line bg-paper p-3 text-left font-display text-base font-semibold">Lands everywhere</th>
            {p.rooms.map((room, j) => {
              const s = summaryFor(p.m, j, p.mode)
              return (
                <th key={j} className="min-w-[150px] border-b border-l border-line p-3 text-left font-normal">
                  <div className="font-display text-base font-semibold leading-tight">{p.m.audiences[j]?.label ?? roomLabel(room, p.showPlace)}</div>
                  {s && <div className="mt-1.5"><LandBar s={s} /></div>}
                  {s && <div className="mt-1 text-[11px] text-muted">{s.misses + s.risky ? `${s.misses + s.risky} weak of ${s.checked}` : `all ${s.checked} land`}</div>}
                  <details className="mt-1">
                    <summary className="cursor-pointer text-[11px] text-muted hover:text-ink">edit room</summary>
                    <div className="mt-2"><RoomHeader room={room} compact showPlace={p.showPlace} onChange={r => p.onRoom(j, r)} onRemove={p.rooms.length > 1 ? () => p.onRemove(j) : undefined} recognised={p.m.audiences[j]?.location_recognised} /></div>
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
                <td className="sticky left-0 z-10 border-b border-line bg-white p-3">
                  <div className="font-medium">{r.name ?? r.surface} <span className="ml-1 rounded-full border border-line px-1.5 text-[10px] text-muted">{TYPE_LABEL[r.type] ?? r.type}</span></div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-muted">{lineOf(r)}</div>
                </td>
                <td className="border-b border-l border-line bg-paper p-3"><ScoreChip score={min} verdict={verdictOf(min, p.m.model.lands, p.m.model.misses)} /></td>
                {vals.map((v, j) => (
                  <td key={j} className="border-b border-l border-line p-3">
                    <button onClick={() => p.onPick(i, j)} title={cellTitle(p.m.cells[i]?.[j] ?? null)} aria-label={`${r.name ?? r.surface} for ${p.m.audiences[j]?.label ?? 'this room'}: ${v.v === null ? 'not in Qloo' : Math.round(v.v)}. Open evidence.`} className="rounded-lg focus-visible:outline-2 focus-visible:outline-ink">
                      <ScoreChip score={v.v} verdict={v.verdict} />
                    </button>
                    {p.mode === 'ai' && differs(p.m.cells[i]?.[j]) && <sup className="ml-0.5 text-[9px] text-muted" aria-label="AI guess differs">◆</sup>}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Tracked changes: each rewritten line shown struck through, with the new line under it. */
export function TrackedChanges(p: { r: LocaliseAllResult; rooms: Room[]; showPlace: boolean; onKeep: () => void; onUndo: () => void }) {
  const before = p.r.original.split('\n'), after = p.r.text.split('\n')
  const fromQloo = p.r.applied?.from_qloo ?? p.r.swaps.filter(s => s.source === 'qloo').length
  const total = p.r.applied?.total ?? p.r.swaps.length
  const sums = (m: MatrixResult) => m.summaries.map(s => s.misses + s.risky)
  const where = whereLabel(p.rooms.length)
  const allLand = p.r.after.summaries.every(s => s.misses + s.risky === 0)
  return (
    <section className="rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line md:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-semibold md:text-2xl">{p.r.kept ? (allLand ? `Rewritten: every reference now lands in ${where}` : `Rewritten: fewer weak references in ${where}`) : `No rewrite beat the original in ${where}`}</h2>
        {p.r.kept && total > 0 && <span className="text-sm text-muted">{fromQloo > 0 ? `${fromQloo} of ${total} stand-ins came straight from Qloo's graph; every one was scored by Qloo in each room` : `Every stand-in was scored by Qloo in each room`}</span>}
      </div>
      {!p.r.kept && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">{p.r.detail ?? 'The best stand-ins would have made a room worse or did not reduce the weak references, so the text was left as it was.'}</p>
          <button onClick={p.onUndo} className="rounded-xl px-3 py-1.5 text-sm ring-1 ring-line hover:ring-ink/40">Close</button>
        </div>
      )}
      {p.r.kept && (
        <>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {p.rooms.map((room, j) => (
              <div key={j} className="rounded-xl bg-paper/70 p-3 text-sm">
                <div className="font-medium">{p.r.after.audiences[j]?.label ?? roomLabel(room, p.showPlace)}</div>
                <div className="text-muted">weak references: {sums(p.r.before)[j]} → <span className="font-semibold text-ink">{sums(p.r.after)[j]}</span></div>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-2 text-[15.5px] leading-7">
            {after.map((line, i) => before[i] !== line ? (
              <div key={i} className="rounded-lg border border-line p-2">
                <div className="del">{before[i]}</div>
                <div className="ins">{line}</div>
              </div>
            ) : null)}
          </div>
          <ul className="mt-4 space-y-2">
            {p.r.swaps.map((s, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="del px-1">{s.from}</span><span aria-hidden>→</span><span className="ins px-1 font-medium">{s.to}</span>
                <SourceBadge source={s.source} why={s.why} />
                <span className="text-xs text-muted">worst room {Math.round(Math.min(...s.scores_from))} → {Math.round(Math.min(...s.scores_to))}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={p.onKeep} className="rounded-xl bg-ink px-4 py-2 text-sm font-medium text-paper">Keep this version</button>
            <button onClick={p.onUndo} className="rounded-xl px-4 py-2 text-sm ring-1 ring-line hover:ring-ink/40">Undo</button>
            <button onClick={() => navigator.clipboard?.writeText(p.r.text).catch(() => {})} className="rounded-xl px-4 py-2 text-sm ring-1 ring-line hover:ring-ink/40">Copy revised script</button>
          </div>
        </>
      )}
    </section>
  )
}

export function Evidence(p: { m: MatrixResult; ref_: number; room: number; rooms: Room[]; showPlace: boolean; locMeasured: boolean; onRoom: (j: number) => void; onClose: () => void }) {
  const r = p.m.references[p.ref_]
  const c = p.m.cells[p.ref_]?.[p.room] ?? null
  const room = p.rooms[p.room]
  const label = p.m.audiences[p.room]?.label ?? roomLabel(room, p.showPlace)
  const v = c ? c.verdict : 'unknown'
  const sentence = c ? plain(c, room, p.showPlace) : (r.why || 'Qloo has no entity for this, so it is not scored.')
  return (
    <aside className="rise fixed inset-x-0 bottom-0 z-30 max-h-[78vh] overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl ring-1 ring-line md:inset-x-auto md:right-4 md:top-4 md:bottom-4 md:w-[380px] md:rounded-2xl" aria-label="Evidence" role="dialog">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
          <h3 className="font-display text-2xl font-semibold leading-tight">{r.name ?? r.surface}</h3>
          <div className="mt-0.5 text-xs text-muted">{TYPE_LABEL[r.type] ?? r.type}{r.name && r.name !== r.surface ? `, written as "${r.surface}"` : ''}{r.trend && r.trend.direction !== 'flat' ? `, ${r.trend.direction} over six months` : ''}</div>
        </div>
        <div className="flex items-center gap-2">
          <ScoreChip big score={c?.score} verdict={v} />
          <button onClick={p.onClose} className="rounded-full p-1.5 text-muted hover:bg-paper hover:text-ink" aria-label="Close">✕</button>
        </div>
      </div>
      {p.rooms.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {p.rooms.map((rm, j) => {
            const cj = p.m.cells[p.ref_]?.[j]
            return (
              <button key={j} onClick={() => p.onRoom(j)} aria-pressed={j === p.room} className={`inline-flex items-center gap-1.5 rounded-full py-0.5 pl-2.5 pr-0.5 text-xs ring-1 ${j === p.room ? 'bg-paper font-semibold ring-ink/40' : 'ring-line'}`}>
                <span className="text-muted">{p.m.audiences[j]?.label ?? roomLabel(rm, p.showPlace)}</span><ScoreChip score={cj?.score} verdict={cj?.verdict ?? 'unknown'} />
              </button>
            )
          })}
        </div>
      )}
      <p className="mt-3 text-sm">{sentence}</p>
      {c && <div className="mt-4"><Waterfall parts={c.parts} showGender={!!room.gender} showPlace={p.showPlace && !!room.location} locMeasured={p.locMeasured} /></div>}
      {r.age_skew && (
        <div className="mt-5">
          <div className="mb-1 text-xs font-medium text-muted">Who leans towards it, by age (Qloo demographics)</div>
          <AgeStrip skew={r.age_skew} selected={room.age} />
        </div>
      )}
      {c && c.llm_guess != null && (
        <div className="mt-5 rounded-xl bg-paper/70 p-3 text-sm">
          <div className="flex items-center justify-between"><span className="text-muted">AI's own estimate (no data)</span><span className="tabular-nums">{Math.round(c.llm_guess)}</span></div>
          <div className="flex items-center justify-between"><span className="text-muted">Qloo-grounded score</span><span className="font-semibold tabular-nums">{Math.round(c.score)}</span></div>
        </div>
      )}
      {r.candidates.length > 1 && (
        <div className="mt-5 text-xs text-muted">
          Matched to <span className="text-ink">{r.name}</span>{r.disambiguation ? ` (${r.disambiguation})` : ''}. Other Qloo entities with this name: {r.candidates.filter(x => x.entity_id !== r.entity_id).map(x => x.name).slice(0, 4).join(', ')}.
        </div>
      )}
      {r.role && <div className="mt-2 text-xs text-muted">Role in the line: {r.role}.</div>}
    </aside>
  )
}

function plain(c: Cell, room: Room, showPlace: boolean): string {
  const known = c.parts.base >= 70 ? 'Widely known' : c.parts.base >= 45 ? 'Fairly well known' : 'Not widely known'
  const who = room.age === '24_and_younger' ? 'people under 25' : room.age === '55_and_older' ? 'people 55 and over' : room.age ? `people aged ${ageLabel(room.age)}` : ''
  const neg: string[] = [], pos: string[] = []
  if (room.age && Math.abs(c.parts.age) >= 3) (c.parts.age < 0 ? neg : pos).push(`${who} ${c.parts.age > 0 ? 'lean towards it' : 'lean away from it'}`)
  if (showPlace && room.location && c.location != null && Math.abs(c.parts.location) >= 3) (c.parts.location < 0 ? neg : pos).push(`it is ${c.parts.location > 0 ? 'strong' : 'weak'} in ${room.location}`)
  return `${known}${neg.length ? ', but ' + neg.join(' and ') : ''}${pos.length ? (neg.length ? ', though ' : ', and ') + pos.join(' and ') : ''}. Likely to land: ${Math.round(c.score)} out of 100.`
}
