# 01 设计规范票 — 独立验收报告（r2）

VERDICT: REJECTED — r1 四处 blocking + 1 Nit 全部亲验修复、零回归、未越界、225 行合规；但 §2:46 `--panel` 用途「画面外分区底」在签字 mock 里指不到（`--panel` 全文仅用于 `.reg-row input`，mock.html:233），且与本轮回改的 §7:165「分区不铺 `--panel`」自相矛盾，是 r1 Nit 同一根因的残留格，过不了票面「每个数值都能在参照图上指到对应位置」。
HEAD: e38d141798b0f71b1501aa4edb1ed41024fbe0d7
LEDGER: 无（gate-ledger.mjs / commit-verdict.mjs 在本仓库与 ~/.agents 全盘不存在，见 [env] 注；本轮证据 = 探针 `verifier-probes/01-design-r2-selfcheck.*` + git 读数，输入哈希见探针 md）

## 定靶

- HEAD `e38d141`。被验提交 `67270fc`（产物修订）+ `e38d141`（设计师自陈报告）。
- `git show --stat 67270fc`：仅 `docs/DESIGN-dashboard.md`（+8/-5 净 +2 行）与票面 +1 行（票面外的决定追记）。**未碰** `src/`、`tests/`、`README.md` —— 越界检查 PASS。
- `git diff 5adcede 67270fc -- docs/DESIGN-dashboard.md` 逐行读过：改动恰为五处（§1 拆 EIE4428 行、§1 按钮 500 档、§6 max-height 来源、§6 移动间距、§7 角标底面），与设计师自陈一致。
- `git status --porcelain`：主工作树仅有 `.scratch/` 未跟踪项（r1 报告、探针、ledger），无 `src/` 侧未提交改动；并行 02 票已提交（`5adcede`）。
- 交付物 225 行（`wc -l` 亲测）≤ 250 上限。文档票：无构建无 pytest，票面要求不跑。
- mock.html `083890b1…`、style.css `9dae0d8e…` 与 r1 账本输入哈希逐字一致 —— 参照物与现状实现自 r1 未动；文档哈希变为 `725b1324…`，本轮全部判据仍用新探针重跑，不引用旧条目。

## 判据重建 → 判定（证据全部来自本轮亲跑）

| 判据 | 判定 | 证据 |
|---|---|---|
| r1-D1 ≤900 分区间距改 8+16 | **FIXED** | doc:156 两档写法；mock.html:181 / :294；探针 F1 五条 PASS |
| r1-D2 max-height 伪来源 | **FIXED** | doc:150 标「本票新增规则」并给 102=56+1+20+24+1 推导；`style.css` `max-height`/`calc(100vh` 0 命中（亲 grep）、mock `.rail`(:180) 无；mock.html:72/:92 支撑拆解；探针 F2 六条 PASS |
| r1-D3 EIE4428 字距 .06em | **FIXED** | doc:22 独立 .06em 行；mock.html:77 `.course .06em`、:328 `EIE4428` 确在 `.course`；meta 行回到 .02em ↔ mock.html:190；探针 F3 五条 PASS |
| r1-D4 按钮/下拉字重 500 | **FIXED** | doc:25 `15/500/sans 按钮与下拉`；doc:24 收窄为输入框+名单行；mock.html:150-151 500、:235/256 400；旧值 11 mono ↔ style.css:89/91；探针 F4 五条 PASS |
| r1-Nit 角标底面改 --bg | **FIXED** | doc:165「对 `--bg` 7.73:1」；探针 N1 两条 PASS |
| 五节齐全、13/15 下限 | PASS 无回归 | doc:9/39/72/91/130；doc:33-35 |
| 对比度复算 | PASS 无回归 | 11 组 WCAG 2.1 独立复算精确命中（灰 7.73/正文 16.65/…）；探针 R-contrast 段 |
| 390 顺序 | PASS 无回归 | doc:151 ↔ mock.html:287-293 order 1-5 |
| 峰值标注可照抄 | PASS 无回归 | doc:161-170 ↔ mock.html:213,220-224,393,395,500,504（含 aria-label、dash 3/3） |
| 五态文案+配色 | PASS 无回归 | doc:178-182 逐字 |
| 与参照图 v2 一致、每值可指 | **FAIL** | §2:46 一处失配，见 FINDINGS-1 |
| 不改 src/tests/README、≤250 行 | PASS | --stat 与 wc 亲测 |
| 无 em dash | PASS | 文档 U+2014 计数 0 |

探针 `.scratch/face-recognition/verifier-probes/01-design-r2-selfcheck.py`：**68/69 PASS，1 FAIL**（exit 1）；读数与明细见 `verifier-probes/01-design-r2-selfcheck.md`。

## FINDINGS

1. **[Blocking] docs/DESIGN-dashboard.md:46** — `--panel` 用途写「输入框底、画面外分区底」；签字 mock 中 `var(--panel)` 全文仅一处（`.reg-row input`，mock.html:233），`.rail`/`.section` 无 `background`（mock.html:180-183），「画面外分区底」指不到参照图任何位置；且与本轮新改的 §7:165「分区不铺 `--panel`」在同一文档内**直接矛盾**。该格抄的是被 v2 替换的旧实现（`style.css:101-103` `.panel` 渐变底仍在），即 r1-Nit 同一根因在 token 表上的残留。03 票照抄 §2 会把全部分区刷成 panel 底而偏离签字图。建议：删「、画面外分区底」（mock 中 --panel 唯一用途即输入框底），或按参照图改写该格。confidence: HIGH
2. [FYI] `.scratch/face-recognition/context.md:34` — 规划段指针称「`max-height: calc(100vh - 102px)`：`src/rvm/web/style.css`」，与现状不符（0 命中，本轮亲验）；此过时指针正是 r1-D2 伪来源的根因，建议派发方订正 context.md 以免下游票再被误导。非本票产物缺陷。
3. [env] `tools/gate-ledger.mjs`、`commit-verdict.mjs`、`adopt-test.mjs` 全机不存在（`dir /s` 空）→ 账本条目无法产生、`## Verdicts` 裁决行无法脚本落盘；沿用 r1 同限制，证据以探针文件与 git 读数代替，报告路径与回执照常给出。

## REMEDIATION

- [spec] docs/DESIGN-dashboard.md:46 删除「、画面外分区底」或按签字 mock 改写 `--panel` 用途格，消除与 §7:165 的自相矛盾（r1-Nit 残留收尾，一行内修复）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| REJECTED | e38d141 | .scratch/face-recognition/reports/01-r2-verifier.md | [spec]1 | 四处整改+Nit 全关零回归，但 §2 --panel 用途残留指不到签字 mock 且与 §7 自相矛盾 |
