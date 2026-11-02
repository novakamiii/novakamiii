#!/usr/bin/env python
"""Embed (or refresh) the koi GIF inside the header card's background slot.

Reads koi/koi.gif, re-encodes it small (ffmpeg, alpha-preserving; falls back to
the original bytes when ffmpeg is missing) and splices it into
assets/header.svg where the generator left the `data:image/gif;base64,…` slot.

Used both locally and by .github/workflows/koi.yml, so the header fish always
matches the latest nightly draw.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "assets" / "header.svg"
GIF = ROOT / "koi" / "koi.gif"

# Same recipe everywhere; keeps the embedded copy small and animated.
FFMPEG_ARGS = [
    "ffmpeg", "-y", "-loglevel", "error", "-i", str(GIF),
    "-vf",
    "fps=8,scale=256:-1,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse",
    "-f", "gif", "pipe:1",
]

B64_RE = re.compile(r"(data:image/gif;base64,)(@@KOI@@|[A-Za-z0-9+/=]+)")


def main() -> int:
    if not HEADER.exists():
        print(f"embed_koi: {HEADER} missing; run scripts/build_assets.py first", file=sys.stderr)
        return 1
    if not GIF.exists():
        print("embed_koi: koi/koi.gif missing; leaving the placeholder untouched", file=sys.stderr)
        return 0

    if shutil.which("ffmpeg"):
        small = subprocess.run(FFMPEG_ARGS, check=True, capture_output=True).stdout
    else:
        small = GIF.read_bytes()
        print(f"embed_koi: ffmpeg not found; embedding the full {len(small) / 1024:.0f} KB gif", file=sys.stderr)

    b64 = base64.b64encode(small).decode("ascii")

    # The re-encoded copy is also committed as koi/koi.gif: it is the only
    # consumer of that file in this repo, and the small version keeps the
    # nightly history from growing by ~550 KB a day.
    GIF.write_bytes(small)
    print(f"embed_koi: wrote {len(small) / 1024:.0f} KB gif back to koi/koi.gif")

    html = HEADER.read_text(encoding="utf-8")
    if not B64_RE.search(html):
        print("embed_koi: no koi slot in header.svg; regenerate the header first", file=sys.stderr)
        return 1
    HEADER.write_text(B64_RE.sub(lambda m: m.group(1) + b64, html), encoding="utf-8")
    print(f"embed_koi: fish embedded ({len(small) / 1024:.0f} KB gif, header now {HEADER.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
