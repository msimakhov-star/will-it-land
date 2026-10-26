# Will It Land

Spellcheck for cultural references. Paste a stand-up bit, an ad script, a toast or a speech, pick the rooms you are playing (an age band, optionally men or women, a city or country, optionally a Qloo audience segment), and Will It Land scores every reference for that audience from Qloo's taste data. Weak references get a stand-in, scored the same way, and the line is rewritten.

Live app: https://m-simakhov--will-it-land-web.us-east.modal.run (built for the Qloo Agentic Hackathon, October 2026). Status while the hackathon API key is pending: the live app runs on demo data and says so in its header.

## What it does
- Two rooms side by side: the same script, marked like a spellchecker for each room (wavy underline: likely misses; dotted: risky; solid: lands; dashed: not in Qloo), with a headline per room such as "Under 25s in London: 3 of 7 will likely miss", and one line naming the biggest split between the rooms.
- Four examples: a comedian's bit in two rooms, a touring comic's opener in six cities, an ad in six markets, and a best man's toast for two tables.
- Up to six rooms as a grid, with a "lands everywhere" column next to each reference that takes its worst room.
- "Make it land in both rooms" (or "in every room"): for each weak reference the agent finds stand-ins, scores every candidate in every room, picks the one whose weakest room scores best, rewrites the line, re-scores the whole script and keeps the rewrite only if no room gets worse. Changes appear as word-level suggestions inside each line, with the part each reference plays and a badge for where each stand-in came from.
- An evidence card for every mark: the score, a plain sentence, the parts of the score (how well known, fit with this age band, strength in this place), the age profile, and the same reference in every other room.
- "Scored by: Qloo data or AI guess alone" repaints the page with the model's unaided guesses, so the difference is visible. It is hidden while the app runs on demo data.
- "Under the hood" lists every request behind the result. Any result can be shared as a link.
- An MCP server, so any writing agent can check its own references before it finishes a draft.

## How the agent works
1. A language model finds the cultural references in the text and names the role each one plays in its line (for example "a dead video-rental chain").
2. Each reference is resolved to a Qloo entity with /search; when several entities share a name, the model picks one from the line's context.
3. For each entity, Qloo's demographics insights give how much each age band and gender over- or under-indexes on it, and /v2/trending gives its six-month direction (shown, not scored).
4. For each room, one insights call per entity type ranks the references in that place against eight fixed anchor entities, so the place term is comparable across calls.
5. The score combines how widely known the entity is (Qloo popularity) with the room's age band, gender and place. The formula is in server/scoring.py.
6. Stand-ins come from two sources: Qloo itself (the reference's characterising tags plus the room's demographics and place, with a popularity floor, filtered by the model for role fit) and the model's own role-based ideas, each resolved to a real Qloo entity. Every candidate is scored the same way as the original, in the same calls.

## Qloo endpoints used
| purpose | Qloo call |
|---|---|
| resolve a name to an entity, popularity | /search |
| age and gender affinity | /v2/insights with filter.type=urn:demographics |
| place affinity, ranked against anchors | /v2/insights with filter.results.entities and signal.location.query |
| tags that characterise a reference | /v2/insights with filter.type=urn:tag |
| stand-ins the room over-indexes on | /v2/insights with signal.interests.tags, signal.interests.entities, signal.demographics.age and signal.location.query |
| audience segments, and ranking for one | /v2/audiences, then /v2/insights with signal.demographics.audiences |
| six-month direction (display only) | /v2/trending |

## How we test it
The method was fixed before any real data arrived and committed in eval/PREREG.md. Results are published whatever they say.
- Who has heard of it, by generation: YouGov Ratings publishes the share of US millennials, Gen X and baby boomers who have heard of thousands of shows, films, artists, brands, people and podcasts. eval/kill_test.py compares the Qloo-grounded score with a language model's unaided guess on about 300 of them (sampled from the 3,428 distinct entities in eval/data/yougov_fame.csv), overall, within each entity type, and on the millennial-minus-boomer gap. Result: not measured yet.
- What under-25s recognise: YouGov has no under-25 figures, so the app hosts an anonymous survey at /survey (age band, city, "have you heard of this?" for 49 items). Result: not measured yet.
- Whether place means anything: 20 regional brands and shows scored at home and far away (eval/location_sanity.py). If place does not separate them, it is dropped from the score and the place box disappears from the app. Result: not measured yet.
- AI writing for a named audience: Claude and Gemini each wrote 18 short pieces for a named room (eval/data/ai_texts.json). The share of their references that miss that room is reported only if the tests above validate the score.

## From request to result (one reference)
1. The model reads "My mum's idea of a wild Friday is a Blockbuster card she never returned" and returns the reference "Blockbuster", type brand, part "a dead video-rental chain".
2. /search with query Blockbuster and type brand returns the entity and its popularity; if several entities share the name, the model picks one from the line.
3. /v2/insights with urn:demographics returns the over- or under-indexing of each age band.
4. For the room "under 25, London", /v2/insights ranks the brand references in London against eight anchor brands.
5. The score combines popularity with the age band and place terms; the evidence card shows each part.
6. If the reference is weak in any room, stand-ins are gathered and each is scored in every room the same way.

## What the score means, and what it does not
- "Likely to land" means likely to be recognised and liked by that audience. It is an estimate for a group, never a statement about one person, and it never claims a joke is funny.
- Until the tests above are run, the score uses hand-set starting values, not calibrated against any data, and the app says so. The YouGov test covers US adults in three generations (roughly 30 and over); under-25s are covered only by our own survey.
- Qloo age bands are under 25, 25 to 29, 30 to 34, 35 to 44, 45 to 54 and 55+.
- References Qloo has no entity for (slang, memes, very local things) are shown as "not in Qloo" and not scored.
- A stand-in can be well known in every room and still break the joke; the writer decides.
- The text goes to a language model, which finds the references. Only reference names and room settings are sent to Qloo, never the text.

## Run it
```bash
uv venv --python 3.12 .venv && uv pip install -e .
export QLOO_API_KEY=...          # hackathon key; works only against hackathon.api.qloo.com
export ANTHROPIC_API_KEY=...     # or GEMINI_API_KEY=... with LLM_PROVIDER=gemini
cd web && npm install && npm run build && cd ..
.venv/bin/uvicorn server.main:app --port 8000
```
Without a key, QLOO_MOCK=1 runs the whole app on clearly labelled demo data.

## Use it from your own agent (MCP)
Hosted endpoint, streamable HTTP: https://m-simakhov--will-it-land-web.us-east.modal.run/mcp
Claude Code:
```bash
claude mcp add --transport http will-it-land https://m-simakhov--will-it-land-web.us-east.modal.run/mcp
```
JSON config (.mcp.json and similar clients):
```json
{ "mcpServers": { "will-it-land": { "type": "http", "url": "https://m-simakhov--will-it-land-web.us-east.modal.run/mcp" } } }
```
Local stdio: `.venv/bin/python -m server.mcp_server`. Tools: check_references, check_matrix, localise, localise_for_all, audience_options.

## Tests
`.venv/bin/python -m pytest -q` runs offline against a fake Qloo with injected faults (rate limits, timeouts, empty answers) and a scripted model. `python -m tools.probe` checks every field the code reads from the real Qloo API.

## Layout
- server/: FastAPI app, Qloo client with cache and call ledger, the agent pipeline, the score model, MCP server, Modal deployment
- web/: React, Vite and Tailwind interface
- eval/: YouGov ground truth, benchmark, calibration, location check, split finder, survey report, AI taste audit
- tools/: key-day probe, cache prewarm, screenshots, prose rendering

## Licence
MIT. Qloo data is fetched live and cached privately; none of it is in this repository. YouGov figures in eval/data are public survey aggregates published on yougov.com.
