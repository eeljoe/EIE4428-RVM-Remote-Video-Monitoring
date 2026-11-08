# 03 号票 r1 — 独立验收探针（verifier probes）

被验提交：`218c7adbac379dea0827513207f950f6a8699df2`（在干净 worktree
`%TEMP%\verify-03-verify-218c7ad` 上跑，服务端从该副本启动，
`--no-camera --port 8137`；served 字节与 worktree 字节 sha256 逐文件相等，
账本 `03-r1-005`）。

脚本：`03-dashboard-readability-verifier.py`（本目录，验收者自写，非 worker
自检脚本）。产物：`03-verifier-measure.json`（全量读数）、
`03-verifier-desktop-1440x1000.png`、`03-verifier-mobile-390x844.png`
（两张均为**真服务器、真遥测 ~34s 后**的实拍截图）。账本 `03-r1-004`。

## 1 字号（实测，非 worker 转述）

390×844 与 1440×1000 两档都用真 Chrome 读 getComputedStyle：

| 元素 | 1440 | 390 |
|---|---|---|
| 读数标签 dt | 13px / 19.5px（行高 1.5） | 14px / 21px |
| 读数 dd | 15px / 22.5px | 15px / 22.5px |
| 正文 body / input / select / button | 15px / 22.5px | 15px / 22.5px |
| 分区标题 h2 | 13px / 19.5px | 14px / 21px |
| 峰值角标 .peak | 12px / 18px | 12px / 18px |
| 画面 OSD | 12px / 18px | 12px / 18px |
| 提示/空态/状态行 | 13px | 14px |
| REMEMBER FACE | 13px | 14px |

CSS 声明扫描：字号字面量集合 {12,14,15,16,20}（变量另有 --fs-title 18px），
最小 12px；行高统一 /1.5（15 处 `font:` 简写全部 /1.5）。手机正文全部
≥14px。12px 只出现在画面 OSD、跟踪标签、峰值角标三类（规范允许的例外档）。

## 2 对比度（本探针独立重算 WCAG 2.1）

从 served style.css 的 :root 取 hex，本探针自写 sRGB→线性→相对亮度→比值：

- `--muted #9aa5aa` on `--bg #0b0d0e` → **7.73:1**（≥7.7 ✓）
- `--text #e9eef0` on `--bg` → **16.65:1**（≥16 ✓）
- `--text-2 #c3ccd0` on `--bg` → 11.94:1
- `--placeholder #7d888d` on `--panel #101416` → 5.10:1（≥5 ✓）
- `--text` on `--panel` → 15.84:1（≥15.8 硬底 ✓）
- accent/ok/warn/alarm/on-accent：10.78 / 9.83 / 10.16 / 6.69 / 8.97

浏览器读回：label/peak/empty = `rgb(154,165,170)`，value =
`rgb(233,238,240)`，body 底 = `rgb(11,13,14)`，与 hex 一致。

## 3 分组与分区

- 分区 5 个（上限 6）：STREAM、TRANSPORT、ANALYSIS、FACE REGISTRY（第 4
  位）、CLIPS。h2 也是 5 个。
- 分组间距：桌面 `margin-top 20 + padding-top 18 = 38px`；≤900
  `8 + 16 = 24px`，均 ≥20px。
- 无 `border-bottom: 1px dashed`、无 gradient、无 `data-channel`；
  `#src-label`/`#time-label` 是画面两角 OSD；`#m-codec` 在 STREAM 标题
  meta 位，不再占读数行；`.rail`/`.section` 无 background。

## 4 390×844 顺序（真浏览器实测 top）

stage 68 → controls 353 → hint 611 → **FACE REGISTRY 656** →
STREAM 861 → TRANSPORT 1089 → ANALYSIS 1328 → CLIPS 1624。
实现方式 `.viewer`/`.rail` `display: contents` + order 1/2/3/4/5。
截图 `03-verifier-mobile-390x844.png` 与 mock-mobile 逐块对上。

## 5 峰值标注与同源

- CSS `.peak`：12px / 400 mono / `--muted` / `margin-left:auto`，挂在
  Video bitrate wide 行行尾，不新增分区。
- app.js:179 `const peak = Math.max(...history.bitrate)` 唯一求值，同喂
  折线归一化 `(v / peak)`、虚线（`setLineDash([3,3])`，
  `rgba(154,165,170,.5)`）、角标 `fmtPeak(peak)` 与 aria-label。
- **运行时实证**（telemetry 副本，真 app.js + 脚本化 14 帧，最大值
  2.5 Mbps 埋在序列中段、尾部回落 0.7）：
  - `history.bitrate` max = 2,500,000 → `#m-peak` 文本 **"peak 2.50 Mbps"**
  - `#m-bitrate` 显示末值 "700 kbps"（证明角标取的是最大值不是最新值）
  - 画布像素：灰色虚线在第 6 行（= 顶部下 6px 的规定刻度位），accent
    折线顶点第 9–10 行（peak 归一化的 apex），aria-label
    `scaled to a peak of 2.50 Mbps`
  - 两档视口结果一致。

## 6 不回归

- 48 个既有 DOM id 全在（ids_missing = []）；七控件 + 拖拽划区 =
  八项操作，JS 接线在（onclick×7、onchange、pointerdown/up→/api/motion）。
- `#stream` = `<img id="stream" src="/api/stream.mjpg" …>` 内联含
  stream.mjpg。
- 1440×1000：scrollHeight 1000 = 视口，七个操作 bottom ≤ 875 全屏内；
  widest_right 1440，无截断（truncated_dd = []，worst-case 值注入后仍 0）。
- 390×844：scrollWidth 390 = clientWidth，widest_right 390，无横向溢出；
  七操作 bottom ≤ 595 < 844 首屏全见；truncated_dd = []、peak 不被省略。
- 远程资源：html src/href、css url()/@import、js 字面量全部为零命中
  （favicon 与下拉箭头为 data: URI）。
- 全套 pytest 自跑全绿（账本 03-r1-001/002）。

## 7 变异四族（账本 03-r1-006..009，全部被杀并还原 sha1）

- `--fs-label 13→12` → type_ladder 红（assert 12px==13px）
- `--muted → #69737a` → grey_text 红（实测 4.02≠7.73）
- `.registry order 4→9` → narrow_layout 红
- `Math.max→Math.min` → peak_rule 红

## 8 NOT RUN（诚实清单）

- Safari/Firefox 的 `display: contents` + `aspect-ratio`（仅 Chrome）。
- ≥901 右栏内容超高时的栏内滚动（1440×1000 内容 809 < 898 未触发）。
- CLIPS/名单有真实条目时的行布局（live 空态；最宽值用注入量过）。
- 真摄像头+真脸时 OSD/跟踪标签观感（本机 --no-camera 合成场景）。
- prefers-reduced-motion 实际观感（仅静态存在性）。
