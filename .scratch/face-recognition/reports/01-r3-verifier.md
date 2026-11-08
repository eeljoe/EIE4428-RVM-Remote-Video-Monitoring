# 01 设计规范票 — 独立验收报告（r3 复验）

VERDICT: VERIFIED — r2 门判唯一残留（§2 `--panel` 用途与 §7 自相矛盾）亲验修复：mock 全文 `var(--panel)` 仅 `:233` 输入框一处，§2:46/§2:66/§7:163/§7:166 口径全一致；攻坚自称清掉的 5 处同根残留逐格对照 mock 原文全部坐实修好；15 组对比度独立复算精确命中；r1/r2 已 PASS 项零回归；越界与行数合规。
HEAD: 6edd865dd9ab199ed0296a6d8c890902f492b2ca
LEDGER: 无（gate-ledger.mjs / commit-verdict.mjs / adopt-test.mjs 在本仓库与 ~/.agents 全盘不存在，本轮 `find` 复验仍缺，同 r1/r2 [env] 限制；证据 = 探针 `verifier-probes/01-design-r3-selfcheck.{py,md}` + git 读数，探针脚本自含全部输入与断言）

## 定靶

- HEAD `6edd865`（`git rev-parse HEAD` 亲跑）。被验提交 `eb0ff43`（产物 8 处 + 票面 r3 段）+ `6edd865`（攻坚报告，不入验收面）。
- `git show --stat eb0ff43`：仅 `docs/DESIGN-dashboard.md`(+8/-7 净 +1) 与票面(+20 `## 实现说明(r3)`)。**未碰** `src/`、`tests/`、`README.md` —— 越界 PASS。
- `git show eb0ff43 -- docs/...` 逐 hunk 读过：4 个 hunk，恰为攻坚自陈的 8 处修改（§2 七格 + 新增规则行 + §7:163 一句），无夹带。
- `git diff HEAD -- docs/DESIGN-dashboard.md` 空、`git log -1 -- docs/...` = `eb0ff43`：工作树文档即被验版本。
- `git status --porcelain`：仅 `.scratch/` 未跟踪项与历史遗留 `nul`；无 `src/` 侧未提交改动。
- 交付物 226 行（`wc -l` 亲测）≤250。文档票：无构建无 pytest，票面要求不跑。

## 判据重建 → 判定（证据全部本轮亲跑）

| 判据 | 判定 | 证据 |
|---|---|---|
| r2-Blocking §2:46 `--panel` 用途与 mock:233 一致 | **FIXED** | doc:46「输入框底(签字 mock 唯一用例…)」；probe 计 `var(--panel)` 全 mock 恰 1 次=`:233 .reg-row input` |
| §2/§7 不再矛盾 | **FIXED** | doc:46+66「分区不铺底色/`--panel` 只给输入框」↔ doc:163「落在 `--bg` 上」↔ doc:166「分区不铺 `--panel`」；mock `.rail`(:180)/`.section` 全文无 `background`（亲 grep 7 处 `.section` 选择器零 background），body `--bg`(:62) |
| 同根残留 1：§7:163 虚线底面 | **FIXED** | doc:163「画布透明、落在 `--bg` 上,叠加后约 `#53595c`,对 `--bg` 约 2.7:1」；mock `#spark`(:213) 无底色 + JS `clearRect`(:495) + `rgba(154,165,170,.5)`(:504)；独立复算合成色 `#52595c`/`#53595c`（82.5 通道取整两可）、对比 2.729≈约 2.7:1 |
| 同根残留 2：§2:49 `--line` 底面 | **FIXED** | doc:49「对 --bg 1.37:1」；复算 1.374；三处线用（:181 分区线、:255 名单线、:270 片段线）+ 折线基线(:523 `#252c30` 画于透明画布) 全落 `--bg` |
| 同根残留 3：`--muted`/`--alarm` panel 括注 | **FIXED** | doc:53/61 复算值保留、括注已删（probe 逐行断言） |
| 同根残留 4：§2:57 `--accent-soft` 用途 | **FIXED** | doc:57「mock 调色板定义、画面未用」；`var(--accent-soft)` 全 mock 0 用例（仅 :38 定义）；ROI 底为字面量 `#5fd3c60f`(:127)、选中底为 `--accent` 实心(:172) |
| 同根残留 5：§2:62 `--alarm-soft` 用途 | **FIXED** | doc:62「录制按钮底(检测框底 mock 用同族字面量 `#f0715a1a`)」；`var(--alarm-soft)` 真用例 `:174 #record.active`（另有 `:265 .x:hover`，doc §4.2:114 已对应，不构成矛盾）；`.bbox` 底确为 `#f0715a1a`(:129) |
| 五节齐全、13/15 下限 | PASS 无回归 | §1-§5 标题在位；doc:33「标签下限 13px；12px 只出现在三类画面与标注文字」 |
| 对比度复算 | PASS 无回归 | 15 组 WCAG 2.1 独立复算全部精确命中（见探针 md 表） |
| 390 顺序 | PASS 无回归 | doc:152 ↔ mock:287-293 order 1-5；doc:157「≤900px 8+16」↔ mock:294 |
| 峰值标注可照抄 | PASS 无回归 | §7 四要素齐（形式/颜色/字号/位置），mock:393 `.peak` 行尾 + :220-224 + :395 aria-label + :500-505 |
| 五态文案+配色 | PASS 无回归 | §8:179-183 五句逐字在 doc；`Saved as…`/`No face…`/`No names saved yet` 锚定 mock:426/428/436 |
| 与参照图 v2 一致、每值可指 | **PASS** | 本轮唯一失配格已修；`panel` 8 处逐处指到 mock |
| 不改 src/tests/README、≤250、无 em dash | PASS | --stat、wc、U+2014 计数 0，全亲测 |
| 参照三文件可打开 | PASS | mock.html 47986B；两 PNG 签名+IHDR 亲读 1440x1000 / 390x844 |

探针 `.scratch/face-recognition/verifier-probes/01-design-r3-selfcheck.py`：**40/40 PASS**（exit 0）；读数与明细见同目录 `01-design-r3-selfcheck.md`。

## FINDINGS

1. [FYI] `.scratch/face-recognition/context.md:34` — 过时 `max-height` 指针（r2 门 FYI-2 复核仍存在）：「`max-height: calc(100vh - 102px)`：`src/rvm/web/style.css`」与现状不符（style.css 全文 0 命中，r2 亲验、本轮沿用其读数且 doc:151 亦自述现状没有该规则）。非本票写域，建议派发方订正，防下游票再被误导。confidence: HIGH
2. [env] `tools/gate-ledger.mjs`、`commit-verdict.mjs`、`adopt-test.mjs` 全机不存在（本轮 `find` 复验）→ 账本条目与 `## Verdicts` 脚本落盘不可行；沿用 r1/r2 同限制，证据以探针文件 + git 读数代替，票面 Verdicts 行由派发方手工落。

无 Blocking / Important / Nit 产物缺陷。`#52595c` vs 文档「约 `#53595c`」属 82.5 取整两可且文档自带「约」对冲、对比值正确，不列缺陷。`--alarm-soft` 第二用例 `.x:hover`(:265) 未列进 §2 用途格但 §4.2:114 已声明同 token，用途格未声称唯一用例，不列缺陷。

## REMEDIATION

无（整改项按标签计数为空）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 6edd865 | .scratch/face-recognition/reports/01-r3-verifier.md | — | r2 唯一残留与 5 处同根残留全部亲验修复，15 组对比度复算精确命中，零回归零越界 |
