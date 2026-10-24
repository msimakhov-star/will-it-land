import { useEffect, useState } from 'react'

type Item = { id: string; name: string; type: string }
const AGE_LABEL: Record<string, string> = { under_18: 'under 18', '18_to_24': '18 to 24', '25_to_29': '25 to 29', '30_to_44': '30 to 44', '45_plus': '45 or over' }
const TYPE_LABEL: Record<string, string> = { tv_show: 'TV show', movie: 'film', artist: 'music', brand: 'brand', person: 'person', book: 'book', videogame: 'game', podcast: 'show or podcast', place: 'place' }

export default function Survey() {
  const [items, setItems] = useState<Item[]>([])
  const [ages, setAges] = useState<string[]>([])
  const [age, setAge] = useState('')
  const [city, setCity] = useState('')
  const [answers, setAnswers] = useState<Record<string, boolean>>({})
  const [state, setState] = useState<'form' | 'sending' | 'done'>('form')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/survey').then(r => r.json()).then(d => { setItems(d.items); setAges(d.ages) }).catch(() => setError('Could not load the survey.'))
  }, [])

  const answered = Object.keys(answers).length
  async function send() {
    setState('sending'); setError(null)
    const r = await fetch('/api/survey', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ age, city, answers }) })
    if (r.ok) setState('done')
    else { const d = await r.json().catch(() => null); setError(typeof d?.detail === 'string' ? d.detail : 'Something went wrong.'); setState('form') }
  }

  if (state === 'done') return (
    <main className="mx-auto max-w-xl px-4 py-16 text-center">
      <h1 className="font-display text-4xl font-bold">Thank you</h1>
      <p className="mt-3 text-muted">Your answers help check whether a computer can tell which references a room of people actually knows.</p>
      <a href="/" className="mt-6 inline-block rounded-xl bg-ink px-4 py-2 text-sm font-medium text-paper">See what it is for</a>
    </main>
  )

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="font-display text-4xl font-bold tracking-tight">Have you heard of these?</h1>
      <p className="mt-2 text-muted">Two minutes, completely anonymous: no name, no email, nothing that identifies you. Tap yes if you have heard of it, even vaguely. There are no wrong answers.</p>
      <div className="mt-6 space-y-3 rounded-2xl bg-white p-4 ring-1 ring-line">
        <div>
          <div className="mb-1 text-sm font-medium">Your age</div>
          <div className="flex flex-wrap gap-1.5">{ages.map(a => <button key={a} onClick={() => setAge(a)} aria-pressed={age === a} className={`rounded-full px-3 py-1.5 text-sm ${age === a ? 'bg-ink text-paper' : 'bg-white ring-1 ring-line'}`}>{AGE_LABEL[a] ?? a}</button>)}</div>
        </div>
        <label className="block">
          <div className="mb-1 text-sm font-medium">City you live in</div>
          <input value={city} onChange={e => setCity(e.target.value)} maxLength={40} placeholder="for example London" className="w-full rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-line outline-none focus:ring-ink/50" />
        </label>
      </div>
      <ol className="mt-4 space-y-2">
        {items.map((it, n) => (
          <li key={it.id} className="flex items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 ring-1 ring-line">
            <div className="min-w-0"><span className="mr-2 text-xs text-muted tabular-nums">{n + 1}.</span><span className="font-medium">{it.name}</span> <span className="text-xs text-muted">({TYPE_LABEL[it.type] ?? it.type})</span></div>
            <div className="flex shrink-0 overflow-hidden rounded-full ring-1 ring-line" role="group" aria-label={`Heard of ${it.name}?`}>
              {([[true, 'yes'], [false, 'no']] as const).map(([v, l]) => (
                <button key={l} onClick={() => setAnswers(a => ({ ...a, [it.id]: v }))} aria-pressed={answers[it.id] === v}
                  className={`px-3.5 py-1.5 text-sm ${answers[it.id] === v ? (v ? 'bg-lands text-white' : 'bg-ink text-paper') : 'bg-white'}`}>{l}</button>
              ))}
            </div>
          </li>
        ))}
      </ol>
      {error && <div className="mt-4 rounded-xl bg-misses/5 p-3 text-sm text-misses ring-1 ring-misses/30">{error}</div>}
      <div className="sticky bottom-0 mt-4 flex items-center justify-between gap-3 bg-paper/95 py-3">
        <span className="text-sm text-muted">{answered} of {items.length} answered</span>
        <button onClick={send} disabled={!age || answered < Math.ceil(items.length / 2) || state === 'sending'} className="rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-paper disabled:opacity-40">{state === 'sending' ? 'Sending...' : 'Send answers'}</button>
      </div>
    </main>
  )
}
