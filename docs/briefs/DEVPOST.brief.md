# Will It Land

## Tagline
Spellcheck for cultural references: it scores every reference in your script for the room you are playing, using Qloo, and swaps the weak ones.

## Inspiration
Ask a language model for a joke, an ad line or a wedding toast and the references come out average: the same handful of shows, artists and brands, whoever the audience is. Writers never perform for the average room. A comedian plays 22-year-olds in one city on Friday and a dinner of 55-year-olds in another on Monday. An ad team ships one script to several markets. A best man gets one audience and one shot. What none of them has at their desk is data on which references a specific audience actually over-indexes on, and which stand-in would play the same part for them. Qloo has that data.

## What it does
Paste a script and pick the rooms: an age band, optionally men or women, a city or country. Will It Land marks every cultural reference like a spellchecker for each room (red wavy: likely misses, amber dotted: risky, green: lands) with a headline per room. One click, "Make it land in both rooms", runs the agent: for each weak reference it gathers stand-ins from Qloo's graph and from the model, scores every candidate in every room with Qloo, picks the one whose worst room scores best, rewrites the line, re-scores the whole script, and keeps the rewrite only if the rooms improved. Each change shows as a tracked change with a badge saying where the stand-in came from. Up to six rooms fit in a grid with a "lands everywhere" column; one example takes a touring comic's opener to six cities. Every mark opens an evidence card: the score, its breakdown (how widely known, this age band, this place), the age profile from Qloo, and what a language model guessed without data. "Under the hood" lists every Qloo request behind the result. It is also an MCP server (check_references, check_matrix, localise, localise_for_all, audience_options), so a writing agent can check its own references before it finishes a draft. The script goes to the language model; only reference names and room settings go to Qloo.

## How I built it
Python and FastAPI on the server, React, Vite and Tailwind in the browser, hosted on Modal with one warm container and a persistent cache. The agent's language steps (finding references, naming each one's role, choosing between entities with the same name, rewriting lines) use Claude through an adapter that can switch to Gemini, because the moat is the data, not the model. The Qloo side: /search to resolve names, /v2/insights with demographics for age and gender affinity, /v2/insights ranking each room's references in a place against eight fixed anchors, /v2/insights with tags for the tags that define a reference, /v2/insights with tags plus the room's demographics and place to find stand-ins the room over-indexes on, and /v2/trending for direction (shown, not scored). The score is a small logistic model in server/scoring.py. The MCP server uses the official Python SDK over stdio and streamable HTTP.

## How I test it
I did not want to assert that Qloo makes the difference, so the method was fixed in eval/PREREG.md before any real data arrived. It compares the Qloo-grounded score with a language model's unaided guess against outside ground truth: YouGov's share of each US generation who have heard of about 300 shows, films, artists, brands, people and podcasts; an anonymous survey of what under-25s recognise (YouGov has no under-25 figures); and a check that place separates 20 regional brands and shows at home and far away. Results: not measured yet. Until then the score runs on hand-set starting values, not calibrated against any data, and the app says so.

## Challenges
Affinity is not awareness: Qloo says how much an audience over-indexes on something, not how many people have heard of it, so the score combines popularity with the room's affinity and is tested against "heard of" data. Popularity is a percentile over a very large catalogue, so almost anything a writer names sits near the top, and a linear score called every famous but dated reference a hit; the score uses a log transform instead. Names are ambiguous ("Friends", "Manhattan"), so the agent reads the line to pick the entity and shows the alternatives. Qloo silently ignores parameters it does not accept, so the client only sends documented ones and a probe checks every field the code reads.

## Accomplishments
One fix that lands in every room at once, scored in every room by Qloo. A public, pre-registered test plan against outside ground truth. A demo that shows its own evidence: every number traces to a Qloo request.

## What I learned
Grounding is not a garnish. The interesting part of a reference check is the stand-in, and only a taste graph can say which stand-in a specific room actually loves.

## What's next
A browser extension for documents and scripts, a localisation report for teams shipping one script to many markets, and rooms defined by Qloo audiences (for example "nurses in Chicago") instead of only age and place.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, gemini, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
