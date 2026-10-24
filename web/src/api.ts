import type { Example, Health, LocaliseAllResult, MatrixResult, Options, Room } from './types'

async function errText(r: Response): Promise<string> {
  const d = await r.json().catch(() => null)
  if (typeof d?.detail === 'string') return d.detail
  if (Array.isArray(d?.detail)) return d.detail.map((x: { msg?: string }) => x.msg ?? '').filter(Boolean).join('; ') || r.statusText
  return r.status === 429 ? 'Too many checks in a short time. Try again in a minute.' : `Request failed (${r.status})`
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(90000)
  const sig = signal && 'any' in AbortSignal ? (AbortSignal as unknown as { any: (s: AbortSignal[]) => AbortSignal }).any([signal, timeout]) : (signal ?? timeout)
  let r: Response
  try {
    r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: sig })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') throw new Error('That took too long. Please try again.')
    throw e
  }
  if (!r.ok) throw new Error(await errText(r))
  return r.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(await errText(r))
  return r.json() as Promise<T>
}

const clean = (rooms: Room[]) => rooms.map(r => ({ name: r.name || null, age: r.age || null, gender: r.gender || null, location: r.location?.trim() || null }))

export const api = {
  health: () => get<Health>('/api/health'),
  options: () => get<Options>('/api/options'),
  examples: () => get<Example[]>('/api/examples'),
  matrix: (text: string, rooms: Room[], signal?: AbortSignal) => post<MatrixResult>('/api/matrix', { text, audiences: clean(rooms) }, signal),
  guesses: (text: string, rooms: Room[], signal?: AbortSignal) => post<{ guesses: (number | null)[][] }>('/api/guesses', { text, audiences: clean(rooms) }, signal),
  landEverywhere: (text: string, rooms: Room[], signal?: AbortSignal) => post<LocaliseAllResult>('/api/localise_all', { text, audiences: clean(rooms) }, signal),
  report: (kind: string, payload: unknown) => post<{ id: string; url: string }>('/api/report', { kind, payload }),
  getReport: (id: string) => get<{ id: string; kind: string; payload: { text: string; rooms: Room[]; result: MatrixResult } }>(`/api/report/${id}`),
}

/** Server offsets are Unicode code points (Python); JS strings index UTF-16 units. Map one to the other. */
export function utf16Offsets(text: string): number[] {
  const off = [0]
  for (const ch of text) off.push(off[off.length - 1] + ch.length)
  return off
}

/** Run only the latest call: earlier in-flight calls are aborted and their results ignored. cancel() drops any in flight. */
export function latest() {
  let ctrl: AbortController | null = null
  let seq = 0
  const run = async function <T>(fn: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> {
    ctrl?.abort()
    ctrl = new AbortController()
    const my = ++seq
    try {
      const out = await fn(ctrl.signal)
      return my === seq ? out : undefined
    } catch (e) {
      if (my !== seq || (e instanceof DOMException && e.name === 'AbortError')) return undefined
      throw e
    }
  }
  return Object.assign(run, { cancel() { ctrl?.abort(); seq++ } })
}
