# Ticket 01 r2 verifier probe (fresh, adversarial).
# Re-verifies the four r1 blocking fixes + the Nit fix, re-checks regressions,
# recomputes contrast (WCAG 2.1), and checks the residual noted in r2 designer
# report ("--panel usage claim vs sections-have-no-background"). Read-only.
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
doc = (ROOT / "docs/DESIGN-dashboard.md").read_text(encoding="utf-8")
mock = (ROOT / ".scratch/face-recognition/design/v2/mock.html").read_text(encoding="utf-8")
css = (ROOT / "src/rvm/web/style.css").read_text(encoding="utf-8")

results = []
def check(name, ok, detail=""):
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

m900 = mock.split("@media (max-width: 900px)")[1].split("@media (max-width: 560px)")[0]

# ---- r2 fix F1: mobile section gap ---------------------------------------
check("F1 doc states desktop 20+18", "分区之间桌面 20 + 18" in doc)
check("F1 doc states <=900 8+16", "≤900px 8 + 16" in doc)
check("F1 stale '仍是 20 + 18' gone", "分区之间仍是 20 + 18" not in doc)
check("F1 mock @900 section gap is 8+16", "margin-top: 8px; padding-top: 16px" in m900)
check("F1 mock desktop gap is 20+18", "margin-top: 20px; padding-top: 18px" in mock.split("@media")[0])

# ---- r2 fix F2: max-height pseudo-source ---------------------------------
check("F2 doc keeps max-height rule", "max-height: calc(100vh - 102px)" in doc)
check("F2 '沿用现有实现' pseudo-source gone", "沿用现有实现" not in doc)
check("F2 doc declares rule is new", "本票新增规则" in doc)
check("F2 style.css has no max-height", "max-height" not in css and "calc(100vh" not in css)
check("F2 mock .rail has no max-height", "max-height" not in mock)
check("F2 102 derivation parts", all(s in doc for s in ["56", "20", "24", "102"]))

# ---- r2 fix F3: EIE4428 letter-spacing -----------------------------------
check("F3 doc has dedicated .06em row for EIE4428",
      bool(re.search(r"\| 13 \| 400 \| \.06em \| mono \|[^\n]*EIE4428", doc)))
check("F3 .02em meta row no longer covers EIE4428",
      not re.search(r"\| 13 \| 400 \| \.02em \| mono \|[^\n]*EIE4428", doc))
course = re.search(r"\.course \{[^}]*letter-spacing: ([\d.]+em)", mock)
check("F3 mock .course = .06em", course and course.group(1) == ".06em",
      course.group(1) if course else "?")
check("F3 mock body uses .course for EIE4428", '<span class="course">EIE4428</span>' in mock)
check("F3 mock h2 .meta = .02em", "letter-spacing: .02em" in
      re.search(r"\.section h2 \.meta \{[^}]*\}", mock).group(0))

# ---- r2 fix F4: button/select weight -------------------------------------
check("F4 doc has 15/500 row for select,button",
      bool(re.search(r"\| 15 \| 500 \| 0 \| sans \|[^\n]*按钮与下拉", doc)))
check("F4 narrowed 15/400 row (inputs+names only)",
      "| 15 | 400 | 0 | sans | 正文:输入框、名单行" in doc.replace("：", ":"))
check("F4 stale broad 400 row gone",
      "按钮、下拉、输入框、名单行" not in doc)
btn = re.search(r"select, button \{\s*font: (\d+) var\(--fs-body\)", mock)
check("F4 mock select,button = 500", btn and btn.group(1) == "500")
check("F4 mock reg-row input = 400", "font: 400 var(--fs-body)/1.5 var(--sans)" in
      re.search(r"\.reg-row input \{[^}]*\}", mock).group(0))

# ---- r2 Nit: peak tag surface ---------------------------------------------
check("N1 tag contrast now vs --bg 7.73", "对 `--bg` 7.73:1" in doc)
check("N1 stale 7.35 tag claim gone", "对 `--panel` 7.35:1)。比读数" not in doc and "对 --panel 7.35:1)。比读数" not in doc)

# ---- regression: five sections, floors, order, peak, copy ----------------
for sec in ["## 1 字号阶", "## 2 颜色与对比度", "## 3 间距", "## 4 组件规则", "## 5 分区清单"]:
    check(f"R section present: {sec}", sec in doc)
check("R label floor 13px", "标签下限 13px" in doc)
check("R reading 15px mono", "读数一律 15px" in doc)
check("R mobile floor 14px", "升到 14" in doc and "14px" in doc)
order_ok = (".stage { order: 1" in mock and ".controls { order: 2" in mock
            and ".hint { order: 3" in mock and ".registry { order: 4" in mock
            and ".section { order: 5" in mock)
check("R mock mobile order 1..5", order_ok)
check("R doc states picture->controls->hint->registry->telemetry order",
      "画面 → 控件 → 提示行 → FACE REGISTRY" in doc)
for s in ["rgba(154,165,170,.5)", "peak 1.33 Mbps", "margin-left: auto",
          "scaled to a peak of"]:
    check(f"R peak spec in doc: {s!r}", s in doc)
    check(f"R peak source in mock: {s!r}", s in mock)
check("R mock dash 3/3", "setLineDash([3 * dpr, 3 * dpr])" in mock)
check("R mock peak font 12/400/mono/.02em/tabnums",
      "400 12px/1.5 var(--mono)" in mock and "tabular-nums" in mock and
      "letter-spacing: .02em" in re.search(r"\.peak \{[^}]*\}", mock).group(0))
for s in ["Saved as Alice Ng, 3 frames averaged", "No face in frame, hold still",
          "Two faces in frame, show one", "Alice Ng is already saved, add a surname",
          "Analysis is off"]:
    check(f"R five-state copy {s!r}", s in doc)
for c in ["#6ecb8f", "#f0715a", "#e3b45c", "#9aa5aa"]:
    check(f"R state color {c} in doc", c in doc)
check("R doc <= 250 lines", len(doc.splitlines()) <= 250, f"{len(doc.splitlines())}")
check("R no em-dash", "—" not in doc)

# ---- contrast recomputation (fresh, WCAG 2.1) ----------------------------
claims = [
    ("#e9eef0", "#0b0d0e", 16.65, "--text/--bg"),
    ("#9aa5aa", "#0b0d0e", 7.73, "--muted/--bg"),
    ("#9aa5aa", "#101416", 7.35, "--muted/--panel"),
    ("#c3ccd0", "#0b0d0e", 11.94, "--text-2/--bg"),
    ("#7d888d", "#101416", 5.10, "--placeholder/--panel"),
    ("#5fd3c6", "#0b0d0e", 10.78, "--accent/--bg"),
    ("#6ecb8f", "#0b0d0e", 9.83, "--ok/--bg"),
    ("#e3b45c", "#0b0d0e", 10.16, "--warn/--bg"),
    ("#f0715a", "#0b0d0e", 6.69, "--alarm/--bg"),
    ("#f0715a", "#101416", 6.36, "--alarm/--panel"),
    ("#072521", "#5fd3c6", 8.97, "--on-accent/--accent"),
]
for fg, bg, want, name in claims:
    got = round(cr(fg, bg), 2)
    check(f"R contrast {name} = {got} (doc {want})", abs(got - want) < 0.02)
check("R grey >= 7.7", cr("#9aa5aa", "#0b0d0e") >= 7.7)
check("R body >= 16", cr("#e9eef0", "#0b0d0e") >= 16.0)

# ---- residual attack: --panel '画面外分区底' attribution -------------------
# In the signed mock, --panel is used by exactly one rule (.reg-row input).
# Sections have no background. Doc line 46 claims --panel = 输入框底、画面外分区底,
# and doc line 165 now asserts 分区不铺 --panel -> internal contradiction +
# value that cannot be pointed to in the reference (violates doc's own §10 rule).
panel_uses = [i for i, l in enumerate(mock.splitlines(), 1) if "var(--panel)" in l]
check("ATTACK mock --panel used only on .reg-row input", panel_uses == [233],
      f"lines={panel_uses}")
check("ATTACK doc no '画面外分区底' unattributable claim", "画面外分区底" not in doc,
      "doc:46 vs doc:165 self-contradiction" )

fails = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS" if ok else "FAIL"), name, detail)
print(f"\n{len(results) - len(fails)}/{len(results)} checks pass, {len(fails)} fail")
sys.exit(1 if fails else 0)
