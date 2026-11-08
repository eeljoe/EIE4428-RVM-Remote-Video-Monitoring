# 03 整页可读性与结构重做 — 独立验收报告（r1）

VERDICT: VERIFIED — 干净 worktree 亲跑：全套 634 绿、定向 53 绿；served 字节与副本逐文件同 sha256；真 Chrome 两档实测字号/行高/颜色全部命中票面数值；对比度按 served hex 独立重算 7.73/16.65；390 顺序、无横向溢出、1440 无截断、峰值与 `history.bitrate` 最大值同源（脚本化 14 帧运行时实测 "peak 2.50 Mbps" 而末值 700 kbps）；四族变异全部被杀并还原。
HEAD: 218c7adbac379dea0827513207f950f6a8699df2
LEDGER: 03-r1-001,03-r1-002,03-r1-003,03-r1-004,03-r1-005,03-r1-006,03-r1-007,03-r1-008,03-r1-009

## 定靶

- 被验提交 `218c7ad`（派发方指定）。其上 `3213681`/`19f7b48` 仅为 worker 报告文档提交，`git diff 218c7ad..HEAD -- src tests` 为空，被验代码不变。
- 验收副本 `C:\Users\joe\AppData\Local\Temp\verify-03-verify-218c7ad`（gate-kit worktree --detach @218c7ad，验收后 cleanup）；`pythonpath=["src"]` 使副本 pytest 解析副本代码；服务端 `run_server.py --no-camera --port 8137` 从副本启动，`WEB_ROOT` 即副本 `src/rvm/web`。
- 基线 `218c7ad~1`；写域 diff = 4 文件 +780/−234（计 1014 行变更：app.js 126、index.html 179、style.css 401、test_app.py +308）。**超过 500 行标注**：票面已预先声明「整体重写 CSS 预计超 300 行，按 OVER-LIMIT 分级走额外静态实例」，属派发方已路由的例外；删除的大头是探针目录清理（4008 行），不计入写域。
- 探针与证据：`.scratch/face-recognition/verifier-probes/03-dashboard-readability-verifier.{py,md}`、`03-verifier-measure.json`、两档 PNG 截图（本目录新文件，未覆盖任何既有条目）。

## 判据重建 → 判定

判据按票面 7 条 AC + spec AS-5/6/7 重建，每条独立取证（账本条目 → `verifier-probes/03-verifier-measure.json` 字段）。

| # | 判据 | 判定 | 亲取证据 |
|---|---|---|---|
| C1 | 标签 13px、读数 15px、正文 15px、手机正文 ≥14px、行高 1.5 | PASS | 真 Chrome getComputedStyle（004→`desktop_1440x1000.fonts`/`mobile_390x844.fonts`）：dt 13px/19.5、dd 15px/22.5、body/input/select/button 15px/22.5、h2 13px/19.5；390 档 label/h2/status/empty/reg-label 升 14px，dd 仍 15px。CSS 声明扫描最小 12px（限 OSD/跟踪标签/峰值角标三类规范豁免档）；`--fs-label:13px`→`@media 560px:14px` 实测生效；15 处 `font:` 简写全 /1.5 |
| C2 | 灰字 ≥7.7:1、正文 ≥16:1 | PASS | 本探针按 served CSS 的 `:root` hex 独立重算 WCAG 2.1（探针自实现，非抄测试）：`--muted #9aa5aa`/`--bg #0b0d0e` = **7.73:1**；`--text #e9eef0`/`--bg` = **16.65:1**；placeholder/panel 5.10、text/panel 15.84、text-2 11.94。浏览器读回 `rgb(154,165,170)`/`rgb(233,238,240)`/`rgb(11,13,14)` 与 hex 一致（004） |
| C3 | 分组 ≥20px、分区 ≤6、去冗余框线与重复标签、画面第一焦点 | PASS | `.section+.section` 桌面 20+18=38px、≤900 8+16=24px（004→`group_gap_px`/`group_gap`）；`class="section"` 恰 5、h2 恰 5；无 `border-bottom:1px dashed`/gradient/`data-channel`；`#m-codec` 在 STREAM 标题 meta；`.rail`/`.section` 无 background；stage 904×678=613k px² > rail 460×809=372k px² |
| C4 | 峰值虚线 + `peak x.xx Mbps` 角标 12px 灰字、不新增分区、与 `history.bitrate` 最大值同源 | PASS | 静态：`app.js:179` `const peak=Math.max(...history.bitrate)` 唯一求值同喂 `(v/peak)` 归一化、`setLineDash([3,3])`、`rgba(154,165,170,.5)`、`setText("m-peak",fmtPeak(peak))`、aria-label；`.peak` 在 STREAM 分区 Video bitrate 行内（004→`peak_same_source` 全 true）。**运行时实证**：telemetry 副本喂 14 帧脚本化码率（最大 2.5Mbps 埋中段、尾值 0.7）→ `#m-peak`="peak 2.50 Mbps"、`#m-bitrate`="700 kbps"、灰虚线第 6 行、accent 顶点第 9–10 行、aria `scaled to a peak of 2.50 Mbps`（004→`telemetry_390`/`telemetry_1440`） |
| C5 | 390px 顺序：画面 → 控件 → FACE REGISTRY → 遥测 | PASS | 实测 top：stage 68 → controls 353 → hint 611 → **#face-registry 656** → STREAM 861 → TRANSPORT 1089 → ANALYSIS 1328 → CLIPS 1624（004→`mobile_390x844`）；`display:contents`+order 1/2/3/4/5 静态确认；截图 `03-verifier-mobile-390x844.png` 与 `mock-mobile.png` 逐块一致 |
| C6 | 既有 DOM ID + 八项操作；`#stream` 内联 src 含 stream.mjpg；1440×1000 无截断、390 无横向溢出 | PASS | 48 id `ids_missing=[]`（004）；七控件 onclick + `sensitivity.onchange` + `stage` pointerdown/up→`postJSON("/api/motion")` 代码亲读 `app.js:315-430`；`<img id="stream" src="/api/stream.mjpg">`；1440 scrollHeight=1000 七操作 bottom≤875 屏内、worst-case 注入后 truncated_dd=[]；390 scrollWidth=clientWidth=390、widest_right=390、七操作 bottom≤595<844 首屏全见 |
| C7 | 无远程资源、无新增依赖、全套测试通过 | PASS | remote_refs 四项全空（html src/href、css url()/@import、js 字面量；favicon/下拉箭头为 data:URI）（004）；`requirements*.txt`/`pyproject.toml` 不在 diff；定向 `pytest tests/test_app.py tests/test_delivery.py -q` 53 绿（001）、全套 `pytest -q` 全绿（002，含 cv2 摄像机告警但 0 fail） |

## FINDINGS

1. [Nit] `src/rvm/web/index.html:80` — `<span class="peak">` 放在 `<dl><div class="wide">` 内与 dt/dd 同级：HTML 规范 dl>div 只许 dt/dd，属无效标记但各浏览器渲染一致、测试与实测均正常；如要洁癖可挪到 dd 内或改用 dd。confidence: HIGH
2. [Nit] `src/rvm/web/style.css:199` — `#m-rec` 恒 `--muted`，录制中显示 "recording" 仍是灰字；规范 §4.1 只钉 `off` 的显示、§8 的 alarm 文案指画面告警，不算违例，但录制态读数与 `off` 同色在投影上偏弱，可下票再议。confidence: MEDIUM
3. [FYI] 写域 diff 1014 行变更 >500（上限标注）：票面自报 OVER-LIMIT 并已路由额外静态实例；4008 行删除属探针目录清理不计写域。confidence: HIGH
4. [FYI] `display:contents`+order 是承载 390 顺序的唯一机制：Safari/Firefox 未验（NOT RUN），worker 实现说明亦自报该脆点；两档实测与截图在 Chrome 正确。confidence: HIGH

## RED-TEAM ATTEMPTS

- 「我若偷懒会在哪 5 处省事」：① 照抄 worker 自检测量（→ 自写探针重测全字段）；② 只看 CSS 声明不算对比度（→ 按 hex 独立重算+浏览器读回）；③ 390 顺序只看 order 声明（→ 实测 top + 截图对 mock）；④ 峰值同源只看 regex（→ 脚本化遥测让 tag 与末值不同，运行时分胜）；⑤ 截图拿 worker 旧图（→ 自己起副本服务器实拍两张）。
- 变异四族（gate-kit，sha1 记录→变异→定向红→还原→sha1 复验，006..009）：
  - `--fs-label 13→12` → `type_ladder` 红（杀 C1，006）
  - `--muted → #69737a` → `grey_text` 红，实测 4.02:1（杀 C2，007）
  - `.registry order 4→9` → `narrow_layout` 红（杀 C5，008）
  - `Math.max→Math.min` → `peak_rule` 红（杀 C4，009）
- 结构族：ID 清单逐条核 48 个、远程资源四种形态扫描、复制件 byte 级断言只含申报改动。
- 每条判据均有可指认的杀死变异或静态钉死；C3/C6 的几何与溢出属真机量测非测试断言，变异不适用于量测本身（量测即证据）。

## NOT RUN / UNVERIFIED

- Safari/Firefox `display:contents`/`aspect-ratio` 兼容性（仅 Chrome headless）。
- ≥901 右栏 `max-height: calc(100vh-102px)` 超高时栏内滚动：1440×1000 实测 rail 809<898 未触发，仅确认规则存在（004→`rail_self_scroll_rule`）。
- CLIPS 实有片段、名单实有名字的布局（live 为空态；最宽值以注入覆盖）。
- 真摄像头+真脸的 OSD 观感、`prefers-reduced-motion` 实感。
- 账本 03-r1-003 为探针首跑失败记录（`--dump-dom` 与脚本化遥测竞态，无产物）；修正后 004 为有效证据运行，在此声明不计缺陷。

## REMEDIATION

none

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 218c7ad | reports/03-r1-verifier.md | 0 | 全套与定向亲跑绿、真机两档实测字号/对比度/间距/顺序/溢出全中票面数值、峰值运行时实证同源、四变异全杀 |
