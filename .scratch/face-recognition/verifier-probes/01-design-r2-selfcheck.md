# 01 设计规范票 r2 — verifier 自检探针（本轮新鲜证据）

运行：`python .scratch/face-recognition/verifier-probes/01-design-r2-selfcheck.py`
结果：**68/69 PASS，1 FAIL**（exit 1）。全部证据在本会话现场重算，未转述上轮读数。

输入哈希（sha256，本次实测）：
- `docs/DESIGN-dashboard.md` `725b1324…`（67270fc 后的新值，r1 时是 `c4f425e0…`）
- `mock.html` `083890b1…`（与 r1 账本一致，参照图未动）
- `src/rvm/web/style.css` `9dae0d8e…`（与 r1 账本一致，实现未动）

## 四条 r1 blocking 逐条核对（doc 行号 ↔ mock 原文行号）

| # | r1 批评 | 现状 | 证据 |
|---|---|---|---|
| 1 | ≤900 仍写 20+18，mock 实为 8+16 | **修复** | doc:156「分区之间桌面 20 + 18(视觉间隔 38),≤900px 8 + 16(视觉间隔 24…)」；mock.html:181 桌面 `margin-top:20px; padding-top:18px`、mock.html:294 @media≤900 `margin-top:8px; padding-top:16px`；旧串「分区之间仍是 20 + 18」已不存在 |
| 2 | `max-height` 伪称「沿用现有实现」 | **修复** | doc:150 改标「本票新增规则,现状里没有:mock 与 style.css 全文都没有这条」，并给出 `102 = 56+1+20+24+1` 推导；亲验 `style.css` 全文 `max-height`/`calc(100vh` 0 命中、mock `.rail`(:180) 无此规则；mock.html:72 顶栏 56+1 边框、:92 `.layout` padding 20/24 与拆解吻合 |
| 3 | `EIE4428` 并入 .02em 档 | **修复** | doc:22 独立行 `13 / 400 / .06em / mono / 顶栏 EIE4428`；mock.html:77 `.course { letter-spacing: .06em }`、:328 `<span class="course">EIE4428</span>`；.02em meta 行（doc:21）只剩 `RVM1 · …`，对 mock.html:190 `.section h2 .meta .02em` |
| 4 | 15px 行标 400 含按钮/下拉 | **修复** | doc:25 新行 `15 / 500 / 0 / sans / 按钮与下拉(select, button,含分段按钮)`；doc:24 收窄为「输入框、名单行」；mock.html:150-151 `select, button { font: 500 var(--fs-body)/1.5 var(--sans) }`、:235 `.reg-row input` 400、:256 `.names .who` 随 body 400；旧值 `11 大写 mono` 对 style.css:89/91 |

Nit：doc:165 已改「对 `--bg` 7.73:1,分区不铺 `--panel`」，7.35 角标残留已清（探针 N1 两条 PASS）。

## 回归项（上一轮 PASS，本轮复核未回归）

五节齐全（doc:9/39/72/91/130）；13/15 下限与 ≤560 升 14 规则（doc:33-35）；
对比度 11 组声明值 WCAG 2.1 独立复算全部精确命中（灰 7.73、正文 16.65、对 --panel 7.35/5.10/6.36、--on-accent 8.97）；门槛 灰≥7.7、正文≥16 复算满足；
390 顺序 doc:151 ↔ mock.html:287-293 `order:1/2/3/4/5`；
峰值标注形式/颜色/字号/位置/aria-label 齐（doc:161-170 ↔ mock.html:213,220-224,393,395,500,504）；
五态文案逐字 + 配色（doc:178-182）；
`删除 ×` 32x32 / ≤900 40x40（doc:113 ↔ mock.html:259-264,304）；
`#spark` CSS 高 30px（mock.html:213，canvas 60 为 backing store，JS 按 CSS box 重设:479-485）；
无 em dash；225 行 ≤250。

## 攻击探针（本轮新增，唯一 FAIL）

- `ATTACK mock --panel used only on .reg-row input` PASS：mock 全文 `var(--panel)` 仅出现于 **mock.html:233**。
- `ATTACK doc no '画面外分区底' unattributable claim` **FAIL**：doc:46 `--panel` 用途仍写「输入框底、画面外分区底」——签字 mock 中分区无底色（mock.html:180-183 无 `background`），该用途指不到参照图位置，且与 doc:165「分区不铺 `--panel`」**自相矛盾**。旧实现 `style.css:101-103` `.panel` 确有 panel 渐变底——即该格抄的是被替换的旧设计。

## 环境记录

`gate-ledger.mjs` / `commit-verdict.mjs` / `adopt-test.mjs` 在本仓库与 `C:\Users\joe\.agents` 全盘不存在（dir /s 搜索为空）→ 本轮无法产生账本条目、裁决无法脚本落盘；证据以本探针与 git 读数代替。与 r1 门同一限制。
