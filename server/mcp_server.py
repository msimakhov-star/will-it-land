"""MCP server so other writing agents can call Will It Land.
stdio:  python -m server.mcp_server
HTTP:   mounted at /mcp by server.main (streamable HTTP)."""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import pipeline

mcp = FastMCP("will-it-land", instructions="Check whether the cultural references in a text will land with a target audience, using Qloo taste data. Call check_references before you finish writing jokes, ads, speeches or localised copy.")


@mcp.tool()
def check_references(text: str, age: str | None = None, gender: str | None = None, location: str | None = None, propose_swaps: bool = True) -> str:
    """Find every cultural reference (shows, films, artists, brands, people, books, games, podcasts, places) in `text`,
    score how likely each is to land with the audience (0-100, grounded in Qloo popularity, age/gender and location
    affinity), and for weak ones return stand-ins that play the same role plus a rewritten line.
    age: one of 24_and_younger, 25_to_29, 30_to_34, 35_to_44, 45_to_54, 55_and_older. gender: male|female. location: a city, region or country."""
    out = pipeline.check(text, pipeline.Audience(age, gender, location), swaps=propose_swaps)
    return json.dumps(out)


@mcp.tool()
def audience_options() -> str:
    """The audience values check_references accepts."""
    return json.dumps({"ages": pipeline.AUDIENCE_AGES, "genders": ["male", "female"], "location": "free text, e.g. London or Texas"})


if __name__ == "__main__":
    mcp.run()
