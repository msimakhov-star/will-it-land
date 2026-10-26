"""Capture the Devpost gallery from a running deploy with playwright-cli: 6 desktop images at 1600x1000 + 1 mobile.

Run: python -m tools.screenshots --base https://m-simakhov--will-it-land-web.us-east.modal.run
Writes docs/screenshots/01-two-rooms.png ... 07-mobile.png. Each image's caption (the Qloo calls behind it) is in
docs/screenshots/CAPTIONS.md.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import time

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
S = "-s=gallery"


def cli(*args: str) -> str:
    return subprocess.run(["playwright-cli", S, *args], capture_output=True, text=True, timeout=180, cwd="/private/tmp/claude-501").stdout


def js(expr: str) -> str:
    return cli("eval", expr)


def wait_for(expr: str, timeout: float = 120) -> bool:
    t = time.time()
    while time.time() - t < timeout:
        if re.search(r"^true$", js(expr), re.M):
            return True
        time.sleep(2)
    return False


def shot(name: str) -> None:
    out = cli("screenshot")
    m = re.findall(r"(\.playwright-cli/[^ )\n]+\.png)", out)
    if m:
        shutil.copy(os.path.join("/private/tmp/claude-501", m[-1]), os.path.join(OUT, name))
        print("saved", name)
    else:
        print("screenshot failed", name, out[-300:])


def click_text(prefix: str) -> None:
    js(f"[...document.querySelectorAll('button')].find(b => b.innerText.trim().startsWith({prefix!r}))?.click()")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    cli("open", a.base)
    cli("resize", "1600", "1000")
    idle = "document.querySelectorAll('[data-ref]').length > 0 && !document.body.innerText.includes('Re-checking') && !document.body.innerText.includes('Reading your script')"
    wait_for(idle)
    time.sleep(3)  # let the one-off pointer to the biggest split finish
    shot("01-two-rooms.png")
    js("[...document.querySelectorAll('[role=button].mark-misses, [role=button].mark-risky')][0]?.click()")
    time.sleep(1.5)
    shot("04-evidence.png")
    js("document.querySelector('aside button[aria-label=\"Close evidence\"]')?.click()")
    click_text("Make it land")
    wait_for("document.body.innerText.includes('Keep this version') || document.body.innerText.includes('No rewrite beat')", 180)
    time.sleep(1.5)
    shot("02-land-in-both-rooms.png")
    click_text("Touring comic")
    wait_for("document.body.innerText.includes('Lands everywhere') && " + idle)
    time.sleep(1)
    shot("03-six-cities.png")
    click_text("Best man")
    wait_for("document.body.innerText.includes('Grandparents') && " + idle)
    time.sleep(3)
    shot("08-two-tables.png")
    click_text("Can you trust")
    time.sleep(1.5)
    shot("05-how-we-know.png")
    js("document.querySelector('dialog button[aria-label=Close]')?.click()")
    click_text("Use it from your AI agent")
    time.sleep(1)
    shot("06-mcp.png")
    js("document.querySelector('dialog button[aria-label=Close]')?.click()")
    cli("resize", "390", "844")
    click_text("Comedian")
    wait_for(idle)
    time.sleep(3)
    shot("07-mobile.png")
    cli("close")


if __name__ == "__main__":
    main()
