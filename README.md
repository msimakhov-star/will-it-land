# Will It Land

Spellcheck for cultural references. Paste a stand-up bit, an ad script, a toast, or a speech. Pick the rooms you are playing. A room is an age band, optionally men or women, and a city or country. Will It Land scores every reference for that audience using Qloo taste data. Weak references get a stand-in. The app scores the stand-in the same way and rewrites the line.

Live app: https://m-simakhov--will-it-land-web.us-east.modal.run (built for the Qloo Agentic Hackathon, October 2026). Status while the hackathon API key is pending: the live app runs on demo data and says so in its header.

## What it does
- Two rooms side by side: the app marks the same script like a spellchecker for each room. Marks include a red wavy underline for likely misses, amber dotted for risky, green for lands, and grey dashed for not in Qloo. A headline per room reads like "Under 25s in London: 2 of 7 risky".
- Up to six rooms as a grid. A "lands everywhere" column next to each reference takes its worst room.
- "Make it land in both rooms" or "in every room": the agent finds stand-ins for each weak reference. It scores every candidate in every room. It picks the one whose worst room scores best and rewrites the line. The app re-scores the whole script and keeps the rewrite only if the rooms improved. Changes appear as tracked changes with a badge per stand-in. Badges say "found in Qloo's graph" or "model idea, scored by Qloo".
- An evidence card for every mark: the card shows the score, a plain sentence, and a breakdown of the score. The breakdown covers how widely known the reference is, this age band, and this place. The card also shows the age profile from Qloo and what a language model guessed without data.
- "Scored by: Qloo data or AI guess alone" repaints the page with the model's unaided guesses. This makes the difference visible. The app hides this button while it runs on demo data.
- "Under the hood" lists every Qloo request behind the result.
- An MCP server lets any writing agent check its own references before it finishes a draft.

## How the agent works
1. A language model finds the cultural references in the text. It names the role each one plays in its line, for example "a dead video-rental chain".
2. The app resolves each reference to a Qloo entity with /search. When several entities share a name, the model picks one from the line's context.
3. Qloo's demographics insights show how much each age band and gender over-indexes or under-indexes on each entity. The /v2/trending endpoint gives the six-month direction. The app shows this direction but does not score it.
4. For each room, one insights call per entity type ranks the references in that place against eight fixed anchor entities. This makes the place term comparable across calls.
5. The score combines how widely known the entity is, which is Qloo popularity, with the room's age band, gender, and place. The formula is in server/scoring.py.
6. Stand-ins come from two sources. The first is Qloo itself. The app uses the reference's characterising tags, the room's demographics, and the place. It applies a popularity floor. The model filters the results for role fit. The second source is the model's own role-based ideas. The app resolves each idea to a real Qloo entity. The agent scores every candidate the same way as the original in the same calls.

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
We fixed the method before any real data arrived and committed it in eval/PREREG.md. We publish results whatever they say.
- Who has heard of it, by generation: YouGov Ratings publishes the share of US millennials, Gen X, and baby boomers who have heard of thousands of shows, films, artists, brands, people, and podcasts. The eval/kill_test.py script compares the Qloo grounded score with a language model's unaided guess on about 300 of them. We sampled these from the 3,428 distinct entities in eval/data/yougov_fame.csv. The script compares them overall, within each entity type, and on the millennial minus boomer gap. Result: not measured yet.
- What under-25s recognise: YouGov has no under-25 figures. The app hosts an anonymous survey at /survey. It asks for age band, city, and "have you heard of this?" for 49 items. Result: not measured yet.
- Whether place means anything: We score 20 regional brands and shows at home and far away in eval/location_sanity.py. If place does not separate them, we drop it from the score and the place box disappears from the app. Result: not measured yet.
- AI writing for a named audience: Claude and Gemini each wrote 18 short pieces for a named room in eval/data/ai_texts.json. We report the share of their references that miss that room only if the tests above validate the score.

## What the score means, and what it does not
- "Likely to land" means likely to be recognised and liked by that audience. It is an estimate for a group. It is never a statement about one person. It never claims a joke is funny.
- Until we run the tests above, the score uses hand set starting values. These values are not calibrated against any data, and the app says so. The YouGov test covers US adults in three generations, roughly 30 and over. Our own survey covers under-25s.
- Qloo age bands are under 25, 25 to 29, 30 to 34, 35 to 44, 45 to 54, and 55+.
- References Qloo has no entity for, like slang, memes, or very local things, are shown as "not in Qloo" and not scored.
- The text goes to a language model. The model finds the references. The app sends only reference names and room settings to Qloo. It never sends the text.

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
`.venv/bin/python -m pytest -q` runs offline against a fake Qloo with injected faults like rate limits, timeouts, and empty answers. It uses a scripted model. `python -m tools.probe` checks every field the code reads from the real Qloo API.

## Layout
- server/: FastAPI app, Qloo client with cache and call ledger, the agent pipeline, the score model, MCP server, and Modal deployment.
- web/: React, Vite, and Tailwind interface.
- eval/: YouGov ground truth, benchmark, calibration, location check, split finder, survey report, and AI taste audit.
- tools/: key-day probe, cache prewarm, screenshots, and prose rendering.

## Licence
MIT. The app fetches Qloo data live and caches it privately. None of this data is in this repository. YouGov figures in eval/data are public survey aggregates published on yougov.com.
