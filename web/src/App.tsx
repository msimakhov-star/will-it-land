import { useEffect, useMemo, useRef, useState } from 'react'

type Swap = { name: string; entity_id: string; score: number; line: string | null }
type Ref = {
  surface: string; start: number; end: number; type: string; query: string; role: string; era: string | null
  llm_guess: number; entity_id: string | null; name: string | null; disambiguation: string | null
  candidates: { name: string; entity_id: string; popularity: number | null; year: string | null; disambiguation: string | null }[]
  popularity: number | null; affinity: number | null; age_skew: Record<string, number> | null
  gender_skew: Record<string, number> | null; trend: { direction: string; delta: number | null } | null
  score: number | null; verdict: 'lands' | 'risky' | 'misses' | 'unknown'; why: string; swaps: Swap[]
}
type Result = { summary: { found: number; checked: number; not_in_qloo: number; lands: number; risky: number; misses: number }; references: Ref[]; took_s: number }
type Example = { id: string; title: string; text: string; audience: { age: string | null; gender: string | null; location: string | null } }

const AGES: [string, string][] = [
  ['24_and_younger', 'under 25'], ['25_to_29', '25 to 29'], ['30_to_34', '30 to 34'],
  ['35_to_44', '35 to 44'], ['45_to_54', '45 to 54'], ['55_and_older', '55+'],
]
const AGE_SHORT = ['<25', '25', '30', '35', '45', '55+']
const TYPE_LABEL: Record<string, string> = { tv_show: 'TV', movie: 'film', artist: 'music', brand: 'brand', person: 'person', book: 'book', videogame: 'game', podcast: 'podcast', place: 'place' }
const VERDICT_TEXT = { lands: 'lands', risky: 'risky', misses: 'misses', unknown: 'not in Qloo' }

export default function App() {
  const [text, setText] = useState('')
  const [age, setAge] = useState<string | null>('24_and_younger')
  const [gender, setGender] = useState<string | null>(null)
  const [location, setLocation] = useState('')
  const [examples, setExamples] = useState<Example[]>([])
  const [result, setResult] = useState<Result | null>(null)
  const [checkedText, setCheckedText] = useState('')
  const [busy, setBusy] = useState(false)
  const [swapping, setSwapping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<number | null>(null)
  const [compare, setCompare] = useState(false)
  const cards = useRef<Record<number, HTMLDivElement | null>>({})

  useEffect(() => { fetch('/api/examples').then(r => r.json()).then(setExamples).catch(() => {}) }, [])

  const dirty = result !== null && text !== checkedText

  async function run(overrides?: Partial<{ age: string | null; gender: string | null; location: string }>) {
    const a = overrides?.age !== undefined ? overrides.age : age
    const g = overrides?.gender !== undefined ? overrides.gender : gender
    const l = overrides?.location !== undefined ? overrides.location : location
    if (!text.trim()) return
    setBusy(true); setError(null); setActive(null)
    const body = { text, age: a, gender: g, location: l || null }
    try {
      const r = await fetch('/api/check', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...body, swaps: false }) })
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
      const first: Result = await r.json()
      setResult(first); setCheckedText(text); setBusy(false)
      if (first.references.some(x => x.verdict === 'risky' || x.verdict === 'misses')) {
        setSwapping(true)
        const r2 = await fetch('/api/swaps', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...body, references: first.references }) })
        if (r2.ok) { const { references } = await r2.json(); setResult(res => res ? { ...res, references } : res) }
        setSwapping(false)
      }
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); setSwapping(false) }
  }

  function loadExample(ex: Example) {
    setText(ex.text); setAge(ex.audience.age); setGender(ex.audience.gender); setLocation(ex.audience.location || ''); setResult(null)
  }

  function applySwap(ref: Ref, swap: Swap) {
    if (!result) return
    const line = lineBounds(checkedText, ref)
    const newLine = swap.line ?? (checkedText.slice(line[0], line[1]).replace(ref.surface, swap.name))
    const next = checkedText.slice(0, line[0]) + newLine + checkedText.slice(line[1])
    setText(next)
  }

  const weakFirst = useMemo(() => result ? [...result.references].map((r, i) => ({ r, i })).sort((a, b) => rank(a.r) - rank(b.r)) : [], [result])

  return (
    <div className="min-h-screen">
      <header className="mx-auto max-w-7xl px-4 pt-8 pb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl md:text-5xl font-bold tracking-tight">Will It Land</h1>
          <p className="mt-2 text-muted max-w-xl">AI writes for the average audience. This checks every cultural reference in your script against the one you are actually writing for, grounded in Qloo taste data.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {examples.map(ex => <button key={ex.id} onClick={() => loadExample(ex)} className="rounded-full border border-line bg-white/70 px-3 py-1.5 text-sm hover:bg-white">{ex.title}</button>)}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-16 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="space-y-4">
          <AudienceBar age={age} gender={gender} location={location}
            onAge={v => { setAge(v); if (result) run({ age: v }) }}
            onGender={v => { setGender(v); if (result) run({ gender: v }) }}
            onLocation={setLocation} onLocationCommit={() => { if (result) run() }} />

          <div className="rounded-2xl border border-line bg-white shadow-sm">
            {result && !dirty ? (
              <Highlighted text={checkedText} refs={result.references} active={active} onPick={i => { setActive(i); cards.current[i]?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }} />
            ) : (
              <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Paste a script, a stand-up bit, an ad, a speech..." className="w-full min-h-[320px] resize-y bg-transparent p-5 text-[17px] leading-7 outline-none placeholder:text-muted/60" />
            )}
            <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3">
              <div className="text-sm text-muted">
                {result && !dirty ? <button onClick={() => setResult(null)} className="underline underline-offset-2 hover:text-ink">Edit text</button> : `${text.length.toLocaleString()} characters`}
              </div>
              <button onClick={() => run()} disabled={busy || !text.trim()} className="rounded-xl bg-ink px-5 py-2.5 font-medium text-paper disabled:opacity-40">
                {busy ? 'Checking...' : dirty ? 'Re-check' : 'Check references'}
              </button>
            </div>
          </div>
          {error && <div className="rounded-xl border border-misses/40 bg-misses/5 p-3 text-sm text-misses">{error}</div>}
          {busy && <Progress />}
        </section>

        <section className="space-y-4">
          {result ? (
            <>
              <Summary r={result} compare={compare} onCompare={setCompare} audience={label(age, gender, location)} />
              {weakFirst.map(({ r, i }) => (
                <div key={i} ref={el => { cards.current[i] = el }}>
                  <Card r={r} active={active === i} compare={compare} age={age} swapping={swapping} onHover={() => setActive(i)} onApply={s => applySwap(r, s)} />
                </div>
              ))}
            </>
          ) : (
            <Empty />
          )}
        </section>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-10 text-xs text-muted">
        Scores say how likely a reference is to land with an audience, not what any one person knows. Audience data is aggregate taste data from Qloo; no personal data is sent anywhere.
        Built for the Qloo Agentic Hackathon. Also available as an MCP tool for writing agents.
      </footer>
    </div>
  )
}

function rank(r: Ref) { return r.verdict === 'misses' ? 0 : r.verdict === 'risky' ? 1 : r.verdict === 'unknown' ? 2 : 3 }
function label(age: string | null, gender: string | null, loc: string) {
  return [age ? AGES.find(a => a[0] === age)?.[1] : null, gender, loc || null].filter(Boolean).join(', ') || 'general audience'
}
function lineBounds(text: string, ref: Ref): [number, number] {
  const a = text.lastIndexOf('\n', ref.start - 1) + 1
  const b = text.indexOf('\n', ref.end)
  return [a, b < 0 ? text.length : b]
}

function AudienceBar(p: { age: string | null; gender: string | null; location: string; onAge: (v: string | null) => void; onGender: (v: string | null) => void; onLocation: (v: string) => void; onLocationCommit: () => void }) {
  return (
    <div className="rounded-2xl border border-line bg-white/70 p-3 flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wide text-muted px-1">Audience</span>
      <div className="flex rounded-xl border border-line overflow-hidden">
        {AGES.map(([v, l]) => (
          <button key={v} onClick={() => p.onAge(p.age === v ? null : v)} className={`px-3 py-1.5 text-sm ${p.age === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
        ))}
      </div>
      <div className="flex rounded-xl border border-line overflow-hidden">
        {[['male', 'men'], ['female', 'women']].map(([v, l]) => (
          <button key={v} onClick={() => p.onGender(p.gender === v ? null : v)} className={`px-3 py-1.5 text-sm ${p.gender === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
        ))}
      </div>
      <input value={p.location} onChange={e => p.onLocation(e.target.value)} onBlur={p.onLocationCommit} onKeyDown={e => e.key === 'Enter' && p.onLocationCommit()} placeholder="city or country" className="min-w-[160px] flex-1 rounded-xl border border-line bg-white px-3 py-1.5 text-sm outline-none focus:border-ink" />
    </div>
  )
}

function Highlighted(p: { text: string; refs: Ref[]; active: number | null; onPick: (i: number) => void }) {
  const parts: React.ReactNode[] = []
  const sorted = p.refs.map((r, i) => ({ r, i })).sort((a, b) => a.r.start - b.r.start)
  let pos = 0
  for (const { r, i } of sorted) {
    if (r.start < pos) continue
    parts.push(p.text.slice(pos, r.start))
    parts.push(<mark key={i} onClick={() => p.onPick(i)} title={`${r.name ?? r.surface}: ${r.score ?? '?'} / 100`} className={`ref ref-${r.verdict} ${p.active === i ? 'active' : ''}`}>{p.text.slice(r.start, r.end)}</mark>)
    pos = r.end
  }
  parts.push(p.text.slice(pos))
  return <div className="whitespace-pre-wrap p-5 text-[17px] leading-7 min-h-[320px]">{parts}</div>
}

function Summary(p: { r: Result; compare: boolean; onCompare: (v: boolean) => void; audience: string }) {
  const s = p.r.summary
  return (
    <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-2xl font-semibold">For {p.audience}</h2>
        <span className="text-xs text-muted">{p.r.took_s}s</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        <Pill color="lands" n={s.lands} label="land" /><Pill color="risky" n={s.risky} label="risky" /><Pill color="misses" n={s.misses} label="miss" />
        {s.not_in_qloo > 0 && <Pill color="unknown" n={s.not_in_qloo} label="not in Qloo" />}
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-muted cursor-pointer">
        <input type="checkbox" checked={p.compare} onChange={e => p.onCompare(e.target.checked)} /> Show what the AI alone guessed, next to the Qloo-grounded score
      </label>
    </div>
  )
}

function Pill(p: { color: string; n: number; label: string }) {
  return <span className={`rounded-full px-2.5 py-1 text-${p.color} bg-${p.color}/10 font-medium`}>{p.n} {p.label}</span>
}

function Card(p: { r: Ref; active: boolean; compare: boolean; age: string | null; swapping: boolean; onHover: () => void; onApply: (s: Swap) => void }) {
  const r = p.r
  const weak = r.verdict === 'risky' || r.verdict === 'misses'
  return (
    <div onMouseEnter={p.onHover} className={`rounded-2xl border bg-white p-4 shadow-sm transition ${p.active ? 'border-ink' : 'border-line'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-lg truncate">{r.name ?? r.surface}</span>
            <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">{TYPE_LABEL[r.type] ?? r.type}</span>
            {r.trend && r.trend.direction !== 'flat' && <span className="text-xs text-muted">{r.trend.direction}</span>}
          </div>
          {r.name && r.name !== r.surface && <div className="text-xs text-muted">written as "{r.surface}"</div>}
          {r.disambiguation && <div className="text-xs text-muted truncate">{r.disambiguation}</div>}
        </div>
        <Score score={r.score} verdict={r.verdict} />
      </div>
      {r.why && <p className="mt-2 text-sm text-muted">{r.why}</p>}
      {r.verdict === 'unknown' && <p className="mt-2 text-sm text-muted">{r.why || 'Qloo has no entity for this, so it is not scored.'}</p>}
      {r.age_skew && <AgeBars skew={r.age_skew} age={p.age} />}
      {p.compare && r.score !== null && (
        <div className="mt-3 text-sm">
          <div className="flex items-center gap-2"><span className="w-24 text-muted">AI alone</span><Bar v={r.llm_guess} muted /><span className="w-8 text-right tabular-nums">{Math.round(r.llm_guess)}</span></div>
          <div className="flex items-center gap-2 mt-1"><span className="w-24 text-muted">with Qloo</span><Bar v={r.score} /><span className="w-8 text-right tabular-nums">{Math.round(r.score)}</span></div>
          {Math.abs(r.llm_guess - r.score) >= 25 && <div className="mt-1 text-xs text-muted">The model guessed {r.llm_guess > r.score ? 'higher' : 'lower'} than the data says.</div>}
        </div>
      )}
      {weak && p.swapping && r.swaps.length === 0 && <div className="mt-3 border-t border-line pt-3 text-sm text-muted pulse">Finding stand-ins that play the same role...</div>}
      {r.swaps.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Stand-ins that play the same role</div>
          <div className="space-y-2">
            {r.swaps.map(s => (
              <div key={s.entity_id} className="rounded-xl bg-paper p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{s.name} <span className="text-muted text-sm">{Math.round(s.score)}</span></span>
                  <button onClick={() => p.onApply(s)} className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs hover:border-ink">Use this</button>
                </div>
                {s.line && <p className="mt-1 text-sm">{s.line}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Score(p: { score: number | null; verdict: Ref['verdict'] }) {
  return (
    <div className="text-right shrink-0">
      <div className={`font-display text-3xl font-bold leading-none text-${p.verdict}`}>{p.score === null ? '--' : Math.round(p.score)}</div>
      <div className={`text-xs font-medium text-${p.verdict}`}>{VERDICT_TEXT[p.verdict]}</div>
    </div>
  )
}

function Bar(p: { v: number; muted?: boolean }) {
  return <div className="h-2 flex-1 rounded-full bg-line overflow-hidden"><div className={`h-full ${p.muted ? 'bg-muted/60' : 'bg-ink'}`} style={{ width: `${Math.max(2, Math.min(100, p.v))}%` }} /></div>
}

function AgeBars(p: { skew: Record<string, number>; age: string | null }) {
  const vals = AGES.map(([k]) => p.skew[k] ?? 0)
  const max = Math.max(0.3, ...vals.map(Math.abs))
  return (
    <div className="mt-3">
      <div className="flex items-end gap-1 h-10">
        {vals.map((v, i) => {
          const h = Math.round(50 * Math.abs(v) / max)
          const sel = AGES[i][0] === p.age
          return (
            <div key={i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${AGES[i][1]}: ${v >= 0 ? '+' : ''}${v.toFixed(2)}`}>
              <div className={`w-full rounded-sm ${v >= 0 ? (sel ? 'bg-lands' : 'bg-lands/35') : (sel ? 'bg-misses' : 'bg-misses/35')}`} style={{ height: `${Math.max(6, h)}%` }} />
            </div>
          )
        })}
      </div>
      <div className="flex gap-1 text-[10px] text-muted mt-1">{AGE_SHORT.map((l, i) => <div key={i} className={`flex-1 text-center ${AGES[i][0] === p.age ? 'text-ink font-semibold' : ''}`}>{l}</div>)}</div>
      <div className="text-[10px] text-muted mt-0.5">Age skew: how much more (green) or less (red) than average each age group cares about this.</div>
    </div>
  )
}

function Progress() {
  const steps = ['Finding references', 'Resolving against Qloo', 'Scoring for this audience', 'Finding stand-ins', 'Rewriting lines']
  const [i, setI] = useState(0)
  useEffect(() => { const t = setInterval(() => setI(x => Math.min(x + 1, steps.length - 1)), 4000); return () => clearInterval(t) }, [])
  return <div className="rounded-2xl border border-line bg-white/70 p-4 text-sm text-muted"><span className="pulse">{steps[i]}...</span></div>
}

function Empty() {
  return (
    <div className="rounded-2xl border border-dashed border-line p-6 text-sm text-muted space-y-2">
      <p className="font-medium text-ink">How it works</p>
      <p>1. Paste your text and pick the audience you are writing for.</p>
      <p>2. The agent finds every cultural reference and resolves it against Qloo's graph of 250M+ entities.</p>
      <p>3. Each reference gets a 0 to 100 "likely to land" score from how widely known it is and how much that audience over- or under-indexes on it.</p>
      <p>4. For weak references it proposes stand-ins that play the same role in the line, and rewrites the line for you to accept or ignore.</p>
      <p>Switch the audience and watch the highlights change.</p>
    </div>
  )
}
