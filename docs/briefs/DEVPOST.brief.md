# Will It Land

## Tagline
Spellcheck for cultural references: it shows which references in your script will land with the room you are playing, and swaps the weak ones for stand-ins that work in every room.

## Status
Until the hackathon Qloo key arrives, the live app runs on clearly labelled demo data, so the numbers on screen are placeholders. The pipeline, the requests it makes and the interface are the real product. (Replace this paragraph with "Runs on live Qloo data" once true.)

## Inspiration
Writers never perform for the average room. A touring comic plays 25-year-olds in Leeds on Friday and in Atlanta on Monday. An ad team ships one script into six markets. A best man speaks to two tables: his friends and the grandparents. Each of them checks references by gut, or asks a language model, and language models tend to reach for the same handful of shows, artists and brands whatever the audience. What none of them has is data on which references a specific audience knows and likes, and which stand-in would play the same part for them. Qloo has that data.

## What it does
Paste a script and pick the rooms: an age band, optionally men or women, a city or country, and optionally a Qloo audience segment such as gamers or new parents. Will It Land marks every cultural reference like a spellchecker, separately for each room: a solid underline lands, dotted is risky, wavy will likely miss, dashed is not in Qloo. Each room gets a headline ("Under 25s in London: 3 of 7 will likely miss") and the page names the biggest split: the same reference scoring very differently in two rooms.

One click, "Make it land in both rooms", runs the agent. For each weak reference it gathers stand-ins from Qloo's taste graph and from the language model, scores every candidate in every room, picks the one whose weakest room scores best, rewrites the line and re-scores the whole script. It keeps the rewrite only if no room gets worse. The result appears as document-style suggestions inside each line, with the part each reference plays ("a dead video-rental chain") and where each stand-in came from. It says plainly that the score measures recognition, not whether the line is funny.

Up to six rooms fit in a grid with a "lands everywhere" column. Every mark opens an evidence card: the score, its parts (how well known, fit with the age band, strength in the place), the age profile, and the same reference in every other room. "Under the hood" lists every request behind a result. Any result can be shared as a link. It is also an MCP server with five tools (check_references, check_matrix, localise, localise_for_all, audience_options), so a writing agent can check its own references before it finishes a draft.

## Who uses it, and when
| who | when |
|---|---|
| touring comic | before each date, for that city |
| ad and localisation teams | before each market signs off a script |
| speechwriter or best man | once, before the day |
| a writing agent, through MCP | on every draft, automatically |

## How I built it
Python and FastAPI on the server, React, Vite and Tailwind in the browser, hosted on Modal with one warm container and a persistent cache. The language steps (finding references, naming each one's part in the line, choosing between entities with the same name, rewriting lines) use Claude through an adapter that can switch to Gemini, because the value is in the data, not the model.

Qloo calls:
- /search resolves each reference to an entity and gives its popularity.
- /v2/insights with urn:demographics gives how much each age band and gender over-indexes on it.
- /v2/insights with filter.results.entities and signal.location.query ranks the references in each place against eight fixed anchor entities, so place scores compare across calls.
- /v2/insights with urn:tag gives the tags that characterise a weak reference.
- /v2/insights with those tags plus the room's age and place finds stand-ins the room over-indexes on.
- /v2/audiences lists Qloo audience segments; /v2/insights with signal.demographics.audiences ranks the references for a chosen segment, against the same anchors as place.
- /v2/trending gives a six-month direction, shown on the card and never scored.

The score is a small logistic model in server/scoring.py.

## From request to result (one reference)
1. The model reads "My mum's idea of a wild Friday is a Blockbuster card she never returned" and returns the reference "Blockbuster", type brand, part "a dead video-rental chain".
2. /search with query Blockbuster and type brand returns the entity and its popularity; if several entities share the name, the model picks one from the line.
3. /v2/insights with urn:demographics and that entity returns the over- or under-indexing of each age band.
4. For the room "under 25, London", /v2/insights ranks the brand references in London against eight anchor brands.
5. The score combines popularity with the age band and place terms; the evidence card shows each part.
6. If the reference is weak in any room, stand-ins are gathered and each is scored in every room the same way.
Only reference names and room settings are sent to Qloo, never the script.

## How I test it
The method was fixed in eval/PREREG.md before any real data arrived, and results are published whatever they say. It compares the Qloo-grounded score with a language model's unaided guess against outside ground truth: YouGov's share of each US generation who have heard of about 300 shows, films, artists, brands, people and podcasts; an anonymous survey of what under-25s recognise (YouGov has no under-25 figures); and a check that place separates 20 regional brands and shows at home and far away. Results: not measured yet. Until then the score runs on starting weights set by hand, and the app says so.

## Known limitations
- The score is an estimate for a group, never a statement about one person, and it does not judge whether a joke is funny.
- Until the tests above run, the weights are set by hand and are not calibrated. The audience-segment weight is set by hand and is not covered by the tests.
- The YouGov test covers US adults in three generations, roughly 30 and over; under-25s are covered only by the survey.
- References Qloo has no entity for (slang, memes, very local things) are marked "not in Qloo" and not scored.
- A stand-in can be well known in every room and still break the joke; the writer decides.

## Challenges
Affinity is not awareness: Qloo says how much an audience over-indexes on something, not how many people have heard of it, so the score combines popularity with affinity and is tested against "heard of" data. Popularity is a percentile over a very large catalogue, so almost anything a writer names sits near the top; a linear score called every famous but dated reference a hit, so the score uses a log transform. Names are ambiguous ("Friends", "Manhattan"), so the agent reads the line to pick the entity and shows the alternatives. Qloo ignores parameters it does not accept, so the client sends only documented ones and a probe checks every field the code reads.

## Accomplishments
One rewrite that works in every room at once, with every stand-in scored in every room. A public, pre-registered test plan against outside ground truth. Every request behind a result is listed in the app; the weights that combine them are set by hand until the tests run, and the app says so.

## What I learned
A taste graph can tell you which stand-in a specific room is more likely to know and like, which a model alone cannot check.

## What's next
A printable localisation report for teams shipping one script to many markets, and a browser extension for documents and scripts.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, gemini, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
