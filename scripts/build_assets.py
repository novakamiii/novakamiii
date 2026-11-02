#!/usr/bin/env python
"""Generate every SVG asset (and README.md) for the profile README.

Text, palette and copy live in scripts/content.toml; edit that file and re-run.
Fonts are subsetted per card to exactly the glyphs used, then embedded as
base64 WOFF2 so the SVGs render in Liberation Serif / JetBrains Mono inside
GitHub's sandboxed <img>.

Setup once:  python -m venv .venv && .venv/bin/pip install fonttools brotli
Run:         .venv/bin/python scripts/build_assets.py
"""

from __future__ import annotations

import base64
import io
import re
import subprocess
import tomllib
from html import escape
from itertools import count
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.subset import Options, Subsetter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = ROOT / "scripts" / "skill-icons"
CONTENT = tomllib.loads((ROOT / "scripts" / "content.toml").read_text(encoding="utf-8"))

# --- Catppuccin Latte, desaturated usage -----------------------------------
BASE = "#eff1f5"      # card background
MANTLE = "#e6e9ef"    # inset panels
CRUST = "#dce0e8"     # hairline dividers
SURFACE0 = "#ccd0da"  # card border
TEXT = "#4c4f69"      # body text
SUBTEXT0 = "#64677e"  # secondary text: Catppuccin Subtext0 (#6c6f85) blended 25% toward
                      # Text so it passes WCAG AA on Base and Mantle (validated below)
ACCENT = "#7f6dab"    # single quiet accent: thin rules only

FONTS = {
    "serif_r": "Liberation Serif:style=Regular",
    "serif_b": "Liberation Serif:style=Bold",
    "serif_i": "Liberation Serif:style=Italic",
    "mono_r": "JetBrains Mono:style=Regular",
    "mono_b": "JetBrains Mono:style=Bold",
}


def _fc_match(pattern: str) -> str:
    return subprocess.run(["fc-match", "-f", "%{file}", pattern], check=True, text=True, capture_output=True).stdout.strip()


class Face:
    """A typographic face: cmap + glyph advance widths (read-only)."""

    def __init__(self, key: str):
        self.path = Path(_fc_match(FONTS[key]))
        self.font = TTFont(self.path, lazy=True)
        self.upem = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]

    def width(self, text: str, size: float) -> float:
        total = 0.0
        for ch in text:
            name = self.cmap.get(ord(ch))
            if name is None:
                print(f"  !! glyph missing: U+{ord(ch):04X} {ch!r} in {self.path.name}")
                continue
            total += self.hmtx[name][0]
        return total / self.upem * size

    def subset_b64(self, chars: str) -> str | None:
        chars = "".join(sorted(set(chars) - {" "}))
        if not chars:
            return None
        font = TTFont(self.path)  # fresh instance; subsetting mutates
        opts = Options(flavor="woff2")
        ss = Subsetter(opts)
        ss.populate(text=chars)
        ss.subset(font)
        font.flavor = "woff2"
        buf = io.BytesIO()
        font.save(buf)
        return base64.b64encode(buf.getvalue()).decode("ascii")


_FACES: dict[str, Face] = {}


def face(key: str) -> Face:
    if key not in _FACES:
        _FACES[key] = Face(key)
    return _FACES[key]


# ----------------------------------------------------------------- card ----

SERIF = "'Liberation Serif','Times New Roman',Times,serif"
MONO = "'JetBrains Mono',ui-monospace,monospace"


class Card:
    """One light Latte card: opaque Base background, 1px border, subsetted fonts."""

    def __init__(self, name: str, width: int, title: str, desc: str):
        self.name, self.w, self.title, self.desc = name, width, title, desc
        self.pad = 24
        self.parts: list[str] = []
        self.used: dict[str, str] = {}  # face key -> chars

    def text(self, x, y, s, key, size, fill, *, anchor=None, spacing=None):
        weight = 'font-weight="700"' if key.endswith("_b") else None
        style = 'font-style="italic"' if key.endswith("_i") else None
        fam = SERIF if key.startswith("serif") else MONO
        attrs = [f'x="{x:g}"', f'y="{y:g}"', f'font-family="{fam}"', f'font-size="{size:g}"', f'fill="{fill}"']
        attrs += [a for a in (weight, style, anchor and f'text-anchor="{anchor}"', spacing and f'letter-spacing="{spacing}"') if a]
        self.parts.append(f"<text {' '.join(attrs)}>{escape(s)}</text>")
        self.used[key] = self.used.get(key, "") + s

    def rule(self, x1, y, x2, stroke=CRUST, w=1):
        self.parts.append(f'<line x1="{x1:g}" y1="{y:g}" x2="{x2:g}" y2="{y:g}" stroke="{stroke}" stroke-width="{w:g}"/>')

    def heading(self, y, s, size=23):
        self.text(self.pad, y, s, "serif_b", size, TEXT, spacing="0.2")
        self.rule(self.pad, y + 13, self.pad + 46, ACCENT, 2)
        return y + 13 + 20

    def finish(self, height: int) -> str:
        def fontface(key: str) -> str:
            b64 = face(key).subset_b64(self.used.get(key, "") + "0123456789")
            if not b64:
                return ""
            fam = "Liberation Serif" if key.startswith("serif") else "JetBrains Mono"
            italic = key.endswith("_i")
            weight = 700 if key.endswith("_b") else 400
            return (
                f"@font-face{{font-family:'{fam}';font-style:{'italic' if italic else 'normal'};"
                f"font-weight:{weight};src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
            )

        style = "<style>" + "".join(fontface(k) for k in sorted(self.used)) + "</style>"
        bg = f'<rect x="0.5" y="0.5" width="{self.w - 1}" height="{height - 1}" rx="8" fill="{BASE}" stroke="{SURFACE0}" stroke-width="1"/>'
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{height}" viewBox="0 0 {self.w} {height}" role="img" aria-labelledby="t d">'
            f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
        )
        return "\n".join([head, style, bg, *self.parts, "</svg>"])


def wrap(face_key: str, text: str, size: float, width: float) -> list[str]:
    f = face(face_key)
    lines, cur = [], ""
    for word in text.split():
        cand = word if not cur else f"{cur} {word}"
        if f.width(cand, size) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# -------------------------------------------------------------- builders ---

def build_header(c: Card) -> int:
    cx = c.w / 2
    y = 54
    c.text(cx, y, CONTENT["header"]["name"], "serif_b", 42, TEXT, anchor="middle", spacing="0.4")
    y += 30
    c.text(cx, y, CONTENT["header"]["handle"], "mono_r", 15, SUBTEXT0, anchor="middle")
    y += 29
    c.text(cx, y, CONTENT["header"]["role"], "serif_i", 15.5, SUBTEXT0, anchor="middle")
    y += 22
    c.rule(cx - 32, y, cx + 32, ACCENT, 2)
    return round(y + 36)


def build_about(c: Card) -> int:
    y = 50
    y = c.heading(y, CONTENT["about"]["heading"])
    for p in CONTENT["about"]["paragraphs"]:
        for line in wrap("serif_r", p, 16.5, c.w - 2 * c.pad):
            c.text(c.pad, y, line, "serif_r", 16.5, TEXT)
            y += 26
        y += 8
    return round(y + 4)


def build_whoami(c: Card) -> int:
    y = 50
    y = c.heading(y, "whoami")
    label_w = 106
    top = y - 12
    rows = CONTENT["whoami"]["rows"]
    body: list[str] = []
    for row in rows:
        body.append(f'<text x="{c.pad + 16:g}" y="{y:g}" font-family="{MONO}" font-size="13.5" font-weight="700" fill="{SUBTEXT0}">{escape(row["label"])}</text>')
        body.append(f'<text x="{c.pad + 16 + label_w:g}" y="{y:g}" font-family="{MONO}" font-size="13.5" fill="{TEXT}">{escape(row["value"])}</text>')
        c.used["mono_b"] = c.used.get("mono_b", "") + row["label"]
        c.used["mono_r"] = c.used.get("mono_r", "") + row["value"]
        y += 25
        if row.get("divider"):
            y += 10
            body.append(f'<line x1="{c.pad + 16:g}" y1="{y:g}" x2="{c.w - c.pad - 16:g}" y2="{y:g}" stroke="{CRUST}" stroke-width="1"/>')
            y += 11
    bottom = y - 9
    inset = f'<rect x="{c.pad}" y="{top}" width="{c.w - 2 * c.pad}" height="{bottom - top}" rx="6" fill="{MANTLE}"/>'
    c.parts.insert(0, inset)
    c.parts.extend(body)
    return round(bottom + 12)


def build_project(c: Card, proj: dict) -> int:
    y = 50
    y = c.heading(y, proj.get("heading", ""))
    y += 4
    c.text(c.pad, y, proj["name"], "serif_b", 22, TEXT)
    y += 23
    c.text(c.pad, y, proj["tag"], "serif_i", 15.5, SUBTEXT0)
    y += 25
    body_w = c.w - 2 * c.pad
    for line in wrap("serif_r", proj["body"], 16.5, body_w):
        c.text(c.pad, y, line, "serif_r", 16.5, TEXT)
        y += 26
    y += 9
    c.text(c.pad, y, proj["stack"], "mono_b", 13, TEXT)
    y += 19
    c.text(c.pad, y, proj["meta"], "mono_r", 12.5, SUBTEXT0)
    return round(y + 6)


def build_skills(c: Card) -> int:
    y = 50
    y = c.heading(y, CONTENT["skills"]["heading"])
    names = ["php", "laravel", "ts", "js", "react", "tailwind", "vite",
             "py", "postgres", "redis", "docker", "git", "github", "githubactions",
             "linux", "arch", "nginx", "neovim", "vscodium", "figma", "ps"]
    tile, gap, per = 56, 14, 7
    x0 = (c.w - (per * tile + (per - 1) * gap)) / 2
    c.parts.append(
        '<filter id="s35" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.35"/></filter>'
        '<filter id="s20" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.2"/></filter>'
    )
    for i, name in enumerate(names):
        row, col = divmod(i, per)
        x, yy = x0 + col * (tile + gap), y + row * (tile + gap)
        path = ICONS / f"{ICON_FILE[name]}.svg"
        raw = path.read_text()
        light_tile = re.search(r'#[fF]4[fF]2[eE][dD]', raw) is not None
        if light_tile:
            raw = re.sub(r'fill="#[fF]4[fF]2[eE][dD]"', f'fill="{MANTLE}"', raw)
        inner = raw[raw.index("<svg") + raw[raw.index('<svg'):].index(">") + 1: raw.rindex("</svg>")]
        pre = f"i{i}-"
        inner = ID_ATTR.sub(lambda m: f'id="{pre}{m.group(1)}"', inner)
        inner = REF_RE.sub(f'\\1{pre}', inner)
        filt = "s35" if light_tile else "s20"
        c.parts.append(f'<g filter="url(#{filt})"><svg x="{x:g}" y="{yy:g}" width="{tile}" height="{tile}" viewBox="0 0 256 256">{inner}</svg></g>')
    rows = (len(names) + per - 1) // per
    y_bottom = y + rows * (tile + gap) - gap
    y = y_bottom + 26
    c.text(c.w / 2, y, CONTENT["skills"]["caption"], "mono_r", 12.5, SUBTEXT0, anchor="middle")
    return round(y + 24)


def build_now(c: Card) -> int:
    y = 54
    c.text(c.pad, y, CONTENT["now"]["date"], "serif_i", 15.5, SUBTEXT0)
    y += 32
    for line in wrap("serif_r", CONTENT["now"]["text"], 17, c.w - 2 * c.pad):
        c.text(c.pad, y, line, "serif_r", 17, TEXT)
        y += 27
    return round(y + 16)


def build_footer(c: Card) -> int:
    y = 54
    c.text(c.w / 2, y, CONTENT["footer"]["line"], "mono_r", 14, SUBTEXT0, anchor="middle")
    y += 24
    c.rule((c.w - 64) / 2, y, (c.w + 64) / 2, ACCENT, 2)
    return round(y + 34)


ID_ATTR = re.compile(r'\bid="([^"]*)"')
REF_RE = re.compile(r'(url\(\s*#|href="#|xlink:href="#)')

# skillicons.dev id -> vendored icon file name in scripts/skill-icons/
ICON_FILE = {
    "php": "PHP", "laravel": "Laravel", "ts": "TypeScript", "js": "JavaScript",
    "react": "React", "tailwind": "TailwindCSS", "vite": "Vite", "py": "Python",
    "postgres": "PostgreSQL", "redis": "Redis", "docker": "Docker", "git": "Git",
    "github": "Github", "githubactions": "GithubActions", "linux": "Linux",
    "arch": "Arch", "nginx": "Nginx", "neovim": "NeoVim", "vscodium": "VSCodium",
    "figma": "Figma", "ps": "Photoshop",
}

# ------------------------------------------------------------------ run ----


def render(name: str, width: int, title: str, desc: str, builder, *args) -> None:
    c = Card(name, width, title, desc)
    h = builder(c, *args)
    svg = c.finish(h)
    ASSETS.mkdir(exist_ok=True)
    out = ASSETS / f"{name}.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"  assets/{name}.svg  {len(svg) / 1024:.1f} KB  ({width}x{h})")


def contrast(fg: str, bg: str) -> float:
    def lum(x: str) -> float:
        v = [int(x[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        v = [0.0 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]

    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def check_contrast() -> None:
    print("contrast (WCAG AA needs 4.50):")
    for label, fg in (("body", TEXT), ("secondary", SUBTEXT0)):
        for bg in (BASE, MANTLE):
            r = contrast(fg, bg)
            flag = "" if r >= 4.5 else "  !! FAILS"
            print(f"  {label} {fg} on {bg}: {r:.2f}{flag}")


def write_readme(alts: dict[str, str]) -> None:
    deck_link = CONTENT["projects"][1].get("link", "https://github.com/novakamiii/DeckMe")
    md = f"""<div align="center">

<p><img src="assets/header.svg" width="800" alt="{escape(alts["header"])}"/></p>

<p>
<table>
<tr><td valign="top"><img src="assets/about.svg" width="536" alt="{escape(alts["about"])}"/></td><td valign="top"><img src="koi/koi.gif" width="256" alt="A pixel-art koi, redrawn from public GitHub activity each day."/></td></tr>
</table>
</p>

<p><img src="assets/whoami.svg" width="800" alt="{escape(alts["whoami"])}"/></p>

<p><img src="assets/work-trapple.svg" width="800" alt="{escape(alts["trapple"])}"/></p>
<p><a href="{deck_link}"><img src="assets/work-deckme.svg" width="800" alt="{escape(alts["deckme"])}"/></a></p>

<p><img src="assets/skills.svg" width="800" alt="{escape(alts["skills"])}"/></p>

<p><img src="assets/now.svg" width="800" alt="{escape(alts["now"])}"/></p>

<p><a href="https://github.com/novakamiii"><img src="assets/footer.svg" width="800" alt="{escape(alts["footer"])}"/></a></p>

</div>
"""
    (ROOT / "README.md").write_text(md, encoding="utf-8")
    print("  README.md written")


def main() -> None:
    check_contrast()
    print("building:")
    render("header", 800, "Paulo — novakamiii", CONTENT["header"]["alt"], build_header)
    render("about", 536, "About Paulo", CONTENT["about"]["alt"], build_about)
    render("whoami", 800, "whoami — system and study", CONTENT["whoami"]["alt"], build_whoami)
    for proj in CONTENT["projects"]:
        render(proj["card"], 800, proj["name"], proj["alt"], build_project, proj)
    render("skills", 800, "Stack", CONTENT["skills"]["alt"], build_skills)
    render("now", 800, "Now", CONTENT["now"]["alt"], build_now)
    render("footer", 800, "github.com/novakamiii", CONTENT["footer"]["alt"], build_footer)
    total = sum(p.stat().st_size for p in ASSETS.glob("*.svg"))
    print(f"  total assets: {total / 1024:.1f} KB")

    alts = {
        "header": CONTENT["header"]["alt"],
        "about": CONTENT["about"]["alt"],
        "whoami": CONTENT["whoami"]["alt"],
        "trapple": CONTENT["projects"][0]["alt"],
        "deckme": CONTENT["projects"][1]["alt"],
        "skills": CONTENT["skills"]["alt"],
        "now": CONTENT["now"]["alt"],
        "footer": CONTENT["footer"]["alt"],
    }
    write_readme(alts)


if __name__ == "__main__":
    main()
