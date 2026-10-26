# Will It Land

## Tagline
Spellcheck for cultural references. It shows which references in a script will land with a specific room. It swaps weak references for stand-ins that work in every room.

## Status
Until the hackathon Qloo key arrives, the live app runs on clearly labelled demo data. The numbers on screen are placeholders. The pipeline, the requests it makes and the interface are the real product. (Replace this paragraph with "Runs on live Qloo data" once true.)

## Inspiration
Writers never perform for the average room. A touring comic plays 25-year-olds in Leeds on Friday and in Atlanta on Monday. An ad team ships one script into six markets. A best man speaks to two tables: his friends and the grandparents. Each writer checks references by gut or asks a language model. Language models tend to reach for the same handful of shows, artists and brands for any audience. Writers lack data on which references a specific audience knows and likes. They also lack data on which stand-in would play the same part for that audience. Qloo has this data.

## What it does
Paste a script and pick the rooms. A room includes an age band, optionally men or women, a city or country, and optionally a Qloo audience segment such as gamers or new parents. Will It Land marks every cultural reference like a spellchecker, separately for each room. A solid underline means the reference lands. A dotted underline means it is risky. A wavy underline means it will likely miss. A dashed underline means it is not in Qloo. Each room gets a headline ("Under 25s in London: 3 of 7 will likely miss"). The page names the biggest split. A split is the same reference scoring very differently in two rooms.

One click on "Make it land in both rooms" runs the agent. The agent gathers stand-ins from the Qloo taste graph and from the language model for each weak reference. It scores every candidate in every room. It picks the candidate whose weakest room scores best. It rewrites the line and re-scores the whole script. It keeps the rewrite only if no room gets worse. The result appears as document-style suggestions inside each line. These suggestions show the part each reference plays ("a dead video-rental chain") and where each stand-in came from. The app states plainly that the score measures recognition, not whether the line is funny.

Up to six rooms fit in a grid with a "lands everywhere" column. Every mark opens an evidence card. The card shows the score and its parts: how well known the reference is, its fit with the age band, and its strength in the place. It also shows the age profile and the same reference in every other room. An "Under the hood" section lists every request behind a result. Users can share any result as a link. The app is also an MCP server with five tools (check_references, check_matrix, localise, localise_for_all, audience_options). A writing agent can use these tools to check its own references before it finishes a draft.

## Who uses it, and when
| who | when |
|---|---|
| touring comic | before each date, for that city |
| ad and localisation teams | before each market signs off a script |
| speechwriter or best man | once, before the day |
| a writing agent, through MCP | on every draft, automatically |

## How I built it
The server uses Python and FastAPI. The browser uses React, Vite and Tailwind. Modal hosts the app with one warm container and a persistent cache. The language steps find references, name the part each reference plays in the line, choose between entities with the same name, and rewrite lines. These steps use Claude through an adapter. The adapter can switch to Gemini. The value sits in the data, not the model.

Qloo calls:
- /search resolves each reference to an entity and gives its popularity.
- /v2/insights with urn:demographics gives how much each age band and gender over-indexes on the entity.
- /v2/insights with filter.results.entities and signal.location.query ranks the references in each place against eight fixed anchor entities. This allows place scores to compare across calls.
- /v2/insights with urn:tag gives the tags that characterise a weak reference.
- /v2/insights with those tags plus the room's age and place finds stand-ins the room over-indexes on.
- /v2/audiences lists Qloo audience segments. /v2/insights with signal.demographics.audiences ranks the references for a chosen segment against the same anchors as place.
- /v2/trending gives a six-month direction. The app shows this direction on the card and never scores it.

The score is a small logistic model in server/scoring.py.

## From request to result (one reference)
1. The model reads "My mum's idea of a wild Friday is a Blockbuster card she never returned" and returns the reference "Blockbuster", type brand, part "a dead video-rental chain".
2. /search with query Blockbuster and type brand returns the entity and its popularity. If several entities share the name, the model picks one from the line.
3. /v2/insights with urn:demographics and that entity returns the over-indexing or under-indexing of each age band.
4. For the room "under 25, London", /v2/insights ranks the brand references in London against eight anchor brands.
5. The score combines popularity with the age band and place terms. The evidence card shows each part.
6. If the reference is weak in any room, the agent gathers stand-ins and scores each one in every room the same way.
The app sends only reference names and room settings to Qloo. It never sends the script.

## How I test it
The method was fixed in eval/PREREG.md before any real data arrived. The app publishes results whatever they say. It compares the Qloo-grounded score with a language model's unaided guess against outside ground truth. This ground truth includes YouGov's share of each US generation who have heard of about 300 shows, films, artists, brands, people and podcasts. It includes an anonymous survey of what under-25s recognise, because YouGov has no under-25 figures. It also includes a check that place separates 20 regional brands and shows at home and far away. Results: not measured yet. Until then, the score runs on starting weights set by hand. The app states this clearly.

## Known limitations
- The score is an estimate for a group, never a statement about one person. It does not judge whether a joke is funny.
- Until the tests above run, the weights are set by hand and are not calibrated. The audience-segment weight is set by hand and is not covered by the tests.
- The YouGov test covers US adults in three generations, roughly 30 and over. The survey covers under-25s.
- The app marks references that lack a Qloo entity (slang, memes, very local things) as "not in Qloo" and does not score them.
- A stand-in can be well known in every room and still break the joke. The writer decides.

## Challenges
Affinity is not awareness. Qloo says how much an audience over-indexes on something, not how many people have heard of it. The score combines popularity with affinity and is tested against "heard of" data. Popularity is a percentile over a very large catalogue. Almost anything a writer names sits near the top. A linear score called every famous but dated reference a hit, so the score uses a log transform. Names are ambiguous ("Friends", "Manhattan"). The agent reads the line to pick the entity and shows the alternatives. Qloo ignores parameters it does not accept. The client sends only documented parameters. A probe checks every field the code reads.

## Accomplishments
The app generates one rewrite that works in every room at once. It scores every stand-in in every room. It includes a public, pre-registered test plan against outside ground truth. The app lists every request behind a result. The weights that combine these requests are set by hand until the tests run. The app states this clearly.

## What I learned
A taste graph can show which stand-in a specific room is more likely to know and like. A model alone cannot check this.

## What's next
The next steps include a printable localisation report for teams shipping one script to many markets. They also include a browser extension for documents and scripts.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, gemini, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
