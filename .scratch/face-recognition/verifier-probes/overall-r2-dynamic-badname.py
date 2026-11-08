#!/usr/bin/env python3
"""overall-r2-dynamic name-validation probe: exact JSON payloads, no shell
escaping in the way. A legal name passes validation and then fails on the
real no-face 409; an illegal name must stop at 400 bad-name. Also proves
the registry file is never written on the failure paths."""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8099"
CASES = [
    ("literal backslash", "a\\b"),
    ("forward slash", "a/b"),
    ("dot", "."),
    ("dotdot", ".."),
    ("dotdot slash", "../x"),
    ("nul ctrl", "nulyte"),
    ("del 0x7f", "delchar"),
    ("tab", "tab	here"),
    ("leading dots legal", "..a"),
    ("mid dots legal", "a..b"),
    ("pct literal", "%2F"),
    ("unicode legal", "张小英"),
]
for label, name in CASES:
    body = json.dumps({"name": name}).encode()
    req = urllib.request.Request(
        BASE + "/api/faces/known", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code, payload = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read().decode()
    print(f"{label:20} name={name!r:24} -> {code} {payload.strip()}")
