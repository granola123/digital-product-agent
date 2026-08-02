# -*- coding: utf-8 -*-
"""
Ingredient-coverage checker.

Flags recipe steps (and draft-en.md ingredient tables / steps) that mention
an ingredient absent from that recipe's scaled ingredient table in
recipes.json. The recurring bug: pantry staples (oil, salt, pepper, …) get
dropped from recipes.json while draft-en.md and the step text still use them.

Usage:
  python check_ingredient_coverage.py              # all status:done countries
  python check_ingredient_coverage.py korean indian
"""
from __future__ import annotations

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "products"))
ROADMAP = os.path.join(ROOT, "_series-roadmap.json")

# Pantry staples that steps commonly reference and scaled tables drop.
# Longer phrases first so "sesame oil" / "black pepper" win over bare forms.
# Deliberately excludes water/stock/broth/sugar — those appear in rinse /
# "adjust to taste" phrasing constantly and drown out the real signal
# (oil / salt / pepper), which is the bug class that keeps recurring.
PANTRY_PHRASES = [
    "vegetable oil",
    "cooking oil",
    "olive oil",
    "sesame oil",
    "neutral oil",
    "canola oil",
    "coconut oil",
    "peanut oil",
    "black pepper",
    "white pepper",
    "kosher salt",
    "sea salt",
    "butter",
    "oil",
    "salt",
    "pepper",
]

# "adjust salt" / "season with salt" / "pinch of salt" count; bare "salt"
# inside "salted" does not (word-boundary match handles that).
# Skip step lines that are clearly about rinsing, not adding an ingredient.
_RINSE_LINE = re.compile(
    r"\b(?:rinse|drain|wash|pat dry|wipe)\b",
    re.I,
)

# Words that appear in steps constantly but aren't ingredients.
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "until", "about", "into", "from", "your", "them", "then", "this", "that",
    "heat", "cook", "add", "stir", "mix", "pour", "serve", "bowl", "pan",
    "pot", "wok", "minutes", "minute", "seconds", "hour", "hours", "medium",
    "high", "low", "over", "under", "each", "every", "piece", "pieces",
    "large", "small", "little", "more", "less", "just", "once", "again",
}


def done_cuisine_ids() -> list[str]:
    with open(ROADMAP, encoding="utf-8") as f:
        data = json.load(f)
    return [c["id"] for c in data["cuisines"] if c.get("status") == "done"]


def folder_for(cuisine_id: str) -> str:
    return os.path.join(ROOT, cuisine_id + "-meal-planner")


def _norm(s: str) -> str:
    s = s.lower()
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parentheticals
    s = re.sub(r"[^a-z0-9\s\-'/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _head_terms(ingredient_cell: str) -> set[str]:
    """
    Derive matchable phrases from an ingredient-table first cell.
    'Beef ribeye or sirloin, thinly sliced' -> {'beef ribeye or sirloin',
    'beef ribeye', 'beef', ...} (bounded).
    """
    base = _norm(ingredient_cell.split(",")[0])
    if not base:
        return set()
    out = {base}
    # Also keep the first 1–3 tokens as shorter aliases when useful.
    tokens = [t for t in base.replace("/", " ").split() if t and t not in _STOP]
    if tokens:
        out.add(tokens[0])
        if len(tokens) >= 2:
            out.add(" ".join(tokens[:2]))
        if len(tokens) >= 3:
            out.add(" ".join(tokens[:3]))
    return {t for t in out if len(t) >= 3 or t in {"oil", "salt"}}


def table_phrases(rows: list) -> set[str]:
    phrases: set[str] = set()
    for row in rows or []:
        if not row:
            continue
        phrases |= _head_terms(str(row[0]))
    return phrases


def text_mentions(text: str, phrases: list[str]) -> list[str]:
    """Return which of `phrases` appear as whole-word-ish matches in text."""
    norm = _norm(text)
    hit = []
    for p in phrases:
        pn = _norm(p)
        if not pn:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(pn) + r"(?![a-z0-9])", norm):
            hit.append(p)
    return hit


def covered_by_table(mention: str, table: set[str]) -> bool:
    m = _norm(mention)
    if m in table:
        return True
    # 'sesame oil' covered if table has 'sesame oil'; bare 'oil' covered
    # only by a table phrase that is exactly oil or ends with ' oil'.
    for t in table:
        if m == t or m in t or t in m:
            # Avoid 'salt' matching 'salamander' etc. — require token boundary
            if re.search(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", t):
                return True
            if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", m):
                return True
    if m == "oil":
        return any(t == "oil" or t.endswith(" oil") for t in table)
    if m in {"pepper", "black pepper", "white pepper"}:
        return any("pepper" in t for t in table)
    if m in {"salt", "kosher salt", "sea salt"}:
        return any(t == "salt" or t.endswith(" salt") or "salt" == t for t in table)
    return False


def parse_draft_recipes(draft_path: str) -> list[dict]:
    """
    Pull recipe blocks from draft-en.md: heading, ingredient-table rows,
    and numbered steps. Best-effort — drafts vary slightly by country.
    """
    if not os.path.isfile(draft_path):
        return []
    with open(draft_path, encoding="utf-8") as f:
        text = f.read()

    # Split on ### N. Title headings inside Recipe Cards section when present.
    parts = re.split(r"\n(?=###\s+\d+\.)", text)
    recipes = []
    for part in parts:
        m = re.match(r"###\s+\d+\.\s+(.+)", part)
        if not m:
            continue
        title = m.group(1).strip()
        ings = []
        # Markdown table rows: | name | qty | ... |
        for row in re.findall(r"^\|\s*([^|]+?)\s*\|", part, flags=re.M):
            cell = row.strip()
            if not cell or cell.lower() in {"ingredient", "---", ":---"}:
                continue
            if set(cell) <= set("-: "):
                continue
            ings.append(cell)
        steps = re.findall(r"^\d+\.\s+(.+)$", part, flags=re.M)
        recipes.append({
            "title": title,
            "ingredients": ings,
            "steps": steps,
        })
    return recipes


def check_country(cuisine_id: str) -> list[dict]:
    """Return a list of issue dicts for one country."""
    folder = folder_for(cuisine_id)
    recipes_path = os.path.join(folder, "recipes.json")
    draft_path = os.path.join(folder, "draft-en.md")
    issues: list[dict] = []

    if not os.path.isfile(recipes_path):
        issues.append({
            "country": cuisine_id,
            "severity": None,
            "kind": "missing_recipes_json",
            "detail": "recipes.json not found",
        })
        return issues

    with open(recipes_path, encoding="utf-8") as f:
        data = json.load(f)
    recipes = data.get("recipes") or data if isinstance(data, list) else data.get("recipes", [])

    draft_recipes = parse_draft_recipes(draft_path)

    for idx, recipe in enumerate(recipes):
        rid = recipe.get("id") or recipe.get("title") or str(idx)
        table_rows = []
        steps = []
        for section in recipe.get("sections") or []:
            st = section.get("type")
            if st == "table":
                table_rows.extend(section.get("rows") or [])
            elif st == "steps":
                steps.extend(section.get("items") or [])

        table = table_phrases(table_rows)
        # Drop rinse/drain lines before pantry matching — "rinse until the
        # water runs clear" is not an ingredient-coverage bug.
        usable_steps = [s for s in steps if not _RINSE_LINE.search(s)]
        step_text = "\n".join(usable_steps)

        # 1) Pantry canaries mentioned in steps but absent from table.
        mentions = text_mentions(step_text, PANTRY_PHRASES)
        # If the longer form already fired, drop the bare synonym.
        if "black pepper" in mentions or "white pepper" in mentions:
            mentions = [m for m in mentions if m != "pepper"]
        if any(m.endswith(" oil") for m in mentions) or "neutral oil" in mentions:
            mentions = [m for m in mentions if m != "oil"]
        if any(m.endswith(" salt") for m in mentions):
            mentions = [m for m in mentions if m != "salt"]
        for mention in mentions:
            if not covered_by_table(mention, table):
                issues.append({
                    "country": cuisine_id,
                    "recipe": rid,
                    "kind": "step_missing_from_table",
                    "detail": "steps mention %r but recipes.json table has no matching ingredient" % mention,
                })

        # 2) Draft pantry staples present in draft-en.md but missing from
        #    recipes.json — same bug class, caught from the other side.
        if idx < len(draft_recipes):
            draft = draft_recipes[idx]
            draft_phrases = set()
            for cell in draft["ingredients"]:
                draft_phrases |= _head_terms(cell)
            pantry_norms = {_norm(p) for p in PANTRY_PHRASES}
            blob = step_text + "\n" + "\n".join(draft.get("steps") or [])
            for phrase in sorted(draft_phrases):
                if phrase not in pantry_norms:
                    continue
                if phrase and not covered_by_table(phrase, table):
                    if text_mentions(blob, [phrase]):
                        issues.append({
                            "country": cuisine_id,
                            "recipe": rid,
                            "kind": "draft_ingredient_missing",
                            "detail": (
                                "draft-en.md lists/uses %r but recipes.json "
                                "ingredient table does not" % phrase
                            ),
                        })

    return issues


def check_many(cuisine_ids: list[str] | None = None) -> list[dict]:
    ids = cuisine_ids or done_cuisine_ids()
    all_issues: list[dict] = []
    for cid in ids:
        all_issues.extend(check_country(cid))
    # De-dupe identical rows
    seen = set()
    uniq = []
    for iss in all_issues:
        key = (iss["country"], iss.get("recipe"), iss["kind"], iss["detail"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(iss)
    return uniq


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ids = argv or None
    issues = check_many(ids)
    if not issues:
        print("PASS  ingredient coverage (%d countries)" % len(ids or done_cuisine_ids()))
        return 0
    print("FAIL  ingredient coverage — %d issue(s)" % len(issues))
    for iss in issues:
        print("  [%s / %s] %s: %s" % (
            iss["country"], iss.get("recipe") or "-", iss["kind"], iss["detail"]
        ))
    return 1


if __name__ == "__main__":
    # Fix accidental typo in parse_draft if any — validate by running.
    sys.exit(main())
