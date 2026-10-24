import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, latest } from './api'
import type { Example, Health, Ledger, LocaliseAllResult, MatrixResult, Options, Room } from './types'
import { CITIES, Evidence, Grid, TrackedChanges, TwoUp, whereLabel, type Scoring } from './rooms'
import { Spinner } from './ui'

const JOBS: Record<string, string> = { comedy: 'Comedian: same bit, two rooms', ad: 'Ad team: one spot, six markets', tour: 'Touring comic: one opener, six cities', speech: 'Best man: one shot' }

const PURPOSE: Record<string, string> = {
  '/search': 'find each reference and how widely known it is',
  'insights: demographics': 'who leans towards it, by age and gender',
  'insights: rank in place': 'how it ranks in each place',
  'insights: recommendations': 'stand-in candidates from the taste graph',
  'insights: tags': 'what a weak reference is like, to find stand-ins',
  'insights: heatmap': 'where it is popular',
  '/v2/trending': 'six-month trend (shown, not scored)',
}

const roomKey = (text: string, rooms: Room[]) => JSON.stringify([text, rooms.map(r => [r.age, r.gender, (r.location ?? '').trim(), r.name])])

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [options, setOptions] = useState<Options | null>(null)
  const [examples, setExamples] = useState<Example[]>([])
  const [text, setText] = useState('')
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState(false)
  const [rooms, setRooms] = useState<Room[]>([])
  const [result, setResult] = useState<MatrixResult | null>(null)
  // the text and settings `result` was scored for: marks are drawn on this text, and a result for older settings is shown dimmed
  const [scored, setScored] = useState<{ text: string; key: string }>({ text: '', key: '' })
  const [mode, setMode] = useState<Scoring>('qloo')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fix, setFix] = useState<LocaliseAllResult | null>(null)
  const [fixing, setFixing] = useState(false)
  const [active, setActive] = useState<{ ref: number; room: number } | null>(null)
  const [hood, setHood] = useState(false)
  const [mcp, setMcp] = useState(false)
  const [proof, setProof] = useState(false)
  const runMatrix = useRef(latest()).current
  const runGuesses = useRef(latest()).current
  const runFix = useRef(latest()).current

  // location carries weight unless calibration set it to zero; if it does not, no place control is shown
  const showPlace = (options?.location_weight ?? 1) > 0

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.options().then(setOptions).catch(() => {})
    api.examples().then(ex => {
      setExamples(ex)
      const first = ex[0]
      if (first) load(first)
    }).catch(e => setError(String(e.message ?? e)))
  }, [])

  function load(ex: Example) {
    setFix(null); setActive(null); setEditing(false); setMode('qloo'); setError(null)
    setText(ex.text); setDraft(ex.text)
    setRooms(ex.matrix ?? [ex.audience])
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setActive(null); setHood(false); setMcp(false); setProof(false) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // hide the AI-only view on demo data: comparing a real model's guesses with made-up Qloo numbers means nothing
  useEffect(() => { if (health?.mock) setMode('qloo') }, [health])

  // score whenever the text or the rooms change (debounced so typing a city does not fire on every key)
  const key = useMemo(() => roomKey(text, rooms), [text, rooms])
  useEffect(() => {
    runFix.cancel()
    if (!text.trim() || !rooms.length) return
    setBusy(true); setError(null)
    const t = setTimeout(async () => {
      try {
        const m = await runMatrix(signal => api.matrix(text, rooms, signal))
        if (!m) return
        setResult(m); setScored({ text, key }); setBusy(false)
        const g = await runGuesses(signal => api.guesses(text, rooms, signal)).catch(() => undefined)
        if (g) setResult(cur => (cur && cur.references.length === m.references.length && cur === m) ? { ...cur, cells: cur.cells.map((row, i) => row.map((c, j) => (c ? { ...c, llm_guess: g.guesses[i]?.[j] ?? null } : c))) } : cur)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e)); setBusy(false)
      }
    }, 350)
    return () => clearTimeout(t)
  }, [key])

  const setRoom = useCallback((i: number, r: Room) => { setFix(null); setRooms(rs => rs.map((x, j) => (j === i ? r : x))) }, [])
  const removeRoom = useCallback((i: number) => { setFix(null); setActive(null); setRooms(rs => rs.filter((_, j) => j !== i)) }, [])
  const addRoom = () => { setFix(null); setRooms(rs => (rs.length >= 6 ? rs : [...rs, { age: '35_to_44', gender: null, location: showPlace ? 'New York' : null }])) }

  async function landEverywhere() {
    setFixing(true); setError(null); setActive(null)
    try {
      const r = await runFix(signal => api.landEverywhere(text, rooms, signal))
      if (r) setFix(r)
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)) } finally { setFixing(false) }
  }

  function keepFix() {
    if (!fix) return
    setText(fix.text); setDraft(fix.text); setResult(fix.after); setScored({ text: fix.text, key: roomKey(fix.text, rooms) }); setFix(null)
  }

  function commitDraft() {
    setFix(null); setActive(null); setEditing(false); setText(draft)
  }

  function pasteOwn() {
    runFix.cancel(); setFix(null); setActive(null); setError(null); setEditing(true); setDraft('')
  }

  const ledger: Ledger | undefined = fix?.ledger ?? result?.ledger
  const kinds = ledger ? Object.keys(ledger.by_capability ?? ledger.by_endpoint).length : 0
  const where = whereLabel(rooms.length)
  const anyWeak = !!result?.summaries.some(s => s.misses + s.risky > 0)
  const anyChecked = !!result?.summaries.some(s => s.checked > 0)
  const stale = !!result && scored.key !== key
  const showToggle = health ? !health.mock : false

  return (
    <div className="min-h-screen">
      <datalist id="wil-cities">{CITIES.map(c => <option key={c} value={c} />)}</datalist>
      <header className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-4 px-4 pt-7 pb-3 md:px-6">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-4xl font-bold tracking-tight md:text-5xl">Will It Land</h1>
            {health && (health.mock
              ? <span className="rounded-full bg-risky/15 px-2.5 py-1 text-xs font-medium text-risky">Demo data: Qloo key pending</span>
              : <span className="rounded-full bg-lands/15 px-2.5 py-1 text-xs font-medium text-lands">Live Qloo data</span>)}
          </div>
          <p className="mt-2 text-[15px] text-muted">Spellcheck for cultural references. Pick the rooms you are playing: each reference in your script is scored for that audience from Qloo's taste data, and the weak ones get a stand-in that is scored the same way.</p>
        </div>
        <div className="flex flex-wrap items-stretch gap-2">
        <button onClick={() => setProof(true)} className="rounded-xl bg-white px-3 py-2 text-left text-xs ring-1 ring-line hover:ring-ink/40">
          <div className="font-semibold text-ink">How we know</div>
          <div className="text-muted">The tests behind the score</div>
        </button>
        {ledger && (
          <button onClick={() => setHood(true)} className="rounded-xl bg-white px-3 py-2 text-left text-xs ring-1 ring-line hover:ring-ink/40">
            <div className="font-semibold text-ink">{ledger.total} Qloo calls, {kinds} kind{kinds === 1 ? '' : 's'} of request</div>
            <div className="text-muted">Under the hood: every request behind this result</div>
          </button>
        )}
        </div>
      </header>

      <nav className="mx-auto flex max-w-7xl flex-wrap gap-2 px-4 pb-4 md:px-6" aria-label="Examples">
        {examples.map(ex => (
          <button key={ex.id} onClick={() => load(ex)} className={`rounded-full px-3.5 py-1.5 text-sm ring-1 transition ${text === ex.text ? 'bg-ink text-paper ring-ink' : 'bg-white ring-line hover:ring-ink/40'}`}>
            {JOBS[ex.kind] ?? ex.title}
          </button>
        ))}
        <button onClick={() => setMcp(true)} className="rounded-full bg-white px-3.5 py-1.5 text-sm ring-1 ring-line hover:ring-ink/40">Writing agent: via MCP</button>
        <button onClick={pasteOwn} className="rounded-full px-3.5 py-1.5 text-sm text-muted underline-offset-2 hover:text-ink hover:underline">Paste your own</button>
      </nav>

      <main className="mx-auto max-w-7xl space-y-4 px-4 pb-16 md:px-6">
        {editing && (
          <section className="rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line">
            <textarea autoFocus value={draft} onChange={e => setDraft(e.target.value)} maxLength={8000} placeholder="Paste a stand-up bit, an ad script, a speech, a toast..." aria-label="Script"
              className="min-h-[200px] w-full resize-y bg-transparent text-[16.5px] leading-7 outline-none placeholder:text-muted/60" />
            <div className="flex items-center justify-between border-t border-line pt-3">
              <span className="text-xs text-muted">{draft.length.toLocaleString()} / 8,000 characters. A language model reads the text to find the references; only their names and the room settings go to Qloo.</span>
              <div className="flex gap-2">
                {text && <button onClick={() => { setEditing(false); setDraft(text) }} className="rounded-xl px-4 py-2 text-sm ring-1 ring-line">Cancel</button>}
                <button onClick={commitDraft} disabled={!draft.trim()} className="rounded-xl bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40">Check it</button>
              </div>
            </div>
          </section>
        )}

        {!editing && (
          <div className="flex flex-wrap items-center gap-2">
            {mode === 'qloo' && (
              <button onClick={landEverywhere} disabled={!result || fixing || busy || stale || !anyWeak || !!fix} className="rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-paper shadow-sm disabled:opacity-40">
                {fixing ? 'Finding stand-ins in Qloo...' : `Make it land in ${where}`}
              </button>
            )}
            {mode === 'qloo' && result && anyChecked && !anyWeak && !busy && <span className="text-sm text-lands">Every reference lands in {where}.</span>}
            <button onClick={() => { setEditing(true); setDraft(text) }} className="rounded-xl bg-white px-3.5 py-2.5 text-sm ring-1 ring-line hover:ring-ink/40">Edit script</button>
            {rooms.length < 6 && <button onClick={addRoom} className="rounded-xl bg-white px-3.5 py-2.5 text-sm ring-1 ring-line hover:ring-ink/40">Add a room</button>}
            <div className="ml-auto flex items-center gap-2 text-xs">
              {showToggle && <>
              <span className="text-muted">Scored by</span>
              <div className="flex overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label="Scored by">
                {([['qloo', 'Qloo data'], ['ai', 'AI guess alone']] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setMode(v)} aria-pressed={mode === v} className={`px-3 py-1.5 ${mode === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
                ))}
              </div>
              </>}
            </div>
          </div>
        )}
        {!editing && result && rooms.length <= 2 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Legend">
            <span><span className="mark mark-lands">solid</span> lands</span>
            <span><span className="mark mark-risky">dotted</span> risky</span>
            <span><span className="mark mark-misses">wavy</span> likely misses</span>
            <span><span className="mark mark-unknown">dashed</span> not in Qloo</span>
            <span>Small numbers are the score out of 100. Tap or click a reference for the evidence.</span>
          </div>
        )}
        {fixing && <Spinner label="Finding stand-ins in Qloo and re-scoring every room..." />}
        {busy && <Spinner label={result ? 'Re-scoring with Qloo...' : 'Finding references and asking Qloo...'} />}
        {error && <div className="rounded-xl bg-misses/5 p-3 text-sm text-misses ring-1 ring-misses/30">{error}</div>}
        {mode === 'ai' && result && <div className="rounded-xl bg-white p-3 text-sm text-muted ring-1 ring-line">Showing what a language model guesses with no data, on the same 0 to 100 scale. ◆ marks a reference where the guess is 25 or more points away from the Qloo-grounded score. Switch back to Qloo data to rewrite.</div>}

        {fix && <TrackedChanges r={fix} rooms={rooms} showPlace={showPlace} onKeep={keepFix} onUndo={() => setFix(null)} />}

        {result && !editing && (rooms.length <= 2
          ? <TwoUp text={scored.text} m={result} rooms={rooms} mode={mode} showPlace={showPlace} dim={stale} active={active} onPick={(ref, room) => setActive({ ref, room })} onRoom={setRoom} onRemove={removeRoom} />
          : <Grid text={scored.text} m={result} rooms={rooms} mode={mode} showPlace={showPlace} dim={stale} onPick={(ref, room) => setActive({ ref, room })} onRoom={setRoom} onRemove={removeRoom} />)}

        {result && active && result.references[active.ref] && rooms[active.room] && (
          <Evidence m={result} ref_={active.ref} room={active.room} rooms={rooms} showPlace={showPlace} locMeasured={!!options?.location_measured} onRoom={j => setActive({ ref: active.ref, room: j })} onClose={() => setActive(null)} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl space-y-2 px-4 pb-10 text-xs text-muted md:px-6">
        <p>"Likely to land" is an estimate for an audience, not a statement about any one person, and not a judgement on whether a joke is funny. Audience data is aggregate taste data from Qloo; only reference names and room settings are sent to it.
          {result && ` Score model: ${result.model.calibrated ? result.model.source : 'hand-set priors, not yet calibrated against survey data'}.`}</p>
        <p>Built for the Qloo Agentic Hackathon. <button onClick={() => setMcp(true)} className="underline underline-offset-2 hover:text-ink">Use it from your own agent (MCP)</button>. <a className="underline underline-offset-2 hover:text-ink" href="https://github.com/msimakhov-star/will-it-land">Source code (MIT)</a>.</p>
      </footer>

      {hood && ledger && <Hood ledger={ledger} onClose={() => setHood(false)} />}
      {mcp && <Mcp onClose={() => setMcp(false)} />}
      {proof && <Proof onClose={() => setProof(false)} />}
    </div>
  )
}

function Hood(p: { ledger: Ledger; onClose: () => void }) {
  const l = p.ledger
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/20" onClick={p.onClose}>
      <aside className="rise h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-2xl" onClick={e => e.stopPropagation()} aria-label="Under the hood">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-display text-2xl font-semibold">Under the hood</h3>
            <p className="mt-1 text-sm text-muted">{l.total} Qloo calls behind this result: {l.live} live, {l.cache} from cache{l.mock ? `, ${l.mock} from demo data` : ''}{l.errors ? `, ${l.errors} failed` : ''}. Only reference names and room settings go to Qloo, never your text.</p>
          </div>
          <button onClick={p.onClose} className="rounded-full p-1.5 text-muted hover:bg-paper hover:text-ink" aria-label="Close">✕</button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(l.by_capability ?? l.by_endpoint).map(([e, n]) => (
            <span key={e} className="rounded-xl bg-paper px-2.5 py-1 text-xs"><span className="font-mono">{e}</span> x{n}{PURPOSE[e] && <span className="block text-muted">{PURPOSE[e]}</span>}</span>
          ))}
        </div>
        <ol className="mt-4 space-y-1.5">
          {l.calls.map((c, i) => (
            <li key={i} className="rounded-lg bg-paper/60 p-2 font-mono text-[11px] leading-snug">
              <span className={c.source === 'error' ? 'text-misses' : c.source === 'live' ? 'text-lands' : 'text-muted'}>{c.source}</span> GET {c.endpoint}?{Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join('&').slice(0, 220)} <span className="text-muted">{c.ms} ms</span>
            </li>
          ))}
        </ol>
        {l.total > l.calls.length && <p className="mt-2 text-xs text-muted">{l.total - l.calls.length} more calls not listed.</p>}
      </aside>
    </div>
  )
}

function Mcp(p: { onClose: () => void }) {
  const url = `${location.origin}/mcp`
  const cfg = JSON.stringify({ mcpServers: { 'will-it-land': { type: 'http', url } } }, null, 2)
  const cli = `claude mcp add --transport http will-it-land ${url}`
  const copy = (s: string) => navigator.clipboard?.writeText(s).catch(() => {})
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/20 p-4" onClick={p.onClose}>
      <div className="rise w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl" onClick={e => e.stopPropagation()} role="dialog" aria-label="Use from your agent">
        <div className="flex items-start justify-between">
          <h3 className="font-display text-2xl font-semibold">Give your writing agent an audience</h3>
          <button onClick={p.onClose} className="rounded-full p-1.5 text-muted hover:bg-paper hover:text-ink" aria-label="Close">✕</button>
        </div>
        <p className="mt-2 text-sm text-muted">Will It Land is also an MCP server. Add it to Claude, ChatGPT or any MCP client and the agent can check its own references before it finishes a joke, an ad or a speech.</p>
        <div className="mt-3 text-xs font-medium text-muted">Hosted endpoint (streamable HTTP)</div>
        <code className="mt-1 block rounded-lg bg-paper p-2 font-mono text-xs break-all">{url}</code>
        <div className="mt-3 flex items-center justify-between text-xs font-medium text-muted">Claude Code<button onClick={() => copy(cli)} className="rounded-full px-2 py-0.5 ring-1 ring-line hover:text-ink">Copy</button></div>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-paper p-2 font-mono text-xs">{cli}</pre>
        <div className="mt-3 flex items-center justify-between text-xs font-medium text-muted">JSON config (.mcp.json and similar)<button onClick={() => copy(cfg)} className="rounded-full px-2 py-0.5 ring-1 ring-line hover:text-ink">Copy</button></div>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-paper p-2 font-mono text-xs">{cfg}</pre>
        <div className="mt-3 text-xs text-muted">Tools: check_references, check_matrix, localise, localise_for_all, audience_options.</div>
      </div>
    </div>
  )
}

type ProofData = {
  model: { calibrated: boolean; source: string; k_loc: number }
  fit?: { n_entities: number; pooled: Record<string, number>; gap: { qloo: number; llm: number; n: number } }
  location?: { scored: number; hits: number; hit_rate: number; decision: string }
  survey?: { respondents: number; items: number; spearman_qloo: number | null; spearman_llm: number | null; ai_picks_most_did_not_know: string[] }
  taste_audit?: { total: { checked: number; weak: number; weak_share: number } }
}

function Proof(p: { onClose: () => void }) {
  const [d, setD] = useState<ProofData | null>(null)
  useEffect(() => { fetch('/api/proof').then(r => r.json()).then(setD).catch(() => {}) }, [])
  const row = (label: string, q: number | undefined | null, a: number | undefined | null) => (
    <tr className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{label}</td><td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{q == null ? '-' : q.toFixed(2)}</td><td className="py-1.5 text-right tabular-nums">{a == null ? '-' : a.toFixed(2)}</td></tr>
  )
  const pending = <span className="text-muted">not measured yet</span>
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/20 p-4" onClick={p.onClose}>
      <div className="rise max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl" onClick={e => e.stopPropagation()} role="dialog" aria-label="How we know">
        <div className="flex items-start justify-between">
          <h3 className="font-display text-2xl font-semibold">How we know it works</h3>
          <button onClick={p.onClose} className="rounded-full p-1.5 text-muted hover:bg-paper hover:text-ink" aria-label="Close">✕</button>
        </div>
        <p className="mt-2 text-sm text-muted">We did not want to assert that Qloo makes the difference, so we test it against outside ground truth, with the method fixed before any data came in (eval/PREREG.md in the repository). Every number below is published whatever it says.</p>
        <section className="mt-4">
          <h4 className="font-semibold">1. Who has heard of it, by generation (YouGov, US)</h4>
          <p className="text-xs text-muted">Rank correlation with the share of each generation who have heard of {d?.fit ? d.fit.n_entities : 'a sample of'} shows, films, artists, brands, people and podcasts. 1.0 is a perfect ordering.</p>
          {d?.fit ? (
            <table className="mt-2 w-full text-sm"><thead><tr className="text-xs text-muted"><th className="text-left font-normal" /><th className="text-right font-normal">With Qloo</th><th className="text-right font-normal">AI alone</th></tr></thead>
              <tbody>{row('fame, all generations', d.fit.pooled.qloo, d.fit.pooled.llm)}{row('generation gap (what a room switch changes)', d.fit.gap.qloo, d.fit.gap.llm)}{row('AI and Qloo combined', d.fit.pooled.blend, null)}</tbody></table>
          ) : <div className="mt-2 text-sm">{pending}</div>}
        </section>
        <section className="mt-4">
          <h4 className="font-semibold">2. What under-25s actually recognise (our own survey)</h4>
          {d?.survey ? <p className="mt-1 text-sm">{d.survey.respondents} respondents, {d.survey.items} items. Correlation with recognition: with Qloo {d.survey.spearman_qloo?.toFixed(2) ?? '-'}, AI alone {d.survey.spearman_llm?.toFixed(2) ?? '-'}.{d.survey.ai_picks_most_did_not_know.length ? ` References the AI chose "for under-25s" that most of them did not know: ${d.survey.ai_picks_most_did_not_know.slice(0, 6).join(', ')}.` : ''}</p>
            : <p className="mt-1 text-sm">{pending}. <a className="underline underline-offset-2" href="/survey">Take the 2-minute survey</a> if you are 18 to 24.</p>}
        </section>
        <section className="mt-4">
          <h4 className="font-semibold">3. Does the place signal mean anything?</h4>
          {d?.location ? <p className="mt-1 text-sm">{d.location.hits} of {d.location.scored} regional brands and shows score stronger at home than far away. {d.model.k_loc > 0 ? 'Place is part of the score.' : 'Place is left out of the score.'}</p> : <p className="mt-1 text-sm">{pending}</p>}
        </section>
        {d?.taste_audit && (
          <section className="mt-4">
            <h4 className="font-semibold">4. AI writing for a named audience</h4>
            <p className="mt-1 text-sm">Claude and Gemini each wrote 18 short pieces "for" a named room. {Math.round(100 * d.taste_audit.total.weak_share)}% of their {d.taste_audit.total.checked} references score risky or likely to miss for the very room they were written for.</p>
          </section>
        )}
        <p className="mt-5 border-t border-line pt-3 text-xs text-muted">Score model: {d ? (d.model.calibrated ? d.model.source : 'hand-set starting values, to be fitted on the data above') : '...'}. "Likely to land" means likely to be recognised and liked by that audience; it never claims a joke is funny.</p>
      </div>
    </div>
  )
}
