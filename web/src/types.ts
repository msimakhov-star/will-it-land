export type Verdict = 'lands' | 'risky' | 'misses' | 'unknown'

export type Parts = { base: number; age: number; gender: number; location: number; score: number }

export type Cell = {
  score: number
  verdict: Verdict
  why: string
  affinity: number | null
  location: number | null
  age_affinity: number | null
  parts: Parts
  llm_guess?: number | null
}

export type Candidate = { entity_id: string; name: string; type: string | null; popularity: number | null; year: string | null; disambiguation: string | null }

export type Swap = { name: string; entity_id: string; score: number; source: 'qloo' | 'ai'; why: string; line: string | null }

export type Ref = {
  surface: string
  start: number
  end: number
  type: string
  query: string
  role: string
  era: string | null
  entity_id: string | null
  name: string | null
  disambiguation: string | null
  candidates: Candidate[]
  popularity: number | null
  age_skew: Record<string, number> | null
  gender_skew: Record<string, number> | null
  trend: { direction: string; delta: number | null; percentile: number | null } | null
  llm_guess: number | null
  score: number | null
  verdict: Verdict
  why: string
  swaps: Swap[]
}

export type Room = { name?: string | null; age: string | null; gender: string | null; location: string | null }

export type Summary = { found: number; checked: number; not_in_qloo: number; lands: number; risky: number; misses: number }

export type LedgerCall = { endpoint: string; params: Record<string, string>; source: 'live' | 'cache' | 'mock' | 'stale' | 'error'; ms: number }
export type Ledger = { total: number; live: number; cache: number; mock: number; errors: number; by_endpoint: Record<string, number>; calls: LedgerCall[] }

export type MatrixResult = {
  audiences: (Room & { label: string; location_recognised: boolean | null })[]
  references: Ref[]
  cells: (Cell | null)[][]
  summaries: Summary[]
  model: { lands: number; misses: number; calibrated: boolean; source: string }
  ledger?: Ledger
  took_s?: number
}

export type LocaliseAllResult = {
  original: string
  text: string
  before: MatrixResult
  after: MatrixResult
  swaps: { from: string; to: string; source: 'qloo' | 'ai'; why: string; scores_from: number[]; scores_to: number[] }[]
  kept: boolean
  detail?: string
  applied?: { total: number; from_qloo: number }
  ledger?: Ledger
}

export type Example = { id: string; title: string; kind: string; text: string; audience: Room; matrix?: Room[] }

export type Health = { ok: boolean; qloo_key: boolean; mock: boolean; llm: string; model: string }
export type Options = { ages: { value: string; label: string }[]; max_audiences: number; location_weight: number; calibrated: boolean }
