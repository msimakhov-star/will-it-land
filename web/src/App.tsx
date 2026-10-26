import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, latest } from './api'
import type { Example, Health, Ledger, LocaliseAllResult, MatrixResult, Options, Room } from './types'
import { CITIES, Evidence, Grid, Legend, TrackedChanges, TwoUp, biggestSplit, whereLabel, type Scoring } from './rooms'
import { Modal, Spinner, headline } from './ui'

const JOBS: Record<string, string> = { comedy: 'Comedian: same bit, two rooms', tour: 'Touring comic: six cities', ad: 'Ad team: six markets', speech: 'Best man: two tables' }

const PURPOSE: Record<string, string> = {
  '/search': 'find each reference and how well known it is',
  'insights: demographics': 'which ages and genders are keener on it',
  'insights: rank in place': 'how it ranks in each place',
  'insights: recommendations': 'stand-in candidates from the taste graph',
  'insights: tags': 'what a weak reference is like, to find stand-ins',
  'insights: heatmap': 'where it is popular',
  '/v2/trending': 'six-month trend (shown, not scored)',
}

const roomKey = (text: string, rooms: Room[]) => JSON.stringify([text, rooms.map(r => [r.age, r.gender, (r.location ?? '').trim(), r.name])])
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const link = 'text-muted underline decoration-line underline-offset-4 hover:text-ink hover:decoration-ink'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [options, setOptions] = useState<Options | null>(null)
  const [examples, setExamples] = useState<Example[]>([])
  const [exampleId, setExampleId] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState(false)
  const [rooms, setRooms] = useState<Room[]>([])
  const [result, setResult] = useState<MatrixResult | null>(null)
  // the text and settings `result` was scored for: marks are drawn on this text, and a result for older settings is shown dimmed
  const [scored, setScored] = useState<{ text: string; key: string }>({ text: '', key: '' })
  const scoredKey = useRef('')
  const [nonce, setNonce] = useState(0)
  const [mode, setMode] = useState<Scoring>('qloo')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [fix, setFix] = useState<LocaliseAllResult | null>(null)
  const [fixing, setFixing] = useState(false)
  const [original, setOriginal] = useState<string | null>(null)
  const [active, setActive] = useState<{ ref: number; room: number } | null>(null)
  const [flash, setFlash] = useState<{ ref: number; room: number } | null>(null)
  const [panel, setPanel] = useState<'hood' | 'mcp' | 'proof' | null>(null)
  const [pill, setPill] = useState(false)
  const [shared, setShared] = useState<{ created: string; demo: boolean } | null>(null)
  const [shareState, setShareState] = useState<'idle' | 'saving' | 'copied' | string>('idle')
  const runMatrix = useRef(latest()).current
  const runGuesses = useRef(latest()).current
  const runFix = useRef(latest()).current
  const flashed = useRef('')

  const demo = !!health?.mock
  // location carries weight unless calibration set it to zero; if it does not, no place control is shown
  const showPlace = (options?.location_weight ?? 1) > 0

  const markScored = (t: string, k: string) => { scoredKey.current = k; setScored({ text: t, key: k }) }

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.options().then(setOptions).catch(() => {})
    const rid = location.pathname.match(/^\/r\/([\w-]+)/)?.[1]
    api.examples().then(async ex => {
      setExamples(ex)
      if (rid) {
        try {
          const rep = await api.getReport(rid)
          const { text: t, rooms: rs, result: m } = rep.payload
          setText(t); setDraft(t); setRooms(rs); setResult(m); markScored(t, roomKey(t, rs))
          setShared({ created: (rep.payload as { created?: string }).created ?? '', demo: !!(rep.payload as { demo?: boolean }).demo })
          return
        } catch { setError('That shared link has expired or does not exist, so here is an example instead.') }
      }
      const want = new URLSearchParams(location.search).get('example')
      const first = ex.find(e => e.id === want) ?? ex[0]
      if (first) load(first)
    }).catch(e => setError(errMsg(e)))
  }, [])

  function load(ex: Example) {
    runFix.cancel()
    setFix(null); setActive(null); setEditing(false); setMode('qloo'); setError(null); setNote(null); setOriginal(null); setShared(null); setShareState('idle')
    setExampleId(ex.id); setText(ex.text); setDraft(ex.text)
    setRooms(ex.matrix ?? [ex.audience])
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setActive(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // hide the AI-only view on demo data: comparing a real model's guesses with made-up numbers means nothing
  useEffect(() => { if (demo) setMode('qloo') }, [demo])

  // score whenever the text or the rooms change (debounced so typing a city does not fire on every key)
  const key = useMemo(() => roomKey(text, rooms), [text, rooms])
  useEffect(() => {
    runFix.cancel()
    if (!text.trim() || !rooms.length || key === scoredKey.current) { setBusy(false); return }
    setBusy(true); setError(null)
    const t = setTimeout(async () => {
      try {
        const m = await runMatrix(signal => api.matrix(text, rooms, signal))
        if (!m) return
        setResult(m); markScored(text, key); setBusy(false)
        const g = await runGuesses(signal => api.guesses(text, rooms, signal)).catch(() => undefined)
        if (g) setResult(cur => (cur && cur === m) ? { ...cur, cells: cur.cells.map((row, i) => row.map((c, j) => (c ? { ...c, llm_guess: g.guesses[i]?.[j] ?? null } : c))) } : cur)
      } catch (e: unknown) {
        setError(errMsg(e)); setBusy(false)
      }
    }, 350)
    return () => clearTimeout(t)
  }, [key, nonce])

  const stale = !!result && scored.key !== key
  const split = useMemo(() => (result ? biggestSplit(result) : null), [result])

  // point at the biggest split once per script, so the first thing a visitor sees is the room changing the answer
  useEffect(() => {
    if (!result || stale || !split || split.gap < 30 || flashed.current === scored.text) return
    flashed.current = scored.text
    setFlash({ ref: split.ref, room: split.lo })
    const t = setTimeout(() => setFlash(null), 2600)
    return () => clearTimeout(t)
  }, [result, stale, split, scored.text])

  const setRoom = useCallback((i: number, r: Room) => { setFix(null); setShared(null); setRooms(rs => rs.map((x, j) => (j === i ? r : x))) }, [])
  const removeRoom = useCallback((i: number) => {
    setFix(null); setActive(null); setShared(null); setRooms(rs => rs.filter((_, j) => j !== i))
    requestAnimationFrame(() => document.getElementById('add-room')?.focus())
  }, [])
  const addRoom = () => { setFix(null); setShared(null); setRooms(rs => (rs.length >= 6 ? rs : [...rs, { age: '35_to_44', gender: null, location: showPlace ? 'New York' : null }])) }

  async function landEverywhere() {
    if (fixing) return
    setFixing(true); setError(null); setActive(null)
    try {
      const r = await runFix(signal => api.landEverywhere(text, rooms, signal))
      if (r) setFix(r)
    } catch (e: unknown) { setError(errMsg(e)) } finally { setFixing(false) }
  }

  function keepFix() {
    if (!fix) return
    setOriginal(o => o ?? text)
    setText(fix.text); setDraft(fix.text); setResult(fix.after); markScored(fix.text, roomKey(fix.text, rooms)); setFix(null)
    requestAnimationFrame(() => document.getElementById('edit-script')?.focus())
  }

  function revert() {
    if (original == null) return
    setText(original); setDraft(original); setOriginal(null); setFix(null)
  }

  function commitDraft() {
    setFix(null); setActive(null); setEditing(false); setText(draft); setExampleId(null); setOriginal(null); setShared(null); setNote(null)
    if (rooms.length === 1) {
      const young = rooms[0].age === '24_and_younger' || rooms[0].age === '25_to_29'
      setRooms(rs => [...rs, { age: young ? '55_and_older' : '24_and_younger', gender: null, location: rs[0].location }])
      setNote('Added a second room so you can compare. Change or remove it any time.')
    }
    requestAnimationFrame(() => document.getElementById('edit-script')?.focus())
  }

  function pasteOwn() {
    runFix.cancel(); setFix(null); setActive(null); setError(null); setEditing(true); setDraft(''); setExampleId(null)
  }

  async function share() {
    if (!result) return
    setShareState('saving')
    try {
      const r = await api.report('matrix', { text: scored.text, rooms, result, demo, created: new Date().toISOString().slice(0, 10) })
      const url = `${location.origin}${r.url}`
      await navigator.clipboard?.writeText(url).catch(() => {})
      setShareState('copied')
      history.replaceState(null, '', r.url)
      setTimeout(() => setShareState('idle'), 2500)
    } catch (e) { setShareState(errMsg(e)) }
  }

  function rerunShared() {
    setShared(null); scoredKey.current = ''; setNonce(n => n + 1); history.replaceState(null, '', '/')
  }

  const ledger: Ledger | undefined = fix?.ledger ?? result?.ledger
  const kinds = ledger ? Object.keys(ledger.by_capability ?? ledger.by_endpoint).length : 0
  const where = whereLabel(rooms.length)
  const anyWeak = !!result?.summaries.some(s => s.misses + s.risky > 0)
  const anyChecked = !!result?.summaries.some(s => s.checked > 0)
  const showToggle = health ? !demo : false
  const callsLabel = ledger ? (demo && !ledger.live ? `${ledger.total} demo lookups` : `${ledger.total} Qloo calls, ${kinds} kind${kinds === 1 ? '' : 's'}`) : ''
  const announce = fix ? (fix.kept ? 'Proposed rewrite ready.' : 'No rewrite beat the original.') : result && !busy ? result.audiences.map((a, j) => result.summaries[j] && headline(a.label, result.summaries[j])).filter(Boolean).join('. ') : ''
  const scoreLine = result?.model.calibrated ? 'Score weights are fitted on survey data' : 'The score uses starting weights set by hand, not yet checked against survey data'
  const splitRef = split && result ? result.references[split.ref] : null

  const aboutLinks = (
    <>
      <button onClick={() => setPanel('proof')} className={link}>Can you trust the score?</button>
      {ledger && <button onClick={() => setPanel('hood')} className={link}>Under the hood: {callsLabel}</button>}
      <button onClick={() => setPanel('mcp')} className={link}>Use it from your AI agent (MCP)</button>
    </>
  )

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only rounded bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50">Skip to results</a>
      <datalist id="wil-cities">{CITIES.map(c => <option key={c} value={c} />)}</datalist>
      <div className="sr-only" role="status" aria-live="polite">{announce}</div>

      <header className="mx-auto max-w-7xl px-4 pt-6 pb-3 md:px-6 md:pt-8">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <h1 className="group font-display text-4xl font-bold tracking-tight md:text-5xl">Will It <span className={`brand-land ${original != null ? 'landed' : ''}`}>Land</span></h1>
              {health && (demo
                ? <button onClick={() => setPill(v => !v)} aria-expanded={pill} className="hatch rounded-full bg-white px-2.5 py-1 text-xs font-medium text-ink ring-1 ring-ink/25">Demo data, not live Qloo</button>
                : <span className="rounded-full bg-lands/10 px-2.5 py-1 text-xs font-medium text-lands ring-1 ring-lands/30">Live Qloo data</span>)}
            </div>
            {pill && demo && <p className="mt-2 max-w-2xl rounded-xl bg-white p-3 text-sm text-muted ring-1 ring-line">The numbers on this page are sample data. The pipeline, the requests it makes and the layout are the real product; the numbers switch to live Qloo data once the hackathon API key is connected.</p>}
            <p className="mt-3 max-w-2xl text-lg font-medium leading-snug md:text-xl">Spellcheck for cultural references.</p>
            <p className="mt-1 hidden max-w-2xl text-[15px] text-muted sm:block">Tell it who is in the room. It marks which references will land, which are risky and which will sail straight past them, then swaps the weak ones for stand-ins that work in every room.</p>
          </div>
          <nav aria-label="About" className="hidden shrink-0 flex-col items-end gap-1.5 pt-2 text-sm md:flex">{aboutLinks}</nav>
        </div>
      </header>

      <nav className="mx-auto max-w-7xl px-4 pb-3 md:px-6" aria-label="Examples">
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
          <span className="shrink-0 self-center text-sm text-muted">Try</span>
          {examples.map(ex => (
            <button key={ex.id} onClick={() => load(ex)} aria-pressed={exampleId === ex.id}
              className={`min-h-9 shrink-0 rounded-full px-3.5 text-sm ring-1 transition pointer-coarse:min-h-11 ${exampleId === ex.id ? 'bg-ink text-paper ring-ink' : 'bg-white ring-line hover:ring-ink/40'}`}>
              {JOBS[ex.kind] ?? ex.title}{exampleId === ex.id && original != null ? ' (edited)' : ''}
            </button>
          ))}
          <button onClick={pasteOwn} aria-pressed={editing && !exampleId}
            className={`min-h-9 shrink-0 rounded-full border border-dashed px-3.5 text-sm pointer-coarse:min-h-11 ${editing && !exampleId ? 'border-ink bg-ink text-paper' : 'border-ink/40 bg-white hover:border-ink'}`}>+ Your own script</button>
        </div>
      </nav>

      <main id="main" tabIndex={-1} className={`mx-auto max-w-7xl space-y-4 px-4 pb-16 outline-none md:px-6 ${active ? 'xl:pr-[412px]' : ''}`}>
        {shared && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3 text-sm ring-1 ring-line">
            <span>Shared result, scored with {shared.demo ? 'demo data' : 'live Qloo data'}{shared.created ? ` on ${shared.created}` : ''}.</span>
            <button onClick={rerunShared} className="min-h-9 rounded-xl px-3 ring-1 ring-line hover:ring-ink/40">Re-run it now</button>
          </div>
        )}

        {editing && (
          <section className="rise rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line" aria-label="Your script">
            <textarea autoFocus value={draft} onChange={e => setDraft(e.target.value)} maxLength={8000} aria-label="Script"
              placeholder="Paste a stand-up bit, an ad script, a speech or a toast. Name real things: shows, songs, brands, people."
              className="min-h-[40dvh] w-full resize-y bg-transparent text-[17px] leading-7 outline-none placeholder:text-muted md:min-h-[200px]" />
            {!draft && (
              <button onClick={() => setDraft('My nan still thinks Netflix is a DVD you post back. My little brother thinks Blockbuster is a Fortnite skin.\nWe tried a family film night with Friends. Grandad asked why nobody in it had a job.')}
                className={`${link} text-sm`}>Use a sample</button>
            )}
            <div className="mt-3 flex flex-col gap-3 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-xs text-muted">{draft.length.toLocaleString()} / 8,000 characters. A language model reads the text to find the references; only their names and the room settings go to Qloo.</span>
              <div className="flex shrink-0 gap-2">
                {text && <button onClick={() => { setEditing(false); setDraft(text); requestAnimationFrame(() => document.getElementById('edit-script')?.focus()) }} className="min-h-10 rounded-xl px-4 text-sm ring-1 ring-line">Cancel</button>}
                <button onClick={commitDraft} disabled={!draft.trim()} className="min-h-10 flex-1 rounded-xl bg-ink px-5 text-sm font-medium text-paper disabled:opacity-40 sm:flex-none">Check it</button>
              </div>
            </div>
          </section>
        )}

        {!editing && (
          <div className="flex flex-wrap items-center gap-2">
            {mode === 'qloo' && result && anyWeak && !fix && (
              <button onClick={landEverywhere} aria-disabled={fixing || busy || stale} className={`inline-flex min-h-11 items-center gap-2 rounded-xl bg-ink px-5 text-sm font-semibold text-paper shadow-sm ${fixing || busy || stale ? 'opacity-60' : 'hover:bg-ink/90'}`}>
                {fixing && <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-paper/40 border-t-paper" />}
                {fixing ? 'Looking for stand-ins...' : `Make it land in ${where}`}
              </button>
            )}
            {mode === 'qloo' && result && anyChecked && !anyWeak && !busy && !fix && <span className="text-sm font-medium text-lands">Every reference lands in {where}. Whether the joke is funny is still on you.</span>}
            {original != null && !fix && <button onClick={revert} className="min-h-11 rounded-xl bg-white px-4 text-sm ring-1 ring-line hover:ring-ink/40">Revert to original</button>}
            <button id="edit-script" onClick={() => { setEditing(true); setDraft(text) }} className="min-h-11 rounded-xl bg-white px-4 text-sm ring-1 ring-line hover:ring-ink/40">Edit script</button>
            {rooms.length < 6 && <button id="add-room" onClick={addRoom} className="min-h-11 rounded-xl bg-white px-4 text-sm ring-1 ring-line hover:ring-ink/40">Add a room</button>}
            {result && !stale && !fix && (
              <button onClick={share} className="min-h-11 rounded-xl bg-white px-4 text-sm ring-1 ring-line hover:ring-ink/40">
                {shareState === 'saving' ? 'Saving...' : shareState === 'copied' ? 'Link copied' : 'Share this result'}
              </button>
            )}
            {showToggle && (
              <div className="ml-auto flex items-center gap-2 text-xs">
                <span className="text-muted">Scored by</span>
                <div className="flex overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label="Scored by">
                  {([['qloo', 'Qloo data'], ['ai', 'AI guess alone']] as const).map(([v, l]) => (
                    <button key={v} onClick={() => setMode(v)} aria-pressed={mode === v} className={`min-h-9 px-3 ${mode === v ? 'bg-ink text-paper' : 'bg-white hover:bg-paper'}`}>{l}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {shareState !== 'idle' && shareState !== 'saving' && shareState !== 'copied' && <div role="alert" className="text-sm text-misses">{shareState}</div>}

        {!editing && result && <Legend model={result.model} />}
        {fixing && <Spinner label="Trying stand-ins in every room and keeping only changes that help. This can take up to 40 seconds." />}
        {busy && <Spinner label={result ? 'Re-checking the room...' : 'Reading your script for references...'} />}
        {note && <div role="status" className="text-sm text-muted">{note}</div>}
        {error && <div role="alert" className="rounded-xl bg-misses/5 p-3 text-sm text-misses ring-1 ring-misses/30">{error}</div>}
        {mode === 'ai' && result && <div className="rounded-xl bg-white p-3 text-sm text-muted ring-1 ring-line">Showing what a language model guesses with no data, on the same 0 to 100 scale. ◆ marks a reference where the guess is 25 or more points from the score with Qloo data. Switch back to Qloo data to rewrite.</div>}

        {result && !editing && !stale && mode === 'qloo' && split && splitRef && split.gap >= 30 && !fix && (
          <p className="text-[15px]">
            <span className="font-semibold">Same line, different room:</span>{' '}
            <button onClick={() => setActive({ ref: split.ref, room: split.lo })} className="font-semibold underline decoration-misses decoration-wavy decoration-2 underline-offset-4">{splitRef.name ?? splitRef.surface}</button>{' '}
            scores {Math.round(result.cells[split.ref][split.lo]!.score)} for {result.audiences[split.lo]?.label} and {Math.round(result.cells[split.ref][split.hi]!.score)} for {result.audiences[split.hi]?.label}.
          </p>
        )}

        {fix && <TrackedChanges r={fix} rooms={rooms} showPlace={showPlace} demo={demo} onKeep={keepFix} onUndo={() => { setFix(null); requestAnimationFrame(() => document.getElementById('edit-script')?.focus()) }} />}

        {result && !editing && (rooms.length <= 2
          ? <TwoUp text={scored.text} m={result} rooms={rooms} mode={mode} showPlace={showPlace} dim={stale || !!fix} demo={demo} active={active} flash={flash}
              onPick={(ref, room) => setActive({ ref, room })} onRoom={setRoom} onRemove={removeRoom} onAiView={() => setMode('ai')} />
          : <Grid text={scored.text} m={result} rooms={rooms} mode={mode} showPlace={showPlace} dim={stale || !!fix} onPick={(ref, room) => setActive({ ref, room })} onRoom={setRoom} onRemove={removeRoom} />)}

        {result && active && result.references[active.ref] && rooms[active.room] && (
          <Evidence key={`${active.ref}`} m={result} ref_={active.ref} room={active.room} rooms={rooms} showPlace={showPlace} locMeasured={!!options?.location_measured} demo={demo}
            onRoom={j => setActive({ ref: active.ref, room: j })} onClose={() => setActive(null)} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-10 md:px-6">
        <div className="grid gap-4 border-t border-line pt-6 text-sm md:grid-cols-[1fr_auto]">
          <p className="max-w-3xl text-muted">"Likely to land" is an estimate for an audience, not a statement about any one person, and not a judgement on whether a joke is funny. {scoreLine}. Your text goes to a language model to find the references; only their names and the room settings go to Qloo.</p>
          <div className="flex flex-wrap gap-x-4 gap-y-2 md:flex-col md:items-end">
            {aboutLinks}
            <a className={link} href="https://github.com/msimakhov-star/will-it-land">Source code (MIT)</a>
          </div>
        </div>
        <p className="mt-4 text-xs text-muted">Built for the Qloo Agentic Hackathon, October 2026.</p>
      </footer>

      {panel === 'hood' && ledger && <Hood ledger={ledger} demo={demo} onClose={() => setPanel(null)} />}
      {panel === 'mcp' && <Mcp onClose={() => setPanel(null)} />}
      {panel === 'proof' && <Proof demo={demo} onClose={() => setPanel(null)} />}
    </div>
  )
}

function Hood(p: { ledger: Ledger; demo: boolean; onClose: () => void }) {
  const l = p.ledger
  const [all, setAll] = useState(false)
  const calls = all ? l.calls : l.calls.slice(0, 12)
  const simulated = p.demo && !l.live
  return (
    <Modal title="Under the hood" side onClose={p.onClose}>
      <p className="mt-1 text-sm text-muted">
        {simulated
          ? `${l.total} lookups behind this result, all simulated demo data: the hackathon Qloo key has not arrived yet, so these are the exact requests the app would send.`
          : `${l.total} Qloo calls behind this result: ${l.live} live, ${l.cache} from cache${l.mock ? `, ${l.mock} from demo data` : ''}${l.errors ? `, ${l.errors} failed` : ''}.`}
        {' '}Only reference names and room settings go to Qloo, never your text.
      </p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {Object.entries(l.by_capability ?? l.by_endpoint).map(([e, n]) => (
          <div key={e} className="rounded-xl bg-paper px-3 py-2 text-xs">
            <div className="flex items-center justify-between gap-2"><span className="font-mono text-ink">{e}</span><span className="rounded-full bg-white px-1.5 font-semibold tabular-nums">x{n}</span></div>
            {PURPOSE[e] && <div className="mt-0.5 text-muted">{PURPOSE[e]}</div>}
          </div>
        ))}
      </div>
      <ol className="mt-4 space-y-1.5">
        {calls.map((c, i) => (
          <li key={i} className="rounded-lg bg-paper/60 p-2 font-mono text-[11px] leading-snug [overflow-wrap:anywhere]">
            <span className={c.source === 'error' ? 'text-misses' : c.source === 'live' ? 'text-lands' : 'text-muted'}>{c.source === 'mock' ? 'demo' : c.source}</span> GET {c.endpoint}?{Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join('&').slice(0, 220)} <span className="text-muted">{c.ms} ms</span>
          </li>
        ))}
      </ol>
      {!all && l.calls.length > 12 && <button onClick={() => setAll(true)} className="mt-3 min-h-10 rounded-xl px-4 text-sm ring-1 ring-line hover:ring-ink/40">Show all {l.calls.length} requests</button>}
      {l.total > l.calls.length && <p className="mt-2 text-xs text-muted">{l.total - l.calls.length} more not listed.</p>}
    </Modal>
  )
}

function Mcp(p: { onClose: () => void }) {
  const url = `${location.origin}/mcp`
  const cfg = JSON.stringify({ mcpServers: { 'will-it-land': { type: 'http', url } } }, null, 2)
  const cli = `claude mcp add --transport http will-it-land ${url}`
  const [copied, setCopied] = useState<string | null>(null)
  const copy = (what: string, s: string) => navigator.clipboard?.writeText(s).then(() => { setCopied(what); setTimeout(() => setCopied(null), 2000) }).catch(() => {})
  const btn = 'min-h-8 rounded-full px-3 text-xs ring-1 ring-line hover:text-ink'
  return (
    <Modal title="Give your writing agent an audience" onClose={p.onClose}>
      <p className="mt-2 text-sm text-muted">Will It Land is also an MCP server. Add it to Claude, ChatGPT or any MCP client and the agent can check its own references before it finishes a joke, an ad or a speech.</p>
      <div className="mt-4 text-xs font-medium text-muted">Hosted endpoint (streamable HTTP)</div>
      <code className="mt-1 block rounded-lg bg-paper p-2 font-mono text-xs break-all">{url}</code>
      <div className="mt-4 flex items-center justify-between text-xs font-medium text-muted">Claude Code<button onClick={() => copy('cli', cli)} className={btn} aria-label="Copy Claude Code command">{copied === 'cli' ? 'Copied' : 'Copy'}</button></div>
      <pre tabIndex={0} className="mt-1 overflow-x-auto rounded-lg bg-paper p-2 font-mono text-xs">{cli}</pre>
      <div className="mt-4 flex items-center justify-between text-xs font-medium text-muted">JSON config (.mcp.json and similar)<button onClick={() => copy('json', cfg)} className={btn} aria-label="Copy JSON config">{copied === 'json' ? 'Copied' : 'Copy'}</button></div>
      <pre tabIndex={0} className="mt-1 overflow-x-auto rounded-lg bg-paper p-2 font-mono text-xs">{cfg}</pre>
      <div className="mt-4 text-xs text-muted">Tools: check_references, check_matrix, localise, localise_for_all, audience_options.</div>
      <div role="status" className="sr-only">{copied ? 'Copied to clipboard' : ''}</div>
    </Modal>
  )
}

type ProofData = {
  model: { calibrated: boolean; source: string; k_loc: number }
  fit?: { n_entities: number; pooled: Record<string, number>; gap: { qloo: number; llm: number; n: number } }
  location?: { scored: number; hits: number; hit_rate: number; decision: string }
  survey?: { respondents: number; items: number; spearman_qloo: number | null; spearman_llm: number | null; ai_picks_most_did_not_know: string[] }
  taste_audit?: { total: { checked: number; weak: number; weak_share: number } }
}

function Status(p: { done: boolean }) {
  return p.done
    ? <span className="rounded-full bg-lands px-2 py-0.5 text-[11px] font-semibold text-white">measured</span>
    : <span className="rounded-full px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-line">not measured yet</span>
}

function Proof(p: { demo: boolean; onClose: () => void }) {
  const [d, setD] = useState<ProofData | null>(null)
  useEffect(() => { fetch('/api/proof').then(r => r.json()).then(setD).catch(() => {}) }, [])
  const row = (label: string, q: number | undefined | null, a: number | undefined | null) => (
    <tr className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{label}</td><td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{q == null ? '-' : q.toFixed(2)}</td><td className="py-1.5 text-right tabular-nums">{a == null ? '-' : a.toFixed(2)}</td></tr>
  )
  const done = [!!d?.fit, !!d?.survey, !!d?.location, !!d?.taste_audit]
  const n = done.filter(Boolean).length
  const Section = (q: { k: number; title: string; sub: string; children: React.ReactNode }) => (
    <section className="mt-3 rounded-xl p-3 ring-1 ring-line">
      <div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{q.title}</h3><Status done={done[q.k]} /></div>
      <p className="mt-0.5 text-xs text-muted">{q.sub}</p>
      <div className="mt-2 text-sm">{q.children}</div>
    </section>
  )
  return (
    <Modal title={n ? 'How we checked the score' : 'How we will check the score'} wide onClose={p.onClose}>
      <p className="mt-2 text-sm text-muted">The score starts from weights set by hand, so we test it against outside facts. The method was written down before any data arrived (eval/PREREG.md in the repository), and the results are published whatever they say.</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-paper px-2.5 py-1">Pre-registered: yes</span>
        <span className="rounded-full bg-paper px-2.5 py-1">Measured: {n} of 4 tests</span>
        {p.demo && <span className="hatch rounded-full bg-white px-2.5 py-1 ring-1 ring-ink/20">Waiting for the Qloo key</span>}
      </div>
      <Section k={0} title="1. Who has heard of it, by generation" sub={`YouGov's share of US millennials, Gen X and baby boomers who have heard of ${d?.fit ? d.fit.n_entities : 'about 300'} shows, films, artists, brands, people and podcasts. Do the scores put them in the same order? 1.0 means exactly the same order.`}>
        {d?.fit ? (
          <table className="w-full text-sm"><thead><tr className="text-xs text-muted"><th className="text-left font-normal" /><th className="text-right font-normal">With Qloo</th><th className="text-right font-normal">AI alone</th></tr></thead>
            <tbody>{row('how well known, all generations', d.fit.pooled.qloo, d.fit.pooled.llm)}{row('gap between generations (what a room switch changes)', d.fit.gap.qloo, d.fit.gap.llm)}{row('AI and Qloo combined', d.fit.pooled.blend, null)}</tbody></table>
        ) : <span className="text-muted">Runs as soon as the Qloo key arrives.</span>}
      </Section>
      <Section k={1} title="2. What under-25s actually recognise" sub="YouGov has no under-25 figures, so we run our own anonymous survey: age band, city, and 'have you heard of this?' for 49 items.">
        {d?.survey ? <>{d.survey.respondents} respondents, {d.survey.items} items. Agreement with what they recognised: with Qloo {d.survey.spearman_qloo?.toFixed(2) ?? '-'}, AI alone {d.survey.spearman_llm?.toFixed(2) ?? '-'}.{d.survey.ai_picks_most_did_not_know.length ? ` References the AI chose "for under-25s" that most of them did not know: ${d.survey.ai_picks_most_did_not_know.slice(0, 6).join(', ')}.` : ''}</>
          : <a className="inline-flex min-h-10 items-center rounded-xl bg-ink px-4 text-sm font-medium text-paper" href="/survey">Take the survey (18 to 24, anonymous)</a>}
      </Section>
      <Section k={2} title="3. Does the place part of the score do anything?" sub="20 regional brands and shows, scored at home and far away. If place does not separate them, it is dropped from the score and the place box disappears.">
        {d?.location ? <>{d.location.hits} of {d.location.scored} score stronger at home than far away. {d.model.k_loc > 0 ? 'Place stays in the score.' : 'Place is left out of the score.'}</> : <span className="text-muted">Runs as soon as the Qloo key arrives.</span>}
      </Section>
      <Section k={3} title="4. AI writing for a named audience" sub="Claude and Gemini each wrote 18 short pieces for a named room. How many of their references are weak for the very room they were written for?">
        {d?.taste_audit ? <>{Math.round(100 * d.taste_audit.total.weak_share)}% of their {d.taste_audit.total.checked} references score risky or likely to miss for that room.</> : <span className="text-muted">Reported only once tests 1 to 3 back the score.</span>}
      </Section>
      <p className="mt-4 border-t border-line pt-3 text-xs text-muted">{d?.model.calibrated ? `Score weights: ${d.model.source}.` : 'Until the tests run, the score uses starting weights set by hand.'} "Likely to land" means the audience is likely to recognise it and like it. It never claims a joke is funny.</p>
    </Modal>
  )
}
