# -*- coding: utf-8 -*-
"""
Repo-bloat / .gitignore gap checker.

Scans products/*/ for directories that look like raw/intermediate photo
folders (photos_raw/, imgs/, img/, b64/, …) and flags any that are NOT
covered by the current root .gitignore — the failure mode that has let
raw photo dumps get committed twice before.

Usage:
  python check_gitignore_gaps.py
"""
from __future__ import annotations

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
PRODUCTS = os.path.join(REPO, "products")
GITIGNORE = os.path.join(REPO, ".gitignore")

# Directory basenames that have historically held raw / intermediate photos.
RAW_LIKE = re.compile(
    r"^(?:"
    r"photos?(?:_raw|_b64|_src|_orig|_original|_tmp|_temp)?"
    r"|imgs?"
    r"|images?(?:_raw|_b64|_src)?"
    r"|b64"
    r"|raw(?:_photos?|_imgs?|_images?)?"
    r"|photo_raw"
    r"|assets_raw"
    r")$",
    re.I,
)


def load_gitignore_patterns() -> list[str]:
    if not os.path.isfile(GITIGNORE):
        return []
    patterns = []
    with open(GITIGNORE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def _glob_to_re(pattern: str) -> re.Pattern:
    """
    Convert a simple gitignore glob (the subset we use: products/*/foo/)
    into a regex matched against repo-relative POSIX paths.
    """
    p = pattern.replace("\\", "/")
    if p.startswith("/"):
        p = p[1:]
    anchored_dir = p.endswith("/")
    if anchored_dir:
        p = p[:-1]

    parts = []
    i = 0
    while i < len(p):
        if p[i] == "*":
            if i + 1 < len(p) and p[i + 1] == "*":
                parts.append(".*")
                i += 2
                if i < len(p) and p[i] == "/":
                    i += 1
                continue
            parts.append("[^/]*")
            i += 1
        elif p[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(p[i]))
            i += 1
    body = "".join(parts)
    if anchored_dir:
        # Match the directory itself or anything inside it.
        rx = r"^" + body + r"(?:/.*)?$"
    else:
        rx = r"^" + body + r"$"
    return re.compile(rx)


def is_ignored(rel_posix: str, patterns: list[str]) -> bool:
    rel = rel_posix.strip("/")
    for pat in patterns:
        # Negation not used in our .gitignore today; skip for simplicity.
        if pat.startswith("!"):
            continue
        if _glob_to_re(pat).match(rel):
            return True
        # Also allow a pattern like "products/*/img/" to cover "products/x/img"
        if not pat.endswith("/") and _glob_to_re(pat + "/").match(rel):
            return True
    return False


def find_raw_like_dirs() -> list[str]:
    found = []
    if not os.path.isdir(PRODUCTS):
        return found
    for country in sorted(os.listdir(PRODUCTS)):
        cpath = os.path.join(PRODUCTS, country)
        if not os.path.isdir(cpath):
            continue
        if not country.endswith("-meal-planner"):
            continue
        for name in os.listdir(cpath):
            sub = os.path.join(cpath, name)
            if not os.path.isdir(sub):
                continue
            if RAW_LIKE.match(name):
                rel = "products/%s/%s" % (country, name)
                found.append(rel.replace("\\", "/"))
    return found


def check() -> list[dict]:
    patterns = load_gitignore_patterns()
    issues = []
    for rel in find_raw_like_dirs():
        if is_ignored(rel, patterns) or is_ignored(rel + "/", patterns):
            continue
        issues.append({
            "country": rel.split("/")[1].replace("-meal-planner", ""),
            "kind": "gitignore_gap",
            "detail": (
                "%s/ looks like a raw-photo folder but is not covered by "
                ".gitignore — add a pattern before it gets committed" % rel
            ),
            "path": rel,
        })
    return issues


def main(_argv: list[str] | None = None) -> int:
    issues = check()
    if not issues:
        print("PASS  gitignore gaps (no uncovered raw-photo-like folders)")
        return 0
    print("FAIL  gitignore gaps — %d issue(s)" % len(issues))
    for iss in issues:
        print("  [%s] %s: %s" % (iss["country"], iss["kind"], iss["detail"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
