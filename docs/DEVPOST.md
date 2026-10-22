# Devpost submission text (draft, update numbers after the kill test)

## Project name
Will It Land

## Tagline
AI writes for the average audience. Will It Land checks every cultural reference in your script against the one you are actually writing for.

## Inspiration
Ask a language model for a joke, an ad line or a wedding toast and the references come out average: Seinfeld, Taylor Swift, Minecraft. Models regress to the mean of their training data. Writers do not get to write for the mean. A comedian plays a room of 22-year-olds in Leeds on Friday and a corporate dinner of 55-year-olds in Houston on Monday. An ad localisation team ships one script to twelve markets. A best man has one audience and one shot.

What nobody has at their desk is the data: which references a specific audience actually over-indexes on, which are fading, and which stand-in would play the same role for them. Qloo has exactly that data. So we built the reference checker.

## What it does
Paste a stand-up bit, an ad script, a toast, a speech or localised copy. Pick the audience: an age band, optionally men or women, a city or country.

The agent then:
1. finds every cultural reference (shows, films, artists, brands, people, books, games, podcasts, places);
2. resolves each one to an entity in Qloo's taste graph, using the line's context to settle ambiguous names;
3. scores how likely each reference is to land with that audience, 0 to 100, from how widely known it is, how much that audience over- or under-indexes on it, how it plays in that location, and whether it is rising or fading;
4. for weak references, works out the role the reference plays in the line ("a dead video-rental chain", "a luxury brand that signals new money"), proposes stand-ins that play the same role, resolves and ranks them for the audience with Qloo, and rewrites the line;
5. re-scores, and leaves the writer to accept or ignore each swap.

Switch the audience from under-25s in London to 55+ in Texas and watch the highlights change colour. Toggle "AI alone" to see where a model guessing without data disagrees with the Qloo-grounded score.

It is also an MCP server (`check_references`), so Claude, ChatGPT or any writing agent can call it before finishing a draft.

## How we built it
- Python, FastAPI, httpx. Qloo REST called directly against the hackathon host with an on-disk cache.
- The agent brain is model-agnostic (Anthropic or Gemini through one adapter), because the moat is the data, not the model.
- Qloo calls per check: `/search` for resolution, `/v2/insights` with `filter.type=urn:demographics` for age and gender affinity, `/v2/insights` with `signal.location.query` and `filter.results.entities` (one call per entity type with fixed calibration anchors, so scores are comparable), `/v2/trending` for momentum, and `/search` again to resolve the stand-ins the model proposes.
- React, Vite and Tailwind for the UI. Hosted on Modal with a warm container and a persistent cache volume.
- MCP via the official Python SDK, over stdio and streamable HTTP.

## Does it beat an AI guessing? (the kill test)
We did not want to assert that Qloo is essential; we wanted to check. `eval/` scores about 300 TV shows, films, artists, brands, people, books and podcasts two ways: the Qloo-grounded score, and a language model's unaided estimate. Ground truth is YouGov Ratings' "fame" (the share of US adults in each generation who have heard of something), which is public.

[TABLE FROM eval/out/kill_test.md]

## What we learned
- Affinity is not awareness. Qloo tells you how much an audience cares about something relative to average; YouGov tells you how many have heard of it. The score combines the two, and the benchmark is the check on that model.
- Ambiguity is the real work. "Friends", "Chelsea", "Manhattan" each resolve to several entities; the agent has to read the line to pick the right one, and it shows you the alternatives.
- Qloo silently returns an empty result for parameters it does not accept for a given entity type, so the client only ever sends parameters from the entity-type guide.

## What's next
Script-level reports for localisation teams (one upload, twelve markets), a Chrome extension for Google Docs, and routing the "stand-in" step through Qloo's tag graph so stand-ins can come from a different entity type when the role allows it.

## Built with
python, fastapi, react, vite, tailwind, qloo, anthropic, modal, mcp

## Links
- Live app: https://m-simakhov--will-it-land-web.us-east.modal.run
- Code (MIT): https://github.com/msimakhov-star/will-it-land
