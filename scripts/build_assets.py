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
import sys
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

    def ornament(self, x1, y, x2, *, gem=5, gap=7):
        """Stylized text break: hairlines that part around a small accent square."""
        cx = (x1 + x2) / 2
        self.rule(x1, y, cx - gap, SURFACE0, 1.25)
        self.rule(cx + gap, y, x2, SURFACE0, 1.25)
        h = gem / 2
        self.parts.append(f'<rect x="{cx - h:g}" y="{y - h:g}" width="{gem}" height="{gem}" fill="{ACCENT}"/>')

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


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th — including the 11th/12th/13th oddities."""
    if n % 100 in (11, 12, 13):
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def views_sentence() -> tuple[str, str]:
    """The viewer greeting and its alt text, with the ordinal filled in."""
    s = ordinal(int(CONTENT["views"]["count"]))
    return (
        CONTENT["views"]["sentence"].replace("{ord}", s),
        CONTENT["views"]["alt"].replace("{ord}", s),
    )


# -------------------------------------------------------------- builders ---

def build_header(c: Card) -> int:
    H = 172
    # Swimming koi in the background: the GIF is injected by scripts/embed_koi.py
    # (placeholder token @@KOI@@ until then), kept faint and clipped to the card.
    c.parts.append(
        '<defs>'
        f'<clipPath id="koi-clip"><rect x="0.5" y="0.5" width="{c.w - 1}" height="{H - 1}" rx="8"/></clipPath>'
        '<filter id="koi-quiet" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.75"/></filter>'
        '</defs>'
        '<g clip-path="url(#koi-clip)" filter="url(#koi-quiet)" opacity="0.45">'
        f'<image x="-210" y="-14" width="200" height="200" preserveAspectRatio="xMidYMid meet" href="data:image/gif;base64,@@KOI@@">'
        '<animateTransform attributeName="transform" type="translate" values="250 0;820 0;250 0" dur="80s" repeatCount="indefinite" calcMode="linear"/>'
        '</image></g>'
    )
    c.ornament(c.pad, 26, c.w - c.pad)
    cx = c.w / 2
    y = 92
    c.text(cx, y, CONTENT["header"]["name"], "serif_b", 44, TEXT, anchor="middle", spacing="0.4")
    y += 28
    c.text(cx, y, CONTENT["header"]["role"], "serif_i", 15.5, SUBTEXT0, anchor="middle")
    y += 18
    c.rule(cx - 32, y, cx + 32, ACCENT, 2)
    return H


def build_about(c: Card) -> int:
    y = 50
    y = c.heading(y, CONTENT["about"]["heading"])
    for p in CONTENT["about"]["paragraphs"]:
        for line in wrap("serif_r", p, 16.5, c.w - 2 * c.pad):
            c.text(c.pad, y, line, "serif_r", 16.5, TEXT)
            y += 26
        y += 8
    return round(y + 4)


# Latte accents for the fastfetch glyphs and the dot row at the bottom.
FF_DOTS = ["#d20f39", "#fe640b", "#df8e1d", "#40a02b", "#179299", "#04a5e5", "#7287fd", "#8839ef", "#ea76cb", "#dc8a78"]


def _ff_icon(c: Card, x: float, y: float, kind: str, color: str) -> None:
    """A small colored glyph in an 11×11 box ending at the text baseline y."""
    t = y - 10  # top of the box
    g = lambda v: f"{v:g}"  # noqa: E731
    p = c.parts
    if kind == "os":
        p.append(f'<path d="M{g(x + 5.5)},{g(t + 1)} L{g(x + 10.6)},{g(t + 10)} L{g(x + 0.4)},{g(t + 10)} Z" fill="{color}"/>')
    elif kind == "kernel":
        p.append(f'<circle cx="{g(x + 5.5)}" cy="{g(t + 5.5)}" r="4.4" fill="none" stroke="{color}" stroke-width="1.6"/>'
                 f'<path d="M{g(x + 5.5)},{g(t + 3)} V{g(t + 5.5)} H{g(x + 7.7)}" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>')
    elif kind == "wm":
        for dx in (0.4, 6.0):
            for dy in (0.4, 6.0):
                p.append(f'<rect x="{g(x + dx)}" y="{g(t + dy)}" width="4.6" height="4.6" rx="1" fill="{color}"/>')
    elif kind == "terminal":
        p.append(f'<rect x="{g(x + 0.5)}" y="{g(t + 1.5)}" width="10" height="8" rx="1.5" fill="none" stroke="{color}" stroke-width="1.4"/>'
                 f'<path d="M{g(x + 2.6)},{g(t + 4)} L{g(x + 4.6)},{g(t + 5.5)} L{g(x + 2.6)},{g(t + 7)}" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'
                 f'<path d="M{g(x + 6.1)},{g(t + 7)} H{g(x + 8.6)}" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>')
    elif kind == "shell":
        p.append(f'<path d="M{g(x + 4.4)},{g(t + 0.8)} L{g(x + 3.6)},{g(t + 10.2)} M{g(x + 7.6)},{g(t + 0.8)} L{g(x + 6.8)},{g(t + 10.2)}'
                 f' M{g(x + 1.2)},{g(t + 4.2)} H{g(x + 10)} M{g(x + 1)},{g(t + 7.2)} H{g(x + 9.8)}" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>')
    elif kind == "editor":
        p.append(f'<path d="M{g(x + 1)},{g(t + 10)} L{g(x + 2.1)},{g(t + 6.7)} L{g(x + 8.3)},{g(t + 0.5)} L{g(x + 10.7)},{g(t + 2.9)} L{g(x + 4.5)},{g(t + 9.1)} Z" fill="{color}"/>')
    elif kind == "school":
        p.append(f'<path d="M{g(x + 0.8)},{g(t + 1.8)} C{g(x + 3)},{g(t + 0.6)} {g(x + 5.2)},{g(t + 1)} {g(x + 5.5)},{g(t + 2.6)}'
                 f' C{g(x + 5.8)},{g(t + 1)} {g(x + 8)},{g(t + 0.6)} {g(x + 10.2)},{g(t + 1.8)} V{g(t + 9.6)}'
                 f' C{g(x + 8)},{g(t + 8.4)} {g(x + 5.8)},{g(t + 8.8)} {g(x + 5.5)},{g(t + 10.4)}'
                 f' C{g(x + 5.2)},{g(t + 8.8)} {g(x + 3)},{g(t + 8.4)} {g(x + 0.8)},{g(t + 9.6)} Z" fill="{color}"/>')
    elif kind == "course":
        p.append(f'<path d="M{g(x + 5.5)},{g(t + 0.6)} L{g(x + 11)},{g(t + 3.6)} L{g(x + 5.5)},{g(t + 6.6)} L{g(x + 0)},{g(t + 3.6)} Z" fill="{color}"/>'
                 f'<path d="M{g(x + 2.4)},{g(t + 5.4)} V{g(t + 8.4)} C{g(x + 2.4)},{g(t + 10.4)} {g(x + 8.6)},{g(t + 10.4)} {g(x + 8.6)},{g(t + 8.4)} V{g(t + 5.4)}" fill="none" stroke="{color}" stroke-width="1.3"/>')
    else:  # fallback: a dot
        p.append(f'<circle cx="{g(x + 5.5)}" cy="{g(t + 5.5)}" r="4" fill="{color}"/>')


FF_ROW_STYLE = {
    "OS": ("os", "#40a02b"),
    "Kernel": ("kernel", "#d20f39"),
    "WM": ("wm", "#179299"),
    "Terminal": ("terminal", "#04a5e5"),
    "Shell": ("shell", "#df8e1d"),
    "Editor": ("editor", "#8839ef"),
    "School": ("school", "#1e66f5"),
    "Course": ("course", "#ea76cb"),
}


def build_fastfetch(c: Card) -> int:
    """Terminal-style panel: the chibi gif on the left, label-glyph rows on the right."""
    rows = CONTENT["fastfetch"]["rows"]
    size = 13
    gif_x, gif_s = 28, 176
    gx = gif_x + gif_s + 24  # right column: title, glyph rows, dots
    # Layout pass first: the card height follows the rows (they are one-liners;
    # wrap() only catches regressions if a future value outgrows the column).
    y = 62
    for row in rows:
        lines = wrap("mono_r", row["value"], size, c.w - c.pad - (gx + 22))
        y += 24 + (len(lines) - 1) * 19
    dots_y = y + 6
    H = round(dots_y + 20)
    gif_y = (H - gif_s) / 2

    # right column
    c.text(gx, 28, "novakamiii", "mono_b", 16, TEXT)
    c.rule(gx, 36, gx + 42, ACCENT, 2)
    y = 62
    for row in rows:
        kind, color = FF_ROW_STYLE.get(row["label"], ("dot", ACCENT))
        _ff_icon(c, gx, y, kind, color)
        lines = wrap("mono_r", row["value"], size, c.w - c.pad - (gx + 22))
        for i, line in enumerate(lines):
            c.text(gx + 22, y + i * 19, line, "mono_r", size, TEXT)
        y += 24 + (len(lines) - 1) * 19
    for i, col in enumerate(FF_DOTS):
        c.parts.append(f'<circle cx="{gx + i * 15 + 4:g}" cy="{dots_y:g}" r="4" fill="{col}"/>')

    # inset panel behind the right column, drawn under everything else
    panel = f'<rect x="{gx - 16}" y="14" width="{c.w - c.pad - (gx - 16)}" height="{H - 14 - 14}" rx="6" fill="{MANTLE}"/>'
    c.parts.insert(0, panel)

    # left: the chibi gif, injected by scripts/embed_fastfetch.py
    c.parts.insert(0, (
        '<defs><clipPath id="ff-clip">'
        f'<rect x="{gif_x:g}" y="{gif_y:g}" width="{gif_s}" height="{gif_s}" rx="8"/></clipPath></defs>'
    ))
    c.parts.append(
        f'<g clip-path="url(#ff-clip)"><image x="{gif_x:g}" y="{gif_y:g}" width="{gif_s}" height="{gif_s}" '
        'preserveAspectRatio="xMidYMid slice" href="data:image/gif;base64,@@FASTFETCH@@"/></g>'
    )
    return H


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


def build_metrics(c: Card) -> int:
    """GitHub Stats: contributions, repo totals and languages — three equal panels."""
    m = CONTENT["metrics"]
    y = 50
    y = c.heading(y, m["heading"])
    top, gap, H, inset = y + 12, 16, 188, 18
    pw = (c.w - 2 * c.pad - 2 * gap) / 3
    cols = [c.pad + i * (pw + gap) for i in range(3)]
    for i, x0 in enumerate(cols):
        c.parts.append(f'<rect x="{x0:g}" y="{top:g}" width="{pw:g}" height="{H}" rx="6" fill="{MANTLE}"/>')
        c.text(x0 + inset, top + 27, m["panels"][i], "mono_b", 10, SUBTEXT0, spacing="1.2")

    # contributions: two stacked figures split by a hairline
    con, cx = m["contributions"], cols[0] + pw / 2
    for (num, label, rng), b in (
        ((con["total"], con["total_label"], con["total_range"]), top + 60),
        ((con["streak"], con["streak_label"], con["streak_range"]), top + 138),
    ):
        c.text(cx, b, num, "mono_b", 26, TEXT, anchor="middle")
        c.text(cx, b + 18, label, "mono_r", 11.5, TEXT, anchor="middle")
        c.text(cx, b + 33, rng, "mono_r", 10.5, SUBTEXT0, anchor="middle")
    c.rule(cols[0] + inset, top + 112, cols[0] + pw - inset, CRUST, 1)

    # repo totals: compact label/value rows
    sx = cols[1]
    for i, row in enumerate(m["stats"]):
        b = top + 58 + i * 25
        c.text(sx + inset, b, row["label"], "mono_r", 11.5, TEXT)
        c.text(sx + pw - inset, b, row["value"], "mono_b", 11.5, TEXT, anchor="end")

    # languages: stacked bar over a compact legend; the CRUST track shows the remainder
    lx = cols[2]
    langs = m["languages"]
    bw, bar_y = pw - 2 * inset, top + 42
    c.parts.append(
        '<defs><clipPath id="metrics-bar">'
        f'<rect x="{lx + inset:g}" y="{bar_y:g}" width="{bw:g}" height="7" rx="3.5"/></clipPath></defs>'
    )
    c.parts.append('<g clip-path="url(#metrics-bar)">')
    c.parts.append(f'<rect x="{lx + inset:g}" y="{bar_y:g}" width="{bw:g}" height="7" fill="{CRUST}"/>')
    seg_x = lx + inset
    for i, lang in enumerate(langs):
        w = float(lang["pct"]) / 100 * bw
        c.parts.append(f'<rect x="{seg_x:g}" y="{bar_y:g}" width="{w:g}" height="7" fill="{FF_DOTS[i]}"/>')
        seg_x += w
    c.parts.append("</g>")
    for i, lang in enumerate(langs):
        b = top + 70 + i * 19
        c.parts.append(f'<circle cx="{lx + inset + 5:g}" cy="{b - 3.5:g}" r="3.5" fill="{FF_DOTS[i]}"/>')
        c.text(lx + inset + 14, b, lang["name"], "mono_r", 10.5, TEXT)
        c.text(lx + pw - inset, b, f'{lang["pct"]}%', "mono_r", 10.5, SUBTEXT0, anchor="end")
    return round(top + H + 24)


def build_skills(c: Card) -> int:
    y = 50
    y = c.heading(y, CONTENT["skills"]["heading"])
    names = ["php", "laravel", "ts", "js", "react", "tailwind", "vite",
             "py", "postgres", "redis", "docker", "git", "github", "githubactions",
             "linux", "arch", "nginx", "neovim", "vscodium", "zed", "krita"]
    tile, gap, per = 56, 14, 7
    x0 = (c.w - (per * tile + (per - 1) * gap)) / 2
    c.parts.append(
        '<filter id="s35" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.35"/></filter>'
        '<filter id="s20" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.2"/></filter>'
    )
    # Each stack row slides in as one group — every icon in a row shares the
    # row's delay, and rows stagger 0.5s apart so nothing queues behind the
    # previous row. Directions alternate: even rows enter left-to-right, odd
    # rows right-to-left. CSS animations survive GitHub's sandboxed <img>;
    # scripts do not.
    rows = (len(names) + per - 1) // per
    row_gap = 0.5  # seconds between row starts
    css = (
        '@keyframes sl-in-l{from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:translateX(0)}}'
        '@keyframes sl-in-r{from{opacity:0;transform:translateX(18px)}to{opacity:1;transform:translateX(0)}}'
        + "".join(
            f'.i.r{r}{{animation:1s ease-out both sl-in-{"l" if r % 2 == 0 else "r"};animation-delay:{r * row_gap:g}s}}'
            for r in range(rows)
        )
    )
    c.parts.append(f"<style>{css}</style>")
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
        c.parts.append(f'<g class="i r{row}" filter="url(#{filt})"><svg x="{x:g}" y="{yy:g}" width="{tile}" height="{tile}" viewBox="0 0 256 256">{inner}</svg></g>')
    y_bottom = y + rows * (tile + gap) - gap
    y = y_bottom + 26
    caption = CONTENT["skills"].get("caption")
    if caption:
        c.text(c.w / 2, y, caption, "mono_r", 12.5, SUBTEXT0, anchor="middle")
        return round(y + 24)
    return round(y_bottom + 24)


def build_now(c: Card) -> int:
    y = 54
    c.text(c.pad, y, CONTENT["now"]["date"], "serif_i", 15.5, SUBTEXT0)
    y += 32
    for line in wrap("serif_r", CONTENT["now"]["text"], 17, c.w - 2 * c.pad):
        c.text(c.pad, y, line, "serif_r", 17, TEXT)
        y += 27
    return round(y + 16)


def build_views(c: Card) -> int:
    # The count is baked in as plain text; scripts/update_views.py refreshes it
    # nightly by patching this text node (no rebuild needed).
    sentence, _ = views_sentence()
    y = 58
    c.text(c.w / 2, y, sentence, "serif_r", 17, TEXT, anchor="middle")
    # Keep every ordinal suffix subsetted: the nightly counter can change th→st etc.
    c.used["serif_r"] += "stnrdth"
    c.ornament(c.pad + 120, y + 30, c.w - c.pad - 120)
    return round(y + 60)


ID_ATTR = re.compile(r'\bid="([^"]*)"')
REF_RE = re.compile(r'(url\(\s*#|href="#|xlink:href="#)')

# skillicons.dev id -> vendored icon file name in scripts/skill-icons/
ICON_FILE = {
    "php": "PHP", "laravel": "Laravel", "ts": "TypeScript", "js": "JavaScript",
    "react": "React", "tailwind": "TailwindCSS", "vite": "Vite", "py": "Python",
    "postgres": "PostgreSQL", "redis": "Redis", "docker": "Docker", "git": "Git",
    "github": "Github", "githubactions": "GithubActions", "linux": "Linux",
    "arch": "Arch", "nginx": "Nginx", "neovim": "NeoVim", "vscodium": "VSCodium",
    "zed": "Zed", "krita": "Krita",
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

<p><img src="assets/about.svg" width="800" alt="{escape(alts["about"])}"/></p>

<p><img src="assets/fastfetch.svg" width="800" alt="{escape(alts["fastfetch"])}"/></p>

<p><img src="assets/work-trapple.svg" width="800" alt="{escape(alts["trapple"])}"/></p>
<p><a href="{deck_link}"><img src="assets/work-deckme.svg" width="800" alt="{escape(alts["deckme"])}"/></a></p>

<p><img src="assets/metrics.svg" width="800" alt="{escape(alts["metrics"])}"/></p>

<p><img src="assets/skills.svg" width="800" alt="{escape(alts["skills"])}"/></p>

<p><img src="assets/now.svg" width="800" alt="{escape(alts["now"])}"/></p>

<p><img src="assets/views.svg" width="800" alt="{escape(alts["views"])}"/></p>

<!-- 0x0 counter pixel: the only source of the view count. It increments the
     badge service; scripts/update_views.py bakes that number into the plain-text
     views card above nightly. -->
<p><img src="https://komarev.com/ghpvc/?username=novakamiii&amp;label=&amp;color=7f6dab" width="0" height="0" alt=""/></p>

</div>
"""
    (ROOT / "README.md").write_text(md, encoding="utf-8")
    print("  README.md written")


def main() -> None:
    check_contrast()
    print("building:")
    views_txt, views_alt = views_sentence()
    render("header", 800, "novakamiii", CONTENT["header"]["alt"], build_header)
    render("about", 800, "About", CONTENT["about"]["alt"], build_about)
    render("fastfetch", 800, "fastfetch", CONTENT["fastfetch"]["alt"], build_fastfetch)
    for proj in CONTENT["projects"]:
        render(proj["card"], 800, proj["name"], proj["alt"], build_project, proj)
    render("metrics", 800, "GitHub Stats", CONTENT["metrics"]["alt"], build_metrics)
    render("skills", 800, "Stack", CONTENT["skills"]["alt"], build_skills)
    render("now", 800, "Now", CONTENT["now"]["alt"], build_now)
    render("views", 800, "Profile views", views_alt, build_views)
    total = sum(p.stat().st_size for p in ASSETS.glob("*.svg"))
    print(f"  total assets: {total / 1024:.1f} KB")

    alts = {
        "header": CONTENT["header"]["alt"],
        "about": CONTENT["about"]["alt"],
        "fastfetch": CONTENT["fastfetch"]["alt"],
        "trapple": CONTENT["projects"][0]["alt"],
        "deckme": CONTENT["projects"][1]["alt"],
        "metrics": CONTENT["metrics"]["alt"],
        "skills": CONTENT["skills"]["alt"],
        "now": CONTENT["now"]["alt"],
        "views": views_alt,
    }
    write_readme(alts)

    # Restore the fish and the chibi: any rebuild deletes their embedded GIFs,
    # so both embedders run at the end.
    for script in ("embed_koi.py", "embed_fastfetch.py"):
        subdir = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=False, capture_output=True, text=True)
        if subdir.stdout.strip():
            print(subdir.stdout.strip())


if __name__ == "__main__":
    main()
