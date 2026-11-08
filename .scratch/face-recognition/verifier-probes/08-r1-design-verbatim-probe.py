# Verifier probe (08 r1): DESIGN-dashboard.md sections 4.4 + 8 vs app.js/style.css.
# Extracts the copy strings the doc promises and checks each verbatim against
# the implementation; also checks the stale strings the old doc promised are
# gone, and the hex values quoted in the table match :root. Usage:
#   python <this> <worktree>
import re
import sys
from pathlib import Path

wt = Path(sys.argv[1])
design = (wt / "docs" / "DESIGN-dashboard.md").read_text(encoding="utf-8")
js = (wt / "src" / "rvm" / "web" / "app.js").read_text(encoding="utf-8")
css = (wt / "src" / "rvm" / "web" / "style.css").read_text(encoding="utf-8")
s8 = design.split("## 8 ", 1)[1].split("## 9", 1)[0]
s44 = design.split("### 4.4", 1)[1].split("###", 1)[0] if "### 4.4" in design else ""

checks = []


def chk(name, cond):
    checks.append((name, bool(cond)))


# §8 verbatim copy: each string the doc quotes must exist verbatim in app.js.
for lit in (
    "Saved as Alice Ng, 3 frames averaged",   # doc example instance
    "no face in frame, hold still",
    "more than one face in frame",
    "Alice Ng is already saved",
    "analysis is off",
    "models still loading",
    "No names saved yet",
    "recording",
    "Start recording",
    "Stop recording",
):
    chk(f"doc-string {lit!r} in §8", lit in s8)

# The dynamic templates behind the doc's example instances.
chk("app.js template 'Saved as ' + ... + ' frames averaged'",
    '", " + body.samples + " frames averaged"' in js)
chk("app.js template name + ' is already saved'",
    'name + " is already saved"' in js)

# Every literal FACE_REASONS copy appears in §8 verbatim.
for lit in re.findall(r'"(no-face|multiple-faces|analysis-disabled|models-loading)":\s*\[\s*"[^"]*"\s*,\s*"([^"]+)"', js):
    chk(f"FACE_REASONS[{lit[0]}] copy in §8", lit[1] in s8)

# Supplementary §8/§4.4 strings that must exist in implementation.
chk("'No names saved yet' in app.js", '"No names saved yet"' in js)
chk("pending readout is 'loading'", '"pending") return "loading"' in js or '"pending" return "loading"' in js)
chk("disabled readout is 'off'", '"disabled") return "off"' in js or '"disabled" return "off"' in js)
chk("recording readout is 'recording'", '"recording" : "off"' in js)
chk("'loading' promised in §4.4", "loading" in s44)
chk("'models still loading' promised in §4.4", "models still loading" in s44)
chk("'No recording yet' (no period) in app.js", "No recording yet<" in js)

# Hex values quoted in §8 must match :root.
for var, hexv in re.findall(r"`(--[a-z-]+)`\s*`(#[0-9a-fA-F]+)`", s8):
    m = re.search(re.escape(var) + r":\s*(#[0-9a-fA-F]+)", css)
    chk(f"{var} == {hexv}", m and m.group(1).lower() == hexv.lower())

# Record button alarm styling (§8 bullet).
chk("#record.active alarm border+text",
    re.search(r"#record\.active\s*\{[^}]*border-color:\s*var\(--alarm\)[^}]*color:\s*var\(--alarm\)", css, re.S))
chk("#record.active alarm-soft bg",
    re.search(r"#record\.active\s*\{[^}]*background:\s*var\(--alarm-soft\)", css, re.S))

# Stale strings the old doc promised must be gone (case-sensitive).
for stale in ("Two faces in frame", "add a surname", "Analysis is off",
              "warming up", "RECORDING"):
    chk(f"stale {stale!r} absent", stale not in design)

# REMEMBER FACE disabled only in flight.
chk("button disabled only during request",
    '$("face-remember").disabled = true;' in js and
    '$("face-remember").disabled = false;' in js)

bad = [c for c in checks if not c[1]]
for name, ok in checks:
    print(f"{'OK ' if ok else 'FAIL'} {name}")
print(f"RESULT: {len(checks) - len(bad)}/{len(checks)}; "
      f"{'ALL GREEN' if not bad else 'FAILURES'}")
sys.exit(1 if bad else 0)
