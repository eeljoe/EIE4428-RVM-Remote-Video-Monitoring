# 01-design r3 verifier probe — WCAG 2.1 contrast recompute + doc/mock consistency checks
# Run: python .scratch/face-recognition/verifier-probes/01-design-r3-selfcheck.py
import re, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__)).split(os.sep + ".scratch")[0]
DOC = os.path.join(ROOT, "docs", "DESIGN-dashboard.md")
MOCK = os.path.join(ROOT, ".scratch", "face-recognition", "design", "v2", "mock.html")

def lum(hexc):
    hexc = hexc.lstrip("#")
    r, g, b = (int(hexc[i:i+2], 16) / 255 for i in (0, 2, 4))
    def lin(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def ratio(fg, bg):
    l1, l2 = lum(fg), lum(bg)
    if l1 < l2: l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)

def blend(fg_rgba, bg_hex):
    r, g, b, a = fg_rgba
    bh = bg_hex.lstrip("#")
    br, bg_, bb = (int(bh[i:i+2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (round(r * a + br * (1 - a)),
                              round(g * a + bg_ * (1 - a)),
                              round(b * a + bb * (1 - a)))

results = []
def check(name, actual, expect, tol=0.06):
    ok = abs(actual - expect) <= tol
    results.append((ok, name, actual, expect))
    print(("PASS" if ok else "FAIL"), name, "actual=%.3f" % actual, "doc=%s" % expect)

BG, PANEL, RAISED = "#0b0d0e", "#101416", "#191f22"

# ---- §2 token table claims (current doc) ----
check("--raised/--bg 1.17",      ratio("#191f22", BG), 1.17)
check("--raised-hover/--bg 1.33", ratio("#212a2e", BG), 1.33)
check("--line/--bg 1.37",        ratio("#252c30", BG), 1.37)
check("--line-strong/--raised 1.67", ratio("#39444a", RAISED), 1.67)
check("--text/--bg 16.65",       ratio("#e9eef0", BG), 16.65)
check("--text-2/--bg 11.94",     ratio("#c3ccd0", BG), 11.94)
check("--muted/--bg 7.73",       ratio("#9aa5aa", BG), 7.73)
check("--placeholder/--panel 5.10", ratio("#7d888d", PANEL), 5.10)
check("--accent/--bg 10.78",     ratio("#5fd3c6", BG), 10.78)
check("--accent-hover/--bg 12.22", ratio("#78ded2", BG), 12.22)
check("--on-accent/--accent 8.97", ratio("#072521", "#5fd3c6"), 8.97)
check("--ok/--bg 9.83",          ratio("#6ecb8f", BG), 9.83)
check("--warn/--bg 10.16",       ratio("#e3b45c", BG), 10.16)
check("--alarm/--bg 6.69",       ratio("#f0715a", BG), 6.69)
check("--text/--panel 15.8 (hard floor, §2:68)", ratio("#e9eef0", PANEL), 15.80, tol=0.08)

# ---- §7 peak dash composite over --bg ----
comp = blend((154, 165, 170, 0.5), BG)
print("composite rgba(154,165,170,.5) over #0b0d0e =", comp, "(doc claims 约 #53595c)")
check("peak dash composite/--bg ~2.7", ratio(comp, BG), 2.7, tol=0.08)

# ---- structural checks on doc text ----
doc = open(DOC, encoding="utf-8").read()
doclines = doc.splitlines()
mock = open(MOCK, encoding="utf-8").read()

def expect(cond, name):
    results.append((cond, name, "", ""))
    print(("PASS" if cond else "FAIL"), name)

expect(len(doclines) <= 250, "doc lines <= 250 (actual %d)" % len(doclines))
expect("—" not in doc, "no U+2014 em dash")
expect(len(re.findall(r"^## ", doc, re.M)) >= 5, "five required sections present")
expect("画面 → 控件 → 提示行 → FACE REGISTRY → 遥测" in doc, "390px order sentence")
expect("peak 1.33 Mbps" in doc, "peak annotation copy")
for s in ["Saved as Alice Ng, 3 frames averaged", "No face in frame, hold still",
          "Two faces in frame, show one", "Alice Ng is already saved, add a surname",
          "Analysis is off"]:
    expect(s in doc, "five-state copy verbatim: %r" % s)

# §2 no leftover "(对 --panel" annotations on muted/alarm/line
muted_line = [l for l in doclines if "`--muted`" in l and "9aa5aa" in l][0]
alarm_line = [l for l in doclines if "`--alarm`" in l and "f0715a`" in l][0]
line_line  = [l for l in doclines if "`--line`" in l and "252c30" in l][0]
expect("(对 --panel" not in muted_line, "--muted row has no --panel annotation")
expect("(对 --panel" not in alarm_line, "--alarm row has no --panel annotation")
expect("--bg 1.37:1" in line_line, "--line row says 对 --bg 1.37:1")

# §2/§7 consistency: every mention of --panel use is input-only
expect("分区不铺底色" in doc and "分区不铺 `--panel`" in doc, "§2/§7 no-panel-on-sections wording consistent")

# mock ground truth
expect(mock.count("var(--panel)") == 1, "mock var(--panel) used exactly once")
expect("background: var(--panel); color: var(--text);" in mock, "mock --panel use is reg-row input")
expect("background:" not in re.search(r"\.rail \{[^}]*\}", mock).group(0), ".rail has no background")
expect("background" not in re.search(r"#spark \{[^}]*\}", mock).group(0), "#spark has no background")
expect('strokeStyle = "rgba(154,165,170,.5)"' in mock, "mock peak dash colour")
expect("var(--accent-soft)" not in mock, "--accent-soft never used in mock")
expect(mock.count("var(--alarm-soft)") == 2, "--alarm-soft used for record.active + .x:hover")
expect("#f0715a1a" in mock, "mock .bbox uses literal #f0715a1a")
expect("#5fd3c60f" in mock, "mock .roi uses literal #5fd3c60f")
expect("clearRect" in mock, "canvas cleared (transparent)")

fails = [r for r in results if not r[0]]
print("\n%d checks, %d FAIL" % (len(results), len(fails)))
sys.exit(1 if fails else 0)
