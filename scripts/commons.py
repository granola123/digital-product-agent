# -*- coding: utf-8 -*-
"""
Wikimedia Commons photo-sourcing helper for the world-cuisine meal-planner
pipeline.

Public API (stable — keep SKILL.md in sync with this list):

    commons.search(q, limit=10, licensed_only=False)
    commons.search_category(category, query="", limit=10, licensed_only=False)
    commons.info(title)                  # url / size / license / artist / ...
    commons.attribution(title)           # manifest.json-ready record, or None
    commons.license_ok(short_name)       # CC0 / CC BY / CC BY-SA only
    commons.thumb_url(title, width=900)
    commons.fetch_and_encode(url, max_w, out_path, crop_square=False)
    commons.strip_html(s)

Search is restricted to .jpg / .jpeg / .png titles — free-text Commons search
increasingly returns Internet Archive book-scan PDFs/DJVUs, which are useless
for recipe-card photos. Pass licensed_only=True (or use search_category with
the same flag) to also drop files whose LicenseShortName is not an allowed
free license.

License matching is token-based on LicenseShortName (e.g. "CC BY-SA 2.0" —
spaces, not hyphens). Hyphens are normalized to spaces before tokenizing so
both "CC-BY-SA 4.0" and "CC BY-SA 4.0" accept.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import urllib.parse
import urllib.request

try:
    from PIL import Image
except ImportError:  # pragma: no cover - fetch_and_encode needs Pillow
    Image = None

UA = (
    "digital-product-agent/1.0 "
    "(personal project research; contact: kimshinhanwha@gmail.com)"
)

API = "https://commons.wikimedia.org/w/api.php"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

# Over-fetch multiplier when post-filtering by extension / license so a
# caller asking for limit=10 still gets ~10 usable hits when possible.
_SEARCH_OVERFETCH = 5
_SEARCH_HARD_CAP = 50


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _api(**params) -> dict:
    params.setdefault("format", "json")
    url = API + "?" + urllib.parse.urlencode(params, safe='":')
    return _get(url)


def strip_html(s: str | None) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    # Commons often leaves leftover wiki/HTML entities in Artist fields.
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", s).strip()


def is_image_title(title: str) -> bool:
    """True if a Commons File: title looks like a raster photo we can use."""
    name = title.split(":", 1)[-1].lower()
    return name.endswith(IMAGE_EXTS)


def license_ok(short_name: str | None) -> bool:
    """
    Accept CC0 / public domain, CC BY (any version), CC BY-SA (any version).
    Reject NC / ND / All-rights-reserved / missing metadata.

    Matching is by short-name tokens after normalizing hyphens to spaces
    ("CC BY-SA 2.0" and "CC-BY-SA 2.0" both work).
    """
    if not short_name:
        return False
    raw = short_name.strip().lower()
    if not raw:
        return False

    compact = re.sub(r"[\s\-_]+", "", raw)
    if compact in {"cc0", "cc0to", "pd", "publicdomain"} or "publicdomain" in compact:
        return True
    if "creativecommonszero" in compact:
        return True

    tokens = re.split(r"[\s\-_]+", raw)
    tokens = [t for t in tokens if t]
    # Reject non-commercial / no-derivatives even if BY is present.
    if "nc" in tokens or "nd" in tokens:
        return False
    if "reserved" in tokens:
        return False

    has_cc = "cc" in tokens or compact.startswith("cc")
    has_by = "by" in tokens
    has_sa = "sa" in tokens
    if has_cc and has_by:
        return True
    # Some short names are just "BY-SA 4.0" without a leading CC.
    if has_by and has_sa:
        return True
    return False


def _meta_value(meta: dict, key: str) -> str:
    entry = meta.get(key) or {}
    return entry.get("value") or ""


def info(title: str) -> dict | None:
    """
    Look up imageinfo + extmetadata for a File: title.

    Returns dict with: url, thumburl (may be absent), width, height,
    license (LicenseShortName), license_url, artist (raw HTML),
    artist_text (stripped), description, credit — or None if missing.
    """
    d = _api(
        action="query",
        titles=title,
        prop="imageinfo",
        iiprop="url|extmetadata|size|mime",
    )
    pages = d.get("query", {}).get("pages", {})
    for p in pages.values():
        if "imageinfo" not in p:
            return None
        ii = p["imageinfo"][0]
        meta = ii.get("extmetadata", {}) or {}
        artist_raw = _meta_value(meta, "Artist")
        license_short = _meta_value(meta, "LicenseShortName")
        return {
            "title": title,
            "url": ii.get("url"),
            "thumburl": ii.get("thumburl"),
            "width": ii.get("width"),
            "height": ii.get("height"),
            "mime": ii.get("mime"),
            "license": license_short,
            "license_url": _meta_value(meta, "LicenseUrl"),
            "artist": artist_raw,
            "artist_text": strip_html(artist_raw),
            "description": strip_html(_meta_value(meta, "ImageDescription")),
            "credit": strip_html(_meta_value(meta, "Credit")),
            "license_ok": license_ok(license_short),
        }
    return None


def attribution(title: str) -> dict | None:
    """
    Manifest.json-ready attribution record for one File: title.

    Shape matches existing country manifests:
        {"title", "artist", "license", "url"}
    Returns None if the file is missing or its license is not allowed.
    """
    i = info(title)
    if not i or not i.get("license_ok"):
        return None
    return {
        "title": title,
        "artist": i["artist_text"] or i.get("credit") or "Unknown",
        "license": i["license"],
        "url": i["url"],
    }


def search(q: str, limit: int = 10, licensed_only: bool = False) -> list[str]:
    """
    Free-text Commons search in the File namespace.

    Results are filtered to .jpg/.jpeg/.png titles. When licensed_only is
    True, each candidate is license-checked via info() (extra API calls —
    space requests if you batch many searches).

    `q` may include Commons search keywords such as incategory:"Pho".
    """
    if limit < 1:
        return []
    fetch_n = min(_SEARCH_HARD_CAP, max(limit * _SEARCH_OVERFETCH, limit))
    d = _api(
        action="query",
        list="search",
        srnamespace=6,
        srlimit=fetch_n,
        srsearch=q,
    )
    titles = [x["title"] for x in d.get("query", {}).get("search", [])]
    out: list[str] = []
    for t in titles:
        if not is_image_title(t):
            continue
        if licensed_only:
            i = info(t)
            if not i or not i["license_ok"]:
                continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def search_category(
    category: str,
    query: str = "",
    limit: int = 10,
    licensed_only: bool = False,
) -> list[str]:
    """
    Search within a Commons category via the incategory:"..." keyword.

    `category` may be "Category:Pho" or just "Pho". Optional `query` is
    AND-ed as free text (e.g. query="bowl" -> 'incategory:"Pho" bowl').
    """
    cat = category.strip()
    if cat.lower().startswith("category:"):
        cat = cat.split(":", 1)[1].strip()
    # Commons search wants the bare category title inside incategory:"..."
    parts = ['incategory:"%s"' % cat.replace('"', "")]
    if query.strip():
        parts.append(query.strip())
    return search(" ".join(parts), limit=limit, licensed_only=licensed_only)


def thumb_url(title: str, width: int = 900) -> str | None:
    """Ask Wikimedia's thumbnailer for a resized URL (avoids full-res 429s)."""
    d = _api(
        action="query",
        titles=title,
        prop="imageinfo",
        iiprop="url",
        iiurlwidth=int(width),
    )
    pages = d.get("query", {}).get("pages", {})
    for p in pages.values():
        if "imageinfo" not in p:
            return None
        ii = p["imageinfo"][0]
        return ii.get("thumburl") or ii.get("url")
    return None


def fetch_and_encode(
    url: str,
    max_w: int,
    out_path: str,
    crop_square: bool = False,
) -> int:
    """
    Download an image URL, crop to square (dish) or 16:10 (prep), resize,
    and write a re-compressed JPEG. Returns byte size written.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for fetch_and_encode (pip install Pillow)")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if crop_square:
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
        target = min(max_w, s)
        im = im.resize((target, target), Image.LANCZOS)
    else:
        w, h = im.size
        target_ar = 16 / 10
        cur_ar = w / float(h) if h else target_ar
        if cur_ar > target_ar:
            new_w = int(h * target_ar)
            im = im.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
        else:
            new_h = int(w / target_ar)
            im = im.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))
        w, h = im.size
        if w > max_w:
            new_h = int(h * max_w / float(w))
            im = im.resize((max_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=72, optimize=True)
    b = buf.getvalue()
    with open(out_path, "wb") as f:
        f.write(b)
    return len(b)


if __name__ == "__main__":
    # CLI used by per-country fetch_photos.py runners and quick manual checks.
    if len(sys.argv) < 2:
        print(
            "usage:\n"
            "  commons.py search <query> [limit]\n"
            "  commons.py search_licensed <query> [limit]\n"
            "  commons.py category <category> [query] [limit]\n"
            "  commons.py info <File:Title>\n"
            "  commons.py attribution <File:Title>\n"
            "  commons.py fetch <url> <max_w> <out_path> <square|wide>"
        )
        sys.exit(2)

    cmd = sys.argv[1]
    if cmd == "search":
        q = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        for t in search(q, limit=limit):
            print(t)
    elif cmd == "search_licensed":
        q = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        for t in search(q, limit=limit, licensed_only=True):
            print(t)
    elif cmd == "category":
        cat = sys.argv[2]
        query = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].isdigit() else ""
        limit_arg = sys.argv[4] if query and len(sys.argv) > 4 else (
            sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].isdigit() else "10"
        )
        for t in search_category(cat, query=query, limit=int(limit_arg)):
            print(t)
    elif cmd == "info":
        i = info(sys.argv[2])
        if i:
            print("URL:", i["url"])
            print("SIZE:", i["width"], "x", i["height"])
            print("LICENSE:", i["license"], "(ok)" if i["license_ok"] else "(REJECT)")
            print("ARTIST:", i["artist_text"])
        else:
            print("NOT FOUND")
    elif cmd == "attribution":
        a = attribution(sys.argv[2])
        if a:
            print(json.dumps(a, ensure_ascii=False, indent=2))
        else:
            print("NOT FOUND OR LICENSE REJECTED")
            sys.exit(1)
    elif cmd == "fetch":
        n = fetch_and_encode(
            sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5] == "square"
        )
        print("bytes:", n)
    else:
        print("unknown cmd:", cmd)
        sys.exit(2)
