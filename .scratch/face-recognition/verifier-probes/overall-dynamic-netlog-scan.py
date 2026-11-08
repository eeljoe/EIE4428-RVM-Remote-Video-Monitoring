#!/usr/bin/env python3
"""Scan a Chrome netlog for URL_REQUESTs initiated BY THE PAGE (initiator set)."""
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
types = {v: k for k, v in data.get("constants", {}).get("logEventTypes", {}).items()}
page_reqs = []
all_reqs = []
for ev in data.get("events", []):
    etype = ev.get("type", {})
    if isinstance(etype, dict):
        tname = types.get(etype.get("id", etype.get("value")), str(etype))
    else:
        tname = types.get(etype, str(etype))
    params = ev.get("params", {})
    url = params.get("url") if isinstance(params, dict) else None
    if "URL_REQUEST" not in str(tname) or not url:
        continue
    initiator = params.get("initiator") or params.get("site_for_cookies") or ""
    all_reqs.append((url, initiator))
    if "127.0.0.1" in str(initiator) or "localhost" in str(initiator):
        page_reqs.append((url, initiator))

print("total URL_REQUEST events:", len(all_reqs))
remote = [u for u, i in page_reqs if "127.0.0.1" not in u and "localhost" not in u]
print("page-initiated requests:", len(page_reqs))
for u, i in page_reqs:
    print("  page ->", u, "| initiator:", i)
print("REMOTE page-initiated:", remote if remote else "none")
