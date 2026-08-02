# -*- coding: utf-8 -*-
"""
Merge every "Taste of ___" preview.html in products/ into one consolidated
sellable book (products/book/taste-of-the-world-full-collection.html), in
_series-roadmap.json's cuisine order. Convert to PDF separately with
agent-browser (`agent-browser open <file>`, then `agent-browser pdf <out>`).

Re-run any time a country's recipes/photos change or a new country is
added to _series-roadmap.json — this script always re-derives from the
current preview.html files, it never hand-edits them.
"""
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(SCRIPT_DIR, "..", "products")
OUT_DIR = os.path.join(ROOT, "book")
OUT_HTML = os.path.join(OUT_DIR, "taste-of-the-world-full-collection.html")
ROADMAP = os.path.join(ROOT, "_series-roadmap.json")

REFERENCE_COUNTRY = "korean-meal-planner"  # bug-fixed reference per project memory


def extract(text, pattern, flags=re.S, group=1, required=True):
    m = re.search(pattern, text, flags)
    if not m:
        if required:
            raise ValueError("pattern not found: " + pattern[:60])
        return None
    return m.group(group)


def parse_root_vars(root_block):
    return dict(re.findall(r'(--[\w-]+):\s*([^;]+);', root_block))


def load(folder):
    path = os.path.join(ROOT, folder, "preview.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


def done_countries():
    with open(ROADMAP, encoding="utf-8") as f:
        roadmap = json.load(f)
    return [(c["id"] + "-meal-planner", c["flag"])
            for c in roadmap["cuisines"] if c["status"] == "done"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    countries = done_countries()

    ref_text = load(REFERENCE_COUNTRY)

    # ---- master <style> (structural CSS shared by every country) ----
    master_style = extract(ref_text, r'<style>(.*?)</style>')
    # neutralize the two hardcoded-rgba tag rules -> var-driven, so each
    # chapter's own accent tint applies instead of the reference country's
    master_style = re.sub(
        r'\.tag\.easy\{[^}]*\}',
        '.tag.easy{ background:var(--tag-easy-bg); color:var(--lemongrass-deep); }',
        master_style, count=1)
    master_style = re.sub(
        r'\.tag\.medium\{[^}]*\}',
        '.tag.medium{ background:var(--tag-medium-bg); color:var(--turmeric-deep); }',
        master_style, count=1)

    # union of every SVG icon <symbol> def across all countries, keyed by id
    symbols = {}
    country_data = []

    for folder, flag in countries:
        text = load(folder)

        root_vars = parse_root_vars(extract(text, r':root\{(.*?)\}'))
        tag_easy_bg = extract(text, r'\.tag\.easy\{\s*background:([^;]+);', required=False) or 'rgba(124,140,94,0.18)'
        tag_medium_bg = extract(text, r'\.tag\.medium\{\s*background:([^;]+);', required=False) or 'rgba(217,164,56,0.2)'

        defs_svg = extract(text, r'(<svg style="position:absolute.*?</svg>)')
        for sym in re.findall(r'<symbol id="[\w-]+"[^>]*>.*?</symbol>', defs_svg):
            sid = re.search(r'id="([\w-]+)"', sym).group(1)
            symbols.setdefault(sid, sym)

        title = extract(text, r'<h1 class="title">(.*?)</h1>')
        subtitle = extract(text, r'<p class="subtitle">(.*?)</p>', required=False) or ''
        gallery = extract(text, r'<section class="gallery">(.*?)</section>')
        photo_credits = extract(text, r'<p class="photo-credits">(.*?)</p>', required=False) or ''

        country_data.append({
            "folder": folder, "flag": flag, "title": title, "subtitle": subtitle,
            "root_vars": root_vars, "tag_easy_bg": tag_easy_bg, "tag_medium_bg": tag_medium_bg,
            "gallery": gallery, "photo_credits": photo_credits,
        })
        print(folder, "ok")

    all_defs = "\n".join(symbols[k] for k in symbols)

    def style_attr(cd):
        parts = ["--tag-easy-bg:%s" % cd["tag_easy_bg"], "--tag-medium-bg:%s" % cd["tag_medium_bg"]]
        for k, v in cd["root_vars"].items():
            if k.startswith("--font-"):
                continue
            parts.append("%s:%s" % (k, v))
        return "; ".join(parts)

    toc_items, chapters, credits_items, flag_line = [], [], [], []
    n = len(country_data)
    for i, cd in enumerate(country_data, start=1):
        anchor = "c%02d" % i
        country_name = cd["title"].replace("Taste of ", "")
        flag_line.append(cd["flag"])
        toc_items.append(
            '<li><a href="#%s"><span class="toc-num">%02d</span>'
            '<span class="toc-flag">%s</span><span class="toc-name">%s</span></a></li>'
            % (anchor, i, cd["flag"], country_name)
        )
        chapters.append(
            '<section class="country-block" id="%s" style="%s">\n'
            '<header class="chapter-divider">\n'
            '<p class="eyebrow">Chapter %02d of %d</p>\n'
            '<h1 class="title">%s</h1>\n'
            '<p class="subtitle">%s</p>\n'
            '</header>\n'
            '<section class="gallery">%s</section>\n'
            '</section>\n'
            % (anchor, style_attr(cd), i, n, cd["title"], cd["subtitle"], cd["gallery"])
        )
        if cd["photo_credits"]:
            credits_items.append('<p><b>%s</b> — %s</p>' % (country_name, cd["photo_credits"]))

    # Count recipe cards from each gallery rather than assuming 8/country —
    # series format is normally 8, but stay accurate as the library grows.
    recipe_total = 0
    for cd in country_data:
        recipe_total += len(re.findall(
            r'class="[^"]*\brecipe-card\b', cd["gallery"]
        ))
    if recipe_total == 0:
        # Fallback if class names differ in an older preview.
        recipe_total = n * 8

    doc = TEMPLATE.format(
        master_style=master_style,
        all_defs=all_defs,
        toc="\n".join(toc_items),
        chapters="\n".join(chapters),
        credits="\n".join(credits_items),
        flags=" ".join(flag_line),
        n=n,
        recipes=recipe_total,
    )

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(doc)
    print("WROTE", OUT_HTML, len(doc), "chars,", n, "countries")
    print("Next: agent-browser open <file>  then  agent-browser pdf <out.pdf>")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Taste of the World — {n}-Cuisine Meal Planner Collection</title>
<style>
{master_style}

/* ---------- Book-specific additions ---------- */
@page {{ size: 850px 1100px; margin: 0; }}

* {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ background: #14100D; }}

.country-block {{
  background:
    radial-gradient(1200px 700px at 15% -10%, var(--ink-2), transparent 60%),
    radial-gradient(900px 600px at 110% 10%, var(--ink-2), transparent 55%),
    var(--ink);
  color: var(--paper);
  padding: clamp(2.5rem,6vw,5.5rem) clamp(1.25rem,4vw,3rem) 4rem;
  page-break-before: always;
  break-before: page;
}}
.chapter-divider {{ text-align:center; max-width:640px; margin:0 auto clamp(3rem,7vw,4.5rem); }}
.country-block .page-card, .country-block article {{ break-inside: avoid; }}

/* ---------- Cover page ---------- */
.book-cover {{
  min-height: 100vh;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  text-align:center; gap:1.25rem;
  background:
    radial-gradient(1400px 900px at 20% -10%, #2A2118, transparent 60%),
    radial-gradient(1000px 700px at 100% 110%, #1D2A22, transparent 55%),
    #14100D;
  color:#F4EFE4;
  padding: 3rem 1.5rem;
}}
.book-cover .kicker {{
  font-family: var(--font-mono); letter-spacing:0.2em; text-transform:uppercase;
  font-size:0.8rem; color:#D9A438;
}}
.book-cover h1 {{
  font-family: var(--font-display); font-weight:700;
  font-size: clamp(2.5rem, 7vw, 4.5rem); margin:0; text-wrap:balance; max-width:16ch;
}}
.book-cover .lede {{ max-width:46ch; color:#C9BFA9; font-size:1.05rem; line-height:1.6; }}
.book-cover .flags {{ font-size:1.6rem; letter-spacing:0.35em; margin-top:0.5rem; }}
.book-cover .stat-row {{ display:flex; gap:2.5rem; margin-top:1.5rem; flex-wrap:wrap; justify-content:center; }}
.book-cover .stat {{ text-align:center; }}
.book-cover .stat b {{ display:block; font-family:var(--font-display); font-size:1.8rem; color:#F4EFE4; }}
.book-cover .stat span {{ font-family:var(--font-mono); font-size:0.7rem; letter-spacing:0.1em; text-transform:uppercase; color:#8C8272; }}

/* ---------- Table of contents ---------- */
.toc-page {{
  min-height:100vh; background:#14100D; color:#F4EFE4;
  padding: clamp(2.5rem,6vw,5.5rem) clamp(1.25rem,4vw,3rem);
  page-break-before: always; break-before: page;
}}
.toc-page h2 {{ font-family: var(--font-display); font-size:2rem; text-align:center; margin:0 0 2.5rem; }}
.toc-list {{ list-style:none; margin:0 auto; padding:0; max-width:640px; display:flex; flex-direction:column; }}
.toc-list li {{ border-bottom:1px solid rgba(244,239,228,0.12); }}
.toc-list a {{ display:flex; align-items:center; gap:1rem; padding:0.9rem 0.25rem; text-decoration:none; color:inherit; font-family:var(--font-body); }}
.toc-num {{ font-family:var(--font-mono); color:#8C8272; width:2ch; }}
.toc-flag {{ font-size:1.3rem; }}
.toc-name {{ font-size:1.05rem; }}

/* ---------- Credits appendix ---------- */
.credits-page {{
  min-height:100vh; background:#14100D; color:#C9BFA9;
  padding: clamp(2.5rem,6vw,5.5rem) clamp(1.25rem,4vw,3rem) 5rem;
  page-break-before: always; break-before: page;
  font-family: var(--font-mono); font-size:0.72rem; line-height:1.9;
}}
.credits-page h2 {{ font-family:var(--font-display); font-size:1.6rem; color:#F4EFE4; margin:0 0 1.5rem; }}
.credits-page p {{ max-width:70ch; }}
.credits-page b {{ color:#F4EFE4; font-family:var(--font-body); }}
</style>
</head>
<body>

<svg style="position:absolute;width:0;height:0" aria-hidden="true">
  <defs>
{all_defs}
  </defs>
</svg>

<section class="book-cover">
  <p class="kicker">The Complete Collection</p>
  <h1>Taste of the World</h1>
  <p class="lede">A {n}-cuisine digital meal-planner library — one weekly dinner plan, one grocery list, and eight illustrated recipe cards for every country, gathered into a single volume.</p>
  <p class="flags">{flags}</p>
  <div class="stat-row">
    <div class="stat"><b>{n}</b><span>Cuisines</span></div>
    <div class="stat"><b>{recipes}</b><span>Recipes</span></div>
  </div>
</section>

<section class="toc-page">
  <h2>Contents</h2>
  <ul class="toc-list">
{toc}
  </ul>
</section>

{chapters}

<section class="credits-page">
  <h2>Photo Credits</h2>
  <p>Every photograph in this collection is licensed CC0, CC BY, or CC BY-SA from Wikimedia Commons, with the photographer credited below by chapter. Swap for original photography before final resale to avoid attribution requirements.</p>
{credits}
</section>

</body>
</html>
"""

if __name__ == "__main__":
    main()
