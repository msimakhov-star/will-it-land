# Will It Land

**AI writes for the average audience. Will It Land checks every cultural reference in your script against the audience you are actually writing for, grounded in Qloo.**

Paste a stand-up bit, an ad, a toast, a speech or localised copy. Pick the audience: an age band, optionally a gender, a city or country. The agent:

1. finds every cultural reference (shows, films, artists, brands, people, books, games, podcasts, places),
2. resolves each one to an entity in Qloo's taste graph, using the line's context to settle ambiguous names,
3. scores how likely each reference is to land with that audience (0 to 100),
4. for weak references, proposes stand-ins that play the same role in the line, ranked for the audience, and rewrites the line,
5. re-scores, and leaves the writer to accept or ignore each swap.

Switch the audience and the highlights change. Toggle "AI alone" to see where a language model guessing without data disagrees with the Qloo-grounded score.

Live demo: _coming_ (hosted on Modal). Built for the [Qloo Agentic Hackathon](https://qloo.devpost.com), October 2026.

## Why Qloo is load-bearing

A language model knows that Gen Z did not grow up with Seinfeld. It does not know how a mid-popularity reference skews by age in a given city, what has risen or faded since its training data, or which stand-in a 55+ audience in Texas actually over-indexes on. Qloo does. Every score here is built from:

| signal | Qloo call |
|---|---|
| how widely known the thing is | entity `popularity` percentile from `/search` |
| how much the audience's age band over- or under-indexes on it | `/v2/insights?filter.type=urn:demographics` (age and gender affinity) |
| how it plays in the audience's city or country | `/v2/insights` with `signal.location.query` and `filter.results.entities`, in one call per entity type with fixed calibration anchors so scores are comparable |
| whether it is rising or fading | `/v2/trending` over the last six months |
| stand-ins that play the same role | the model names the role, proposes candidates, `/search` resolves them, the same scoring ranks them for the audience |

If this project would work the same without Qloo, it would be the wrong project. The "AI alone" toggle and the benchmark below exist to check that claim rather than assert it.

## Does it beat an AI guessing? The kill test

`eval/` compares the Qloo-grounded score against an LLM's unaided guess, using public ground truth: YouGov Ratings' "fame" figure (the share of US adults in each generation who have heard of something) for about 1,800 TV shows, films, artists, brands, people, books and podcasts (`eval/yougov.py` fetches it; `eval/data/yougov_fame.csv`).

Results: _pending the hackathon API key; the table from `python -m eval.kill_test` goes here, whatever it says._

## What the score means, and what it does not

- The score says how likely a reference is to **land with an audience**, not what any one person knows. Qloo data is aggregate taste data. No personal data is sent anywhere; the only thing that leaves your machine besides the text you paste is entity names.
- Affinity is not awareness. The score starts from how widely known a thing is and shifts it by how much the audience over- or under-indexes on it. The benchmark above is the check on that model.
- References Qloo has no entity for (slang, memes, very local things) are shown as "not in Qloo" and not scored.
- The agent offers stand-ins that play the same role. It does not claim the joke got funnier. The writer decides.

## Run it

```bash
# backend
uv venv --python 3.12 .venv && uv pip install -e .
export QLOO_API_KEY=...            # hackathon key; works only against hackathon.api.qloo.com
export ANTHROPIC_API_KEY=...       # or GEMINI_API_KEY=... (set LLM_PROVIDER=gemini)
.venv/bin/uvicorn server.main:app --reload --port 8000

# frontend (dev)
cd web && npm install && npm run dev   # proxies /api to :8000
# or build once and let FastAPI serve it
cd web && npm run build
```

Open http://localhost:5173 (dev) or http://localhost:8000 (built).

### As an MCP tool for your own writing agent

```json
{ "mcpServers": { "will-it-land": { "command": "/path/to/.venv/bin/python", "args": ["-m", "server.mcp_server"], "cwd": "/path/to/will-it-land" } } }
```

Tools: `check_references(text, age?, gender?, location?, propose_swaps?)` and `audience_options()`. Same pipeline, same result shape as the web app.

### Deploy

```bash
modal secret create qloo QLOO_API_KEY=...
modal secret create llm ANTHROPIC_API_KEY=...
cd web && npm run build && cd ..
modal deploy server/modal_app.py
```

## Layout

```
server/   FastAPI app, Qloo client with on-disk cache, LLM adapter (Anthropic or Gemini), the agent pipeline, MCP server, Modal entrypoint
web/      Vite + React + Tailwind UI
eval/     YouGov ground truth fetcher and the kill test
```

## Known limitations

- Qloo age buckets are coarse (under 25, 25 to 29, 30 to 34, 35 to 44, 45 to 54, 55+), so "Gen Z" and "under 18" are the same bucket.
- Location affinity is relative to two fixed anchors per entity type, which keeps it comparable but means it is a ranking signal, not a probability.
- Trend data is weekly and global, not per location.
- Qloo returns an empty result rather than an error for parameters it does not accept for a given entity type; the client only sends parameters from the entity-type guide, but an empty result is still shown as "not in Qloo".

## Licence

MIT. Qloo data is fetched live and cached privately; none of it is in this repository. YouGov figures in `eval/data` are public survey aggregates published on yougov.com.
