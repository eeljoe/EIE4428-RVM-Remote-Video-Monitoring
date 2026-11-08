# 03 整页可读性与结构重做 — r1 worker 报告

- 票面：`.scratch/face-recognition/issues/03-dashboard-readability.md`
- 状态：claimed（`resolved` 是门的动作）
- 提交：认领 `889f0d5`，交付 `218c7ad`
- 规范：`docs/DESIGN-dashboard.md`（数值照抄），参照图 `.scratch/face-recognition/design/v2/`
- 真机证据：`.scratch/face-recognition/verifier-probes/03-dashboard-readability-selfcheck.md`

## 交付了什么

整页重写三件套（`index.html` 116 → 135 行、`style.css` 191 → 326 行、`app.js` 411 → 495 行，另 `tests/test_app.py` 346 → 654 行）。分区从「4 个分区 + 一个独立 Bitrate 分区 + 每行一条虚线 + 三组控件各一个框」变成 5 个分区、全页只剩分区之间的细线；字号从 10/11/12 的微字阶升到 13 标签 / 15 读数 / 15 正文；画面两角 OSD 取代底部 overlay 与 `CAM 01` 双份标签；码率折线加了峰值虚线与 `peak x.xx Mbps` 角标；390 用 `display: contents` + `order` 排成 画面 → 控件 → 提示 → FACE REGISTRY → 遥测。

`docs/DESIGN-dashboard.md` §5 的三处迁移都做了：`#m-codec` 进 STREAM 标题 meta、`#m-rec` 进 TRANSPORT 末行、`#src-label`/`#time-label` 进画面两角 OSD、`#view-label` 转 `sr-only`。既有 48 个 DOM id 全部保留。

## AC → 证据

| AC | 证据 |
|---|---|
| 标签 13 / 读数 15 / 正文 15 / 手机 ≥14 / 行高 1.5 | `tests/test_app.py:411`、`:442`；实测 `13px/19.5px`、`15px/22.5px`、390 上 `14px/21px` + 读数仍 `15px/22.5px` |
| 灰字 ≥7.7:1、正文 ≥16:1 | `tests/test_app.py:452`（从服务端 CSS 取 hex 实算）；实测 **7.73:1** / **16.65:1** |
| 分组 ≥20px、分区 ≤6、去冗余框线与重复标签、画面第一焦点 | `tests/test_app.py:477`、`:502`、`:529`；实测 20+18（桌面）/ 8+16（单列）、分区 5 个、画面盒 904x678 为页面最大面积 |
| 峰值虚线与 `peak x.xx Mbps`（12px 灰、不新增分区、与 `history.bitrate` 最大值同源） | `tests/test_app.py:549`；`app.js:179` 的 `const peak = Math.max(...history.bitrate)` 同时喂 `app.js:225` 角标与折线归一化；截图里虚线在折线上缘、`peak 0.12 Mbps` 与其同高 |
| 390 顺序 画面 → 控件 → FACE REGISTRY → 遥测 | `tests/test_app.py:585`；实测 top 68 / 353 / 611 / 656 / 861 |
| 既有 DOM ID + 八项操作、390 无横向溢出、1440 无截断操作 | `tests/test_app.py:605`、`:639`；实测 `scrollWidth 390`、最右边 390、读数 0 条截断；1440 文档高 1000、七个操作底边 815/875 |
| 无远程资源、无新增依赖、全套通过 | `tests/test_app.py:87` 既有禁令；`pytest` 562 passed |

## TESTS

命令与退出码（票面给的两条，原样）：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_delivery.py -q
.....................................................                    [100%]
exit=0

$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [100%]
exit=0
```

`pyproject.toml` 的 `addopts` 已带一个 `-q`，再加 `-q` 会把汇总行也压掉，所以同一棵树再跑一遍不带重复 `-q` 的，拿到计数：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_delivery.py
53 passed in 3.05s
exit=0

$ .venv\Scripts\python.exe -m pytest
562 passed in 24.00s
exit=0
```

### 先红：改造前跑新增的十条（`src/rvm/web/` 还是旧版）

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py -q -k 'type_ladder or mobile_keeps or grey_text or groups_are or redundant_frames or first_focus or peak_rule or narrow_layout or every_id or registry_section'
FAILED tests/test_app.py::test_the_type_ladder_is_13px_labels_and_15px_values
FAILED tests/test_app.py::test_mobile_keeps_body_text_at_15px_and_labels_at_14px
FAILED tests/test_app.py::test_the_grey_text_clears_7_7_to_1_and_body_text_clears_16_to_1
FAILED tests/test_app.py::test_groups_are_separated_by_at_least_20px_and_there_are_five_sections
FAILED tests/test_app.py::test_the_redundant_frames_and_duplicate_labels_are_gone
FAILED tests/test_app.py::test_the_picture_is_the_first_focus_and_nothing_else_is_boxed
FAILED tests/test_app.py::test_the_peak_rule_and_its_tag_share_the_traces_maximum
FAILED tests/test_app.py::test_narrow_layout_orders_picture_controls_registry_then_telemetry
FAILED tests/test_app.py::test_the_page_keeps_every_id_and_all_eight_operations
E       AssertionError: missing DOM ids: ['m-peak', 'face-name', 'face-remember', 'face-status', 'face-list']
FAILED tests/test_app.py::test_the_registry_section_holds_the_name_input_and_the_list
exit code 1
```

十条全红，理由都是「旧页面还没这么写」，不是测试写错。

### 改一行必须红（自打首攻靶，改完按 SHA256 还原）

样式表 `sha256 8351fbc2…4fc65e1`、`app.js sha256 443999fb…d3fda336`，每轮改完都回到同一哈希再复绿。

```
--fs-label: 13px -> 12px        -> FAILED test_the_type_ladder_is_13px_labels_and_15px_values      -> 复绿
.peak 400 12px -> 400 15px      -> FAILED test_the_peak_rule_and_its_tag_share_the_traces_maximum -> 复绿
.registry { order: 4 } -> 3     -> FAILED test_narrow_layout_orders_picture_controls_registry_then_telemetry -> 复绿
app.js peak = Math.max(...) -> const peak = 1000000
                                -> FAILED test_the_peak_rule_and_its_tag_share_the_traces_maximum -> 复绿
restored sha=8351FBC2…4FC65E1 / 443999FB…D3FDA336（与改前逐字节相同）
```

### 覆盖清单

派发消息里的 `node tools/coverage-tests.mjs` 读数为「无覆盖：`src/rvm/web/index.html`、`style.css`、`app.js`、`tests/test_app.py`」——这四个文件没有既有覆盖测试，所以没有「改完先跑、不许改红」的对象；相关回归靠 `tests/test_app.py` 的既有断言（远程资源禁令、focus-visible、reduced-motion、两份 media query、`min-height: 40px`、DOM 契约）与 `tests/test_delivery.py` 的 `#stream` 内联 `src` 断言，二者都仍在且全绿。

### 一次并非我造成的红（如实记录）

改造中途的某次全套跑出 2 条失败：`tests/test_face_store.py::test_a_registration_that_lands_during_a_removal_is_not_lost`、`::test_two_removals_of_different_names_both_take_effect`。当时工作区里 `src/rvm/server/session.py` 与 `tests/test_face_store.py` 有另一会话（06 号票）未提交的改动（`git diff --stat` 显示 +174/−8 行）；该会话提交后（`2af49cd`）再跑全套即 562 passed。这两条与 Web 资产无关，也不在本票写域内。

## 真机自检

文件：`.scratch/face-recognition/verifier-probes/03-dashboard-readability-selfcheck.md`（脚本、JSON、截图同目录）。

- 服务：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099`（`Invoke-WebRequest` 读到 `/` 200、`/static/style.css` 200）
- 截图：`03-desktop-1440x1000.png`（1440x1000）、`03-mobile-390x844.png`（390x844），都用看图工具逐张看过（结论写在探针文末）
- 关键读数：桌面文档 `1440x1000`（无页面滚动）、画面盒 904x678、右栏 460x809、灰字 7.73:1、正文 16.65:1；390 `scrollWidth 390`（无横向溢出）、标签 14 / 读数 15、顺序 68→353→611→656→861、七个操作底边 ≤595
- 偏差记录：390 的读数改单列。同一页面强制双列量到 9 条读数被截断（`m-res 79>45` 等），按规范 §4.1「超过三条才退回单列」的条款退回，字号未动

## COMMITS

| 哈希 | 说明 |
|---|---|
| `889f0d5` | `chore: 认领 03 可读性重做`（只含票文件 Status） |
| `218c7ad` | `feat(web): 03 整页可读性重做（字号阶梯、对比度、分组、峰值标注、390 顺序）`（三件套 + `tests/test_app.py` + 票面实现说明 + 探针脚本/JSON/两张 PNG + 清掉被误提交的探针中间件）——回执里的提交哈希指这一条 |
| `3213681` | `docs: 03 号票 r1 worker 报告与回执`（本报告；顺带把票面与报告里的 id 计数由 43 校正为 48） |

精确暂存：逐个 `git add <路径>`，未用 `git add -A`；同目录里另一会话的 `ledger/06-r1.jsonl` 与 `verifier-probes/06-det/` 保持未跟踪、未进本票提交。

## IMPLEMENTED

1. **字号阶梯**（`style.css:10-33` 的变量、`style.css:40-45` 的 `body`、`style.css:188-216` 的读数与角标）：`--fs-label: 13px` / `--fs-body: 15px`、`body { font: var(--fs-body)/1.5 }`、`.readouts dt` 13px、`dd` 15px mono `tabular-nums`、标题 13px/600/大写/`--text-2`、meta 13px mono、OSD 与跟踪标签与峰值角标 12px；`@media (max-width:560px)` 只把 `--fs-label` 升到 14px。
2. **颜色与对比度**（`style.css:10-33`）：按规范 §9 逐字抄 18 个变量；全表 `gradient` 出现 0 次（无渐变底、无扫描线）。
3. **结构**（`index.html`）：5 个分区 + 顶栏 + 画面区；`#m-codec` 进 STREAM 标题 meta（`:74`）；`#m-rec` 进 TRANSPORT；两枚 OSD 进画面两角（`:28`）；`#view-label` 转 `sr-only`；删 `data-channel` 与底部 overlay；`dl.readouts` 双列 + 三条 wide 行（Video bitrate / Detection zone / Face IDs，`:80`）。
4. **控件**（`style.css:137-163`）：40px 高、`--raised` 底 + `--line-strong` 边、hover/active/focus-visible/disabled 齐、`.seg.active`（`:158`）实心强调色、`#record.active` 告警色。
5. **峰值标注**（`app.js:162-235`）：`drawSpark` 按 canvas 的 CSS 尺寸 × DPR 定后端尺寸，`peak = Math.max(...history.bitrate)`（`:179`）同时决定归一化与 `peak x.xx Mbps` 角标（`:225`），`setLineDash([3,3])` 的 `rgba(154,165,170,.5)` 虚线（`:187`）与折线上缘同高，`aria-label` 写成 `scaled to a peak of X Mbps`；1 个样本时画点，0 个样本时角标 `peak -`。
6. **390 顺序**（`style.css:285-311`）：`.viewer, .rail { display: contents }`（`:289`）+ `.stage{order:1}` `.controls{order:2}` `.hint{order:3}` `.registry{order:4}`（`:296`）`.section{order:5}`；控件在 390 三列（标签/下拉/按钮）逐行、Camera|Decoded 与三个动作两列、`Export metrics` 独占。
7. **读数占位**（`app.js:17-23` 的 `setText` + `style.css:198` 的 `.pending`）：未到的值显示灰色 `-`（不是长破折号、不是 `n/a`），首帧到数即去掉灰。
8. **测试**（`tests/test_app.py:350-654`）：新增 10 条静态测试 + 5 个解析/对比度助手（`:root` 取 token、`@media` 块按花括号配对、WCAG 相对亮度、字号扫描）。
9. **真机探针**：`03-dashboard-readability-selfcheck.py` 自包含（起 8111 的慢像素服务、iframe 视口、`--dump-dom` 取读数、`--screenshot` 裁到视口），落 JSON 与两张 PNG。

## 收尾自检

逐条回对 diff 与文件：

- 「48 个 DOM id 全在」→ 命中（`test_the_page_keeps_every_id_and_all_eight_operations` 的 kept 列表逐条 grep 命中）
- 「八项操作」→ 命中（7 个 `.onclick`/`.onchange` + `wireZone` 的 pointerdown/up + `postJSON("/api/motion"`）
- 「`#stream` 仍是内联 src 且含 stream.mjpg」→ 命中（`index.html:22`，`test_delivery.py:40` 绿）
- 「分区 5 个」→ 命中（HTML `class="section` 5 次、浏览器 `querySelectorAll(".section").length` 5）
- 「无渐变/扫描线」→ 命中（`linear-gradient` 不出现；`repeating-linear-gradient` 不出现）
- 「无远程资源」→ 命中（`test_operator_page_loads_no_remote_frontend_assets` 绿；新 CSS 只引 data: SVG）
- 「字号最小 12px」→ 命中（`font_sizes()` 最小 12）
- 「390 无横向溢出」→ 命中（探针 `scrollWidth 390` / `widest_right 390`）
- 「1440 无被截断操作」→ 命中（七个操作底边 815/875 ≤ 1000）
- 「峰值与数组同源」→ 命中（`app.js:179` 单点取值，静态测试 + 改 1000000 即红）
- 「灰字 7.73 / 正文 16.65」→ 命中（测试实算 + 浏览器读回色值）
- 「390 顺序」→ 命中（静态 order 断言 + 浏览器 top 值）

12 条命中、0 条落空。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 03 | 交票 | 218c7ad | reports/03-r1-worker.md | 十条静态测试先红后绿、双档真机截图与读数落盘、全套 562 通过 |
