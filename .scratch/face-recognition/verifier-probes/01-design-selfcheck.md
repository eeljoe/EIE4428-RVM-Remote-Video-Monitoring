# 01 设计规范票 — verifier 自检证据（r1）

靶：HEAD `0f46685b73dba4ff211d15a856e012284f857b5e`；交付 `docs/DESIGN-dashboard.md`（223 行）。
账本：`01-r1-001`（探针 52 项，48 PASS / 4 FAIL，退出码 1 为预期）、`01-r1-002`（三提交 `--stat`）、`01-r1-003`（HEAD）。
探针脚本：`.scratch/face-recognition/verifier-probes/01-design-selfcheck.py`（只读，可复跑）。

## 逐条取证

### 1. 五节齐全 + 字号下限 + 行高 1.5 — PASS
- 文档 §1 字号阶 / §2 颜色与对比度 / §3 间距 / §4 组件规则 / §5 分区清单齐全（另有 §6-§10 扩展节，票面未禁）。
- §1:31「标签下限 13px；12px 只出现在画面 OSD / 跟踪标签 / 峰值角标三类」；§1:32「读数一律 15px」；§1:23 正文（按钮、下拉、输入框、名单行）15px；§1:33「≤560px 时 --fs-label 档 13→14，读数正文按钮仍 15px」→ 手机 ≥14px 成立。
- §1:11「全页行高 1.5，无例外」；mock.html `font: var(--fs-body)/1.5` 全局一致。
- 12px 例外与 AS-6「最小标签 12px」相容（真实标签档仍 13px，严于规格）。

### 2. 对比度重算（WCAG 2.1 相对亮度，独立实现）— PASS
算式：`L = 0.2126·R + 0.7152·G + 0.0722·B`（sRGB 分量 ≤0.03928 线性段 `c/12.92`，否则 `((c+0.055)/1.055)^2.4`），`CR = (L_hi+0.05)/(L_lo+0.05)`。
- 灰字 `--muted #9aa5aa` 对 `--bg #0b0d0e` = **7.73:1**（≥7.7 ✓）；对 `--panel #101416` = 7.35:1。
- 正文 `--text #e9eef0` 对 `--bg` = **16.65:1**（≥16 ✓）。
- 其余 9 组声明值全部复算精确命中：text-2 11.94、placeholder 对 panel 5.10（顺带修正 mock 注释自称 4.6 的笔误）、accent 10.78、accent-hover 12.22、on-accent 8.97、ok 9.83、warn 10.16、alarm 6.69 / 6.36、装饰线 1.17/1.31/1.33/1.67。
- 峰值虚线 `rgba(154,165,170,.5)` 叠 `--panel` = `#555c60`（逐通道 0.5·154+0.5·16=85 等），对 panel **2.72:1**，与文档一致。

### 3. 间距 ≥20px + 分区 ≤6 — PASS（桌面）／D3 见 FAIL
- §3:87「分组之间 ≥20px 是硬规则」；桌面分区 `margin-top 20 + padding-top 18 + 1px 线 = 38` 与 mock.html:181 逐字一致。
- §5 点名 5 个分区：STREAM / TRANSPORT / ANALYSIS / FACE REGISTRY / CLIPS（上限 6），mock 恰有 5 个 `.section`。
- §3 表逐项对 mock：页边距 20/24/24、列距 28 行距 20（`gap: 20px 28px`）、读数列间 32、标签到值 10、行 padding 3、注册区 8/10/8/10/5、片段 6/12、顶栏 56×24、OSD 10/(3,8) — 全命中。

### 4. 390px 顺序 — PASS
- §6:149「画面 → 控件 → 提示行 → FACE REGISTRY → 遥测四区」，与票面「画面→控件→FACE REGISTRY→遥测」相容（提示行是 viewer 子项）。
- mock @≤900 order 属性实证：`.stage 1 / .controls 2 / .hint 3 / .registry 4 / .section 5`；mock-mobile.png 实拍同序。注意 mock.html:19 与 :285 注释写成「picture, face registry, controls」是过期注释，CSS 与 PNG 为准 —— 文档对的是渲染事实。
- 390 控件逐行排布（label+select+button 三格、Camera/Decoded 两列、Save/Start 两列、Export 整行）与 mock @900 网格规则及 PNG 一致；七个操作首屏内可见（PNG 实测）。

### 5. 峰值标注 + 五态 — PASS（可落地、与 mock 一致）
- 形式：折线上缘 1px 虚线 = 窗口峰值刻度（画布顶下 6px）、dash 3/gap 3、`rgba(154,165,170,.5)` —— 逐字对 mock.html:499-507（`ceiling=6*dpr`、setLineDash [3,3]、strokeStyle 同值、lineWidth 1）。
- 角标 `peak 1.33 Mbps`（peak + 空格 + 两位小数 + Mbps）12px/400/mono/.02em/tabular-nums/`--muted`，`margin-left:auto` 挂 Video bitrate 行尾 —— 对 mock.html:220-224、393；desktop PNG 右上角证实与 `RVM1 · H.264-style hybrid` 同一条右边线。
- `role="img"` + `aria-label "scaled to a peak of X Mbps"` 对 mock.html:395。
- 五态文案逐字 + 色值：成功 `Saved as Alice Ng, 3 frames averaged`/`#6ecb8f`（mock:436 原句）、无脸 `No face in frame, hold still`/`#f0715a`（mock 注释 :426）、多脸 `Two faces in frame, show one`/`#f0715a`、重名 `Alice Ng is already saved, add a surname`/`#e3b45c`、分析关闭 `Analysis is off`/`#9aa5aa`。后三态 mock 无截图/注释锚，实现说明已声明为按语义分配（重名→--warn、分析关闭→--muted），属票面要求的设计产出；色值全部来自签字调色板。
- 补态：`No names saved yet`（mock 注释 :428）、`No recording yet`（替换现 index.html:109 / app.js:383 的 `No recording yet.` 句号，现存原文已核）。

### 6. 越界检查 — PASS
- `git show --stat dbb669f 3f2c2f9 0f46685`（条目 01-r1-002）：三提交仅触 `docs/DESIGN-dashboard.md`、票面、设计师报告。无 `src/`、`tests/`、`README.md` 改动。
- 工作树现有 `M src/rvm/server/app.py`、`M src/rvm/server/session.py`、`?? tests/test_face_api.py`、`?? tests/test_zzprobe.py` 属 02 票并行 worker，未提交、不在本票三提交内。
- 无新依赖、无新 HTML mock、文档 223 行 ≤ 250。

## FAIL 项（文档 vs 签字 mock / 现状的数值失配）

| # | 文档位置 | 文档写 | 实际（mock/现状） | 证据 |
|---|---|---|---|---|
| D1 | §1:21 | 顶栏 `EIE4428` 与标题 meta 同列 `.02em` | mock.html:77 `.course` `letter-spacing: .06em` | 探针 FAIL D1 |
| D2 | §1:23 | 15px 正文档标 `400`，用途含「按钮、下拉」 | mock.html:151 `select, button { font: 500 var(--fs-body) }` 字重 500 | 探针 FAIL D2 |
| D3 | §6:154 | ≤900/390px「分区之间仍是 20 + 18」 | mock.html:294 @≤900 `.section + .section { margin-top: 8px; padding-top: 16px }`（视觉 24px） | 探针 FAIL D3 |
| D4 | §6:148 | 右栏滚动 `max-height: calc(100vh - 102px)`「沿用现有实现」 | `src/rvm/web/style.css` 全文 `max-height`/`calc(100vh` 出现 0 次；mock `.rail` 亦无此规则 | 探针 FAIL D4 |

四处均为「可直接照抄」的具体值，照抄即偏离签字参照图；且违反文档自订规则 §10:223「每个数值都能在参照图上指到位置；指不到的数值不许写进本文」。
