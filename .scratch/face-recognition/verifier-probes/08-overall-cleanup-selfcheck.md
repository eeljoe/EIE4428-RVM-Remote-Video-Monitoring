# 08 — 真机自检：≤900px 下 FACE REGISTRY 与 STREAM 的间隔与分隔线

票：`.scratch/face-recognition/issues/08-overall-cleanup.md`（AS-6 / UI）。
自检对象：本票改后的 `src/rvm/web/style.css`（工作区未提交状态，基线 `6abf9cc`）。

## 环境与命令

- 服务器：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099`（票面原文）。
  启动横幅逐字：`RVM serving on http://0.0.0.0:8099/  (320x240 @ 15 fps, source: synthetic)`。
  未指定 `--known-faces`，`data/known_faces.json` 不存在（自检前 `Test-Path` = False），所以名单为空、页面显示 `No names saved yet`；自检全程没有任何注册/删除请求，自检后该文件仍不存在。
- 浏览器：系统 Chrome `156.0.8078.81`，`--headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --virtual-time-budget=12000`。
- 视口：Chromium 的窗口尺寸不等于 390px 布局视口，所以沿用前序门的做法——把真实页面放进**恰好 390×844 CSS px** 的 iframe 里量，再截图。
- 驱动页 `08-overall-cleanup-viewport.html`（本目录存档一份）自检期间临时拷到 `src/rvm/web/08-vp.html` 以便同源，**截图与读数取完后已删除**（`src/rvm/web/08-vp.html` 现不存在，`git status` 无该文件）。它只读页面布局，不发任何写请求。
- 读数用 `--dump-dom` 落到 `08-overall-cleanup-dom-mobile.html`；截图另一次 Chrome 调用（两次调用，见「诚实说明」）。

## 读数（`#bar` 原文，逐字）

修后（本票要交的状态）：

```
VP 390x844  docW=390/390
SEAM registry.bottom=845 stream.top=869
SEAM box=24px visual=25px line=1px solid rgb(37, 44, 48)
ALL box/visual/line: Stream=24/25/1  Transport=24/25/1
                    Analysis=24/25/1  Clips=24/25/1
```

撤掉本票那条 CSS 规则后（同一台服务器、同一个驱动页、只改 `style.css` 一处；测完按 sha256 还原并复核）：

```
VP 390x844  docW=390/390
SEAM registry.bottom=845 stream.top=861
SEAM box=16px visual=0px line=0px none rgb(233, 238, 240)
ALL box/visual/line: Stream=16/0/0  Transport=24/25/1
                    Analysis=24/25/1  Clips=24/25/1
```

还原后复测与「修后」逐字一致；`style.css` 的 sha256 与撤销前相等（`RESTORED_HASH_MATCH=True`）。

落盘：`08-overall-cleanup-dom-mobile.html`（修后）、`08-overall-cleanup-dom-mobile-before.html`（撤规则）及其 `.err`（均 0 字节）。

## 三个数字的定义

- `box` = 后一分区的 border-box 顶边 − 前一分区 border-box 底边（含 `.layout` 的 `row-gap`）。
- `visual` = 后一分区的 `margin-top + border-top-width + padding-top`（设计文档 §6 说的「8 + 16 = 视觉间隔 24」就是这一口径，本行多算了 1px 边框）。
- `line` = 后一分区 `border-top-width style color`。

`rgb(37, 44, 48)` = `--line #252c30`，与其余四条分区界线同一个值。

## 截图

- `.scratch/face-recognition/verifier-probes/08-overall-cleanup-mobile-390x844-seam.png`（390×844）
  画面：`FACE REGISTRY` 一段（标签、输入框、`REMEMBER FACE`、`No names saved yet`）→ 一条与页面同宽的 1px 分隔线 → `STREAM` 标题与读数；底部黄条是驱动页把上面的读数打在同一张图里。
- `.scratch/face-recognition/verifier-probes/08-overall-cleanup-mobile-390x844-top.png`（390×844）
  画面：顶栏 `RVM / EIE4428 / LIVE` → 4:3 画面（两角 OSD、`MOTION DETECTED`）→ 七项控件与提示行全部在首屏内 → `FACE REGISTRY` 开头。

亲眼看图结论（不是从代码推断）：seam 图上 `No names saved yet` 与 `STREAM` 之间那条线肉眼可见、与页面左右内边距对齐；两图均为 390 宽、无横向溢出、无内容被裁在右边界外。

## 诚实说明

- 驱动页是**自检用探针**，不是产品文件；它自检后已删除，产品只改了 `style.css` 一条规则。
- 截图与 `--dump-dom` 是两次 Chrome 调用：读数来自 dump，图来自 screenshot；两次都指向同一台 :8099 服务器，但页面遥测数字（`Frame rate`、`Packets sent`）在两次之间会变，间距读数不受影响（布局由 CSS 决定，本票未改内容高度）。
- 黄条压在页面底部（约 90px），会遮住首屏最后一点内容；seam 图已把要看的边界滚到距顶 300px 处，未被遮住。
- `docW=390/390`：`--hide-scrollbars` 下竖滚动条不占宽；前序门实测的 375/375 是滚动条占 15px 的结果，两者都不代表横向溢出。
- 本自检**没有**验证：桌面 1440 档（本票规则只在 `@media (max-width: 900px)` 内，桌面档读数与门报告 `minSectionGap=20` 同值）、`≤560px` 档（390 已落在该档内，`--fs-label: 14px` 生效）。
