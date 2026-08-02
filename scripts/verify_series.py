# -*- coding: utf-8 -*-
"""
Series verification harness — standard pre-push / pre-batch regression sweep.

Runs every automated content-consistency check against every cuisine with
status: "done" in products/_series-roadmap.json (or against an explicit
list of cuisine ids passed on the CLI):

  1. ingredient coverage   (check_ingredient_coverage)
  2. bundle metadata       (check_bundle_metadata)
  3. gitignore gaps        (check_gitignore_gaps)   — repo-wide, not per-country
  4. template placeholders (check_placeholders)

Does NOT modify anything under products/. Failures are reported for the
content lane to fix.

Usage:
  python scripts/verify_series.py
  python scripts/verify_series.py korean thai french
  python scripts/verify_series.py --list-done
"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import check_bundle_metadata as bundle_meta  # noqa: E402
import check_gitignore_gaps as gitignore_gaps  # noqa: E402
import check_ingredient_coverage as ingredients  # noqa: E402
import check_placeholders as placeholders  # noqa: E402

ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "products"))
ROADMAP = os.path.join(ROOT, "_series-roadmap.json")


def done_cuisine_ids() -> list[str]:
    with open(ROADMAP, encoding="utf-8") as f:
        data = json.load(f)
    return [c["id"] for c in data["cuisines"] if c.get("status") == "done"]


def _section(title: str, issues: list[dict]) -> tuple[str, int]:
    if not issues:
        line = "PASS  %s" % title
        print(line)
        return line, 0
    line = "FAIL  %s — %d issue(s)" % (title, len(issues))
    print(line)
    for iss in issues:
        country = iss.get("country") or "?"
        recipe = iss.get("recipe")
        loc = "%s / %s" % (country, recipe) if recipe else country
        print("  [%s] %s: %s" % (loc, iss.get("kind"), iss.get("detail")))
    return line, len(issues)


def run(cuisine_ids: list[str] | None = None) -> int:
    ids = list(cuisine_ids) if cuisine_ids else done_cuisine_ids()
    print("verify_series — %d countr%s: %s" % (
        len(ids),
        "y" if len(ids) == 1 else "ies",
        ", ".join(ids),
    ))
    print("-" * 60)

    total = 0
    _, n = _section(
        "ingredient coverage",
        ingredients.check_many(ids),
    )
    total += n

    _, n = _section(
        "bundle metadata",
        bundle_meta.check_many(ids),
    )
    total += n

    _, n = _section(
        "gitignore gaps",
        gitignore_gaps.check(),
    )
    total += n

    _, n = _section(
        "template placeholders",
        placeholders.check_many(ids),
    )
    total += n

    print("-" * 60)
    if total == 0:
        print("ALL CHECKS PASSED")
        return 0
    print("FAILED — %d total issue(s). Content lane owns fixes under products/." % total)
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list-done" in argv:
        for cid in done_cuisine_ids():
            print(cid)
        return 0
    ids = [a for a in argv if not a.startswith("-")]
    return run(ids or None)


if __name__ == "__main__":
    sys.exit(main())
