# Will It Land

## Tagline
Spellcheck for cultural references: it checks every reference in your script against the room you are actually playing using Qloo, and swaps the ones that will not land.

## Inspiration
Ask a language model for a joke, an ad line or a wedding toast. The references come out average. The model suggests the same handful of shows, artists and brands for every audience. Writers never perform for the average room. A comedian plays 22-year-olds in one city on Friday and a dinner of 55-year-olds in another on Monday. An ad team ships one script to several markets. A best man gets one audience and one shot. None of them has data at their desk on which references a specific audience actually over-indexes on. They do not know which stand-in plays the same part for that audience. Qloo has that data.

## What it does
Paste a script and pick the rooms. A room is an age band, optionally men or women, and a city or country. Will It Land marks every cultural reference like a spellchecker for each room. Red wavy lines mean likely misses. Amber dotted lines mean risky. Green means the reference lands. Each room gets a headline. 

You click "Make it land in both rooms" to run the agent. For each weak reference, the agent gathers stand-ins from the Qloo graph and the language model. It scores every candidate in every room with Qloo. It picks the candidate whose worst room scores best. The agent rewrites the line and re-scores the whole script. It keeps the rewrite only if the rooms improved. Each change appears as a tracked change with a badge. The badge shows where the stand-in came from. 

Up to six rooms fit in a grid with a "lands everywhere" column. Every mark opens an evidence card. The card shows the score and its breakdown: how widely known, this age band, and this place. It shows the age profile from Qloo and what a language model guessed without data. An "Under the hood" section lists every Qloo request behind the result. Will It Land is also an MCP server. A writing agent can check its own references before it finishes a draft.

## How I built it
The server uses Python and FastAPI. The browser uses React, Vite and Tailwind. Modal hosts the app with one warm container and a persistent cache. The agent uses Claude for language steps: finding references, naming each role, choosing between entities with the same name, and rewriting lines. An adapter can switch Claude to Gemini. 

The Qloo side uses several endpoints. It uses /search to resolve names. It uses /v2/insights with demographics for age and gender affinity. It uses /v2/insights to rank each room's references in a place against eight fixed anchors. It uses /v2/insights with tags for the tags that define a reference. It uses /v2/insights with tags plus the room's demographics and place to find stand-ins the room over-indexes on. It uses /v2/trending for direction. The app shows trending direction but does not score it. 

The score is a small logistic model in server/scoring.py. The MCP server uses the official Python SDK over stdio and streamable HTTP.

## How I test it
The test method was fixed in eval/PREREG.md before any real data arrived. The test compares the Qloo-grounded score with a language model's unaided guess against outside ground truth. The ground truth includes YouGov's share of each US generation who have heard of about 300 shows, films, artists, brands, people and podcasts. It includes an anonymous survey of what under-25s recognise, because YouGov has no under-25 figures. It also includes a check that place separates 20 regional brands and shows at home and far away. Results: not measured yet.

## Challenges
Affinity is not awareness. Qloo says how much an audience over-indexes on something, not how many people have heard of it. The score combines popularity with the room's affinity. The app tests this score against "heard of" data. Popularity is a percentile over a very large catalogue. Almost anything a writer names sits near the top. A linear score called every famous but dated reference a hit. The score uses a log transform instead. 

Names are ambiguous, like "Friends" or "Manhattan". The agent reads the line to pick the entity and shows the alternatives. Qloo silently ignores parameters it does not accept. The client only sends documented parameters. A probe checks every field the code reads.

## Accomplishments
The agent finds one fix that lands in every room at once. Qloo scores this fix in every room. The project has a public, pre-registered test plan with ground truth no other entry uses. The demo shows its own evidence. Every number traces to a Qloo request.

## What I learned
Grounding is not a garnish. The interesting part of a reference check is the stand-in. Only a taste graph can say which stand-in a specific room actually loves.

## What's next
Next steps include a browser extension for documents and scripts. The project will add a localisation report for teams shipping one script to many markets. It will also add rooms defined by Qloo audiences, for example "nurses in Chicago", instead of only age and place.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, gemini, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
