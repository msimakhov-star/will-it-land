import type { Cell, Parts, Summary, Verdict } from './types'

export const AGES: [string, string, string][] = [
  ['24_and_younger', 'under 25', '<25'], ['25_to_29', '25 to 29', '25'], ['30_to_34', '30 to 34', '30'],
  ['35_to_44', '35 to 44', '35'], ['45_to_54', '45 to 54', '45'], ['55_and_older', '55+', '55+'],
]
export const ageLabel = (a: string | null) => (a ? AGES.find(x => x[0] === a)?.[1] ?? a : 'any age')

export const TYPE_LABEL: Record<string, string> = { tv_show: 'TV', movie: 'film', artist: 'music', brand: 'brand', person: 'person', book: 'book', videogame: 'game', podcast: 'podcast', place: 'place' }

// Static class maps (Tailwind cannot see dynamically built class names)
export const TONE: Record<Verdict, { text: string; bg: string; ring: string; mark: string; label: string }> = {
  lands: { text: 'text-lands', bg: 'bg-lands/10', ring: 'ring-lands/40', mark: 'mark-lands', label: 'lands' },
  risky: { text: 'text-risky', bg: 'bg-risky/10', ring: 'ring-risky/40', mark: 'mark-risky', label: 'risky' },
  misses: { text: 'text-misses', bg: 'bg-misses/10', ring: 'ring-misses/40', mark: 'mark-misses', label: 'likely misses' },
  unknown: { text: 'text-unknown', bg: 'bg-unknown/10', ring: 'ring-unknown/40', mark: 'mark-unknown', label: 'not in Qloo' },
}

export function verdictOf(score: number | null | undefined, lands: number, misses: number): Verdict {
  if (score === null || score === undefined) return 'unknown'
  return score >= lands ? 'lands' : score >= misses ? 'risky' : 'misses'
}

export function ScoreChip(p: { score: number | null | undefined; verdict: Verdict; big?: boolean; dim?: boolean; title?: string }) {
  const t = TONE[p.verdict]
  return (
    <span title={p.title} className={`inline-flex items-center justify-center rounded-lg font-semibold tabular-nums ring-1 ${t.bg} ${t.text} ${t.ring} ${p.big ? 'min-w-[3.25rem] px-2 py-1 text-xl' : 'min-w-[2.5rem] px-1.5 py-0.5 text-sm'} ${p.dim ? 'opacity-60' : ''}`}>
      {p.score === null || p.score === undefined ? '--' : Math.round(p.score)}
    </span>
  )
}

export function LandBar(p: { s: Summary }) {
  const total = Math.max(1, p.s.lands + p.s.risky + p.s.misses + p.s.not_in_qloo)
  const seg = (n: number, cls: string, label: string) => n > 0 && <div className={cls} style={{ width: `${(100 * n) / total}%` }} title={`${n} ${label}`} />
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-line" aria-hidden>
      {seg(p.s.lands, 'bg-lands', 'land')}
      {seg(p.s.risky, 'bg-risky', 'risky')}
      {seg(p.s.misses, 'bg-misses', 'likely miss')}
      {seg(p.s.not_in_qloo, 'bg-unknown/50', 'not in Qloo')}
    </div>
  )
}

export function headline(label: string, s: Summary): string {
  if (!s.checked) return s.found ? `${label}: none of the references are in Qloo` : `${label}: no cultural references found`
  const weak = s.misses + s.risky
  if (weak === 0) return `${label}: all ${s.checked} land`
  if (s.misses) return `${label}: ${s.misses} of ${s.checked} will likely miss${s.risky ? `, ${s.risky} risky` : ''}`
  return `${label}: ${s.risky} of ${s.checked} risky`
}

const PART_LABEL: Record<keyof Omit<Parts, 'score'>, [string, string]> = {
  base: ['How widely known', '/search popularity'],
  age: ['This age band', 'urn:demographics'],
  gender: ['Men or women', 'urn:demographics'],
  location: ['This place', 'insights rank in place'],
}

/** Sequential breakdown of the score in points: base, then each audience term (see server/scoring.py). */
export function Waterfall(p: { parts: Parts; showGender: boolean; showPlace: boolean }) {
  const rows = (['base', 'age', ...(p.showGender ? ['gender'] : []), ...(p.showPlace ? ['location'] : [])] as (keyof Omit<Parts, 'score'>)[])
  let acc = 0
  return (
    <div className="space-y-1.5">
      {rows.map(k => {
        const v = p.parts[k]
        const from = k === 'base' ? 0 : acc
        acc = k === 'base' ? v : acc + v
        const lo = Math.min(from, acc), hi = Math.max(from, acc)
        return (
          <div key={k} className="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-2 text-xs">
            <div className="text-muted leading-tight">{PART_LABEL[k][0]}<div className="text-[10px] text-muted/70">{PART_LABEL[k][1]}</div></div>
            <div className="relative h-3 rounded bg-line/70">
              <div className={`absolute top-0 h-3 rounded ${k === 'base' ? 'bg-ink/70' : v >= 0 ? 'bg-lands' : 'bg-misses'}`} style={{ left: `${lo}%`, width: `${Math.max(0.8, hi - lo)}%` }} />
            </div>
            <div className={`text-right tabular-nums ${k === 'base' ? 'text-ink' : v >= 0 ? 'text-lands' : 'text-misses'}`}>{k === 'base' ? Math.round(v) : `${v >= 0 ? '+' : ''}${Math.round(v)}`}</div>
          </div>
        )
      })}
      <div className="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-2 border-t border-line pt-1.5 text-xs font-semibold">
        <div>Likely to land</div><div /><div className="text-right tabular-nums">{Math.round(p.parts.score)}</div>
      </div>
    </div>
  )
}

export function AgeStrip(p: { skew: Record<string, number>; selected: string | null }) {
  const vals = AGES.map(([k]) => p.skew[k] ?? 0)
  const max = Math.max(0.25, ...vals.map(Math.abs))
  return (
    <div>
      <div className="flex h-12 items-center gap-1">
        {vals.map((v, i) => {
          const h = Math.round((48 * Math.abs(v)) / max)
          const sel = AGES[i][0] === p.selected
          return (
            <div key={i} className={`relative flex h-full flex-1 flex-col ${sel ? 'rounded ring-2 ring-ink/70' : ''}`} title={`${AGES[i][1]}: ${v >= 0 ? '+' : ''}${v.toFixed(2)}`}>
              <div className="flex h-1/2 items-end">{v > 0 && <div className="w-full rounded-t-sm bg-lands/70" style={{ height: `${h}%` }} />}</div>
              <div className="flex h-1/2 items-start border-t border-line">{v < 0 && <div className="w-full rounded-b-sm bg-misses/70" style={{ height: `${h}%` }} />}</div>
            </div>
          )
        })}
      </div>
      <div className="mt-1 flex gap-1 text-[10px] text-muted">{AGES.map(([k, , s]) => <div key={k} className={`flex-1 text-center ${k === p.selected ? 'font-semibold text-ink' : ''}`}>{s}</div>)}</div>
    </div>
  )
}

export function SourceBadge(p: { source: 'qloo' | 'ai'; why?: string }) {
  return p.source === 'qloo'
    ? <span title={p.why} className="inline-flex items-center gap-1 rounded-full bg-ink px-2 py-0.5 text-[11px] font-medium text-paper">found in Qloo's graph</span>
    : <span title={p.why} className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-2 py-0.5 text-[11px] text-muted">model idea, scored by Qloo</span>
}

export function cellTitle(c: Cell | null) {
  return c ? `${Math.round(c.score)} / 100: ${c.why}` : 'not in Qloo'
}

export function Spinner(p: { label: string }) {
  return <span className="inline-flex items-center gap-2 text-sm text-muted"><span className="h-3 w-3 animate-spin rounded-full border-2 border-muted/40 border-t-ink" />{p.label}</span>
}
