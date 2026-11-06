#!/usr/bin/env python3
"""Refresh the GitHub Stats card, private contributions included.

The card's numbers are ordinary <text> nodes tagged with data-field by the
builder, so this patches assets/metrics.svg in place and keeps
scripts/content.toml (and the README alt text) in sync — stdlib only, no
fonts or build venv needed on the runner.

Data comes from the authenticated GraphQL contributions API and the REST
languages endpoint as novakamiii, so private repository work counts. Needs a
classic PAT with repo scope in $METRICS_TOKEN (the nightly workflow supplies
it as a secret; locally: METRICS_TOKEN=$(gh auth token) python3 scripts/update_metrics.py).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "metrics.svg"
TOML = ROOT / "scripts" / "content.toml"
README = ROOT / "README.md"
LOGIN = "novakamiii"
TOP_LANGS = 6

STAT_FIELDS = {
    "Total Stars Earned": "stars",
    "Total Commits (last year)": "commits",
    "Total PRs": "prs",
    "Total Issues": "issues",
    "Contributed to (last year)": "contributed",
}

GRAPHQL = """query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner }
      }
    }
  }
}"""


def year_windows(created: date, today: date) -> list[tuple[date, date]]:
    """≤1-year windows tiling [created, today]: contributionsCollection caps the range."""
    out, start = [], created
    while start <= today:
        try:
            step = date(start.year + 1, start.month, start.day)
        except ValueError:  # Feb 29 account creation
            step = date(start.year + 1, start.month, 28)
        end = min(step - timedelta(days=1), today)
        out.append((start, end))
        start = end + timedelta(days=1)
    return out


def fetch(token: str) -> dict:
    def api(url: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"bearer {token}",
            "User-Agent": "novakamiii-metrics-updater",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.load(res)

    today = date.today()
    created = date.fromisoformat(api(f"https://api.github.com/users/{LOGIN}")["created_at"][:10])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def span(d0: date, d1: date) -> tuple[str, str]:
        return (f"{d0.isoformat()}T00:00:00Z",
                now if d1 >= today else f"{d1.isoformat()}T23:59:59Z")

    def collect(window: tuple[str, str]) -> dict:
        gql = api("https://api.github.com/graphql",
                  {"query": GRAPHQL, "variables": {"login": LOGIN, "from": window[0], "to": window[1]}})
        if "errors" in gql:
            sys.exit(f"graphql: {gql['errors'][0].get('message', 'unknown error')}")
        return gql["data"]["user"]["contributionsCollection"]

    # all-time figures, summed over disjoint ≤1-year windows
    days: dict[str, int] = {}
    all_time = {"total": 0, "commits": 0, "prs": 0, "issues": 0}
    for window in year_windows(created, today):
        cc = collect(span(*window))
        all_time["total"] += cc["contributionCalendar"]["totalContributions"]
        all_time["commits"] += cc["totalCommitContributions"]
        all_time["prs"] += cc["totalPullRequestContributions"]
        all_time["issues"] += cc["totalIssueContributions"]
        for w in cc["contributionCalendar"]["weeks"]:
            for day in w["contributionDays"]:
                days[day["date"]] = days.get(day["date"], 0) + day["contributionCount"]

    # the two "last year" rows get their own trailing window (it overlaps the
    # final span on purpose — separate fields, no double counting). "Contributed
    # to" unions commit and PR contribution repos: PR-only contributions count.
    cc = collect(span(today - timedelta(days=365), today))
    owned = f"{LOGIN}/"
    outside = {r["repository"]["nameWithOwner"]
               for key in ("commitContributionsByRepository", "pullRequestContributionsByRepository")
               for r in cc[key] if not r["repository"]["nameWithOwner"].startswith(owned)}
    trailing = {"commits": cc["totalCommitContributions"], "contributed": len(outside)}

    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/user/repos?per_page=100&type=owner&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    langs: dict[str, int] = {}
    for repo in repos:
        for name, size in api(repo["languages_url"]).items():
            langs[name] = langs.get(name, 0) + size

    return {
        "days": sorted(days.items()),
        # per-day buckets merged across windows attribute every day exactly
        # once, unlike summing each window's totalContributions (which clips
        # contributions near UTC window boundaries)
        "total": sum(days.values()),
        "commits": trailing["commits"],
        "prs": all_time["prs"],
        "issues": all_time["issues"],
        "contributed": trailing["contributed"],
        "stars": sum(r["stargazers_count"] for r in repos),
        "langs": sorted(langs.items(), key=lambda kv: -kv[1]),
    }


def fmt_day(iso: str, with_year: bool = False) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%b %-d, %Y" if with_year else "%b %-d")


def compute(d: dict) -> dict:
    active = [iso for iso, n in d["days"] if n > 0]
    if not active:
        sys.exit("calendar: no contribution days returned")

    best, cur, best_span, cur_start = 0, 0, None, None
    for iso, n in d["days"]:
        if n > 0:
            cur_start = iso if cur == 0 else cur_start
            cur += 1
            if cur > best:
                best, best_span = cur, (cur_start, iso)
        else:
            cur = 0
    if not best:
        sys.exit("calendar: no streak found")

    grand = sum(size for _, size in d["langs"])
    top = [(name, size / grand * 100) for name, size in d["langs"][:TOP_LANGS]]
    if len(top) < TOP_LANGS:
        sys.exit(f"languages: expected at least {TOP_LANGS}, found {len(top)}")

    return {
        "total": f"{d['total']:,}",
        "total_range": f"{fmt_day(active[0], with_year=True)} – Present",
        "streak": str(best),
        "streak_range": f"{fmt_day(best_span[0])} – {fmt_day(best_span[1])}",
        "stars": str(d["stars"]),
        "commits": str(d["commits"]),
        "prs": str(d["prs"]),
        "issues": str(d["issues"]),
        "contributed": str(d["contributed"]),
        "langs_list": [(name, f"{pct:.2f}") for name, pct in top],
    }


def set_text(html: str, field: str, value: str) -> str:
    html, n = re.subn(rf'(data-field="{field}"[^>]*>)[^<]*(</text>)',
                      lambda m: m.group(1) + escape(value) + m.group(2), html)
    if n != 1:
        sys.exit(f"patch: expected exactly one {field} node, found {n}")
    return html


def set_segment(html: str, i: int, x: float, width: float) -> str:
    html, n = re.subn(
        rf'(<rect data-field="lang-seg-{i}" )x="[^"]*" (y="[^"]*" )width="[^"]*"',
        lambda m: f'{m.group(1)}x="{x:g}" {m.group(2)}width="{width:g}"', html)
    if n != 1:
        sys.exit(f"patch: expected exactly one lang-seg-{i} rect, found {n}")
    return html


def patch_toml(toml: str, v: dict) -> str:
    for key in ("total", "total_range", "streak", "streak_range"):
        toml, n = re.subn(rf'(?m)^({key} = ")[^"]*(")$', rf"\g<1>{v[key]}\g<2>", toml)
        if n != 1:
            sys.exit(f"toml: expected one '{key}' line, found {n}")
    for label, field in STAT_FIELDS.items():
        toml, n = re.subn(rf'(?m)(label = "{re.escape(label)}"\nvalue = ")[^"]*(")',
                          rf"\g<1>{v[field]}\g<2>", toml)
        if n != 1:
            sys.exit(f"toml: expected one '{label}' row, found {n}")
    block = "".join(f'[[metrics.languages]]\nname = "{name}"\npct = "{pct}"\n'
                    for name, pct in v["langs_list"])
    toml, n = re.subn(r"\[\[metrics\.languages\]\].*?(?=\[skills\])", block + "\n", toml, flags=re.S)
    if n != 1:
        sys.exit(f"toml: expected one languages block, found {n}")
    return toml


def fmt_alt(alt_template: str, v: dict) -> str:
    return alt_template.format(
        total=v["total"], total_range=v["total_range"], streak=v["streak"],
        streak_range=v["streak_range"], stars=v["stars"], commits=v["commits"],
        prs=v["prs"], issues=v["issues"], contributed=v["contributed"],
        langs=", ".join(f"{name} {pct}%" for name, pct in v["langs_list"]))


def patch_readme(readme: str, alt: str) -> str:
    readme, n = re.subn(r'(src="assets/metrics\.svg" width="800" alt=")[^"]*(")',
                        lambda m: m.group(1) + alt + m.group(2), readme)
    if n != 1:
        sys.exit(f"readme: expected one metrics img tag, found {n}")
    return readme


def main() -> None:
    token = os.environ.get("METRICS_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("env: set METRICS_TOKEN (classic PAT with repo scope) to include private contributions")

    v = compute(fetch(token))

    toml = TOML.read_text(encoding="utf-8")
    alt_template = re.search(r'(?m)^alt = "(GitHub Stats.*)"$', toml)
    if not alt_template:
        sys.exit("toml: metrics alt template not found")
    TOML.write_text(patch_toml(toml, v), encoding="utf-8")

    alt = fmt_alt(alt_template.group(1), v)
    svg = SVG.read_text(encoding="utf-8")
    svg, n = re.subn(r'(<desc id="d">)[^<]*(</desc>)',
                     lambda m: m.group(1) + escape(alt) + m.group(2), svg)
    if n != 1:
        sys.exit(f"patch: expected one desc node, found {n}")
    for field in ("total", "total_range", "streak", "streak_range", *STAT_FIELDS.values()):
        svg = set_text(svg, field, v[field])
    track = re.search(r'<rect data-field="lang-track" x="([\d.]+)"[^>]*width="([\d.]+)"', svg)
    if not track:
        sys.exit("patch: language bar track not found")
    seg_x, bw = float(track.group(1)), float(track.group(2))
    for i, (name, pct) in enumerate(v["langs_list"]):
        width = float(pct) / 100 * bw
        svg = set_segment(svg, i, seg_x, width)
        svg = set_text(svg, f"lang-name-{i}", name)
        svg = set_text(svg, f"lang-pct-{i}", f"{pct}%")
        seg_x += width
    SVG.write_text(svg, encoding="utf-8")

    README.write_text(patch_readme(README.read_text(encoding="utf-8"), alt), encoding="utf-8")

    name, pct = v["langs_list"][0]
    print(f"metrics baked: {v['total']} contributions, longest streak {v['streak']} days "
          f"({v['streak_range']}), {v['commits']} commits last year, top language {name} {pct}%")


if __name__ == "__main__":
    main()
