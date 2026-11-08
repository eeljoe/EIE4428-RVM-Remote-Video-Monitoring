# 01 设计规范票 — 设计师返工报告（r2）

范围：只改 r1 门报告 `.scratch/face-recognition/reports/01-r1-verifier.md` 的四处 [spec] 与一处 Nit（§6 移动端分区间距、§6 max-height 伪来源、§1 `EIE4428` 字距、§1 15px 按钮字重、§7 峰值角标对比度）。没有碰 §2/§3/§4/§5/§8/§9/§10，没有碰 `src/`、`tests/`、`README.md`，没有重写文档。
基数：HEAD `5adcede` → 提交 `67270fc`；`docs/DESIGN-dashboard.md` 223 → 225 行（上限 250）；票面「票面外的决定」+1 行。

## 整改对照（门批评 → 改了哪里 → 源依据）

| # | 门批评原文要点 | 改前 | 改后 | 源依据 |
|---|---|---|---|---|
| 1 | `docs/DESIGN-dashboard.md:154` ≤900 写「分区之间仍是 20 + 18」 | `分区之间仍是 20 + 18。` | `分区之间桌面 20 + 18(视觉间隔 38),≤900px 8 + 16(视觉间隔 24,mock @media (max-width: 900px) 同一选择器)` | `mock.html:181` 桌面 `.section + .section { margin-top: 20px; padding-top: 18px; }`；`mock.html:294` ≤900 同选择器 `{ margin-top: 8px; padding-top: 16px; }`；两档都保留 1px `--line` 上边框 |
| 2 | `:148` `max-height: calc(100vh - 102px)` 标「沿用现有实现」，`style.css` 无此规则 | `(沿用现有实现)` | `(本票新增规则,现状里没有:mock 与 src/rvm/web/style.css 全文都没有这条;102 = 顶栏 56 + 下边框 1 + 布局上内边距 20 + 下内边距 24 + 1px 余量,右栏超高时在栏内滚动,不把整页撑长)` | `style.css` 搜 `max-height` / `calc(100vh` 命中 0；mock `.rail`（`mock.html:180`）只有 `display:flex; flex-direction:column; min-width:0`；102 由 `mock.html:72` 顶栏 `height:56px` + `border-bottom` 1px + `mock.html:92` `.layout padding: 20px 24px 24px` 推得 57+20+24+1 |
| 3 | `:21` 顶栏 `EIE4428` 与标题 meta 并档 `.02em`，mock `.course` 为 `.06em` | 一行同时管 meta 与顶栏，字距 `.02em` | 拆两行：meta 行保留 `.02em`；新增一行 `13 / 400 / .06em / mono / 顶栏 EIE4428 / 旧值 10` | `mock.html:190` `.section h2 .meta { letter-spacing: .02em }`；`mock.html:77` `.course { … letter-spacing: .06em }` |
| 4 | `:23` 15px 正文标 400 且用途含按钮/下拉，mock 为 500 | 一行 `15 / 400 / 0 / sans`，用途写「按钮、下拉、输入框、名单行」，旧值 14 / 11 | 该行收窄为「正文:输入框、名单行」；新增一行 `15 / 500 / 0 / sans`，用途「按钮与下拉(select, button,含分段按钮)」，旧值 `11 大写 mono` | `mock.html:150-151` `select, button { font: 500 var(--fs-body)/1.5 var(--sans) }`；`mock.html:235` `.reg-row input` 400；`mock.html:256` 名单行只给 `font-size: var(--fs-body)`，随 body 400；旧值 `style.css:89` `font: 11px var(--mono)` |
| 5 | Nit `:163` 角标对比度写「对 `--panel` 7.35:1」，实际落在 `--bg` | `色 --muted(对 --panel 7.35:1)` | `色 --muted(对 --bg 7.73:1,角标落在分区底即页底,分区不铺 --panel)` | mock 的分区没有 `background`（`mock.html:181/183` 只有 margin/padding/border），`var(--panel)` 在 mock 全文只用于 `.reg-row input`（`mock.html:233`）；独立复算 `#9aa5aa`/`#0b0d0e` = 7.73、`#9aa5aa`/`#101416` = 7.35 |

改后跑了一组 14 条断言（文档 ↔ mock.html / style.css 原文比对 + WCAG 复算 + 行数），全 PASS：

```
PASS D1 桌面 20+18 仍在            PASS D1 ≤900 8+16 新增          PASS D1 mock 源 8/16
PASS D2 沿用字样已删               PASS D2 新增规则+来源声明        PASS D2 style.css 无 max-height
PASS D3 EIE4428 独立 .06em 行      PASS D3 mock .course .06em
PASS D4 15/500 sans 按钮下拉行     PASS D4 15/400 仅输入框名单行    PASS D4 mock select,button 500
PASS N1 角标对 --bg 7.73           PASS N1 §7 无 7.35 残留          PASS 行数 ≤250 (225)
fail=0
```

## 自截自改（本轮为何没有截图）

本票产物是一份 markdown 规范，没有构建、没有渲染产物，也没有改任何页面代码。四处改动是文字数值：字距 `.02em → .06em` 在 13px mono 上肉眼不可见，分区 `20+18 → 8+16` 只在 ≤900px 生效。所以这一轮我没有截图，也没有重新打开两张 PNG 冒充「看过」；替代证据是上面 14 条对源文件的断言 + `git diff` 逐行核对。这是本轮唯一的取舍：看图能判「位置对不对」，这五条要判「数值抄得对不对」，后者只能对 mock.html / style.css 原文。r1 已对两张图做过逐项定位，本次没有推翻任何位置结论。

自评三行（对着 mock 样式表，不是对着图）：

- 层级：15px 现在分两档权重（按钮/下拉 500、输入框与名单行 400），层级靠字重不靠字号，与 mock `select, button` 500 对齐；读数仍独占 15/500 mono + `tabular-nums`，不与控件混档。
- 对齐：`EIE4428` 的 .06em 与分区 meta 的 .02em 拆开后各有唯一出处（mock:77 / mock:190），不再「一个值两个用途」；角标与标题 meta、折线右端共用同一条右边线，本次未动。
- 重复项：§1 表里不再有「一档管两种字重」的行，15px 两行用途互斥；字重只在 §1 给一次，§4.2 仍只管尺寸与状态，没有第二处写同一件事。

## 假设

- 102px 的拆解按 mock 的顶栏 56 + 下边框 1 + `.layout` 上下内边距 20/24 推得，另留 1px 余量；若 03 票把滚动容器放在 `.rail` 之外，这条要重算。
- 「≤900px 8 + 16」取 mock 的 `@media (max-width: 900px)`，与本文 §6 的 900/901 断点一致，不新增断点。
- 按钮 500 只写进 §1，不在 §4.2 重复第二遍字重，避免两处维护同一个值。

## 没覆盖什么

- 没改 §2/§3/§4/§5/§8/§9/§10；没改票面 AC、`Status:`、`## Verdicts`；没碰 `src/`、`tests/`、`README.md`；没跑 pytest（票面要求不跑）。
- 观察但不改（超出 r1 门报告四条范围）：§2 第 44 行把 `--panel` 用途写成「输入框底、画面外分区底」，而 mock 的分区没有底色（`mock.html:181` 只有 border/margin/padding），`var(--panel)` 在 mock 只服务 `.reg-row input`（`mock.html:233`）。这句与 Nit 的结论同源，但不在四条之内，按要求未动，交派发方决定是否另开一轮。
- 返工轮按规矩跳过认领、不改 `Status:`（仍为 `claimed`）。

## 复现

```powershell
git show --stat 67270fc                     # 2 files: docs/DESIGN-dashboard.md + 票面
(Get-Content docs/DESIGN-dashboard.md).Count   # 225
Select-String -Path .scratch/face-recognition/design/v2/mock.html -Pattern '\.course|select, button|@media \(max-width: 900px\)|\.section \+ \.section'
Select-String -Path src/rvm/web/style.css -Pattern 'max-height|calc\(100vh'   # 0 命中
git diff 5adcede 67270fc -- docs/DESIGN-dashboard.md
# 对比度：#9aa5aa on #0b0d0e = 7.73；on #101416 = 7.35（WCAG 2.1 相对亮度实算）
```

## 最脆的一处

§6 的 `102`。它是**新增**值，按 mock 的顶栏 56 + 1px 边框 + 上下内边距 20/24 推出，任何一项改（顶栏变高、padding 变）都要同步改 102；它同时是「1440x1000 一屏到底」的支点（1000 − 102 = 898，按 §7 记录右栏从 y=77 起、内容底 953，即右栏内容 876，刚好放得下）。实现若把右栏内容塞进别的滚动容器，这条会静默失效而页面看起来仍然正常，只有真机短视口才暴露。

## 回执

| 票号 | 交票/受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 01-design-dashboard | 交票 | 67270fc | `.scratch/face-recognition/reports/01-r2-designer.md` | r1 门报告四处 [spec] 与 1 Nit 全部按 mock.html/style.css 原文订正，14 条断言全 PASS，只动 docs/ 与票面一行 |
