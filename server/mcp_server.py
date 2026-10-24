"""MCP server so other writing agents can call Will It Land.
stdio:  python -m server.mcp_server
HTTP:   mounted at /mcp by server.main (streamable HTTP, stateless)."""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    "will-it-land",
    instructions=(
        "Checks whether the cultural references in a text will land with a target audience, grounded in Qloo taste data. "
        "Call check_references before you finish jokes, ads, speeches or localised copy; call check_matrix when one text ships "
        "to several audiences; call localise to get a version rewritten for one audience."
    ),
)

AGES = "one of 24_and_younger, 25_to_29, 30_to_34, 35_to_44, 45_to_54, 55_and_older"


def _aud(d: dict | None):
    from . import pipeline

    d = d or {}
    return pipeline.Audience(d.get("age"), d.get("gender"), d.get("location"), d.get("name"))


@mcp.tool()
def check_references(text: str, age: str | None = None, gender: str | None = None, location: str | None = None, propose_swaps: bool = True) -> str:
    """Find every cultural reference (shows, films, artists, brands, people, books, games, podcasts, places) in `text`,
    score how likely each is to land with the audience (0-100, grounded in Qloo popularity, age/gender and location
    affinity), and for weak ones return stand-ins that play the same role (some found by Qloo itself) plus a rewritten line.
    age: """ + AGES + """. gender: male|female. location: a city, region or country."""
    from . import pipeline

    return json.dumps(pipeline.check(text, pipeline.Audience(age, gender, location), swaps=propose_swaps))


@mcp.tool()
def check_matrix(text: str, audiences: list[dict]) -> str:
    """Score every reference in `text` against several audiences at once (up to 8). Each audience is
    {"name"?: str, "age"?: str, "gender"?: "male"|"female", "location"?: str}. Returns references, one score cell per
    reference x audience, and a summary per audience."""
    from . import pipeline

    return json.dumps(pipeline.matrix(text, [_aud(a) for a in audiences[:8]]))


@mcp.tool()
def localise(text: str, age: str | None = None, gender: str | None = None, location: str | None = None) -> str:
    """Rewrite `text` for one audience: check, swap the references that miss for Qloo-scored stand-ins that play the same
    role, re-check, and stop when it lands or stops improving. Returns the new text, before/after summaries and each step."""
    from . import pipeline

    return json.dumps(pipeline.localise(text, pipeline.Audience(age, gender, location)))


@mcp.tool()
def audience_options() -> str:
    """The audience values the other tools accept, plus ready-made presets."""
    from . import pipeline
    from .examples import PRESETS

    return json.dumps({"ages": pipeline.AUDIENCE_AGES, "genders": ["male", "female"], "location": "free text, e.g. London or Texas", "presets": PRESETS})


def http_app():
    from mcp.server.transport_security import TransportSecuritySettings

    return mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


if __name__ == "__main__":
    mcp.run()
