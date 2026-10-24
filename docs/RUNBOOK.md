# Runbook: the day the Qloo key arrives

Keys come by email from Qloo (check spam). Never paste the key into chat, git, or a screenshot.
Deadline: Fri 30 Oct 2026, 23:45 EDT (03:45 Sat UK time). After the deadline the submission cannot change, so a real-data build must be live before then.

## Full path (about 10 hours, any day up to Thursday)

| step | time | command / action | done when |
|---|---|---|---|
| 1 | 0:00 | `export QLOO_API_KEY=...` then `.venv/bin/python -m tools.probe` | "ALL CONTRACT CHECKS PASSED", or each FAIL fixed in `server/qloo.py` parsers (tests still green) |
| 2 | 1:30 | `python3.12 -m modal secret create qloo QLOO_API_KEY="$QLOO_API_KEY" --force` (drops QLOO_MOCK), `cd web && npm run build && cd .. && python3.12 -m modal deploy server/modal_app.py` | `curl .../api/health` shows `"mock": false`, AND a real `POST /api/matrix` on the hosted URL returns live Qloo calls in its ledger |
| 3 | 2:00 | `.venv/bin/python -m eval.kill_test --n 300` then `.venv/bin/python -m eval.fit` | `eval/out/kill_test.md` and `fit_report.json` exist |
| 4 | 4:00 | `.venv/bin/python -m eval.fit --write` only if CV Spearman for `qloo` beats `no_age` (otherwise keep priors and say so) | `server/calibration.json` written, tests green |
| 5 | 4:15 | `.venv/bin/python -m eval.location_sanity` | hit rate known; if under 15 of 20, set `"k_loc": 0` in `server/calibration.json` (the UI hides the place box automatically) |
| 6 | 5:15 | `.venv/bin/python -m eval.split_finder` | pick the hero room pair and, if needed, rewrite `server/examples.py` texts from references that really split (never invent a split) |
| 7 | 7:15 | tune `STANDIN_MIN_POP` (env, default 0.99) so a Qloo-found stand-in beats the original for at least half the weak references in the examples | applied-swap Qloo share measured |
| 8 | 7:45 | redeploy, then `.venv/bin/python -m tools.prewarm --base https://m-simakhov--will-it-land-web.us-east.modal.run` (background, ~10 min) | prewarm log all 200 |
| 9 | 8:00 | `.venv/bin/python -m eval.taste_audit run` (background) and `eval/freshness.py` if the probe showed trending works | numbers saved in `eval/out/` |
| 10 | 8:30 | `.venv/bin/python -m tools.screenshots --base <live url>` | 6 gallery images + 1 mobile in `docs/screenshots/` |
| 11 | 9:00 | Public text: write the factual brief, render with `tools/prose.py` (Gemini, via `eval/gemini_remote.py` if the API refuses this location), check every number against `eval/out/`, no claims about trend in the score, location only if k_loc > 0 | README and docs/DEVPOST.md updated, `tests/test_text.py` green |
| 12 | 10:00 | Devpost: fill the draft (#1248003), upload images, links (live URL, repo), submit | Devpost shows "Submitted" |

## Friday minimum path (about 5 hours)
1 probe and fix, 2 deploy, 3 kill test at `--n 120` and fit (no refit loop), 6 split finder on the existing examples only, 8 prewarm, 10 screenshots, 11 text with the numbers that exist, 12 submit before 20:00 EDT.

## If there is no key by Thursday 18:00 EDT
Submit the complete entry clearly labelled "demo data: Qloo key pending", keep chasing the key, and update before the deadline. A demo running on fake data cannot be presented as using Qloo.

## After submitting
No code deploys. Keep the Modal app up (min 1 container) through judging (ends 16 Nov) and the live final on 5 Nov. Re-run the prewarm the day before the final.
