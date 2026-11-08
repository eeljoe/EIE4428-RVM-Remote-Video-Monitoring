# 01 设计规范票 — 独立验收报告（r1）

VERDICT: REJECTED — 主体数值核验全过，但 §6/§1 有四处可直接照抄的数值与签字 mock 或现状不符（移动端分区间距、幽灵 max-height、EIE4428 字距、按钮字重），违反 AC「规范与参照图 v2 一致」与票面「每个数值都能在参照图上指到对应位置」。
HEAD: 0f46685b73dba4ff211d15a856e012284f857b5e
LEDGER: 01-r1-001,01-r1-002,01-r1-003

注：`commit-verdict.mjs` 拒绝落盘——票面第 3 行是 `Status: claimed`（无 `**` 加粗），脚本只认 `**Status:**`。verifier 不改票面，未追加 `## Verdicts` 行；请派发方处理票面格式后重跑落盘。

## 定靶

- HEAD `0f46685`（条目 01-r1-003）。被验三提交 `3f2c2f9`（文档+票面）、`dbb669f`（票面订正）、`0f46685`（设计师报告）；`--stat` 证实仅触 `docs/DESIGN-dashboard.md` 与票面/报告文件（条目 01-r1-002），未碰 `src/`、`tests/`、`README.md`。工作树未提交改动属 02 票并行 worker，不计入本票。
- 交付物 `docs/DESIGN-dashboard.md`，223 行（上限 250）。文档票：无构建、无 pytest，票面亦要求不跑。

## 判据重建（票面 AC → 判定）

| AC | 判定 | 证据 |
|---|---|---|
| 五节齐全、下限取签字版 13/15 | PASS | 探针 01-r1-001 第 1-9 项；§1:31-33 |
| 峰值标注形式/颜色/字号/位置可照抄 | PASS | 探针第 32-38 项；mock.html:220-224,393,499-507 |
| 390 顺序 画面→控件→FACE REGISTRY→遥测 | PASS | mock order 1/2/3/4/5；mock-mobile.png 实拍；§6:149 |
| 五态精确文案与配色 | PASS | 探针第 40-47 项；两态锚定 mock 原文，三态已声明设计分配 |
| 与参照图 v2 一致、三文件可打开 | **FAIL** | mock.html 与两 PNG 均可打开且主体一致，但 D1-D4 四处数值失配（下表） |
| 不改 src/tests/README | PASS | 条目 01-r1-002 |

补充亲核：对比度 12 组声明值按 WCAG 2.1 独立复算全部精确命中（灰字 7.73≥7.7、正文 16.65≥16）；`rgba(154,165,170,.5)` 叠加 `#101416` = `#555c60`、对比 2.72，与文档一致。五节之外 §6-§10 为扩展，票面未禁。

## FINDINGS

1. [Blocking] docs/DESIGN-dashboard.md:154 — ≤900/390px 写「分区之间仍是 20 + 18」；mock.html:294 @media≤900 实为 `margin-top: 8px; padding-top: 16px`（视觉间隔 24px 而非 38px）。照抄即让 03 票写错移动端分区间距；且该值在参照图指不到。建议改为照 mock 写 8+16，或明确声明桌面/移动两档各自数值。confidence: HIGH
2. [Important] docs/DESIGN-dashboard.md:148 — 右栏 `max-height: calc(100vh - 102px)` 标「沿用现有实现」；`src/rvm/web/style.css` 全文无 `max-height`/`calc(100vh`（0 次），mock `.rail` 亦无此规则。属伪称沿用、值无出处。建议删除「沿用」表述并给值的来由，或按实际重拟。confidence: HIGH
3. [Important] docs/DESIGN-dashboard.md:21 — `.02em` 行把顶栏 `EIE4428` 与标题 meta 并档；mock.html:77 `.course` 实为 `letter-spacing: .06em`。建议拆行或改 .06em。confidence: HIGH
4. [Important] docs/DESIGN-dashboard.md:23 — 15px 正文档标 `400` 且用途含「按钮、下拉」；mock.html:151 `select, button` 字重 500。建议该行收窄到输入框/名单行，或给按钮单开 500 档。confidence: HIGH
5. [Nit] docs/DESIGN-dashboard.md:163 — 峰值角标对比度引「对 --panel 7.35:1」；分区无面板底色，角标实际落在 `--bg` 上应为 7.73:1。方向保守不误事，但引错表面。confidence: MEDIUM

## REMEDIATION

- [spec] §6:154 移动端分区间距改为与 mock 一致的 8+16（或分档写清桌面 20+18 / ≤900 8+16）。
- [spec] §6:148 `max-height: calc(100vh - 102px)` 去掉「沿用现有实现」伪来源；要么按实际实现写值，要么标为新增规则并给依据。
- [spec] §1:21 顶栏 `EIE4428` 字距改 .06em 或与 meta 拆成两行。
- [spec] §1:23 按钮/下拉字重对齐 mock 的 500（收窄该行用途或新增行）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| REJECTED | 0f46685 | .scratch/face-recognition/reports/01-r1-verifier.md | [spec]4 | 核心数值全过，但四处可照抄值与签字 mock/现状不符 |
