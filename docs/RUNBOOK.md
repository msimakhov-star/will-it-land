# Runbook: the day the Qloo key arrives

Keys come by email from Qloo (check spam). Then, in order:

```bash
cd ~/will-it-land
export QLOO_API_KEY=...    # never commit, never paste into chat

# 1. does it work at all
.venv/bin/python -c "from server import qloo; print(qloo.search('Seinfeld', ['tv_show'], 3))"
.venv/bin/python -c "from server import qloo; print(qloo.demographics([qloo.search('Seinfeld', ['tv_show'], 1)[0]['entity_id']]))"

# 2. kill test (LLM baseline is already cached in eval/out/llm_guesses.json)
.venv/bin/python -m eval.kill_test --n 300
#    -> paste eval/out/kill_test.md into README.md and docs/DEVPOST.md, whatever it says.
#    If Qloo does not beat the LLM on the millennial-minus-boomer gap, re-fit land_score weights
#    (eval/fit.py, to write) before deciding; if it still loses, say so in the README and keep going.

# 3. real end-to-end run on the three examples, read every score and swap for sanity
set -a; . ~/horizon/.env; set +a; LLM_PROVIDER=anthropic .venv/bin/uvicorn server.main:app --port 8000
.venv/bin/python /private/tmp/claude-501/time_phases.py   # or the three examples through the UI

# 4. deploy for real
python3.12 -m modal secret create qloo QLOO_API_KEY="$QLOO_API_KEY" --force     # drops QLOO_MOCK
cd web && npm run build && cd .. && python3.12 -m modal deploy server/modal_app.py
curl https://m-simakhov--will-it-land-web.us-east.modal.run/api/health   # qloo_key must be true

# 5. screenshots for Devpost (judges may score from text and images alone)
```

Deadline: Fri 30 Oct 2026 23:45 EDT. Submit Thursday 29 Oct on https://qloo.devpost.com (Mike's Devpost login; draft #1248003 exists).
Keep the Modal app up through judging (ends 16 Nov) and the live final on 5 Nov.
