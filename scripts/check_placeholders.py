# -*- coding: utf-8 -*-
"""
Template placeholder checker.

Greps generated HTML under products/*/ for leftover Mustache-style
`{{...}}` tokens (and a few known unreplaced template sentinels like
`Bundle NN`). France once shipped etsy-price-research.html with an
unreplaced `{{slug}}`; this is the regression net for that class of bug.

Usage:
  python check_placeholders.py              # all status:done countries
  python check_placeholders.py french jamaican
"""
from __future__ import annotations

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "products"))
ROADMAP = os.path.join(ROOT, "_series-roadmap.json")

PLACEHOLDER_RE = re.compile(
    r"\{\{\s*[^}]+\s*\}\}"           # {{COUNTRY}}, {{slug}}, …
    r"|Bundle\s+NN\b"                # card-template sentinel
    r"|\$\{\{[A-Za-z0-9_]+\}\}"      # ${{PRICE}} style
    , re.I,
)

# HTML files we expect to be fully filled in per country.
HTML_NAMES = (
    "preview.html",
    "etsy-price-research.html",
)


def done_cuisine_ids() -> list[str]:
    with open(ROADMAP, encoding="utf-8") as f:
        data = json.load(f)
    return [c["id"] for c in data["cuisines"] if c.get("status") == "done"]


def folder_for(cuisine_id: str) -> str:
    return os.path.join(ROOT, cuisine_id + "-meal-planner")


def _strip_html_comments(text: str) -> str:
    """Remove <!-- ... --> so template-instruction comments don't false-positive."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _scan_file(path: str) -> list[str]:
    """Return unique placeholder token strings found in the file."""
    hits: list[str] = []
    seen = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        return ["<read error: %s>" % e]

    # Drop base64 payloads and HTML comments before scanning.
    raw = re.sub(
        r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+",
        "data:image/elided",
        raw,
    )
    raw = _strip_html_comments(raw)

    for m in PLACEHOLDER_RE.finditer(raw):
        tok = m.group(0)
        if tok not in seen:
            seen.add(tok)
            hits.append(tok)
    return hits


def check_country(cuisine_id: str) -> list[dict]:
    issues: list[dict] = []
    folder = folder_for(cuisine_id)
    if not os.path.isdir(folder):
        return [{
            "country": cuisine_id,
            "kind": "missing_folder",
            "detail": "products/%s-meal-planner/ not found" % cuisine_id,
        }]

    # Deliverable HTML only — skip scratch/template copies like
    # preview-template.html / new_cards.html (those are allowed to still
    # carry placeholders while being assembled).
    names = set(HTML_NAMES)

    for name in sorted(names):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            # preview / etsy missing is a content-lane problem; report lightly.
            if name in HTML_NAMES:
                issues.append({
                    "country": cuisine_id,
                    "kind": "missing_html",
                    "detail": "%s not found" % name,
                    "file": name,
                })
            continue
        for tok in _scan_file(path):
            issues.append({
                "country": cuisine_id,
                "kind": "unreplaced_placeholder",
                "detail": "%s still contains %s" % (name, tok),
                "file": name,
                "token": tok,
            })
    return issues


def check_many(cuisine_ids: list[str] | None = None) -> list[dict]:
    ids = cuisine_ids or done_cuisine_ids()
    issues: list[dict] = []
    for cid in ids:
        issues.extend(check_country(cid))
    return issues


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ids = argv or done_cuisine_ids()
    issues = check_many(ids if argv else None)
    if not issues:
        print("PASS  placeholders (%d countries)" % len(ids))
        return 0
    print("FAIL  placeholders — %d issue(s)" % len(issues))
    for iss in issues:
        print("  [%s] %s: %s" % (iss["country"], iss["kind"], iss["detail"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
