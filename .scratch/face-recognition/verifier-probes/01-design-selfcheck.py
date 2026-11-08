# Ticket 01 verifier probe: recompute contrast (WCAG 2.1) and mechanically
# cross-check docs/DESIGN-dashboard.md against the signed v2 mock and the
# current implementation. Read-only; prints PASS/FAIL lines.
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
doc = (ROOT / "docs/DESIGN-dashboard.md").read_text(encoding="utf-8")
mock = (ROOT / ".scratch/face-recognition/design/v2/mock.html").read_text(encoding="utf-8")
css = (ROOT / "src/rvm/web/style.css").read_text(encoding="utf-8")
notes = (ROOT / ".scratch/face-recognition/design/v2/NOTES.md").read_text(encoding="utf-8")

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))

def lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def lum(h):
    h = h.lstrip("#")
    return 0.2126 * lin(int(h[0:2], 16)) + 0.7152 * lin(int(h[2:4], 16)) + 0.0722 * lin(int(h[4:6], 16))

def cr(fg, bg):
    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)

# ---- 1. five required sections present ---------------------------------
for sec in ["## 1 字号阶", "## 2 颜色与对比度", "## 3 间距", "## 4 组件规则", "## 5 分区清单"]:
    check(f"section present: {sec}", sec in doc, "")

# ---- 2. font floors -----------------------------------------------------
check("line-height 1.5 stated", "行高 1.5" in doc or "/1.5" in doc, "")
check("label floor 13px", "标签下限 13px" in doc, "")
check("reading 15px", "15px" in doc and "读数一律 15px" in doc, "")
check("mobile >=14px", "14px" in doc and "升到 14" in doc, "")
check("doc <= 250 lines", len(doc.splitlines()) <= 250, f"{len(doc.splitlines())} lines")
check("no em-dash in doc", "\u2014" not in doc, "")

# ---- 3. contrast recomputation (WCAG 2.1 relative luminance) ------------
claims = [
    ("#e9eef0", "#0b0d0e", 16.65, "body --text on --bg"),
    ("#9aa5aa", "#0b0d0e", 7.73, "label --muted on --bg"),
    ("#9aa5aa", "#101416", 7.35, "--muted on --panel"),
    ("#c3ccd0", "#0b0d0e", 11.94, "--text-2 on --bg"),
    ("#7d888d", "#101416", 5.10, "--placeholder on --panel"),
    ("#5fd3c6", "#0b0d0e", 10.78, "--accent on --bg"),
    ("#6ecb8f", "#0b0d0e", 9.83, "--ok on --bg"),
    ("#e3b45c", "#0b0d0e", 10.16, "--warn on --bg"),
    ("#f0715a", "#0b0d0e", 6.69, "--alarm on --bg"),
    ("#f0715a", "#101416", 6.36, "--alarm on --panel"),
    ("#072521", "#5fd3c6", 8.97, "--on-accent on --accent"),
]
for fg, bg, want, name in claims:
    got = round(cr(fg, bg), 2)
    check(f"contrast {name} = {got} (doc {want})", abs(got - want) < 0.02, "")

# grey on near-black >= 7.7, body >= 16 (gate thresholds)
check("grey >= 7.7", cr("#9aa5aa", "#0b0d0e") >= 7.7, f"{cr('#9aa5aa','#0b0d0e'):.2f}")
check("body >= 16", cr("#e9eef0", "#0b0d0e") >= 16.0, f"{cr('#e9eef0','#0b0d0e'):.2f}")

# dashed-peak overlay: rgba(154,165,170,.5) over --panel #101416
ov = tuple(round(c * 0.5 + b * 0.5) for c, b in zip((154, 165, 170), (16, 20, 22)))
ov_hex = "#%02x%02x%02x" % ov
check("peak overlay hex #555c60", ov_hex == "#555c60", ov_hex)
check("peak overlay vs --panel ~2.72", abs(cr(ov_hex, "#101416") - 2.72) < 0.02, f"{cr(ov_hex,'#101416'):.2f}")

# ---- 4. spacing & section count -----------------------------------------
check("doc states >=20px group rule", "≥20px" in doc or ">=20px" in doc or "20px 是硬规则" in doc, "")
check("5 sections named", all(s in doc for s in ["STREAM", "TRANSPORT", "ANALYSIS", "FACE REGISTRY", "CLIPS"]), "")
check("mock desktop section gap 20+18", "margin-top: 20px; padding-top: 18px" in mock, "")

# ---- 5. 390px order ------------------------------------------------------
order_ok = (
    ".stage { order: 1" in mock and ".controls { order: 2" in mock
    and ".hint { order: 3" in mock and ".registry { order: 4" in mock
    and ".section { order: 5" in mock
)
check("mock mobile order picture>controls>hint>registry>sections", order_ok, "")
check("doc states picture->controls->registry->telemetry",
      "画面 → 控件" in doc and "FACE REGISTRY" in doc and "遥测" in doc and "→" in doc, "")

# ---- 6. peak annotation matches mock -------------------------------------
check("mock dashed rule rgba(154,165,170,.5)", "rgba(154,165,170,.5)" in mock, "")
check("mock dash 3/3", "setLineDash([3 * dpr, 3 * dpr])" in mock, "")
check("mock peak tag text", "peak 1.33 Mbps" in mock, "")
check("mock peak margin-left:auto", ".peak" in mock and "margin-left: auto" in mock, "")
check("mock peak 12px", "400 12px/1.5 var(--mono)" in mock, "")
check("doc peak spec", "peak 1.33 Mbps" in doc and "margin-left: auto" in doc and "rgba(154,165,170,.5)" in doc, "")
check("mock aria-label peak", "scaled to a peak of" in mock, "")

# ---- 7. five-state copy ---------------------------------------------------
for s in ["Saved as Alice Ng, 3 frames averaged", "No face in frame, hold still",
          "Two faces in frame, show one", "Alice Ng is already saved, add a surname",
          "Analysis is off"]:
    check(f"doc copy: {s!r}", s in doc, "")
for s, c in [("Saved as Alice Ng", "#6ecb8f"), ("No face in frame", "#f0715a"),
             ("Two faces", "#f0715a"), ("already saved", "#e3b45c"), ("Analysis is off", "#9aa5aa")]:
    check(f"doc copy+color pair {s!r}/{c}", s in doc and c in doc, "")

# ---- 8. doc-vs-mock numeric fidelity (the adversarial part) ---------------
m900 = mock.split("@media (max-width: 900px)")[1].split("@media (max-width: 560px)")[0]
mobile_gap_changed = "margin-top: 8px; padding-top: 16px" in m900
doc_claims_20_18_unchanged = "分区之间仍是 20 + 18" in doc
check("D3: doc 'mobile keeps 20+18' vs mock '8+16' -> MISMATCH" if doc_claims_20_18_unchanged and mobile_gap_changed else "D3 ok",
      not (doc_claims_20_18_unchanged and mobile_gap_changed),
      "mock.html @900: " + re.search(r"\.section \+ \.section \{[^}]*\}", m900).group(0) if mobile_gap_changed else "")

course = re.search(r"\.course \{[^}]*letter-spacing: ([\d.]+em)", mock)
doc_row = re.search(r"顶栏 `EIE4428`", doc)
doc_02_row = re.search(r"\| 13 \| 400 \| \.02em \| mono \|[^\n]*EIE4428", doc)
check("D1: doc .02em for EIE4428 vs mock .06em -> MISMATCH" if (doc_02_row and course and course.group(1) == ".06em") else "D1 ok",
      not (doc_02_row and course and course.group(1) == ".06em"),
      f"mock .course letter-spacing={course.group(1) if course else '?'}")

btn = re.search(r"select, button \{\s*font: (\d+) var\(--fs-body\)", mock)
doc_400_row = "| 15 | 400 | 0 | sans | 正文:按钮、下拉、输入框、名单行" in doc.replace("：", ":")
check("D2: doc 400 for select/button vs mock 500 -> MISMATCH" if (doc_400_row and btn and btn.group(1) == "500") else "D2 ok",
      not (doc_400_row and btn and btn.group(1) == "500"),
      f"mock select/button weight={btn.group(1) if btn else '?'}")

has_maxheight = "max-height" in css or "calc(100vh" in css
doc_cites = "max-height: calc(100vh - 102px)" in doc
check("D4: doc cites max-height calc(100vh-102px) '沿用现有实现' but rule absent in style.css -> MISMATCH" if (doc_cites and not has_maxheight) else "D4 ok",
      not (doc_cites and not has_maxheight),
      f"style.css max-height count={css.count('max-height')}")

# ---- summary --------------------------------------------------------------
fails = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS" if ok else "FAIL"), name, detail)
print(f"\n{len(results) - len(fails)}/{len(results)} checks pass, {len(fails)} fail")
sys.exit(1 if fails else 0)
