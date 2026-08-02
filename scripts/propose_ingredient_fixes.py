# -*- coding: utf-8 -*-
"""
Propose pantry-staple ingredient rows for recipes.json gaps.

Reads the live findings from check_ingredient_coverage (step_missing_from_table
only), then for each (country, dish, missing_ingredient) looks at sibling
ingredient rows in that country's recipes.json to infer name + 1/2/3/4-serving
quantities. Writes a human-reviewable markdown report — never edits products/.

Usage:
  python scripts/propose_ingredient_fixes.py
  python scripts/propose_ingredient_fixes.py --out scripts/ingredient_fix_proposals.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import check_ingredient_coverage as coverage  # noqa: E402

ROOT = coverage.ROOT
DEFAULT_OUT = os.path.join(SCRIPT_DIR, "ingredient_fix_proposals.md")

# Staples we propose rows for (matches the confirmed bug class).
TARGET_KEYS = {"salt", "pepper", "black pepper", "white pepper", "oil", "butter"}

# Classify a table row's first cell into a pantry family.
_FAMILY_PATTERNS = [
    ("salt", re.compile(r"\bsalt\b", re.I)),
    ("black_pepper", re.compile(r"\bblack\s+pepper\b", re.I)),
    ("white_pepper", re.compile(r"\bwhite\s+pepper\b", re.I)),
    ("pepper", re.compile(r"\bpepper\b", re.I)),
    ("sesame_oil", re.compile(r"\bsesame\s+oil\b", re.I)),
    ("olive_oil", re.compile(r"\bolive\s+oil\b", re.I)),
    ("coconut_oil", re.compile(r"\bcoconut\s+oil\b", re.I)),
    ("neutral_oil", re.compile(r"\b(?:neutral|vegetable|cooking|canola|peanut)\s+oil\b", re.I)),
    ("oil", re.compile(r"\boil\b", re.I)),
    ("butter", re.compile(r"\bbutter\b", re.I)),
]

_TO_TASTE = re.compile(
    r"to\s+taste|pinch|as\s+needed|for\s+(?:seasoning|frying|greasing)|optional",
    re.I,
)


def _mention_from_issue(iss: dict) -> str | None:
    m = re.search(r"steps mention '([^']+)'", iss.get("detail") or "")
    return m.group(1) if m else None


def _family_for_mention(mention: str) -> str:
    m = coverage._norm(mention)
    if m in {"salt", "kosher salt", "sea salt"}:
        return "salt"
    if m == "black pepper":
        return "black_pepper"
    if m == "white pepper":
        return "white_pepper"
    if m == "pepper":
        return "pepper"
    if m == "butter":
        return "butter"
    if "sesame" in m:
        return "sesame_oil"
    if "olive" in m:
        return "olive_oil"
    if "coconut" in m:
        return "coconut_oil"
    if m == "oil" or m.endswith(" oil"):
        return "oil"
    return m.replace(" ", "_")


def _row_family(name: str) -> str | None:
    n = name.lower()
    # Non-seasoning / non-cooking-fat phrases that contain the keywords.
    if re.search(
        r"oil-?packed|packed in oil|butter lettuce|peanut butter|"
        r"shea butter|cocoa butter|buttermilk",
        n,
    ):
        return None
    for fam, rx in _FAMILY_PATTERNS:
        if rx.search(name):
            # Avoid "bell pepper" counting as pepper seasoning.
            if fam in {"pepper", "black_pepper", "white_pepper"}:
                if re.search(r"\b(?:bell|chili|chilli|sweet)\s+pepper", name, re.I):
                    continue
                if re.search(r"\bpeppers?\b", name, re.I) and not re.search(
                    r"\b(?:black|white|ground)\s+pepper\b|\bpepper\b", name, re.I
                ):
                    continue
                # "Salt & pepper" is a combined row — counts for both families
                # via the salt and pepper patterns; allow it.
            return fam
    return None


def _clean_name(name: str) -> str:
    return (
        name.replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .strip()
    )

def _load_recipes(cuisine_id: str) -> list[dict]:
    path = os.path.join(coverage.folder_for(cuisine_id), "recipes.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("recipes") or []


def _table_rows(recipe: dict) -> list[list]:
    rows = []
    for section in recipe.get("sections") or []:
        if section.get("type") == "table":
            rows.extend(section.get("rows") or [])
    return rows


def _qty_signature(cols: list[str]) -> str:
    """Normalize quantity cells for frequency counting."""
    parts = []
    for c in cols:
        s = (c or "").strip().lower().replace("½", "1/2").replace("¼", "1/4")
        s = s.replace("¾", "3/4").replace("⅓", "1/3").replace("⅔", "2/3")
        s = re.sub(r"\s+", " ", s)
        parts.append(s)
    return " | ".join(parts)


def _is_fixed_style(cols: list[str]) -> bool:
    """True when all four servings share the same non-scaling label."""
    norms = [_qty_signature([c]) for c in cols]
    if len(set(norms)) != 1:
        return False
    return bool(_TO_TASTE.search(cols[0] or "")) or norms[0] in {
        "pinch", "to taste", "as needed", "—", "-", ""
    }


def collect_country_patterns(cuisine_id: str) -> dict:
    """
    Gather every salt/oil/pepper/butter row in this country's recipes.json,
    keyed by family, with frequency of (name, qty signature).
    """
    by_family: dict[str, list[dict]] = defaultdict(list)
    for recipe in _load_recipes(cuisine_id):
        rid = recipe.get("id") or recipe.get("title") or "?"
        for row in _table_rows(recipe):
            if not row or len(row) < 5:
                continue
            name = _clean_name(str(row[0]))
            fam = _row_family(name)
            if not fam:
                continue
            cols = [str(row[i]).strip() for i in range(1, 5)]
            by_family[fam].append({
                "recipe": rid,
                "name": name,
                "cols": cols,
                "sig": _qty_signature(cols),
                "fixed": _is_fixed_style(cols),
            })
    return by_family


def _pick_pattern(family: str, patterns: dict, dish_rows: list[list], steps_text: str = "") -> dict | None:
    """
    Choose the best sibling row to mirror.

    Preference order:
      1. Most common (name, qty) pair for that family in the country
      2. For oil: prefer saute-scale quantities when steps aren't deep-frying
    """
    aliases = {
        "salt": ["salt"],
        "pepper": ["black_pepper", "pepper", "white_pepper"],
        "black_pepper": ["black_pepper", "pepper"],
        "white_pepper": ["white_pepper", "pepper"],
        "oil": ["neutral_oil", "oil", "olive_oil", "sesame_oil", "coconut_oil"],
        "sesame_oil": ["sesame_oil", "neutral_oil", "oil"],
        "olive_oil": ["olive_oil", "neutral_oil", "oil"],
        "coconut_oil": ["coconut_oil", "neutral_oil", "oil"],
        "butter": ["butter"],
    }
    keys = aliases.get(family, [family])

    candidates = []
    for k in keys:
        candidates.extend(patterns.get(k, []))
    if not candidates:
        return None

    # Oil scale filter: "lightly oil the pan" should not inherit churro deep-fry ml.
    if family == "oil" and steps_text:
        deep = bool(re.search(r"deep[- ]fry|pot of oil|inches? of oil", steps_text, re.I))
        if not deep:
            saute_like = [
                c for c in candidates
                if not re.search(r"for frying|deep", c["name"], re.I)
                and not _looks_like_deep_fry_qty(c["cols"])
            ]
            if saute_like:
                candidates = saute_like

    name_counts = Counter(c["name"] for c in candidates)
    sig_counts = Counter(c["sig"] for c in candidates)
    fixed_n = sum(1 for c in candidates if c["fixed"])
    scaled_n = len(candidates) - fixed_n

    prefer_fixed = family == "salt" and fixed_n > scaled_n

    pool = [c for c in candidates if c["fixed"] == prefer_fixed] if family == "salt" else candidates
    if not pool:
        pool = candidates

    sig_counts_pool = Counter(c["sig"] for c in pool)
    best_sig, _ = sig_counts_pool.most_common(1)[0]
    with_sig = [c for c in pool if c["sig"] == best_sig]
    name_counts_sig = Counter(c["name"] for c in with_sig)
    best_name, _ = name_counts_sig.most_common(1)[0]
    exemplar = next(c for c in with_sig if c["name"] == best_name)

    return {
        "name": exemplar["name"],
        "cols": list(exemplar["cols"]),
        "exemplar_recipe": exemplar["recipe"],
        "exemplar_name": exemplar["name"],
        "count_same_sig": sig_counts_pool[best_sig],
        "total_family": len(candidates),
        "prefer_fixed": prefer_fixed,
        "fixed_n": fixed_n,
        "scaled_n": scaled_n,
        "name_diversity": len(name_counts),
        "sig_diversity": len(sig_counts),
    }


def _looks_like_deep_fry_qty(cols: list[str]) -> bool:
    """True if 1-serving qty looks like a vat of oil (>= 100ml / 1 cup)."""
    s = (cols[0] or "").lower().replace(" ", "")
    m = re.match(r"(\d+(?:\.\d+)?)\s*(ml|g|cup)?", s)
    if not m:
        return False
    n = float(m.group(1))
    unit = m.group(2) or ""
    if unit == "cup" and n >= 0.5:
        return True
    if unit in {"ml", "g", ""} and n >= 100:
        return True
    return False


def _infer_oil_name_from_steps(steps_text: str, fallback_name: str) -> str:
    """If steps say 'sesame oil' / 'olive oil' etc., prefer that label."""
    lower = steps_text.lower()
    for label in (
        "sesame oil", "olive oil", "coconut oil", "peanut oil",
        "vegetable oil", "canola oil", "neutral oil", "cooking oil",
    ):
        if re.search(r"(?<![a-z])" + re.escape(label) + r"(?![a-z])", lower):
            # Title-case lightly
            return label[0].upper() + label[1:]
    return fallback_name


def _step_context(recipe: dict, mention: str) -> str:
    steps = []
    for section in recipe.get("sections") or []:
        if section.get("type") == "steps":
            steps.extend(section.get("items") or [])
    usable = [s for s in steps if not coverage._RINSE_LINE.search(s)]
    hits = [s for s in usable if coverage.text_mentions(s, [mention])]
    return hits[0] if hits else (usable[0] if usable else "")


def propose_for_issue(iss: dict, patterns_cache: dict) -> dict:
    country = iss["country"]
    rid = iss.get("recipe")
    mention = _mention_from_issue(iss)
    out = {
        "country": country,
        "recipe": rid,
        "mention": mention,
        "status": "needs_manual_judgment",
        "proposed_row": None,
        "rationale": "",
        "step_quote": "",
    }
    if not mention or coverage._norm(mention) not in {
        coverage._norm(t) for t in TARGET_KEYS
    } and coverage._norm(mention) not in {
        "oil", "salt", "pepper", "black pepper", "white pepper", "butter"
    }:
        # Still handle oil/salt/pepper
        pass
    if not mention:
        out["rationale"] = "Could not parse missing ingredient from checker detail."
        return out

    recipes = _load_recipes(country)
    recipe = next((r for r in recipes if r.get("id") == rid), None)
    if recipe is None:
        out["rationale"] = "Recipe id %r not found in recipes.json." % rid
        return out

    out["step_quote"] = _step_context(recipe, mention)
    family = _family_for_mention(mention)
    patterns = patterns_cache[country]
    picked = _pick_pattern(
        family, patterns, _table_rows(recipe), steps_text=_all_steps(recipe)
    )

    if not picked:
        out["rationale"] = (
            "No sibling %s/%s/%s rows found anywhere in this country's "
            "recipes.json — needs manual judgment."
            % ("salt", "pepper", "oil")
        )
        return out

    # Low confidence only when the winning qty pattern is a singleton among
    # many disagreeing siblings (no real convention). A single clear sibling
    # in the whole country is still a usable convention — propose it.
    low_confidence = (
        picked["sig_diversity"] >= 3 and picked["count_same_sig"] == 1
        and picked["total_family"] >= 3
    )

    name = _clean_name(picked["name"])
    # When the flag was bare "oil", prefer a generic cooking-oil label if the
    # exemplar is a specialty oil the steps don't mention.
    if family == "oil" and re.search(r"sesame|chili|chilli|flavou?red", name, re.I):
        generics = [
            c for c in patterns.get("neutral_oil", []) + patterns.get("oil", [])
            if not re.search(r"sesame|chili|chilli|flavou?red", c["name"], re.I)
        ]
        if generics:
            sig_counts = Counter(c["sig"] for c in generics)
            best_sig = sig_counts.most_common(1)[0][0]
            g = next(c for c in generics if c["sig"] == best_sig)
            name = _clean_name(g["name"])
            picked["cols"] = list(g["cols"])
            picked["exemplar_recipe"] = g["recipe"]
            picked["exemplar_name"] = g["name"]
        else:
            name = "Neutral oil"
            low_confidence = True

    if family == "oil":
        name = _infer_oil_name_from_steps(_all_steps(recipe), name)

    # Combined "Salt & pepper" sibling → split to the staple we actually need.
    if family == "salt" and re.search(r"pepper", name, re.I):
        name = "Salt"
    if family in {"pepper", "black_pepper"} and re.search(r"salt", name, re.I):
        name = "Black pepper" if "black" in (picked["exemplar_name"] or "").lower() or coverage._norm(mention) == "black pepper" else "Pepper"

    # Pepper: if mention was "black pepper", prefer that name form.
    if coverage._norm(mention) == "black pepper" and "black" not in name.lower():
        name = "Black pepper"

    only = picked["total_family"] == 1
    row = [name] + picked["cols"]
    rationale = (
        "Mirrored `%s` quantities from `%s` (%s/%s sibling %s rows use this "
        "qty pattern%s%s)."
        % (
            _clean_name(picked["exemplar_name"]),
            picked["exemplar_recipe"],
            picked["count_same_sig"],
            picked["total_family"],
            family,
            "; country prefers fixed/to-taste salt" if picked.get("prefer_fixed")
            else ("; country prefers scaled salt" if family == "salt" else ""),
            "; only sibling of this family in the file" if only else "",
        )
    )

    if low_confidence:
        out["status"] = "needs_manual_judgment"
        out["proposed_row"] = row
        out["rationale"] = (
            "LOW CONFIDENCE — weak sibling signal. Tentative row shown; "
            "confirm before applying. " + rationale
        )
        return out

    out["status"] = "proposed"
    out["proposed_row"] = row
    out["rationale"] = rationale
    return out


def _all_steps(recipe: dict) -> str:
    parts = []
    for section in recipe.get("sections") or []:
        if section.get("type") == "steps":
            parts.extend(section.get("items") or [])
    return "\n".join(parts)


def _fmt_row(row: list[str]) -> str:
    return "`[%s]`" % ", ".join(json.dumps(c, ensure_ascii=False) for c in row)


def render_report(proposals: list[dict], skipped: list[dict]) -> str:
    by_country: dict[str, list[dict]] = defaultdict(list)
    for p in proposals:
        by_country[p["country"]].append(p)

    proposed_n = sum(1 for p in proposals if p["status"] == "proposed")
    manual_n = sum(1 for p in proposals if p["status"] == "needs_manual_judgment")

    lines = []
    lines.append("# Ingredient fix proposals")
    lines.append("")
    lines.append(
        "Auto-generated by `scripts/propose_ingredient_fixes.py` from "
        "`check_ingredient_coverage` findings. **Proposal only** — do not "
        "treat this as applied. Content lane reviews and edits `recipes.json`."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| | count |")
    lines.append("|---|---:|")
    lines.append("| Proposed rows (confident) | %d |" % proposed_n)
    lines.append("| Needs manual judgment | %d |" % manual_n)
    lines.append("| Skipped (non-row issues, e.g. missing recipes.json) | %d |" % len(skipped))
    lines.append("| Countries with proposals | %d |" % len(by_country))
    lines.append("")
    lines.append(
        "Each proposed row is the JSON array to append to that recipe's "
        "ingredients `table.rows`: "
        "`[name, qty_1_serving, qty_2, qty_3, qty_4]`."
    )
    lines.append("")

    if skipped:
        lines.append("## Skipped")
        lines.append("")
        for s in skipped:
            lines.append(
                "- **%s** — `%s`: %s"
                % (s["country"], s.get("kind"), s.get("detail"))
            )
        lines.append("")

    for country in sorted(by_country):
        items = by_country[country]
        lines.append("## %s" % country)
        lines.append("")
        for p in items:
            status = p["status"]
            badge = "PROPOSED" if status == "proposed" else "NEEDS MANUAL JUDGMENT"
            lines.append("### `%s` — add **%s** · %s" % (
                p["recipe"], p["mention"], badge
            ))
            lines.append("")
            if p.get("step_quote"):
                lines.append("> %s" % p["step_quote"].replace("\n", " "))
                lines.append("")
            if p.get("proposed_row"):
                lines.append("- **Row:** %s" % _fmt_row(p["proposed_row"]))
            else:
                lines.append("- **Row:** _(none)_")
            lines.append("- **Rationale:** %s" % p["rationale"])
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Tooling notes (`build_book.py`)")
    lines.append("")
    lines.append(
        "`scripts/build_book.py` already loads the country list dynamically "
        "from `products/_series-roadmap.json` via `done_countries()` — no "
        "hardcoded cuisine list or stale series size. Chapter numbers and "
        "cover `{n}` stats use `len(country_data)`. The cover recipe count "
        "now tallies `.recipe-card` nodes from each gallery (fallback: "
        "`n * 8` only if none are found). `REFERENCE_COUNTRY = "
        "\"korean-meal-planner\"` is intentional (shared CSS/reference "
        "chapter), not a series-size assumption."
    )
    lines.append("")
    lines.append(
        "Full book HTML→PDF pipeline was **not** run here (needs "
        "`agent-browser`); only the script source was reviewed/updated."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_Regenerate anytime with_ "
        "`python scripts/propose_ingredient_fixes.py`."
    )
    lines.append("")
    return "\n".join(lines)


def run(out_path: str) -> tuple[int, int]:
    issues = coverage.check_many()
    skipped = []
    targets = []
    for iss in issues:
        if iss.get("kind") != "step_missing_from_table":
            skipped.append(iss)
            continue
        mention = _mention_from_issue(iss)
        if not mention:
            skipped.append(iss)
            continue
        targets.append(iss)

    countries = sorted({t["country"] for t in targets})
    patterns_cache = {c: collect_country_patterns(c) for c in countries}

    proposals = [propose_for_issue(t, patterns_cache) for t in targets]
    report = render_report(proposals, skipped)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    proposed_n = sum(1 for p in proposals if p["status"] == "proposed")
    manual_n = sum(1 for p in proposals if p["status"] == "needs_manual_judgment")
    return proposed_n, manual_n


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out_path = DEFAULT_OUT
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
    proposed_n, manual_n = run(out_path)
    print("Wrote %s" % out_path)
    print("Proposed: %d  |  Needs manual judgment: %d" % (proposed_n, manual_n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
