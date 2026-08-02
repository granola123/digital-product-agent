# -*- coding: utf-8 -*-
"""
Bundle metadata consistency checker for preview.html files.

Recurring bugs this catches:
  (a) Eyebrow "Bundle NN" and footer "Bundle NN" desync within one file,
      or the set of bundle numbers across status:done countries has gaps
      in the 01..N sequence.
  (b) --chili / --turmeric / --lemongrass hex values still exactly match
      Thailand's original palette (copy-paste that was never retinted).
  (c) .tag.easy / .tag.medium background uses a hardcoded rgba() instead
      of var()/color-mix referencing the CSS custom properties.

Usage:
  python check_bundle_metadata.py              # all status:done countries
  python check_bundle_metadata.py korean thai
"""
from __future__ import annotations

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "products"))
ROADMAP = os.path.join(ROOT, "_series-roadmap.json")

# Thailand pilot originals — any non-Thai country still carrying all three
# is almost certainly an unretinted copy-paste.
THAI_PALETTE = {
    "--chili": "#D6472B",
    "--turmeric": "#D9A438",
    "--lemongrass": "#7C8C5E",
}

BUNDLE_RE = re.compile(r"Bundle\s+(NN|\d+)", re.I)
VAR_RE = re.compile(
    r"(--chili|--turmeric|--lemongrass)\s*:\s*(#[0-9A-Fa-f]{3,8})",
)
TAG_RULE_RE = re.compile(
    r"\.tag\.(easy|medium)\s*\{([^}]*)\}",
    re.I | re.S,
)


def done_cuisine_ids() -> list[str]:
    with open(ROADMAP, encoding="utf-8") as f:
        data = json.load(f)
    return [c["id"] for c in data["cuisines"] if c.get("status") == "done"]


def folder_for(cuisine_id: str) -> str:
    return os.path.join(ROOT, cuisine_id + "-meal-planner")


def _read_preview(cuisine_id: str) -> str | None:
    path = os.path.join(folder_for(cuisine_id), "preview.html")
    if not os.path.isfile(path):
        return None
    # preview.html can be huge (base64 photos). We only need the head/CSS
    # and the footer — read in chunks and keep the non-base64 parts.
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    # Drop enormous data-URI payloads so regex stays cheap.
    text = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "data:image/elided", text)
    return text


def extract_bundle_numbers(text: str) -> tuple[str | None, str | None]:
    """Return (eyebrow_num, footer_num) as digit strings or 'NN' or None."""
    eyebrow = None
    footer = None
    # Eyebrow line near the top.
    m = re.search(r'class="eyebrow"[^>]*>\s*([^<]*Bundle\s+(NN|\d+)[^<]*)', text, re.I)
    if m:
        eyebrow = m.group(2)
    else:
        # Fallback: first Bundle mention in the file.
        m = BUNDLE_RE.search(text)
        if m:
            eyebrow = m.group(1)

    # Footer note — prefer the foot-note block.
    foot = re.search(r'class="foot-note"[^>]*>(.*?)</footer>', text, re.I | re.S)
    region = foot.group(1) if foot else text
    matches = list(BUNDLE_RE.finditer(region))
    if matches:
        footer = matches[0].group(1)
    elif eyebrow is not None:
        # If we already consumed the only match as eyebrow, look for a second.
        all_m = list(BUNDLE_RE.finditer(text))
        if len(all_m) >= 2:
            footer = all_m[1].group(1)
    return eyebrow, footer


def extract_palette(text: str) -> dict[str, str]:
    found = {}
    for m in VAR_RE.finditer(text):
        found[m.group(1).lower()] = m.group(2).upper()
    return found


def tag_rgba_issues(text: str) -> list[str]:
    issues = []
    for m in TAG_RULE_RE.finditer(text):
        level = m.group(1).lower()
        body = m.group(2)
        bg = re.search(r"background\s*:\s*([^;]+);", body, re.I)
        if not bg:
            continue
        val = bg.group(1).strip()
        # Acceptable: uses var(…) or color-mix(… var(…))
        if "var(" in val:
            continue
        if re.search(r"rgba?\s*\(", val, re.I):
            issues.append(
                ".tag.%s background uses hardcoded %s (not var())" % (level, val)
            )
    return issues


def check_country(cuisine_id: str) -> list[dict]:
    issues: list[dict] = []
    text = _read_preview(cuisine_id)
    if text is None:
        return [{
            "country": cuisine_id,
            "kind": "missing_preview",
            "detail": "preview.html not found",
        }]

    eyebrow, footer = extract_bundle_numbers(text)
    if eyebrow is None and footer is None:
        issues.append({
            "country": cuisine_id,
            "kind": "bundle_missing",
            "detail": "no 'Bundle NN' found in eyebrow or footer",
        })
    elif eyebrow is None or footer is None:
        issues.append({
            "country": cuisine_id,
            "kind": "bundle_partial",
            "detail": "eyebrow=%r footer=%r (one side missing)" % (eyebrow, footer),
        })
    elif eyebrow.upper() == "NN" or footer.upper() == "NN":
        issues.append({
            "country": cuisine_id,
            "kind": "bundle_placeholder",
            "detail": "unreplaced Bundle NN placeholder (eyebrow=%r footer=%r)" % (
                eyebrow, footer
            ),
        })
    elif eyebrow != footer:
        issues.append({
            "country": cuisine_id,
            "kind": "bundle_mismatch",
            "detail": "eyebrow Bundle %s != footer Bundle %s" % (eyebrow, footer),
        })

    palette = extract_palette(text)
    thai_norm = {k: v.upper() for k, v in THAI_PALETTE.items()}
    if cuisine_id != "thai" and all(
        palette.get(k, "").upper() == thai_norm[k] for k in thai_norm
    ):
        issues.append({
            "country": cuisine_id,
            "kind": "palette_is_thailand",
            "detail": (
                "--chili/--turmeric/--lemongrass exactly match Thailand's "
                "original %s / %s / %s" % (
                    THAI_PALETTE["--chili"],
                    THAI_PALETTE["--turmeric"],
                    THAI_PALETTE["--lemongrass"],
                )
            ),
        })

    for detail in tag_rgba_issues(text):
        issues.append({
            "country": cuisine_id,
            "kind": "tag_hardcoded_rgba",
            "detail": detail,
        })

    return issues


def check_sequence(cuisine_ids: list[str], per_country_issues: list[dict]) -> list[dict]:
    """Flag gaps in the 01..N numbering across the given (done) countries."""
    # Skip countries that already failed to produce a usable number.
    broken = {
        i["country"] for i in per_country_issues
        if i["kind"] in {
            "bundle_missing", "bundle_partial", "bundle_placeholder",
            "bundle_mismatch", "missing_preview",
        }
    }
    numbers: list[tuple[str, int]] = []
    for cid in cuisine_ids:
        if cid in broken:
            continue
        text = _read_preview(cid)
        if not text:
            continue
        eyebrow, footer = extract_bundle_numbers(text)
        num_s = eyebrow or footer
        if not num_s or not str(num_s).isdigit():
            continue
        numbers.append((cid, int(num_s)))

    issues: list[dict] = []
    if not numbers:
        return issues

    by_num: dict[int, list[str]] = {}
    for cid, n in numbers:
        by_num.setdefault(n, []).append(cid)

    for n, cids in sorted(by_num.items()):
        if len(cids) > 1:
            issues.append({
                "country": "*",
                "kind": "bundle_duplicate",
                "detail": "Bundle %02d used by %s" % (n, ", ".join(cids)),
            })

    expected = list(range(1, len(cuisine_ids) + 1))
    present = set(by_num)
    for n in expected:
        if n not in present:
            issues.append({
                "country": "*",
                "kind": "bundle_gap",
                "detail": "Bundle %02d missing from status:done sequence (expected 01..%02d)" % (
                    n, len(cuisine_ids)
                ),
            })

    extras = sorted(present - set(expected))
    for n in extras:
        issues.append({
            "country": "*",
            "kind": "bundle_extra",
            "detail": "Bundle %02d present but outside expected 01..%02d for %d done countries" % (
                n, len(cuisine_ids), len(cuisine_ids)
            ),
        })
    return issues


def check_many(cuisine_ids: list[str] | None = None) -> list[dict]:
    ids = cuisine_ids or done_cuisine_ids()
    issues: list[dict] = []
    for cid in ids:
        issues.extend(check_country(cid))
    issues.extend(check_sequence(ids, issues))
    return issues


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ids = argv or done_cuisine_ids()
    issues = check_many(ids if argv else None)
    if not issues:
        print("PASS  bundle metadata (%d countries)" % len(ids))
        return 0
    print("FAIL  bundle metadata — %d issue(s)" % len(issues))
    for iss in issues:
        print("  [%s] %s: %s" % (iss["country"], iss["kind"], iss["detail"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
