# 监控页设计规范

RVM operator page 的设计规范。本文是把已签字的参照图 v2 落成可执行数值的唯一来源:实现 `src/rvm/web/` 时按本文照抄,不再自己调字号与间距。本文与参照图冲突时以参照图为准,并回来改本文。

- 视觉来源(签字版):`.scratch/face-recognition/design/v2/mock.html`、`mock-desktop.png`(1440x1000)、`mock-mobile.png`(390x844)、`NOTES.md`
- 覆盖范围:只写数值与规则,不含实现代码
- 适用性:本页是密集监控面板,设计指南把 dashboard 列为范围外;本文只取指南里对面板依然成立的部分(单一强调色、禁纯黑纯白、字号阶、圆角一致、无 em dash、状态齐全、数据不造假),不套用落地页的 hero / bento / 图片资产规则。单暗色也不套用指南的双模式要求,见 §10。

## 1 字号阶

全页行高 1.5,无例外。字重只用 400 / 500 / 600 / 700 四档,没有斜体标题。

| px | 字重 | 字距 | 族 | 用途 | 旧值 |
|---|---|---|---|---|---|
| 12 | 600 | .06em | mono 大写 | 画面 OSD:`SOURCE: CAMERA`、`21:42:41` | 10 |
| 12 | 700 | 0 | mono | 画面内跟踪标签(`Alice` 挂在跟踪点上,衬底 `#000000b8` 即 72% 黑) | 9 |
| 12 | 400 | .02em | mono | 峰值角标:`peak 1.33 Mbps` | 新增 |
| 13 | 600 | .08em | sans 大写 | 分区标题 h2,色 `--text-2` | 10 |
| 13 | 400 | 0 | sans | 字段标签、提示行、注册行标签、空态、状态行、片段副行 | 10 |
| 13 | 700 | .04em | sans | 主按钮 `REMEMBER FACE` | 11 大写 |
| 13 | 400 | .02em | mono | 分区标题右侧 meta(`RVM1 · H.264-style hybrid`)、顶栏 `EIE4428` | 10 |
| 14 | 400 | 0 | sans | 顶栏产品名 `Remote Video Monitor`;≤560px 时 `--fs-label` 这一档全升到此档(见规则) | 10 |
| 15 | 400 | 0 | sans | 正文:按钮、下拉、输入框、名单行 | 14 / 11 |
| 15 | 500 | 0 + tabular-nums | mono | 读数 dd(Face IDs、Faces 等监控数值);片段日期时间 | 12 |
| 16 | 400 | 0 | mono | 删除 `×` | 9 |
| 18 | 700 | .14em | sans | `RVM` 字标,色 `--accent` | 27 |
| 20 | 700 | .18em | mono | 画面内告警 `MOTION DETECTED` | 20 |

规则:

- 标签下限 13px;12px 只出现在三类画面与标注文字(画面 OSD、画面内跟踪标签、峰值角标),它们都不承载读数本身;12px 即绝对下限,不得再小。
- 读数一律 15px 等宽 + `tabular-nums`,数字换位时不做宽度跳动。
- 手机正文不小于 14px:≤560px 时读数、正文、按钮文字仍是 15px;`--fs-label` 这一档(标签、分区标题、标题 meta、状态行、空态、主按钮、顶栏 `EIE4428`)从 13 升到 14,读数不缩小。
- 分区标题大写但不放大:层级靠 600 字重与 `--text-2` 色阶区分,不靠字号。
- 旧值对照(改前):正文 14、标签 10 大写 mono、读数 12、分区标题 10、按钮 11 大写、字标 27。所有 10px 与 9px 档取消。

## 2 颜色与对比度

对比度列按 WCAG 2.1 相对亮度实算,基准底 `--bg`,注明处为 `--panel`。

| 变量 | hex | 用途 | 对比度 |
|---|---|---|---|
| `--bg` | `#0b0d0e` | 页底 | 基准 |
| `--panel` | `#101416` | 输入框底、画面外分区底 | 基准 |
| `--raised` | `#191f22` | 下拉与按钮底 | 填充,对 --bg 1.17:1 |
| `--raised-hover` | `#212a2e` | 控件 hover 底 | 填充,对 --bg 1.33:1 |
| `--line` | `#252c30` | 分区间 1px 线、名单行内线、折线基线 | 装饰线,对 --panel 1.31:1 |
| `--line-strong` | `#39444a` | 控件边框 | 装饰线,对 --raised 1.67:1 |
| `--text` | `#e9eef0` | 正文、读数 | 16.65:1 |
| `--text-2` | `#c3ccd0` | 分区标题、产品名 | 11.94:1 |
| `--muted` | `#9aa5aa` | 标签、提示、空态、meta、峰值角标 | 7.73:1(对 --panel 7.35:1) |
| `--placeholder` | `#7d888d` | 占位字 | 5.10:1(对 --panel) |
| `--accent` | `#5fd3c6` | 唯一强调色,饱和 57%:选中视图、主按钮、折线、ROI、跟踪点 | 10.78:1 |
| `--accent-hover` | `#78ded2` | 强调色 hover | 12.22:1 |
| `--accent-soft` | `#5fd3c61f` | ROI 底、选中视图底 | 底纹,不载文字 |
| `--on-accent` | `#072521` | 强调色底上的文字 | 8.97:1(对 --accent) |
| `--ok` | `#6ecb8f` | 注册成功、live 点 | 9.83:1 |
| `--warn` | `#e3b45c` | 重名提示 | 10.16:1 |
| `--alarm` | `#f0715a` | 无脸、多脸、录制中、检测框 | 6.69:1(对 --panel 6.36:1) |
| `--alarm-soft` | `#f0715a1f` | 录制按钮底、检测框底 | 底纹,不载文字 |

规则:

- 一个强调色锁死全页:只有 `--accent` 及其 hover / soft。语义色只标状态,不参与装饰。
- 灰字门槛 ≥7.7:1(对 --bg),正文与读数 ≥16:1(硬底线 15.8:1,对 --panel 时),占位字 ≥5:1。改任一 hex 都要重算这张表。
- 不出现纯黑纯白:页面、面板、文字都不用 `#000000` / `#ffffff`。唯一例外是画面盒子内部(视频 letterbox 与片段缩略图底)填 `#000`,那是解码图像的底色,不是页面底色。
- 不做渐变底、扫描线、画面内发光、双层边框;画面装饰只有 1px 环 `#2b3439` 加投影 `0 20px 48px #00000073`。
- 折线不用强调色标注峰值,免得读成第二条数据线(见 §7)。

## 3 间距

基准 4px。档位用 8 / 10 / 12 / 16 / 18 / 20 / 24 / 28 / 32 / 40 / 48。

| 位置 | 值 |
|---|---|
| 页面内边距 | 桌面 20 24 24(上 右 下),左 24;≤900px 四边 16 |
| 两栏间距 | 列 28,行 20 |
| 分区之间 | `margin-top 20` + `padding-top 18` + 1px `--line`,视觉间隔 38 |
| 分区标题到内容 | 6 |
| 字段标签到控件 | 12;同行控件之间 12;两行控件之间 20(行 gap 12 / 列 gap 40) |
| 读数双列 | 列间 32;标签到值 10;每行上下 3 |
| 注册区 | 标签到输入行 8;输入到按钮 10;状态行 8;名单首行 10;名单行 5 |
| 片段 | 行 6;缩略图到文字 12 |
| 顶栏 | 高 56,左右 24 |
| 画面内 OSD | 距边 10;标签内 3 8 |

规则:分组之间 ≥20px 是硬规则;同一行内的元素用 8 到 12;不许用小于 6px 的间隔来表达分组。旧版每行一条虚线的做法全部删除,全页保留的分隔线只有分区之间的 5 条。

## 4 组件规则

### 4.1 读数行(readout)

- 双列:`grid-template-columns: 1fr 1fr`,列间 32,行内 `padding: 3px 0`。
- 标签 `flex: 0 0 108px`、13px `--muted`、不换行、溢出省略号;值紧跟标签 10px。
- 值 15px mono `--text`、`tabular-nums`、单行省略号。
- 跨两列的 wide 行只给三条:Video bitrate、Detection zone、Face IDs。
- 一行一条,行间不加边框;只有分区之间画线。
- 值还没到时显示一个连字符 `-`(`--muted`),不用长破折号、不用 `n/a`、不留空白;`Recording` 关闭时显示 `off`。
- 390px 仍双列,不改字号;值放不下就省略号。若真机出现大面积截断(超过三条),才退回单列,并且不许顺手缩小字号。

### 4.2 控件

- 高度:select / button / input 一律 `min-height: 40px`,`padding: 8px 12px`;主按钮 `padding: 8px 14px`;分段按钮 `padding-inline: 16px`。
- 默认:`--raised` 底 + 1px `--line-strong` + `--text` 字,圆角 4px。输入框底用 `--panel`。
- hover:底 `--raised-hover`、边框 `#4d5a61`。
- active(按下):`translateY(1px)`,不改底色。
- focus-visible:`outline: 2px solid var(--accent)`,offset 2px。键盘可达,不许去掉轮廓。
- disabled:`opacity: .45`,`cursor: not-allowed`,不位移。
- 选中态(视图):`.seg.active` 用 `--accent` 实心底 + `--on-accent` 字 + 600 字重;`.seg.active:hover` 换成 `--accent-hover`。
- 录制态:`#record.active` 边框 `--alarm`、底 `--alarm-soft`、字 `--alarm`。
- 删除 `×`:32x32、透明底、1px `--line` 边、`--muted` 字;hover 变 `--alarm-soft` 底 + `--alarm` 边与字。≤900px 放大到 40x40(名单行内唯一的例外,其余控件恒 40 高)。
- 过渡:150ms,只过渡 background-color / border-color / color;`prefers-reduced-motion: reduce` 时全部降到 .01ms。
- 标签在输入框上方,不用占位符当标签;占位符只给例子(`e.g. Alice Ng`)。
- 按钮文案 ≤3 词且桌面单行:`Apply`、`Clear zone`、`Camera`、`Decoded (RVM1)`、`Save snapshot`、`Start recording`、`Export metrics`、`REMEMBER FACE`。

### 4.3 状态行与名单

- 状态行 13px、行首 7px 实心圆(`currentColor`)、上边距 8,固定在输入行下方。
- 一行只报一个结果;出现与消失都不改变布局,始终预留一行高度。
- 名单行:名字 15px `--text` 左对齐,删除 `×` 右对齐;行间 1px `--line`,首行上边距 10。

### 4.4 loading / empty / error

- loading:模型预热 2 到 3 秒期间,读数值显示 `warming up`(`--muted`),`REMEMBER FACE` 置 disabled。不用转圈、不用骨架闪动。
- empty:名单 `No names saved yet`,片段 `No recording yet`(替换现有 `No recording yet.` 的句号);13px `--muted`,上下 8,说明怎么填(去上面输入名字并点 REMEMBER FACE)。
- error:内联在状态行,不弹 toast,不写日志行、异常类名、HTTP 码。

## 5 分区清单

全页 5 个分区(上限 6),桌面右栏 460px 从上到下:

| # | 标题 | 内容 | 布局族 |
|---|---|---|---|
| 1 | `STREAM` | 5 条读数(其中 Video bitrate 为 wide)+ 码率折线 + 峰值角标;标题右侧挂 `RVM1 · H.264-style hybrid` | 读数双列 + 全宽画布 |
| 2 | `TRANSPORT` | 6 条读数:Packets sent、Pictures、Packet loss、Jitter、Viewers、Recording | 读数双列 |
| 3 | `ANALYSIS` | 8 条读数:Motion、Faces、Tracked objects、Gestures、Expressions、Audio events、Detection zone(wide)、Face IDs(wide) | 读数双列 |
| 4 | `FACE REGISTRY` | 标签 + 输入行 + 状态行 + 名单 | 表单块 |
| 5 | `CLIPS` | 单行片段:56x42 缩略图 + 日期时间 + 帧数 | 列表行 |

分区之外只有两块:顶栏(高 56,左 `RVM` / `Remote Video Monitor` / `EIE4428`,右 live 点与 `live`)与画面区(4:3 画面 + 两枚 OSD + 两行控件 + 一行提示)。

既有 DOM id 全部保留(`#stream`、`#view-source`、`#view-decoded`、`#m-*`、`#spark`、`#clips`、`#alarm` 等),页面静态测试钉住了它们;只改结构、样式与位置,不改 id。三处迁移:`#m-codec` 从 STREAM 读数行移到该区标题右侧 meta;`Recording`(`#m-rec`)从 ANALYSIS 移到 TRANSPORT 末行;`#src-label` 与 `#time-label` 从底部横条移到画面顶部两角 OSD,`#view-label` 转 `sr-only` 供读屏(当前视图由 `.seg.active` 的按下态承载)。

规则:每区只干一件事;不满 6 条读数不许拆区,超过 8 条要拆就另开票;画面是页面第一焦点(桌面最大面积),遥测不抢画面。分区标题格式统一:`13px / 600 / 大写 / --text-2`,不加序号,不加装饰点。

## 6 响应式顺序

- ≥901px:两栏 `minmax(0, 1fr) 460px`,列间 28 行间 20;右栏自身滚动 `max-height: calc(100vh - 102px)`(沿用现有实现);1440x1000 一屏到底、无滚动无截断(参照图实测:文档高 1000,见 NOTES 第 9 条)。
- ≤900px:单列,顺序固定为 **画面 → 控件 → 提示行 → FACE REGISTRY → 遥测四区**(STREAM、TRANSPORT、ANALYSIS、CLIPS)。用 `.viewer` / `.rail` 的 `display: contents` 加 `order` 实现,不改 DOM 顺序、不动无障碍阅读序。
- 390px(落在 ≤560px 档):顶栏 52 高,隐藏 `Remote Video Monitor`;标签 14px;画面 4:3 满宽。控件逐行排:
  - 第一行控件每行一条,三格「标签 + 下拉(占满剩余宽度) + 按钮」,即 `Target bitrate` 与 `Apply` 同一行、`Motion sensitivity` 与 `Clear zone` 同一行。
  - `Camera` / `Decoded (RVM1)` 两列等宽;`Save snapshot` / `Start recording` 两列等宽;`Export metrics` 独占整行。
  - 删除 `×` 40x40。
- 逐节折叠写死:读数仍双列;折线高度 30 不变;OSD 12px 不缩放;片段缩略图 56x42 不变;分区之间仍是 20 + 18。
- 七个操作(Apply、Clear zone、Camera、Decoded (RVM1)、Save snapshot、Start recording、Export metrics)在 390x844 首屏内全部可见,不需要滚动才能点到(与 `mock-mobile.png` 逐项对上)。

## 7 码率折线峰值标注

- 形式:折线上缘一条 1px 水平虚线,虚线的水平位置就是该窗口峰值所在的刻度高度(画布顶部往下 6px)。
- 线型:dash 3px / gap 3px、宽 1px;颜色 `rgba(154,165,170,.5)`,即 `--muted` 半透明,叠加后 `#555c60`,对 `--panel` 2.72:1。它只作刻度边,不承载文字,所以不按文字对比度要求。
- 不用 `--accent`:峰值虚线若用强调色会被读成第二条数据线。
- 角标文案:`peak 1.33 Mbps`,即 `peak` + 空格 + 两位小数 + 空格 + `Mbps`;数值取该窗口最大值。
- 角标字体:12px / 400 / mono / 字距 .02em / `tabular-nums` / 色 `--muted`(对 `--panel` 7.35:1)。比读数 15px 小一档、比分区标题 13px 更轻,桌面与 390 同值不缩放。
- 角标位置:挂在 `Video bitrate` 那一行的行尾,`margin-left: auto` 右对齐,与折线右端、与标题右侧 meta(`RVM1 · H.264-style hybrid`)同一条右边线。
- 不新增块:不加图例框、不加高、不占新行。1440x1000 下最低内容底 953,分区位置与上一版逐像素相同。
- 数字与画布同源:画布按同一个 peak 归一化,所以角标数字永远等于折线天花板,不许两边各算一次。
- 390px:角标同样 12px 不换行;若该行放不下,角标下移到折线右上角,仍不加块。
- 无障碍:canvas 用 `role="img"` 且 `aria-label` 写明 `scaled to a peak of X Mbps`,角标是它的可见副本。

## 8 五态文案与配色

UI 文案全英文,一句一行不超过 60 字符,句末不加句号,不用感叹号。名字取输入框原文,不加引号。

| 态 | 触发 | 文案(逐字) | 颜色 | 行为 |
|---|---|---|---|---|
| 注册成功 | 最近三帧每帧一张脸,取平均入库 | `Saved as Alice Ng, 3 frames averaged` | `--ok` `#6ecb8f` | 名单立刻出现该名字;行首圆点同色 |
| 无脸 | 画面内 0 张脸 | `No face in frame, hold still` | `--alarm` `#f0715a` | 按钮保持可用,名单不变 |
| 多脸 | 画面内超过 1 张脸 | `Two faces in frame, show one` | `--alarm` `#f0715a` | 不取平均,不写盘 |
| 重名 | 名字已在名单里 | `Alice Ng is already saved, add a surname` | `--warn` `#e3b45c` | 不覆盖旧向量,名单不变 |
| 分析关闭 | 服务以 `--no-analysis` 启动 | `Analysis is off` | `--muted` `#9aa5aa` | Faces / Face IDs 值显示 `off`(`--muted`);`REMEMBER FACE` disabled(.45) |

补三个非错误态:

- 空名单:`No names saved yet`,13px `--muted`,说明去上面输入名字。
- 预热:Faces / Face IDs 值显示 `warming up`(`--muted`)。
- 录制中:`RECORDING` 用 `--alarm`,画面外框换成 `--alarm` 3px。

规则:五态共用同一条状态行,同一时刻只显示一条;文案里不出现命令行参数、文件路径、异常类名、HTTP 码,`Analysis is off` 后面不接参数说明。

## 9 设计变量(可直接抄)

```css
:root {
  --bg: #0b0d0e;            --panel: #101416;
  --raised: #191f22;        --raised-hover: #212a2e;
  --line: #252c30;          --line-strong: #39444a;
  --text: #e9eef0;          --text-2: #c3ccd0;
  --muted: #9aa5aa;         --placeholder: #7d888d;
  --accent: #5fd3c6;        --accent-hover: #78ded2;
  --accent-soft: #5fd3c61f; --on-accent: #072521;
  --ok: #6ecb8f;            --warn: #e3b45c;
  --alarm: #f0715a;         --alarm-soft: #f0715a1f;
  --fs-label: 13px;         --fs-body: 15px;   --fs-title: 18px;
  --sans: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  --mono: "Cascadia Mono", "Consolas", ui-monospace, "SF Mono", monospace;
  --radius: 4px;
  color-scheme: dark;
}
@media (max-width: 560px) { :root { --fs-label: 14px; } }
```

命名与 §1 到 §3 一一对应:`--fs-label` 即标签档,`--fs-body` 即正文与读数档;间距不设变量,按 §3 表内数值直接写死。字体只用上面两个系统栈,不引任何远程字体或图标 CDN(`tests/test_app.py` 有远程资源禁令,`src=` / `href=` / `url()` / `@import` 指向外部都会被判失败)。圆角统一 4px(画面盒子、输入框、下拉、按钮);例外只有四档:OSD 标签与片段缩略图 3px、ROI 框与跟踪点 2px、状态点 50%(正圆)、告警框与检测框直角 0(它们要贴住画面内容边界)。

## 10 禁项与交付前校对

- 内部串不上屏:版本号、`TODO`、`#id`、日志、堆栈、绝对路径、`lorem` 一律不许出现在页面上。
- 无重复项:一屏只有一个「把这张脸存下来」的动作;Camera / Decoded 是状态,不另外加一句文字副本说明当前视图。
- 同级同权:全部读数 15px / 500 mono;全部分区标题 13px / 600 `--text-2`;全部次级按钮同高同边。
- 层级清楚:画面 > 读数 > 标签,靠字重与色阶区分;强调色只标「当前选中」与「主操作」。
- 数据要有人味:`24.6 fps`、`0.42 %`、`18,493`、`3.17 ms`、`1.18 Mbps`、`peak 1.33 Mbps`;不用 `99.99%`、`50%`、`1234567`,不用 Jane Doe / Acme。
- 不出现长破折号(U+2014)与用作分隔的短破折号:正文、按钮、角标、状态文案一律不用;范围与日期写连字符,如 `2026-10-24 21:38`。
- 单暗色:本页锁定暗色(`color-scheme: dark`),现场投影与录屏都按暗色校验;不提供亮色,也不做半套亮色。要与指南的双模式要求对齐需另开票。
- 逐条自检:每个数值都能在 `mock-desktop.png` 或 `mock-mobile.png` 上指到位置;指不到的数值不许写进本文。
