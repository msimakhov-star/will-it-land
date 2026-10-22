"""Deploy: modal deploy server/modal_app.py
Secrets (create once): modal secret create qloo QLOO_API_KEY=... ; modal secret create llm ANTHROPIC_API_KEY=...
The Qloo cache lives on a Volume so judges hammering the demo do not burn quota."""
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi>=0.115", "httpx>=0.27", "anthropic>=0.40", "google-genai>=1.0", "mcp>=1.2", "pydantic>=2.7")
    .add_local_dir("server", remote_path="/root/server")
    .add_local_dir("web/dist", remote_path="/root/web/dist")
)
app = modal.App("will-it-land", image=image)
vol = modal.Volume.from_name("will-it-land-cache", create_if_missing=True)


@app.function(
    secrets=[modal.Secret.from_name("qloo"), modal.Secret.from_name("llm")],
    volumes={"/cache": vol},
    min_containers=1,
    timeout=300,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    import os
    import sys

    os.environ.setdefault("QLOO_CACHE", "/cache/qloo.sqlite")
    sys.path.insert(0, "/root")
    from server.main import app as fastapi_app

    return fastapi_app
