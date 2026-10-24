import { useMemo } from 'react'
import type { Cell, LocaliseAllResult, MatrixResult, Ref, Room, Verdict } from './types'
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
  return bits.filter(Boolean).join(', ')
}

/** The value a cell shows under the current scoring mode. */
export function shown(c: Cell | null, mode: Scoring, m: MatrixResult['model']): { v: number | null; verdict: Verdict } {
  if (!c) return { v: null, verdict: 'unknown' }
  if (mode === 'ai') return { v: c.llm_guess ?? null, verdict: c.llm_guess == null ? 'unknown' : verdictOf(c.llm_guess, m.lands, m.misses) }
  return { v: c.score, verdict: c.verdict }
}

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
    const differs = p.cells[i]?.llm_guess != null && Math.abs((p.cells[i]!.llm_guess as number) - p.cells[i]!.score) >= 25
    parts.push(
      <span key={i} role="button" tabIndex={0} onClick={() => p.onPick(i)} onKeyDown={ev => (ev.key === 'Enter' || ev.key === ' ') && p.onPick(i)}
        title={`${r.name ?? r.surface}: ${v === null ? 'not scored' : Math.round(v)} (${TONE[verdict].label})`}
        className={`mark ${TONE[verdict].mark} ${p.active === i ? 'active' : ''}`}>
        {p.text.slice(s, e)}{differs && <sup className="ml-0.5 text-[9px] text-muted" aria-label="AI guess differs">◆</sup>}
      </span>,
    )
    pos = e
  }
  parts.push(p.text.slice(pos))
  return <div className="whitespace-pre-wrap text-[16.5px] leading-[1.85]">{parts}</div>
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
      <div className="flex flex-wrap items-center gap-1.5">
        {p.showPlace && (
          <>
            <input list="wil-cities" value={r.location ?? ''} placeholder="any place" aria-label="City or country"
              onChange={e => p.onChange({ ...r, name: null, location: e.target.value })}
              className="min-w-0 flex-1 rounded-full bg-white px-3 py-1 text-xs ring-1 ring-line outline-none focus:ring-ink/50" />
          </>
        )}
        <div className="flex overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label="Gender">
          {([['male', 'men'], ['female', 'women']] as const).map(([v, l]) => (
            <button key={v} onClick={() => p.onChange({ ...r, name: null, gender: r.gender === v ? null : v })} aria-pressed={r.gender === v}
              className={`px-2.5 py-1 text-xs ${r.gender === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
          ))}
        </div>
        {p.onRemove && <button onClick={p.onRemove} className="rounded-full px-2 py-1 text-xs text-muted hover:text-ink" aria-label="Remove room">remove</button>}
      </div>
      {p.recognised === false && <div className="text-xs text-risky">Qloo did not recognise this place, so it is scored without location.</div>}
    </div>
  )
}

export function TwoUp(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; active: { ref: number; room: number } | null; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void }) {
  return (
    <div className={`grid gap-4 ${p.rooms.length > 1 ? 'md:grid-cols-2' : ''}`}>
      {p.rooms.map((room, j) => {
        const cells = p.m.cells.map(row => row[j] ?? null)
        const s = p.m.summaries[j]
        const label = roomLabel(room, p.showPlace)
        return (
          <section key={j} className="rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line md:p-5">
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
  )
}

export function Grid(p: { text: string; m: MatrixResult; rooms: Room[]; mode: Scoring; showPlace: boolean; onPick: (ref: number, room: number) => void; onRoom: (i: number, r: Room) => void; onRemove: (i: number) => void }) {
  const off = useMemo(() => utf16Offsets(p.text), [p.text])
  const lineOf = (r: Ref) => {
    const s = off[r.start] ?? r.start
    const a = p.text.lastIndexOf('\n', s - 1) + 1
    const b = p.text.indexOf('\n', s)
    return p.text.slice(a, b < 0 ? undefined : b)
  }
  return (
    <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-line">
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="align-top">
            <th className="w-[30%] border-b border-line p-3 text-left text-xs font-medium uppercase tracking-wide text-muted">Reference</th>
            {p.rooms.map((room, j) => (
              <th key={j} className="border-b border-l border-line p-3 text-left font-normal">
                <div className="mb-2 font-display text-base font-semibold">{roomLabel(room, p.showPlace)}</div>
                <RoomHeader room={room} compact showPlace={p.showPlace} onChange={r => p.onRoom(j, r)} onRemove={p.rooms.length > 1 ? () => p.onRemove(j) : undefined} recognised={p.m.audiences[j]?.location_recognised} />
                {p.m.summaries[j] && <div className="mt-2"><LandBar s={p.m.summaries[j]} /></div>}
              </th>
            ))}
            <th className="border-b border-l border-line bg-paper/60 p-3 text-left font-display text-base font-semibold">Lands everywhere</th>
          </tr>
        </thead>
        <tbody>
          {p.m.references.map((r, i) => {
            const vals = p.rooms.map((_, j) => shown(p.m.cells[i]?.[j] ?? null, p.mode, p.m.model))
            const nums = vals.map(v => v.v).filter((v): v is number => v !== null)
            const min = nums.length === p.rooms.length ? Math.min(...nums) : null
            return (
              <tr key={i} className="align-top hover:bg-paper/40">
                <td className="border-b border-line p-3">
                  <div className="font-medium">{r.name ?? r.surface} <span className="ml-1 rounded-full border border-line px-1.5 text-[10px] text-muted">{TYPE_LABEL[r.type] ?? r.type}</span></div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-muted">{lineOf(r)}</div>
                </td>
                {vals.map((v, j) => (
                  <td key={j} className="border-b border-l border-line p-3">
                    <button onClick={() => p.onPick(i, j)} title={cellTitle(p.m.cells[i]?.[j] ?? null)} className="rounded-lg focus-visible:outline-2 focus-visible:outline-ink">
                      <ScoreChip score={v.v} verdict={v.verdict} />
                    </button>
                  </td>
                ))}
                <td className="border-b border-l border-line bg-paper/60 p-3"><ScoreChip score={min} verdict={verdictOf(min, p.m.model.lands, p.m.model.misses)} /></td>
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
  return (
    <section className="rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line md:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-semibold md:text-2xl">{p.r.kept ? `Rewritten to land in ${p.rooms.length === 2 ? 'both rooms' : 'every room'}` : 'No rewrite beat the original everywhere'}</h2>
        {total > 0 && <span className="text-sm text-muted">{fromQloo} of {total} stand-ins came from Qloo's graph; all were scored by Qloo in every room</span>}
      </div>
      {!p.r.kept && <p className="mt-2 text-sm text-muted">{p.r.detail ?? 'The best stand-ins did not reduce the misses across all rooms, so the text was left as it was.'}</p>}
      {p.r.kept && (
        <>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {p.rooms.map((room, j) => (
              <div key={j} className="rounded-xl bg-paper/70 p-3 text-sm">
                <div className="font-medium">{roomLabel(room, p.showPlace)}</div>
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

export function Evidence(p: { m: MatrixResult; ref_: number; room: number; rooms: Room[]; showPlace: boolean; mode: Scoring; onClose: () => void }) {
  const r = p.m.references[p.ref_]
  const c = p.m.cells[p.ref_]?.[p.room] ?? null
  const room = p.rooms[p.room]
  const label = roomLabel(room, p.showPlace)
  const v = c ? c.verdict : 'unknown'
  const sentence = c ? plain(c, room, p.showPlace) : (r.why || 'Qloo has no entity for this, so it is not scored.')
  return (
    <aside className="rise fixed inset-x-0 bottom-0 z-30 max-h-[78vh] overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl ring-1 ring-line md:inset-x-auto md:right-4 md:top-4 md:bottom-4 md:w-[400px] md:rounded-2xl" aria-label="Evidence">
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
      <p className="mt-3 text-sm">{sentence}</p>
      {c && <div className="mt-4"><Waterfall parts={c.parts} showGender={!!room.gender} showPlace={p.showPlace && !!room.location} /></div>}
      {r.age_skew && (
        <div className="mt-5">
          <div className="mb-1 text-xs font-medium text-muted">Who over-indexes on it, by age (Qloo urn:demographics)</div>
          <AgeStrip skew={r.age_skew} selected={room.age} />
        </div>
      )}
      {c && c.llm_guess != null && (
        <div className="mt-5 rounded-xl bg-paper/70 p-3 text-sm">
          <div className="flex items-center justify-between"><span className="text-muted">AI guess alone</span><span className="tabular-nums">{Math.round(c.llm_guess)}</span></div>
          <div className="flex items-center justify-between"><span className="text-muted">With Qloo data</span><span className="font-semibold tabular-nums">{Math.round(c.score)}</span></div>
          {Math.abs(c.llm_guess - c.score) >= 25 && <div className="mt-1 text-xs text-muted">The model's unaided guess and the Qloo-grounded score disagree by {Math.round(Math.abs(c.llm_guess - c.score))} points here.</div>}
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
  const bits: string[] = []
  if (room.age && Math.abs(c.parts.age) >= 3) bits.push(`${ageLabel(room.age)} ${c.parts.age > 0 ? 'over-index' : 'under-index'} on it`)
  if (showPlace && room.location && c.location != null && Math.abs(c.parts.location) >= 3) bits.push(`it is ${c.parts.location > 0 ? 'strong' : 'weak'} in ${room.location}`)
  return `${known}${bits.length ? (c.parts.age < 0 || c.parts.location < 0 ? ', but ' : ', and ') + bits.join(' and ') : ''}. Likely to land: ${Math.round(c.score)} out of 100.`
}
