# 08 — 整体门收口验收（r1）

VERDICT: VERIFIED — 三条整体门 Important（≤900px 分区界线、不可删名字、§8 文案漂移）逐条拿到本轮新鲜证据并通过；全套 590 绿、回归面零改动；唯一存活变异是套件合法名参数列缺「含点名字」导致的过拒盲区，记 Important[test] 并附收编清单。
HEAD: c15b659dcae2f6e577a40672151fd950827e5f08
LEDGER: 08-r1-001,08-r1-002,08-r1-005,08-r1-006,08-r1-007,08-r1-008,08-r1-009,08-r1-010,08-r1-012,08-r1-014,08-r1-015,08-r1-016

- 定靶：票面「已交票，提交 cbca0dc」；实际验收定靶 `c15b659`（cbca0dc 之后一个 commit，仅落盘 worker 报告与自检探针，产品 diff 相同）；基线 `01d08b7`（整体双轴门已 VERIFIED 的 HEAD）。
- 范围：`git diff 01d08b7..c15b659` 产品面 = `session.py` +18、`style.css` +7、`DESIGN-dashboard.md` ~20、`test_face_api.py` +62、`test_app.py` +57；`app.js`、`index.html`、`recognition.py`、`face_store.py` 零改动（实测 diff 为空）。~164 行 / 5 文件，尺寸内；写域偏差（改 session.py 非 app.py）在票面 §6 已声明且与开工包「收进现有校验函数」一致，接受。
- 环境：gate-kit worktree `verify-08-r1-c15b659`（已 cleanup）；主仓 `.venv` Python 3.13；系统 Chrome headless；真服务器 `run_server.py --no-camera --port 8234`（worktree cwd）。
- 我若偷懒会在这 5 处省事：①拿 worker 自检读数/截图当本轮证据；②名字校验只跑他们写的测试、不自写参数表；③§8 只抽查一两条文案不逐条对；④变异只打产品不打文档；⑤回归只用「全套绿」一句话带过、不核 app.js 是否真没动。

## 判据 → 本轮证据

### AS-6 ≤900px FACE REGISTRY→STREAM 间隔 ≥20px 或一致分隔线 — 满足

- 自写驱动页 `08-r1-viewport-probe.html`（iframe 钉死 390×844 CSS px，`getBoundingClientRect` 实测；同源拷入 worktree `src/rvm/web/08-vp.html`）：`VP 390x844 docW=390/390 winInner=390`，`SEAM reg.bottom=844.5 stream.top=868.5`，**box=24px、visual(m+p)=24、line=1px solid rgb(37,44,48)**；其余四条分区界线 `GAPS` 全部 box=24/line=1px —— 与其它分区逐值一致（08-r1-015，`verifier-probes/08-r1-dom-mobile-ledger.html`；另有同读数 `08-r1-dom-mobile.html`）。
- 700×900 同测：`SEAM box=24 line=1px`，整条 ≤900 档不只有 390 一个点。
- 截图亲眼看图（08-r1-016，`08-r1-mobile-390x844-seam-ledger.png` / `08-r1-mobile-390x844-seam.png`）：`No names saved yet` 与 `STREAM` 标题之间一条肉眼可见的 1px 横线，与 STREAM→TRANSPORT 之间的线同款同粗；`08-r1-mobile-390x844-top.png` 首屏顺序 画面→控件→提示→FACE REGISTRY，与 390 设计序一致。
- **变异双证**：删 `.rail > .section:first-child` 规则后同一台服务器同一驱动页实测 `SEAM box=16 line=0px none`（其余界线仍 24/1px）——正是整体动态门当初量到的缺陷形态，证明读数确实由本票规则产生、不是别的规则顺带抬起来的；还原 sha1 `6a3628f8…` 一致后复测回到 24/1px（`08-r1-dom-mobile-mutated.html`）。规则文本变异（去掉 margin/padding/border）使定向测试变红（08-r1-009）。
- DOM 结构核对：`.rail` 首子 `.section` = STREAM（index.html:73），registry 在 `.rail` 内 DOM 第四但 `order:4` 排到视觉第一 —— 选择器命中正确节点，worker §5 披露的「DOM 首节点≠视觉顺序」脆性成立但当前结构下命中无误。

### AS-4 名字校验 → 400 bad-name 且零写入；合法名 201 — 满足

- 自写探针 `08-r1-name-validation-probe-v3.py`（aiohttp TestClient 走真 HTTP 层，取样桩化、名单路径隔离到 tmp；非套件成员）：**23/23 全绿**（08-r1-005）。
  - HOSTILE 14 条：`.`、`..`、` . `、`../x`、`a/b`、`a\b`、`/etc/passwd`、`tab\there`、`nul\x00`、`del\x7f`、`   `、`\t\n`、`""`、41 字超长 —— 每条 400 + `reason=bad-name` + 名单文件不存在（零写入逐条断言，不止末尾一次）。
  - LEGAL 8 条：`Alice Ng`、`张小英`、`O'Brien`、`Zoë`、`  Mary Ann  `、`a..b`、`..a`、`a%2Fb` —— 每条 201 + 落盘为 trim 后原名 + 同名 URL 段 DELETE 200。
  - 收尾 `GET /api/faces/known` = `[]`：被拒名字连内存镜像都没进（补上了 worker 自陈「没测读路径」的洞）。
- 变异三发全杀：`..` 移出点段判定 → `[..]` 参数 201 红（08-r1-007）；`==127`→`==126` → `del\x7f` 201 红（08-r1-008）；去掉 `\\` 判定 → `a\b` 201 红（08-r1-014，脚本化 sha1 前后一致）。
- **存活变异一发**（见 FINDINGS-1）：`cleaned in (".","..")`→`cleaned.startswith(".")`，定向 15/15 仍绿（08-r1-012）——套件合法名参数列没有含点名字，`..a` 这种可寻址名被过拒无人发现；我的探针 LEGAL 列表已含 `..a`/`a..b` 可杀死它。
- 实现静态核对（session.py:83-110）：判定确收在 `validated_face_name` 单一函数内（非字符串/空白/超长/控制符 `<32 或 ==127`/点段/`/`+`\` 六条），app.py 只判请求体形状，无第二份判定。

### AS-7 DESIGN §8 五态文案与 app.js 逐字一致 — 满足

- 自写逐字探针 `08-r1-design-verbatim-probe.py`：**36/36 全绿**（08-r1-006）。逐条：
  - §8 表内 5 条 + 补充 5 条字串（`Saved as Alice Ng, 3 frames averaged`/`no face in frame, hold still`/`more than one face in frame`/`Alice Ng is already saved`/`analysis is off`/`models still loading`/`No names saved yet`/`recording`/`Start recording`/`Stop recording`）逐字存在于 §8 且 app.js 有对应模板（`" frames averaged"`、`" is already saved"`、FACE_REASONS:481-484、:516、:112、:371）。
  - FACE_REASONS 四条 reason→文案与 §8 逐字对上；`loading`/`off` 读数、`models still loading`、`No recording yet`（无句号）§4.4 与实现一致。
  - 色值 `--ok #6ecb8f`/`--alarm #f0715a`/`--warn #e3b45c`/`--muted #9aa5aa` 与 `:root` 逐一相等；`#record.active` 告警态（border+text `--alarm`、bg `--alarm-soft`）与 §8 录制中条款一致；3px `--alarm` 边框属 `.alarm` 动检叠层（style.css:124-126）非录制外框，§8「画面不加外框」属实。
  - 旧文案 `Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING` 五条全部不存在；`REMEMBER FACE` disabled 仅在途（app.js:583/598）。
- 变异一发即杀：§8 内 `more than one face in frame`→`...in the frame`，设计一致性测试变红（08-r1-010）。

### AS-5 回归：定向 + 全套 + 03/04/07 不回退 — 满足

- 定向 `pytest tests/test_face_api.py tests/test_app.py -q`：**89 passed，exit 0**（08-r1-001）。
- 全套 `pytest`：**590 passed in 31.97s，exit 0**（08-r1-002），与票面「590 左右」一致（前基线 573 + 新增 17）。
- 03 可读性：本票未动任何字号/行高/对比度规则（style.css 仅媒体块内加 7 行一条规则）；`test_app.py` 的字号阶梯（13/15/14px）、WCAG 对比度计算（:414-468）随全套绿。
- 04 五态：app.js 零改动（diff 为空），FACE_REASONS 原样。
- 07 race 防回写：`namesStamp` 守卫三件套原位（app.js:500/505/619-622），测试钉 `:805-811`，app.js 未改 + 全套绿 = 不回退。
- 未对 03/04/07 文件做变异：本票 diff 不含这些文件（实测为空 diff），回归面只剩本票四个改动文件，均已各自打过变异——理由成立，不另开族。

## FINDINGS

1. `[Important] [test] tests/test_face_api.py:335` — 合法名参数列（`Alice Ng`/`张小英`/`O'Brien`/`Zoë`/`  Mary Ann  `）没有任何含点的名字：`cleaned in (".", "..")` 被收紧成 `cleaned.startswith(".")` 后，`..a` 这类可寻址（可经 `DELETE /api/faces/known/..a` 删除）的合法名被 400，而定向 15/15 仍全绿（08-r1-012 实测存活）。为何重要：本修复的全部语义就是「只有 `.` 与 `..` 精确两段不可寻址」，套件钉住了外缘（`.`/`..` 被拒）却没钉内缘（其它含点名仍收）；AS-4「合法名仍 201」半条在该轴上没有牙。建议修法：LEGAL 参数列加 `..a`（或 `a..b`），见收编清单。confidence: HIGH（本轮变异实测）。
2. `[FYI] [env]` — `-k` 定向跑 test_app.py 子集时进程以 0xC0000409 退出（本机 OpenCV 4.14 OpenCL `clReleaseDevice` abort，context.md 票2 r1 已记的环境坑）；断言红绿在 abort 前已正确打印，全套退出码 0。非本票缺陷。confidence: HIGH。

## 收编清单

- 目标套件路径：`tests/test_face_api.py`
- 变异描述或变异文件：`src/rvm/server/session.py` 中 `cleaned in (".", "..")` → `cleaned.startswith(".")`（过拒：`..a` 等以点开头但可寻址的合法名被一并 400）
- 测试命令：`.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k can_be_deleted_again`
- 探针测试文件路径：`.scratch/face-recognition/verifier-probes/08-r1-name-validation-probe-v3.py`（其 LEGAL 列表含 `..a`、`a..b`；变异态下 `..a` 由 201 翻 400 即红）。建议收编形式：把 `..a` 或 `a..b` 加进 `test_a_name_that_can_be_deleted_again_is_still_accepted` 的参数列即可，不必整探针入套件。

## NOT RUN

- 桌面 1440 档与 ≥901px 未重测：本票规则在 `@media (max-width: 900px)` 块内，静态上不外溢；桌面档沿用整体动态门 `minSectionGap=20` 读数（该 HEAD 产品未变此区域）。
- ≤560 档未取第二点（390 已落该档内，另有 700×900 补一个同档点）。
- 每条逐字引用均可被内容搜索命中；探针与读数文件均在 `verifier-probes/08-r1-*`。

## 诚实说明

- 账本 003/004/011/013 四条是本门探针/记账命令自身失败（import 名打错两处、gate-kit `--find`/`--replace` 引号转义两处），与产品无关；正确探针为 v3 与 014。
- DOM 读数与截图为两次 Chrome 调用（与整体动态门同口径），读数来自 dump-dom、图来自 screenshot；同服务器同规则，间距由 CSS 决定不受遥测数字影响。
- 驱动页是探针非产品：只在 worktree 副本 `src/rvm/web/08-vp.html` 存在过，worktree 已 cleanup，主仓零写入该文件。
- 本票 AS-4 的不对称遗留（DELETE 侧 `remove_face` 不复用 `validated_face_name`，手改文件塞入 `a/b` 仍可删、`.` 仍删不掉）worker §3 已自陈、静态门 FINDINGS-5 已记，非本票 AC 范围，不重复记。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | c15b659 | reports/08-r1-verifier.md | [test]1 | 三条 Important 逐项亲核通过（缝 24px+1px 线实测/23 名探针/§8 逐字 36 项），全套 590 绿；唯含点合法名过拒变异存活，记 Important[test] 附收编 |
