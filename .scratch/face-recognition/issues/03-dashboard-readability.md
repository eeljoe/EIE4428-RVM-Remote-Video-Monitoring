# 03 — 整页可读性与结构重做

**Status:** resolved
**Blocked by:** 01
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/03-dashboard-readability-selfcheck.md`）
**UI:** yes

## What to build

按 01 号票的设计规范重做监控页的可读性与结构：字号阶梯、对比度、行距与分组、去掉冗余框线与重复标签、码率折线加峰值标注。保留全部既有元素 ID、控件与八项操作。

## Acceptance criteria

- [ ] 标签 13px、读数 15px、正文 15px、手机正文 ≥14px，行高 1.5 [AS-6]
- [ ] 灰字对比度 ≥7.7:1、正文 ≥16:1，并在实现说明里给出实测读数 [AS-6]
- [ ] 分组间距 ≥20px；分区不超过 6 个；去冗余框线与重复标签；画面为第一焦点 [AS-7]
- [ ] 码率折线有峰值虚线与 `peak x.xx Mbps` 角标，字号 12px、灰字、不新增分区，数值与 `history.bitrate` 最大值同源 [AS-6, AS-7]
- [ ] 390px 宽下面板顺序为：画面 → 控件 → FACE REGISTRY → 遥测 [AS-7, AS-5]
- [ ] 既有 DOM ID 与八项操作保持；390×844 无横向溢出；1440×1000 无被截断的操作 [AS-5, AS-7]
- [ ] 无远程资源、无新增依赖；全套测试通过 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_delivery.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 目视：`run_server.py --no-camera --port 8099`，桌面与手机视口各截一张图。

## 写域

- `src/rvm/web/index.html`
- `src/rvm/web/style.css`
- `src/rvm/web/app.js`
- `tests/test_app.py`

## 开工包

- **写域**：`src/rvm/web/index.html`, `src/rvm/web/style.css`, `src/rvm/web/app.js`, `tests/test_app.py`

- **设计来源**：`docs/DESIGN-dashboard.md`（01 号票产出）与 `.scratch/face-recognition/design/v2/mock.html`。
- **锚点**：`grep -n "id=\"stream\"" src/rvm/web/index.html`（必须仍是内联 `src=` 且含 `stream.mjpg`）；`grep -n "class=\"layout\"" src/rvm/web/index.html`；`grep -n "history.bitrate" src/rvm/web/app.js`。
- **保留 ID**：`view-source`、`view-decoded`、`roi`、`sensitivity`、`clear-roi`、`clips`、`spark`、`m-*` 全部保留。
- **尺寸上限**：目标 ≤300 行 / ≤3 文件；本票要整体重写 CSS，预计超过 300 行，按 OVER-LIMIT 分级走额外静态实例。
- **估算**：预计 50 分钟 / 230 步。

## 验收包

- **判据**：AS-6、AS-7、AS-5；每条 AC 给出截图或 CSS 实测值。
- **首攻靶**：字号是否真 13px、对比度是否实测、1440 是否截断、390 顺序是否正确、旧 ID 与八项操作是否还在、峰值标注是否与数组同源。
- **相关 AS 摘录**：AS-6 可读性（标签 12px 起、值 15px、对比 4.5:1、行高 1.5、间距 20px）；AS-7 简洁（分区 ≤6、画面第一焦点）；AS-5 不回归。

## 完成条件

测试先红后绿；独立动态门用真实浏览器在两档视口取证并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

真机读数与截图：`.scratch/face-recognition/verifier-probes/03-dashboard-readability-selfcheck.md`（脚本、JSON、两张 PNG 同目录）。

### 1. AC → 证据

- 标签 13px / 读数 15px / 正文 15px / 手机 ≥14px / 行高 1.5：`tests/test_app.py:411`（字阶与 12px 下限）、`tests/test_app.py:442`（≤560 标签升 14、值仍 15）；实测 `style.css:29` 的 `--fs-label: 13px` 在浏览器里读到 `13px / 19.5px`，读数 `15px / 22.5px`，390 上标签 `14px / 21px`、读数仍 `15px / 22.5px`。
- 灰字 ≥7.7:1、正文 ≥16:1：`tests/test_app.py:452` 从服务端样式表取 hex、按 WCAG 2.1 实算；浏览器读回 `rgb(154,165,170)` / `rgb(233,238,240)`，底 `rgb(11,13,14)` → **7.73:1** / **16.65:1**（次级 11.94:1、占位 5.10:1）。
- 分组 ≥20px、分区 ≤6、去冗余框线与重复标签、画面第一焦点：`tests/test_app.py:477`（`style.css:169` 的 20+18、≤900 的 8+16、"class=\"section" 恰 5 个）、`tests/test_app.py:502`（无 `border-bottom: 1px dashed`、无渐变、无 `data-channel`、`#m-codec` 移到标题 meta）、`tests/test_app.py:529`（`.stage` 4:3、`.rail`/`.section` 不铺底）；实测桌面画面盒 904x678 = 页面最大面积。
- 峰值虚线与 `peak x.xx Mbps` 角标（12px、灰、不新增分区、与 `history.bitrate` 最大值同源）：`tests/test_app.py:549`（`index.html:80` 角标在 STREAM 分区内、`style.css:208` 的 12px/`--muted`、`app.js:179` 的 `const peak = Math.max(...history.bitrate)` 同时喂 `app.js:225` 的角标与折线归一化、`app.js:187` 的虚线）；截图里 `peak 0.12 Mbps` 与折线上缘虚线同高。
- 390 顺序 画面 → 控件 → FACE REGISTRY → 遥测：`tests/test_app.py:585`（`style.css:289` 的 `display: contents`、`order` 1/2/4/5）；实测 top：stage 68 → controls 353 → hint 611 → registry 656 → STREAM 861。
- 既有 DOM ID 与八项操作、390 无横向溢出、1440 无被截断操作：`tests/test_app.py:605`（48 个 id 逐条、七个控件 + 拖拽划区）、`tests/test_app.py:639`（FACE REGISTRY 是第 4 个分区）；实测 390 `scrollWidth 390`、最右内容边 390、读数 0 条截断；1440 文档高 1000、`scrollHeight 1000`，七个操作底边 815/875 全在屏内。
- 无远程资源、无新增依赖、全套通过：`tests/test_app.py:87` 既有禁令不动；`pytest -q` 全绿（见 TESTS 段）。

### 2. 假设

- 截图与量测里「iframe 的 CSS 尺寸 = 视口」成立（Chrome 156 headless，`--force-device-scale-factor=1`）。
- 静态测试取 `:root` 时口径是「第一个含 `--bg` 的块」，且全表只有一个这样的块；`@media (max-width:560px)` 里的 `:root` 只覆盖 `--fs-label`。
- 所有字号都用 px 字面量或 `--fs-label`/`--fs-body`；扫描 12px 下限的 `font_sizes()` 依赖这一点。
- `.section` 这个类只用在右栏五个分区上（分区计数的口径）。
- 390 改单列的前提是「双列会截断超过三条」，这一条由探针量到 9 条（见探针文末）。
- `#m-peak` 的文本只由 `drawSpark` 写，没有第二处写入。
- 画面 4:3 与 `object-fit: contain` 下，`fractionAt()` 用 `#stream` 的矩形算比例仍是准的（拖拽划区沿用既有实现）。

### 3. 我知道没覆盖什么

- 没有真实摄像头/真人脸时的观感：本机自检一律 `--no-camera`（合成场景），所以「画面里有脸时 OSD 与跟踪标签是否压字」没看。
- `#face-status` 有文案时的高度（现在是空态，靠 `min-height: 20px` 预留）；04 号票接线后要复核行高不变。
- CLIPS 有片段时的行布局（本机无录像文件，只有 `No recording yet`）；`clipLabel()` 的日期格式化没进测试。
- 只量了 Chrome 156；Safari / Firefox 的 `display: contents` 与 `aspect-ratio` 表现未验。
- `prefers-reduced-motion` 只有静态断言，没有实际观感证据。
- UNVERIFIED：≥901px 右栏 `max-height: calc(100vh - 102px)` 的栏内滚动。1440x1000 实测右栏高 809 < 898，没触发滚动，所以「超高时在栏内滚动」只是声明。

### 4. 复现命令

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\03-dashboard-readability-selfcheck.py
```

跑完同目录出现两张 PNG 与 `03-dashboard-readability-selfcheck.json`；约 90 秒（截图各等 32 秒的慢像素，好让码率折线有形状）。只看测试：`.venv\Scripts\python.exe -m pytest tests/test_app.py -q`。

### 5. 我认为最脆的一处

390 上的读数行：标签定宽 108px、值单列剩余 240px、再加行尾 `peak` 自动右边。把 `style.css:189` 的 `flex: 0 0 108px` 改成 `auto`，或把 `.readouts` 在 ≤560 改回双列，读数立刻被省略号切断（实测双列 9 条截断）。第二个靶子是 `display: contents` + `order` 那套顺序：换成真实 DOM 重排或换浏览器就可能失效，而它承载的是「390 上先看到控件与注册」。

### 6. 票面外的决定

- 决定：FACE REGISTRY 在本票只做静态外壳（分区标题、名字标签、输入框、`REMEMBER FACE`、空状态行、名单空态），不接任何请求 / 理由：本票 AC 的 390 顺序点名 FACE REGISTRY，没有这个分区就量不出顺序；行为、五态文案与删除属 04 号票 / 影响面：04 号票接线时只补 JS，不必动结构；本票动态门不应期待注册可用。
- 决定：390 的读数改单列（规范 §4.1 默认双列）/ 理由：双列时读数只剩 45px，9 条被截断，超过 §4.1 自己写的「超过三条」退让条件 / 影响面：仅 ≤560；字号未动。
- 决定：折线只有 1 个样本时也画点、也写角标 / 理由：否则开页第一秒是 `peak -` 加空白画布，容易被读成「折线坏了」；对 1 元素窗口峰值仍成立 / 影响面：多样本时的线形不变。
- 决定：未到的读数占位从 `&mdash;` 改成 `-` 并加 `.pending` 灰字 / 理由：规范 §4.1 要连字符、§10 禁长破折号 / 影响面：首帧视觉；`setText()` 多一步去 class。
- 决定：CLIPS 行把 `20261024_213812` 显示成 `2026-10-24 21:38` / 理由：规范 NOTES 第 8 条要求现场好念 / 影响面：只改可见文案，文件名与下载路径不变。
- 决定：删掉 `#stage` 的 `data-channel="CAM 01"` 与底部 overlay / 理由：它们是来源标签的第二份副本，规范把来源与时间移进画面两角 OSD / 影响面：`data-channel` 属性不再存在，`#src-label`/`#time-label`/`#view-label` 三个 id 保留。
- 决定：≥901px 右栏加 `max-height: calc(100vh - 102px)` 与栏内滚动 / 理由：规范 §6 说明这是本票新增规则 / 影响面：仅在内容超高时生效，1440x1000 实测不触发。
- 决定：八项操作按「七个控件 + 画面拖拽划区」计 / 理由：spec AS-5 与规范 §6 只列了七个按钮，第八项只能是 ROI 拖拽 / 影响面：测试按这八条钉住，若门另有口径只改测试一处。
- 决定：`#record` 仍用 `active` 类驱动 `Start/Stop recording` 文案，不并入 `.seg` / 理由：既有 app.js 依赖该 class 与文案切换，改它属行为变更 / 影响面：录制态样式改走 `#record.active` 的告警色。


## Verdicts

- 2026-11-09 r1 VERIFIED 218c7ad — 干净 worktree 亲跑：全套 634 绿、定向 53 绿；served 字节与副本逐文件同 sha256；真 Chrome 两档实测字号/行高/颜色全部命中票面数值；对比度按 served hex 独立重算 7.73/16.65；390 顺序、无横向溢出、1440 无截断、峰值与 `history.bitrate` 最大值同源（脚本化 14 帧运行时实测 "peak 2.50 Mbps" 而末值 700 kbps）；四族变异全部被杀并还原。｜报告：.scratch/face-recognition/reports/03-r1-verifier.md｜模型路线：SWE-2 High
