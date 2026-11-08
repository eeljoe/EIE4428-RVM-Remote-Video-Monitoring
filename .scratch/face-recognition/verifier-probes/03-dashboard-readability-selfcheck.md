# 03 可读性重做 — 真机自检

票面要求「真机自检：必须」。本文是读数与截图，不是结论。

- 命令：(先起服务)
  - `.venv\Scripts\python.exe run_server.py --no-camera --port 8099`
  - `.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\03-dashboard-readability-selfcheck.py`
- 脚本：`03-dashboard-readability-selfcheck.py`（自包含，跑完落盘 `03-dashboard-readability-selfcheck.json`）
- 产物：
  - `03-desktop-1440x1000.png`（1440x1000，412073 B）
  - `03-mobile-390x844.png`（390x844，118449 B）
- 浏览器：Chrome for Testing 156.0.8078.81，`--headless=new`，`--force-device-scale-factor=1`
- 量法：页面装进与目标视口等大的 iframe（Chrome 只能设窗口，窗口框与滚动条会让视口不等于 1440x1000），再从渲染后的文档里读 `getComputedStyle` 与 `getBoundingClientRect`。

## 被测的是哪一份字节

截图是**活服务**（`http://127.0.0.1:8099/`）的页面。测量走一份落盘副本，因为活页面的 MJPEG 是永不结束的 multipart 响应，`--dump-dom` 在 1.7 s 就开火，框里的页面还没解析完。

副本与 `GET /` 的差别只有两处，脚本里逐字断言可逆：

1. `<link rel="stylesheet" href="/static/style.css" />` 换成同样字节的内联 `<style>`（落盘的 HTML 找不到站内路径；内联后不存在「样式还没到就量了」的窗口）。
2. 去掉 `<script src="/static/app.js"></script>`（活 socket 会让 `--dump-dom` 永远等不到 settle）。被量的每个数都只由样式表与标记决定。

哈希（`GET /`、`/static/style.css`、`/static/app.js` 分别）：

- index.html `319bdd6c1c8881561324afc63e42518c54566d7933be75d0e47bff39d85c8a6c`
- style.css `8351fbc2b34bfc7a5e25299327a546cc8452fb1d7a31c974cba69d60f4fc65e1`
- app.js `443999fb05d7fd7d3f73974b4a05985d43cccd6dc89fbcbb317742a7d3fda336`

后两个哈希与工作区文件一致（`Get-FileHash` 同值），所以读数与截图对应的是同一份样式与脚本。

## 1440x1000 读数

| 项 | 读数 |
|---|---|
| 视口 / 文档 | `1440x1000` / `scrollWidth 1440`、`scrollHeight 1000`（一屏到底，无页面滚动） |
| 画面盒 | `904x678`（4:3），右栏 `460x809` |
| 正文 | `15px / 22.5px`（行高 1.5） |
| 读数标签 `.readouts dt` | `13px / 19.5px`，色 `rgb(154,165,170)` = `#9aa5aa` |
| 读数 `.readouts dd` | `15px / 22.5px`，色 `rgb(233,238,240)` = `#e9eef0` |
| 分区标题 | `13px / 19.5px`，色 `rgb(195,204,208)` = `#c3ccd0` |
| 分区标题 meta `#m-codec` | `13px / 19.5px` |
| 峰值角标 `#m-peak` | `12px / 18px`，色 `rgb(154,165,170)` |
| 画面 OSD | `12px / 18px` |
| select / button | `15px / 22.5px` |
| 主按钮 `#face-remember` | `13px / 19.5px` |
| 状态行 / 提示行 / 空态 | `13px / 19.5px` |
| 页底 | `rgb(11,13,14)` = `#0b0d0e` |
| 分区之间 | `margin-top 20` + `padding-top 18`（视觉间隔 38 ≥ 20） |
| 分区数 | 5（STREAM / TRANSPORT / ANALYSIS / FACE REGISTRY / CLIPS） |
| 最右内容边 | `1440`（= 视口宽，无横向溢出） |
| 读数截断 | 0 条 |
| 折线画布 | CSS 高 `30`，宽 `460`（右栏满宽） |
| 七个操作 | 全部在屏内（`apply`/`clear-roi` 底 815，其余五个底 875） |

对比度（由浏览器读回的色值、按 WCAG 2.1 相对亮度算；底色 `rgb(11,13,14)`）：

- 灰字 `#9aa5aa` / `#0b0d0e` = **7.73:1**（门槛 7.7）
- 正文 `#e9eef0` / `#0b0d0e` = **16.65:1**（门槛 16）
- 次级 `#c3ccd0` / `#0b0d0e` = **11.94:1**
- 占位字 `#7d888d` / `#101416` = **5.10:1**

## 390x844 读数

| 项 | 读数 |
|---|---|
| 视口 / 文档 | `390x844` / `scrollWidth 390`、`clientWidth 390`（**无横向溢出**）、`scrollHeight 1721` |
| 画面盒 | `358x269`（4:3，满宽） |
| 正文 / 读数 | `15px / 22.5px`（不缩小） |
| 标签 / 分区标题 / 主按钮 / 状态行 / 空态 | `14px / 21px` |
| 峰值角标 / OSD | `12px / 18px`（不缩放） |
| 分区之间 | `margin-top 8` + `padding-top 16` = 24 ≥ 20 |
| 最右内容边 | `390`（无横向溢出） |
| 读数截断 | 0 条 |

单列顺序（`getBoundingClientRect().top`）：

| 块 | top | bottom |
|---|---|---|
| `.stage`（画面） | 68 | 337 |
| `.controls`（控件） | 353 | 595 |
| `.hint`（提示行） | 611 | 632 |
| `#face-registry`（FACE REGISTRY） | 656 | 845 |
| STREAM | 861 | — |
| TRANSPORT | 1089 | — |
| ANALYSIS | 1328 | — |
| CLIPS | 1624 | — |

即 画面 → 控件 →（提示行）→ FACE REGISTRY → 遥测四区。

七个操作的底边：`apply 393`、`clear-roi 444`、`view-source 494`、`view-decoded 494`、`snapshot 545`、`record 545`、`metrics 595` — 全部 ≤ 844，首屏可点。

### 为什么 390 的读数改单列（与规范 §4.1「390 仍双列」的偏差）

同一页面、同一视口，只把 `.readouts` 强制回双列再量一遍：

```
truncated: m-res 79>45, m-fps 70>45, m-psnr 62>45, m-pkts 53>45, m-loss 53>45,
           m-jitter 62>45, m-motion 53>45, m-gestures 62>45, m-emotions 62>45
```

9 条读数只剩 45px 可用宽度，全部被省略号切断 —— 远超规范 §4.1 给的退让条件「超过三条」，所以按同一条款退回单列，字号一个没动（标签 14、读数 15）。单列后为 0 条截断。

## 我看图看到什么（亲眼看图，不靠排版数字）

- 桌面图：左栏 4:3 画面占据页面最大面积；画面两角是 `SOURCE: SYNTHETIC` 与时钟 OSD；下面两行控件（Target bitrate + Apply / Motion sensitivity + Clear zone，Camera 实心选中 + Decoded，再加三个动作）；右栏五个分区，分区之间只有一条 1px 细线，读数双列、标签灰、值亮；`Video bitrate 68 kbps` 那一行行尾是 `peak 0.12 Mbps`，折线上缘一条虚线横贯画布，折线本身是一条完整的青绿曲线；`FACE REGISTRY` 的输入框与 `REMEMBER FACE` 在分区底部，状态行为空时只有一个不可见圆点位；`CLIPS` 显示 `No recording yet`。
- 手机图：顶栏只剩 `RVM` / `EIE4428` / `LIVE`，`Remote Video Monitor` 隐去；画面满宽 4:3；控件逐行：`Target bitrate`+`Apply`、`Motion sensitivity`+`Clear zone`、`Camera`|`Decoded (RVM1)` 两列、`Save snapshot`|`Start recording` 两列、`Export metrics` 独占整行；随后提示行、`FACE REGISTRY`（标签 + 输入 + 按钮 + `No names saved yet`）——与 `mock-mobile.png` 逐项对上，遥测四区在首屏之下。
- 两张图都看不到：横向滚动条、被截断的按钮、重复的来源标签、每行一条的虚线。

## 这套自检没覆盖什么

- 折线只积累了约 34 s 的样本（窗口 60 格 × 0.5 s），所以截图里折线不是满窗的 60 点；截图里 `peak` 是那一刻窗口最大值（0.12 Mbps），不是固定值。同一数源由 `tests/test_app.py` 的 `test_the_peak_rule_and_its_tag_share_the_traces_maximum` 钉住（`const peak = Math.max(...history.bitrate)` 同时喂 scale 与角标）。
- 截图走的是 Chrome headless CLI，等的是包装页里那枚「慢像素」（32 s 后才响应、落在裁切区外的 1x1 图），它只影响截图时机，不出现在画面里。
- 五态文案、注册与删除的行为属于 04 号票，本票只做了分区外壳，未在此自检。
