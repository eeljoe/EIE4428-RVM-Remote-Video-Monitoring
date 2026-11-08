# 01 — 监控页设计规范（可读性与简化）

**Status:** claimed
**Blocked by:**
真机自检：不需要
**UI:** yes

## What to build

把已签字的参照图 v2 落成一份可执行的设计规范 `docs/DESIGN-dashboard.md`：字号阶梯、颜色与对比度、间距、组件规则、分区清单、响应式顺序、码率折线峰值标注、注册成功与失败态的精确文案。只写规范，不写实现代码，不改 `src/` 与 `tests/`。

## Acceptance criteria

- [ ] 文档含字号、颜色、间距、组件、分区五节，每节给出可直接照抄的具体值，字号下限取签字版 13px / 15px [AS-6, AS-7]
- [ ] 峰值标注写明形式、颜色、字号与位置，能按文档直接实现 [AS-6]
- [ ] 写明 390px 宽下面板顺序：画面 → 控件 → FACE REGISTRY → 遥测 [AS-7, AS-5]
- [ ] 写明注册成功、无脸、多脸、重名、分析关闭五态的精确文案与配色 [AS-1, AS-4]
- [ ] 规范与参照图 v2 一致，路径、mock.html 与两张截图均可打开 [AS-7, AS-6]
- [ ] 不修改任何 `src/`、`tests/` 或 `README.md` 文件 [AS-5]

## 测试命令

- 人工核对：文档存在、路径有效、每个数值都能在参照图上指到对应位置。
- 无自动化测试；本票不改代码，不跑 pytest。

## 写域

- `docs/DESIGN-dashboard.md`

## 开工包

- **写域**：`docs/DESIGN-dashboard.md`

- **视觉来源**：`.scratch/face-recognition/design/v2/mock.html`（含状态文案注释）与两张截图、`NOTES.md`；mock.html 与截图同为唯一来源，不只用截图。
- **锚点**：`grep -n "font-size" src/rvm/web/style.css` 与 `grep -n "color:" src/rvm/web/style.css` 取旧值对照。
- **尺寸上限**：文档 ≤250 行；不新增依赖、不生成 HTML mock。
- **估算**：预计 25 分钟 / 120 步（设计规范票，固定角色，不受甜点区间下限约束）。

## 验收包

- **判据**：AS-6、AS-7、AS-5；文档五节齐全且数值可指到截图。
- **首攻靶**：字号下限是否写成 13px、对比度是否给数值、390 顺序是否写明、五态文案是否可落地、是否偷偷改了实现文件。
- **相关 AS 摘录**：AS-6 可读性（最小标签 12px、值 15px、对比 4.5:1、行高 1.5、间距 20px）；AS-7 简洁（分区 ≤6、画面第一焦点）。

## 完成条件

文档提交后由独立门对照截图逐条核对；判 `VERIFIED` 前不得标 `resolved`。

## 实现说明

### AC → 证据

- 五节齐全、每节可照抄的具体值:`docs/DESIGN-dashboard.md` §1 字号(第 9-36 行,含 13px 标签 / 15px 读数 / 15px 正文 / 行高 1.5)、§2 颜色与对比度(第 37-69 行,18 个 token 全给 hex + WCAG 实算比值)、§3 间距(第 70-88 行,基准 4 与 11 个档位)、§4 组件(第 89-127 行,含控件五态与 loading/empty/error)、§5 分区清单(第 128-145 行,5 个分区 + 上限 6)。
- 峰值标注可照抄实现:§7 第 157-169 行给出形式(折线上缘 1px 水平虚线)、颜色(`rgba(154,165,170,.5)`,叠加后 `#555c60`,对面板 2.72:1)、字号(12px / 400 / mono / 字距 .02em)、位置(`Video bitrate` 那一行行尾 `margin-left:auto`,与折线右端、与标题右侧 meta 同一条右边线)。位置已按截图核对:`mock-desktop.png` 1440x1000 右上角,裁 x930-1440 / y70-240 放大 2 倍看清 `peak 1.33 Mbps` 与 `RVM1 · H.264-style hybrid` 右端对齐。
- 390px 顺序:§6 第 146-156 行(≤900 的单列顺序在第 149-150 行)写明 画面 → 控件 → 提示行 → FACE REGISTRY → 遥测四区;`mock-mobile.png`(390x844)自上而下可见的画面、两组控件、`Drag on the picture to watch only that area.`、`FACE REGISTRY`,与文档逐项对上。
- 五态文案与配色:§8 第 170-189 行,五态表在第 174-180 行,逐字文案 + 色值(成功 `#6ecb8f`、无脸与多脸 `#f0715a`、重名 `#e3b45c`、分析关闭 `#9aa5aa`),第 182-187 行另补空名单 / 预热 / 录制中三态。
- 与参照图 v2 一致、三份文件可打开:`mock.html` 47986 字节全文读过(样式与结构均取自它),`mock-desktop.png` 1440x1000 / 665562 字节、`mock-mobile.png` 390x844 / 174347 字节,两张都用读图工具打开看过并做过裁切放大核对。
- 不改 `src/`、`tests/`、`README.md`:本票提交 `git show --stat` 只有 2 个文件(`docs/DESIGN-dashboard.md`、本票)。工作树里另有并行 worker 的改动(`src/rvm/server/app.py`、`src/rvm/server/session.py`、`tests/test_face_api.py`)属于其他票,不是本票产物,我没有暂存也没有改它们。

### 假设

- 文档叙述用中文、UI 文案保留参照图英文原文;与票面语言一致,不另翻。
- 重名用 `--warn`、分析关闭用 `--muted`:参照图调色板定义了这两个色但没有可见用例,五态要落色,按语义分配(不是从截图抄的)。
- `No recording yet` 沿用 `src/rvm/web/index.html` 现有文案去掉句号;`No names saved yet` 取 `mock.html` 注释原文。
- Codec 从读数行移到 STREAM 标题右侧 meta(`#m-codec` id 保留),依据 NOTES 第 7 条与 mock 结构。
- 13px 标签下限与 12px 例外并存:13px 管页面文字,12px 只给画面内 OSD、跟踪标签与峰值角标,绝对下限 12px。

### 没覆盖什么

- 没有实现代码、没有新 mock、没有跑 pytest(本票不改代码,票面也要求不跑)。
- 亮色模式未定义:签字版是单暗色,已在 §10 写明要亮色需另开票。
- 无脸 / 多脸 / 重名 / 分析关闭四态的截图不存在(参照图只在 `mock.html` 注释里给了前两个),文案按注释与本票要求落,没有像素证据。
- 390px 下遥测区在首屏之下,未在截图里出现;§4.1 只写了「仍双列、溢出省略号」,真机若大面积截断的退让条件写在同节。

### 复现命令

```powershell
# 文档与行数(上限 250)
Get-Content docs/DESIGN-dashboard.md; (Get-Content docs/DESIGN-dashboard.md).Count

# 数值来源:参照图样式表
Select-String -Path .scratch/face-recognition/design/v2/mock.html -Pattern '--fs-label|--fs-body|\.peak|\.readouts|--muted|--placeholder'

# 对比度复算(WCAG 2.1 相对亮度),灰字 7.73 / 正文 16.65 / 占位 5.10 / 虚线 2.72

# 截图核对:直接打开两张 PNG,或按报告里记录的裁切命令放大右栏
```

### 最脆的一处

峰值角标的落位。实现若把 `peak x.xx Mbps` 塞进读数 `dd` 里而不是 wide 行的行尾弹性位,右对齐会掉到数值后面,12px 也会被 15px 读数继承冲掉;§7 的「同一条右边线」与 §1 的 12px 例外会同时失守。判据以 `mock-desktop.png` 右上角为准。

### 票面外的决定

- 新增 §9 设计变量块:票面五节之外,但不引入新设计决定,只是把 §1-§3 落成可直接抄的 CSS 变量,与文档一一对应。
- 新增 §10 禁项与交付前校对:em dash 禁令、禁远程字体(`tests/test_app.py` 有远程资源禁令)、读数空值占位、DOM id 保留清单,均来自设计指南与仓库现状,不是票面 AC。
- 读数空值由现行 `&mdash;` 改为单个 `-`(`--muted`):现行页面用长破折号当空值,与指南的 em dash 禁令冲突,按指南改,并写进文档。
- `Recording`(`#m-rec`)从 ANALYSIS 移到 TRANSPORT 末行:与 mock 一致,同时避免录制状态在两处重复出现。
- 新增 `docs/DESIGN-dashboard.md`,未触碰 `src/`、`tests/`、`README.md`。

## Verdicts
2026-11-09 r1 REJECTED 0f46685 门判文档四处数值与签字 mock 不符（[spec]4 按产物缺陷改走 [impl] 返工 r2）
