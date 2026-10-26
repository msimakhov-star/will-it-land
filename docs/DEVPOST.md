# Will It Land

## Tagline
Spellcheck for cultural references. It shows which references in your script will land with the room you are playing. It swaps weak references for stand-ins that work in every room.

## Status
Until the hackathon Qloo key arrives, the live app runs on clearly labelled demo data. The numbers on screen are placeholders. The pipeline, the requests it makes and the interface are the real product. (Replace this paragraph with "Runs on live Qloo data" once true.)

## Inspiration
Writers never perform for the average room. A touring comic plays 25-year-olds in Leeds on Friday and in Atlanta on Monday. An ad team ships one script into six markets. A best man speaks to two tables: his friends and the grandparents. Each of them checks references by gut, or asks a language model. Language models tend to reach for the same handful of shows, artists and brands whatever the audience. None of them has data on which references a specific audience knows and likes. They also lack data on which stand-in would play the same part for them. Qloo has that data.

## What it does
Paste a script and pick the rooms. A room is an age band, optionally men or women, and a city or country. Will It Land marks every cultural reference like a spellchecker, separately for each room. A solid underline lands, a dotted underline is risky, a wavy underline will likely miss, and a dashed underline is not in Qloo. Each room gets a headline ("Under 25s in London: 3 of 7 will likely miss"). The page names the biggest split. This is the same reference scoring very differently in two rooms.

One click, "Make it land in both rooms", runs the agent. For each weak reference, it gathers stand-ins from Qloo's taste graph and from the language model. It scores every candidate in every room. It picks the one whose weakest room scores best. It rewrites the line and re-scores the whole script. It keeps the rewrite only if no room gets worse. The result appears as document-style suggestions inside each line. It shows the part each reference plays ("a dead video-rental chain") and where each stand-in came from. It states plainly that the score measures recognition, not whether the line is funny.

Up to six rooms fit in a grid with a "lands everywhere" column. Every mark opens an evidence card. The card shows the score, its parts (how well known, fit with the age band, strength in the place), the age profile, and the same reference in every other room. "Under the hood" lists every request behind a result. Any result can be shared as a link. It is also an MCP server with five tools (check_references, check_matrix, localise, localise_for_all, audience_options). A writing agent can check its own references before it finishes a draft.

## Who uses it, and when
| who | when |
|---|---|
| touring comic | before each date, for that city |
| ad and localisation teams | before each market signs off a script |
| speechwriter or best man | once, before the day |
| a writing agent, through MCP | on every draft, automatically |

## How I built it
The server uses Python and FastAPI. The browser uses React, Vite and Tailwind. Modal hosts the app with one warm container and a persistent cache. The language steps find references, name each one's part in the line, choose between entities with the same name, and rewrite lines. These steps use Claude through an adapter that can switch to Gemini. The value is in the data, not the model.

Qloo calls:
- /search resolves each reference to an entity and gives its popularity.
- /v2/insights with urn:demographics gives how much each age band and gender over-indexes on it.
- /v2/insights with filter.results.entities and signal.location.query ranks the references in each place against eight fixed anchor entities. Place scores compare across calls.
- /v2/insights with urn:tag gives the tags that characterise a weak reference.
- /v2/insights with those tags plus the room's age and place finds stand-ins the room over-indexes on.
- /v2/trending gives a six-month direction. The card shows this direction, and the app never scores it.

The score is a small logistic model in server/scoring.py.

## From request to result (one reference)
1. The model reads "My mum's idea of a wild Friday is a Blockbuster card she never returned". It returns the reference "Blockbuster", type brand, part "a dead video-rental chain".
2. /search with query Blockbuster and type brand returns the entity and its popularity. If several entities share the name, the model picks one from the line.
3. /v2/insights with urn:demographics and that entity returns the over-indexing or under-indexing of each age band.
4. For the room "under 25, London", /v2/insights ranks the brand references in London against eight anchor brands.
5. The score combines popularity with the age band and place terms. The evidence card shows each part.
6. If the reference is weak in any room, the app gathers stand-ins and scores each one in every room the same way.
Only reference names and room settings go to Qloo. The script never goes to Qloo.

## How I test it
The method was fixed in eval/PREREG.md before any real data arrived. Results are published whatever they say. It compares the Qloo-grounded score with a language model's unaided guess against outside ground truth. The ground truth includes YouGov's share of each US generation who have heard of about 300 shows, films, artists, brands, people and podcasts. It includes an anonymous survey of what under-25s recognise. YouGov has no under-25 figures. It includes a check that place separates 20 regional brands and shows at home and far away. Results: not measured yet. Until then, the score runs on starting weights set by hand. The app says so.

## Known limitations
- The score is an estimate for a group, never a statement about one person. It does not judge whether a joke is funny.
- Until the tests above run, the weights are set by hand and are not calibrated.
- The YouGov test covers US adults in three generations, roughly 30 and over. Under-25s are covered only by the survey.
- References Qloo has no entity for (slang, memes, very local things) are marked "not in Qloo" and not scored.
- A stand-in can be well known in every room and still break the joke. The writer decides.

## Challenges
Affinity is not awareness. Qloo says how much an audience over-indexes on something, not how many people have heard of it. The score combines popularity with affinity and is tested against "heard of" data. Popularity is a percentile over a very large catalogue. Almost anything a writer names sits near the top. A linear score called every famous but dated reference a hit, so the score uses a log transform. Names are ambiguous ("Friends", "Manhattan"). The agent reads the line to pick the entity and shows the alternatives. Qloo ignores parameters it does not accept. The client sends only documented parameters, and a probe checks every field the code reads.

## Accomplishments
One rewrite works in every room at once. Every stand-in is scored in every room. A public, pre-registered test plan runs against outside ground truth. Every request behind a result is listed in the app. The weights that combine them are set by hand until the tests run, and the app says so.

## What I learned
A taste graph can tell you which stand-in a specific room is more likely to know and like. A model alone cannot check this.

## What's next
Rooms defined by Qloo audiences (for example "nurses in Chicago") as well as age and place. A printable localisation report for teams shipping one script to many markets. A browser extension for documents and scripts.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, gemini, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
