# Third-party assets and attributions

## Fonts (embedded as subsetted WOFF2 in `assets/*.svg`)

| Font | Source | License |
| --- | --- | --- |
| Liberation Serif (Regular, Bold, Italic) | <https://github.com/liberationfonts/liberation-fonts> | SIL Open Font License 1.1 |
| JetBrains Mono (Regular, Bold) | <https://www.jetbrains.com/lp/mono/> | SIL Open Font License 1.1 |

Both are metric-compatible or by-design substitutes for the README's type system
(Times/Liberation Serif for prose, JetBrains Mono for anything code-like), and are
redistributed here only as embedded subsets containing exactly the glyphs each card
renders. License texts: <https://scripts.sil.org/OFL>.

## Icons (`scripts/skill-icons/`, rendered muted in `assets/skills.svg`)

| Project | Source | License |
| --- | --- | --- |
| skill-icons (tandpfun) | <https://github.com/tandpfun/skill-icons> | MIT |

Vendored files are copied from the project's `icons/` directory (light-variant files
and single-file icons). The vendored copies are modified in two ways, applied at build
time by `scripts/build_assets.py` (the on-disk copies are unmodified): tile backgrounds
are recolored to the README's palette, and every icon is desaturated through an SVG
feColorMatrix filter. Logos remain the property of their respective owners.

## git-koi (`koi/koi.gif`, drawn nightly by `.github/workflows/koi.yml`)

| Project | Source | License |
| --- | --- | --- |
| git-koi (yalongwastaken) | <https://github.com/yalongwastaken/git-koi> | MIT |

Used as the pinned GitHub Action `yalongwastaken/git-koi@7305e9b1fadee6f43d3b4fa543a25d4cde79856e`
(tag `v1.0.2`).
