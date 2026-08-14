# -*- coding: utf-8 -*-
"""Search helper for Russia photo sourcing. Prints candidates with license info
and downloads a small preview thumbnail for visual verification."""
import os
import sys
import urllib.request

REPO_ROOT = r"C:\Users\KimSh\OneDrive\바탕 화면\digital-product-agent"
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import commons

PREVIEW_DIR = os.path.join(REPO_ROOT, "products", "russian-meal-planner", "photo_previews")
os.makedirs(PREVIEW_DIR, exist_ok=True)


def check(query, limit=8, tag=""):
    print("=== QUERY:", query, "===")
    titles = commons.search(query, limit=limit, licensed_only=True)
    if not titles:
        print("  (no licensed results)")
        return []
    results = []
    for t in titles:
        i = commons.info(t)
        if not i:
            continue
        print("  -", t, "|", i["license"], "|", i["artist_text"], "|", i["width"], "x", i["height"])
        results.append(t)
    return results


def save_preview(title, name):
    url = commons.thumb_url(title, 300)
    if not url:
        print("no thumb for", title)
        return
    req = urllib.request.Request(url, headers={"User-Agent": commons.UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    path = os.path.join(PREVIEW_DIR, name + ".jpg")
    with open(path, "wb") as f:
        f.write(data)
    print("saved preview:", path)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "search":
        check(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    elif cmd == "preview":
        save_preview(sys.argv[2], sys.argv[3])
