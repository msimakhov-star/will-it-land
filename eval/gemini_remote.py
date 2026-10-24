"""Run Gemini calls from a US-hosted Modal container (the Gemini API refuses some client locations).
Used by eval/taste_audit.py and tools/prose.py as a fallback: modal run eval/gemini_remote.py --prompts-file X --out Y"""
import json

import modal

app = modal.App("will-it-land-gemini")
image = modal.Image.debian_slim(python_version="3.12").pip_install("google-genai>=1.0")


@app.function(image=image, secrets=[modal.Secret.from_name("gemini")], region="us-east", timeout=600)
def generate(prompts: list[dict], model: str) -> list[dict]:
    import os
    from concurrent.futures import ThreadPoolExecutor

    from google import genai
    from google.genai import types

    c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def one(p):
        try:
            cfg = types.GenerateContentConfig(system_instruction=p.get("system"), temperature=p.get("temperature", 0.7)) if p.get("system") else None
            r = c.models.generate_content(model=model, contents=p["prompt"], config=cfg)
            return {**p, "text": (r.text or "").strip()}
        except Exception as ex:
            return {**p, "error": str(ex)[:300]}

    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(one, prompts))


@app.local_entrypoint()
def main(prompts_file: str, out: str, model: str = "gemini-3.5-flash"):
    prompts = json.load(open(prompts_file))
    res = generate.remote(prompts, model)
    json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"{sum(1 for r in res if r.get('text'))}/{len(res)} ok -> {out}")
