# Will It Land

Spellcheck for cultural references. Paste a stand-up bit, an ad script, a toast or a speech. Pick the rooms you are playing. A room is an age band, optionally men or women, and a city or country. Will It Land checks every reference against what that audience actually knows. It uses Qloo's taste graph. References that will not land get a stand-in that does. The app rewrites the line.

Live app: https://m-simakhov--will-it-land-web.us-east.modal.run (built for the Qloo Agentic Hackathon, October 2026). Status while the hackathon API key is pending: the live app runs on demo data and says so in its header.

## What it does
- Two rooms side by side: the app marks the same script like a spellchecker for each room. A red wavy underline means likely misses. Amber dotted means risky. Green means it lands. Grey dashed means it is not in Qloo. Each room gets a headline, such as "Under 25s in London: 2 of 7 risky".
- Up to six rooms as a grid. A last column, "lands everywhere", takes each reference's worst room.
- "Make it land in both rooms" (or "in every room"): the agent finds stand-ins for each weak reference. It scores every candidate in every room. It picks the one whose worst room scores best. It rewrites the line, re-scores the whole script and keeps the rewrite only if the rooms improved. Changes appear as tracked changes with a badge per stand-in. Badges say "found in Qloo's graph" or "model idea, scored by Qloo".
- An evidence card for every mark: the card shows the score, a plain sentence and a breakdown of the score. The breakdown shows how widely known the reference is, this age band and this place. It also shows the age profile from Qloo and what a language model guessed without data.
- "Scored by: Qloo data or AI guess alone" repaints the page with the model's unaided guesses. This makes the difference visible.
- "Under the hood" lists every Qloo request behind the result.
- An MCP server lets any writing agent check its own references before it finishes a draft.

## How the agent works
1. A language model finds the cultural references in the text. It names the role each one plays in its line (for example "a dead video-rental chain").
2. Each reference is resolved to a Qloo entity with /search. When several entities share a name, the model picks one from the line's context.
3. For each entity, Qloo's demographics insights give how much each age band and gender over-indexes or under-indexes on it. The /v2/trending endpoint gives its six-month direction. The app shows this direction but does not score it.
4. For each room, one insights call per entity type ranks the references in that place against eight fixed anchor entities. This makes the place term comparable across calls.
5. The score combines how widely known the entity is (Qloo popularity) with the room's age band, gender and place. The formula is in server/scoring.py.
6. Stand-ins come from two sources. The first is Qloo itself. This uses the reference's characterising tags plus the room's demographics and place, with a popularity floor, filtered by the model for role fit. The second is the model's own role-based ideas. Each idea resolves to a real Qloo entity. The app scores every candidate the same way as the original, in the same calls.

## Qloo endpoints used
| purpose | Qloo call |
|---|---|
| resolve a name to an entity, popularity | /search |
| age and gender affinity | /v2/insights with filter.type=urn:demographics |
| place affinity, ranked against anchors | /v2/insights with filter.results.entities and signal.location.query |
| tags that characterise a reference | /v2/insights with filter.type=urn:tag |
| stand-ins the room over-indexes on | /v2/insights with signal.interests.tags, signal.interests.entities, signal.demographics.age and signal.location.query |
| six-month direction (display only) | /v2/trending |

## How we test it
The method was fixed before any real data arrived. It is committed in eval/PREREG.md. Results are published whatever they say.
- Who has heard of it, by generation: YouGov Ratings publishes the share of US millennials, Gen X and baby boomers who have heard of thousands of shows, films, artists, brands, people and podcasts. eval/kill_test.py compares the Qloo-grounded score with a language model's unaided guess on about 300 of them. It compares them overall, within each entity type, and on the millennial-minus-boomer gap. Result: not measured yet.
- What under-25s recognise: YouGov has no under-25 figures. The app hosts an anonymous survey at /survey. It asks for age band, city, and "have you heard of this?" for 49 items. Result: not measured yet.
- Whether place means anything: 20 regional brands and shows scored at home and far away (eval/location_sanity.py). If place does not separate them, it is dropped from the score. The place box then disappears from the app. Result: not measured yet.
- AI writing for a named audience: Claude and Gemini each wrote 18 short pieces for a named room (eval/data/ai_texts.json). The share of their references that miss that room is reported only if the tests above validate the score.

## What the score means, and what it does not
- "Likely to land" means likely to be recognised and liked by that audience. It is an estimate for a group. It is never a statement about one person. It never claims a joke is funny.
- Until the tests above are run, the score uses hand-set starting values. The app says so.
- Qloo age bands are under 25, 25 to 29, 30 to 34, 35 to 44, 45 to 54 and 55+.
- References Qloo has no entity for (slang, memes, very local things) are shown as "not in Qloo". They are not scored.
- Only reference names and audience settings are sent to Qloo. The text is never sent.

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
```json
{ "mcpServers": { "will-it-land": { "url": "https://m-simakhov--will-it-land-web.us-east.modal.run/mcp" } } }
```
Local stdio: `.venv/bin/python -m server.mcp_server`. Tools: check_references, check_matrix, localise, localise_for_all, audience_options.

## Tests
`.venv/bin/python -m pytest -q` runs offline against a fake Qloo with injected faults (rate limits, timeouts, empty answers) and a scripted model. The `python -m tools.probe` command checks every field the code reads from the real Qloo API.

## Layout
- server/: FastAPI app, Qloo client with cache and call ledger, the agent pipeline, the score model, MCP server, Modal deployment
- web/: React, Vite and Tailwind interface
- eval/: YouGov ground truth, benchmark, calibration, location check, split finder, survey report, AI taste audit
- tools/: key-day probe, cache prewarm, screenshots, prose rendering

## Licence
MIT. Qloo data is fetched live and cached privately. None of it is in this repository. YouGov figures in eval/data are public survey aggregates published on yougov.com.
