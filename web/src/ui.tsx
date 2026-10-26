import { useEffect, useRef, type ReactNode } from 'react'
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

// weak verdicts are filled so they pop; strong ones stay tinted and recede
const FILL: Record<Verdict, string> = { lands: 'bg-lands/10 text-lands ring-lands/40', risky: 'bg-risky text-white ring-risky', misses: 'bg-misses text-white ring-misses', unknown: 'bg-white text-unknown ring-unknown/50' }

export function ScoreChip(p: { score: number | null | undefined; verdict: Verdict; big?: boolean; dim?: boolean; title?: string }) {
  const none = p.score === null || p.score === undefined
  return (
    <span title={p.title} className={`inline-flex items-center justify-center rounded-lg font-semibold tabular-nums ring-1 ${FILL[p.verdict]} ${p.big ? 'min-w-[3.25rem] px-2 py-1 text-xl' : 'min-w-[2.5rem] px-1.5 py-0.5 text-sm'} ${p.dim ? 'opacity-60' : ''}`}>
      <span aria-hidden>{none ? '--' : Math.round(p.score!)}</span>
      <span className="sr-only">{none ? 'not in Qloo' : `${Math.round(p.score!)}, ${TONE[p.verdict].label}`}</span>
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
  base: ['How well known it is', 'Qloo popularity'],
  age: ['Fit with this age band', 'Qloo age data'],
  gender: ['Fit with men or women', 'Qloo gender data'],
  location: ['Strength in this place', 'Qloo place rank'],
}

/** Sequential breakdown of the score in points: base, then each audience term (see server/scoring.py). */
export function Waterfall(p: { parts: Parts; showGender: boolean; showPlace: boolean; locMeasured?: boolean; demo?: boolean }) {
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
          <div key={k} className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-2 text-xs">
            <div className="leading-tight text-ink">{PART_LABEL[k][0]}<div className="text-[11px] text-muted">{p.demo ? 'demo data' : `from ${PART_LABEL[k][1]}`}{k === 'location' && !p.locMeasured ? ', weight set by hand' : ''}</div></div>
            <div className="relative h-3 rounded bg-line/70" aria-hidden>
              <div className="absolute inset-y-0 left-1/2 w-px bg-ink/15" />
              <div className={`absolute top-0 h-3 rounded ${k === 'base' ? 'bg-ink/70' : v >= 0 ? 'bg-lands' : 'bg-misses'}`} style={{ left: `${lo}%`, width: `${Math.max(0.8, hi - lo)}%` }} />
            </div>
            <div className={`text-right tabular-nums ${k === 'base' ? 'text-ink' : v >= 0 ? 'text-lands' : 'text-misses'}`}>{k === 'base' ? Math.round(v) : `${v >= 0 ? '+' : ''}${Math.round(v)}`}</div>
          </div>
        )
      })}
      <div className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-2 border-t border-line pt-1.5 text-xs font-semibold">
        <div>Likely to land</div><div /><div className="text-right tabular-nums">{Math.round(p.parts.score)}</div>
      </div>
    </div>
  )
}

export function AgeStrip(p: { skew: Record<string, number>; selected: string | null }) {
  const vals = AGES.map(([k]) => p.skew[k] ?? 0)
  const max = Math.max(0.25, ...vals.map(Math.abs))
  const said = AGES.map(([, l], i) => `${l} ${vals[i] > 0.05 ? 'keener' : vals[i] < -0.05 ? 'less keen' : 'about average'}`).join(', ')
  return (
    <div role="img" aria-label={`By age: ${said}.`}>
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

export function SourceBadge(p: { source: 'qloo' | 'ai'; why?: string; demo?: boolean }) {
  const tags = p.why?.includes('via its tags ') ? p.why.split('via its tags ')[1] : ''
  return p.source === 'qloo'
    ? <span title={p.why} className="inline-flex items-center gap-1 rounded-full bg-ink px-2 py-0.5 text-[11px] font-medium text-paper">{p.demo ? 'from the demo taste graph' : `Qloo suggested this${tags ? ` (similar taste: ${tags})` : ''}`}</span>
    : <span title={p.why} className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-2 py-0.5 text-[11px] text-muted">{p.demo ? 'AI suggested this, scored on demo data' : 'AI suggested this, checked against Qloo data'}</span>
}

export function cellTitle(c: Cell | null) {
  return c ? `${Math.round(c.score)} / 100: ${c.why}` : 'not in Qloo'
}

export function Spinner(p: { label: string }) {
  return <span role="status" className="inline-flex items-center gap-2 text-sm text-muted"><span aria-hidden className="h-3 w-3 animate-spin rounded-full border-2 border-muted/40 border-t-ink" />{p.label}</span>
}

/** Native modal dialog: focus moves in and is trapped, the page behind is inert, Escape closes, focus returns on close. */
export function Modal(p: { title: string; onClose: () => void; children: ReactNode; side?: boolean; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    const back = document.activeElement as HTMLElement | null
    d?.showModal()
    return () => { back?.focus?.() }
  }, [])
  const id = `dlg-${p.title.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <dialog ref={ref} aria-labelledby={id} onCancel={e => { e.preventDefault(); p.onClose() }} onClick={e => { if (e.target === ref.current) p.onClose() }}
      className={p.side
        ? 'rise m-0 ml-auto h-dvh max-h-dvh w-full max-w-xl overflow-y-auto overscroll-contain bg-white p-5 text-ink shadow-2xl'
        : `rise max-h-[88dvh] w-[calc(100%-2rem)] ${p.wide ? 'max-w-2xl' : 'max-w-lg'} overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 text-ink shadow-2xl`}>
      <div className="flex items-start justify-between gap-3">
        <h2 id={id} className="font-display text-2xl font-semibold leading-tight">{p.title}</h2>
        <button onClick={p.onClose} className="-mr-2 -mt-1 grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted hover:bg-paper hover:text-ink" aria-label="Close">✕</button>
      </div>
      {p.children}
    </dialog>
  )
}
