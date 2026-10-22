"""One LLM entry point. Provider picked by env: ANTHROPIC_API_KEY (default) or GEMINI_API_KEY.

complete(system, user) -> str. complete_json(...) -> parsed JSON (dict or list).
The app is model-agnostic on purpose: Qloo is the moat, not the model.
"""
from __future__ import annotations

import json
import os
import re

PROVIDER = os.environ.get("LLM_PROVIDER") or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "gemini")
MODEL = os.environ.get("LLM_MODEL") or {"anthropic": "claude-sonnet-5-5", "gemini": "gemini-3.5-flash"}[PROVIDER]
FAST_MODEL = os.environ.get("LLM_FAST_MODEL") or {"anthropic": "claude-haiku-5-5", "gemini": "gemini-3.5-flash-lite"}[PROVIDER]

_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic

        import httpx2  # the anthropic SDK (2.x) ships its own httpx fork

        # trust_env=False: macOS proxy auto-discovery inside httpx was measured at up to 80 s on first use
        _client = anthropic.Anthropic(timeout=45.0, max_retries=2, http_client=httpx2.Client(trust_env=False, timeout=45.0))
    return _client


def _gemini():
    global _client
    if _client is None:
        from google import genai

        os.environ.setdefault("no_proxy", "localhost,127.0.0.1")  # same macOS proxy-discovery stall, see _anthropic
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def complete(system: str, user: str, max_tokens: int = 4000, temperature: float = 0.2, fast: bool = False) -> str:
    model = FAST_MODEL if fast else MODEL
    if PROVIDER == "anthropic":
        import time

        t = time.time()
        msg = _anthropic().messages.create(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
        print(f"llm {model} {time.time() - t:.1f}s in={msg.usage.input_tokens} out={msg.usage.output_tokens} stop={msg.stop_reason}", flush=True)
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    from google.genai import types

    r = _gemini().models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=system, temperature=temperature, max_output_tokens=max_tokens),
    )
    return r.text or ""


def warm() -> None:
    """Build the client and make one tiny call on the main thread at startup. The first call from a
    server worker thread was measured at 35 to 70 s on macOS; after a warm-up every call is 2 to 8 s."""
    try:
        complete("Reply with the word ok.", "ok", max_tokens=5, fast=True)
    except Exception as ex:  # no key, no network: the first real request will report it properly
        print("llm warm-up skipped:", ex, flush=True)


def complete_json(system: str, user: str, max_tokens: int = 4000, fast: bool = False):
    text = complete(system + "\nReply with JSON only, no prose, no code fences.", user, max_tokens=max_tokens, temperature=0, fast=fast)
    return parse_json(text)


def parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
        end = max(text.rfind("}"), text.rfind("]")) + 1
        return json.loads(text[start:end])


if __name__ == "__main__":
    out = complete_json("You extract numbers.", 'Return {"n": 2+2}.')
    assert out == {"n": 4}, out
    print("ok", PROVIDER, MODEL)
