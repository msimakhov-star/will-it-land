# Will It Land

Qloo Agentic Hackathon entry (qloo.devpost.com). Deadline Fri 30 Oct 2026 23:45 EDT; submit Thu 29 Oct.
Pitch: "AI writes for the average audience. Will It Land checks every cultural reference against the real one."

## What it does
Paste a script, set, ad or speech + pick an audience (age band, optional gender, country/city).
Agent: extract cultural references -> resolve to Qloo entities (disambiguate from context) ->
score "likely to land" (Qloo popularity + age/gender affinity + location affinity + trend) ->
for weak ones propose same-role swaps (entity_tags + rank) -> rewrite line -> re-score -> writer picks.
Also exposed as an MCP tool `check_references` so other writing agents can call it (rule c).

## Stack (keep it this small)
- `server/` Python 3.12, FastAPI, httpx. Qloo REST direct (base https://hackathon.api.qloo.com, header X-Api-Key).
  sqlite cache of every Qloo call. LLM adapter: Anthropic (default) or Gemini via env.
- `server/mcp_server.py` FastMCP: stdio + mounted at /mcp.
- `web/` Vite + React + TS + Tailwind, built to `web/dist`, served by FastAPI.
- Deploy: Modal (`modal deploy server/modal_app.py`), min_containers=1, secrets `qloo`, `llm`.
- `eval/` kill test: Qloo score vs YouGov fame (ground truth) vs LLM-only guess. Numbers go in README whatever they are.

## Rules that bind the code
- Never send personal data to Qloo. Aggregate audiences only. Say "likely to land", never "recognised".
- Scores from `qloo_rank`-style calls are comparable only within one call: always include calibration anchors.
- Invalid Qloo params return 200 + empty: validate params against the entity-type guide.
- Never commit keys or Qloo response data. Cache lives outside the repo.
- No em/en dashes in any text. Git author email stays the noreply address.
