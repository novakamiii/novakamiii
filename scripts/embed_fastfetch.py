#!/usr/bin/env python
"""Embed the fastfetch chibi GIF inside the fastfetch card's left slot.

Reads assets/fastfetch-logo.gif (the committed original), re-encodes it small
with ffmpeg and splices it into assets/fastfetch.svg where the generator left
the `data:image/gif;base64,…` slot. Unlike the koi, the source is static, so
the original on disk is never overwritten.

Used both locally and after builds: run scripts/embed_fastfetch.py, or let
scripts/build_assets.py call it at the end.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "assets" / "fastfetch.svg"
GIF = ROOT / "assets" / "fastfetch-logo.gif"

# The card shows the gif at ~176px; 224 keeps some sharpness at a weight the
# README can carry (palette-based GIF, 8 fps is the source's own cadence).
FFMPEG_ARGS = [
    "ffmpeg", "-y", "-loglevel", "error", "-i", str(GIF),
    "-vf",
    "fps=8,scale=224:-1,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
    "-f", "gif", "pipe:1",
]

B64_RE = re.compile(r"(data:image/gif;base64,)(@@FASTFETCH@@|[A-Za-z0-9+/=]+)")


def main() -> int:
    if not CARD.exists():
        print(f"embed_fastfetch: {CARD} missing; run scripts/build_assets.py first", file=sys.stderr)
        return 1
    if not GIF.exists():
        print(f"embed_fastfetch: {GIF.name} missing; leaving the placeholder untouched", file=sys.stderr)
        return 0

    if shutil.which("ffmpeg"):
        small = subprocess.run(FFMPEG_ARGS, check=True, capture_output=True).stdout
    else:
        small = GIF.read_bytes()
        print(f"embed_fastfetch: ffmpeg not found; embedding the full {len(small) / 1024:.0f} KB gif", file=sys.stderr)

    b64 = base64.b64encode(small).decode("ascii")

    html = CARD.read_text(encoding="utf-8")
    if not B64_RE.search(html):
        print("embed_fastfetch: no gif slot in fastfetch.svg; regenerate the card first", file=sys.stderr)
        return 1
    CARD.write_text(B64_RE.sub(lambda m: m.group(1) + b64, html), encoding="utf-8")
    print(f"embed_fastfetch: chibi embedded ({len(small) / 1024:.0f} KB gif, card now {CARD.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
