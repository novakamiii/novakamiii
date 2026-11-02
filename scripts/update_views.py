#!/usr/bin/env python3
"""Refresh the plain-text view counter.

The README renders a 1px counter pixel (komarev) as the only counting source.
This fetches that same badge, reads the number back, and bakes it into the
views card: it patches the factored sentence in assets/views.svg directly (the
number is an ordinary <text> node, so no rebuild or font step is needed) and
updates "count =" in scripts/content.toml for future local rebuilds.

Stdlib only — the nightly workflow runs this without the build venv.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "views.svg"
TOML = ROOT / "scripts" / "content.toml"


def ordinal(n: int) -> str:
    """Must stay identical to build_assets.ordinal (kept stdlib-only here)."""
    if n % 100 in (11, 12, 13):
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fetch_count() -> int:
    req = urllib.request.Request(
        "https://komarev.com/ghpvc/?username=novakamiii&label=&color=7f6dab",
        headers={"User-Agent": "novakamiii-profile-updater"},
    )
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    matches = re.findall(r">\s*(\d+)\s*</text>", body)
    if not matches:
        sys.exit("fetch: no number in the counter response — check the badge URL")
    counts = {int(m) for m in matches}  # komarev draws the count twice (shadow + face)
    if len(counts) != 1:
        sys.exit(f"fetch: inconsistent count values {sorted(counts)}")
    return counts.pop()


def main() -> None:
    n = fetch_count()
    sentence = f"You are the {ordinal(n)} viewer. Welcome."

    svg = SVG.read_text(encoding="utf-8")
    svg, done = re.subn(
        r'(<text [^>]*>)(You are the \d+(?:st|nd|rd|th) viewer\. Welcome\.)(</text>)',
        lambda m: m.group(1) + sentence + m.group(3),
        svg,
    )
    if done != 1:
        sys.exit(f"patch: expected exactly one text node in {SVG.name}, found {done}")
    SVG.write_text(svg, encoding="utf-8")

    toml = TOML.read_text(encoding="utf-8")
    toml, done = re.subn(r"(?m)^count = \d+$", f"count = {n}", toml)
    if done != 1:
        sys.exit(f"patch: expected one 'count = …' line in content.toml, found {done}")
    TOML.write_text(toml, encoding="utf-8")

    print(f"view count baked in: {sentence}")


if __name__ == "__main__":
    main()
