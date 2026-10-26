# Will It Land

Spellcheck for cultural references. Paste a stand-up bit, an ad script, a toast or a speech. Pick the rooms you are playing. A room is an age band, optionally men or women, a city or country, and optionally a Qloo audience segment. Will It Land scores every reference for that audience from Qloo taste data. Weak references get a stand-in. The app scores the stand-in the same way and rewrites the line.

Live app: https://m-simakhov--will-it-land-web.us-east.modal.run (built for the Qloo Agentic Hackathon, October 2026). Status while the hackathon API key is pending: the live app runs on demo data and says so in its header.

## What it does
- Two rooms side by side. The app marks the same script like a spellchecker for each room. A wavy underline means likely misses. A dotted line means risky. A solid line means lands. A dashed line means not in Qloo. Each room has a headline, such as "Under 25s in London: 3 of 7 will likely miss". One line names the biggest split between the rooms.
- Four examples. These are a comedian's bit in two rooms, a touring comic's opener in six cities, an ad in six markets, and a best man's toast for two tables.
- Up to six rooms as a grid. A "lands everywhere" column sits next to each reference. This column takes the worst room for that reference.
- "Make it land in both rooms" or "in every room". For each weak reference, the agent finds stand-ins. It scores every candidate in every room. It picks the candidate whose weakest room scores best. The agent rewrites the line and re-scores the whole script. It keeps the rewrite only if no room gets worse. Changes appear as word-level suggestions inside each line. These suggestions show the part each reference plays. A badge shows where each stand-in came from.
- An evidence card for every mark. The card shows the score, a plain sentence, and the parts of the score. The parts are how well known the reference is, its fit with the age band, and its strength in the place. The card also shows the age profile and the same reference in every other room.
- "Scored by: Qloo data or AI guess alone". A toggle repaints the page with the model's unaided guesses. This makes the difference visible. The toggle is hidden while the app runs on demo data.
- "Under the hood". This section lists every request behind the result. Users can share any result as a link.
- An MCP server. This lets any writing agent check its own references before it finishes a draft.

## How the agent works
1. A language model finds the cultural references in the text. It names the role each reference plays in its line, for example "a dead video-rental chain".
2. Each reference resolves to a Qloo entity with /search. When several entities share a name, the model picks one from the line context.
3. For each entity, Qloo demographics insights show how much each age band and gender over-indexes or under-indexes on it. The /v2/trending endpoint gives the six-month direction. The app shows this direction but does not score it.
4. For each room, one insights call per entity type ranks the references in that place against eight fixed anchor entities. This makes the place term comparable across calls.
5. The score combines how widely known the entity is, from Qloo popularity, with the room age band, gender and place. The formula is in server/scoring.py.
6. Stand-ins come from two sources. The first is Qloo itself. This uses the reference characterising tags, the room demographics and place, and a popularity floor. The model filters these for role fit. The second source is the model's own role-based ideas. Each idea resolves to a real Qloo entity. The agent scores every candidate the same way as the original reference in the same calls.

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
The method was fixed before any real data arrived. It is committed in eval/PREREG.md. We publish results whatever they say.
- Who has heard of it by generation: YouGov Ratings publishes the share of US millennials, Gen X and baby boomers who have heard of thousands of shows, films, artists, brands, people and podcasts. The eval/kill_test.py script compares the Qloo-grounded score with a language model unaided guess on about 300 of them. These are sampled from the 3,428 distinct entities in eval/data/yougov_fame.csv. The script compares them overall, within each entity type, and on the millennial minus boomer gap. Result: not measured yet.
- What under-25s recognise: YouGov has no under-25 figures. The app hosts an anonymous survey at /survey. It asks for age band, city, and "have you heard of this?" for 49 items. Result: not measured yet.
- Whether place means anything: We score 20 regional brands and shows at home and far away in eval/location_sanity.py. If place does not separate them, it is dropped from the score. The place box then disappears from the app. Result: not measured yet.
- AI writing for a named audience: Claude and Gemini each wrote 18 short pieces for a named room in eval/data/ai_texts.json. We report the share of their references that miss that room only if the tests above validate the score.

## From request to result (one reference)
1. The model reads "My mum's idea of a wild Friday is a Blockbuster card she never returned". It returns the reference "Blockbuster", type brand, part "a dead video-rental chain".
2. A /search with query Blockbuster and type brand returns the entity and its popularity. If several entities share the name, the model picks one from the line.
3. A /v2/insights call with urn:demographics returns the over-indexing or under-indexing of each age band.
4. For the room "under 25, London", /v2/insights ranks the brand references in London against eight anchor brands.
5. The score combines popularity with the age band and place terms. The evidence card shows each part.
6. If the reference is weak in any room, the agent gathers stand-ins. It scores each stand-in in every room the same way.

## What the score means, and what it does not
- "Likely to land" means likely to be recognised and liked by that audience. It is an estimate for a group. It is never a statement about one person. It never claims a joke is funny.
- Until the tests above are run, the score uses hand-set starting values. These are not calibrated against any data. The app says so. The YouGov test covers US adults in three generations, roughly 30 and over. Under-25s are covered only by our own survey.
- Qloo age bands are under 25, 25 to 29, 30 to 34, 35 to 44, 45 to 54 and 55+.
- References Qloo has no entity for, like slang, memes, and very local things, are shown as "not in Qloo". They are not scored.
- A stand-in can be well known in every room and still break the joke. The writer decides.
- The text goes to a language model. The model finds the references. Only reference names and room settings are sent to Qloo. The text is never sent.

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
The command `.venv/bin/python -m pytest -q` runs offline against a fake Qloo with injected faults. These faults include rate limits, timeouts, and empty answers. It uses a scripted model. The command `python -m tools.probe` checks every field the code reads from the real Qloo API.

## Layout
- server/: FastAPI app, Qloo client with cache and call ledger, the agent pipeline, the score model, MCP server, and Modal deployment.
- web/: React, Vite and Tailwind interface.
- eval/: YouGov ground truth, benchmark, calibration, location check, split finder, survey report, and AI taste audit.
- tools/: key-day probe, cache prewarm, screenshots, and prose rendering.

## Licence
MIT. Qloo data is fetched live and cached privately. None of it is in this repository. YouGov figures in eval/data are public survey aggregates published on yougov.com.
