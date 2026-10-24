"""Deploy: modal deploy server/modal_app.py
Secrets (create once): modal secret create qloo QLOO_API_KEY=... ; modal secret create llm ANTHROPIC_API_KEY=...
The Qloo cache lives on a Volume so judges hammering the demo do not burn quota."""
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi==0.159.1", "uvicorn", "httpx==0.28.1", "httpx2==2.16.0", "anthropic==2.1.0", "google-genai==2.32.0", "mcp==2.3.0", "pydantic==2.14.1", "modal")
    .add_local_dir("server", remote_path="/root/server")
    .add_local_dir("web/dist", remote_path="/root/web/dist")
    .add_local_file("eval/data/survey_items.json", remote_path="/root/eval/data/survey_items.json")
    .add_local_dir("eval/out", remote_path="/root/eval/out")  # measured numbers for /api/proof (no Qloo payloads)
)
app = modal.App("will-it-land", image=image)
vol = modal.Volume.from_name("will-it-land-cache", create_if_missing=True)


@app.function(
    secrets=[modal.Secret.from_name("qloo"), modal.Secret.from_name("llm"), modal.Secret.from_name("survey")],
    volumes={"/cache": vol},
    min_containers=1,
    max_containers=1,  # one sqlite writer on the Volume, and a hard ceiling on LLM spend
    timeout=300,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    import os
    import sys

    os.environ.setdefault("QLOO_CACHE", "/cache/qloo.sqlite")
    os.environ.setdefault("WIL_VOLUME", "will-it-land-cache")
    os.environ.setdefault("WIL_VOLUME", "will-it-land-cache")
    sys.path.insert(0, "/root")
    from server.main import app as fastapi_app

    return fastapi_app
