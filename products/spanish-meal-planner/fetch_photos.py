# -*- coding: utf-8 -*-
"""
Runner script for sourcing Spanish dish photos from Wikimedia Commons.
Anchors sys.path to the skill's scripts dir using a Windows-style path
(per lessons-learned.md — Windows-native Python doesn't resolve POSIX
paths from Git Bash reliably).
"""
import sys
import os
import time

SCRIPTS_DIR = r"C:\Users\KimSh\.claude\skills\world-cuisine-meal-planner-pipeline\scripts"
sys.path.insert(0, SCRIPTS_DIR)
import commons  # noqa: E402

import json

CMD = sys.argv[1] if len(sys.argv) > 1 else "search"

if CMD == "search":
    q = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    for t in commons.search(q, limit=limit):
        print(t)
elif CMD == "info":
    title = sys.argv[2]
    i = commons.info(title)
    if i:
        print("URL:", i["url"])
        print("SIZE:", i["width"], "x", i["height"])
        print("LICENSE:", i["license"])
        print("ARTIST:", commons.strip_html(i["artist"]))
    else:
        print("NOT FOUND")
elif CMD == "fetch":
    # fetch <title> <max_w> <out_path> <square|wide>
    title = sys.argv[2]
    max_w = int(sys.argv[3])
    out_path = sys.argv[4]
    shape = sys.argv[5]
    i = commons.info(title)
    if not i:
        print("NOT FOUND:", title)
        sys.exit(1)
    tu = None
    for attempt in range(4):
        try:
            tu = commons.thumb_url(title, max_w + 200)
            break
        except Exception as e:
            wait = 5 * (attempt + 1)
            print("thumb_url retry after error:", e, "-> sleeping", wait, "s")
            time.sleep(wait)
    if not tu:
        print("FAILED to get thumb_url:", title)
        sys.exit(1)
    for attempt in range(4):
        try:
            n = commons.fetch_and_encode(tu, max_w, out_path, shape == "square")
            print("bytes:", n, "license:", i["license"], "artist:", commons.strip_html(i["artist"]))
            break
        except Exception as e:
            wait = 5 * (attempt + 1)
            print("fetch retry after error:", e, "-> sleeping", wait, "s")
            time.sleep(wait)
    else:
        print("FAILED to fetch:", title)
        sys.exit(1)
else:
    print("unknown cmd")
