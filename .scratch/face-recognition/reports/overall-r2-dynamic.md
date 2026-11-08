# Overall gate r2 — integration dynamic axis

VERDICT: VERIFIED — AS-1..AS-7 逐条拿到本轮新鲜证据（干净 worktree + 真服务器 + 真 Chrome）；r1 三条 Important（mobile 分区界线、不可删名字、DESIGN §8 文案漂移）逐条亲核关闭；全套 594 绿、返工改动两族变异被杀、review-leads 三条预测逐条复验为「未复现为缺陷」。
HEAD: 4dc0acedb86393fc91c2eb9df487c371fc2d9252
LEDGER: 00-r2-001,002,003,004,005,006,007,008,010,011,012,013,014,015,016,018,019,020,021,022,023,024,025,026,027,028,029,030,031,032,033,034,035,036,037,038,039,040,042,043（00-r2-009/017/041 为探针自身调用错误——cmd 层嵌套引号与含空格/unicode 的 venv 路径，已由 010/018-019/043 取代，非产品失败）

- 定靶：HEAD `4dc0ace`；范围 `git diff 8db38f4..HEAD`；产品 diff（除 .scratch）18 文件 +3643/−258（>1000 行，集成门按 WARN 标注，非驳回项；与 r1 同口径）；9 票全部 `resolved`；自 r1 靶 `01d08b7` 起新增为 08/09 两票的收口改动。
- 环境：gate-kit worktree `verify-overall-r2-4dc0ace-4dc0ace`；主仓 `.venv` Python；系统 Chrome 156 `--headless=new`；证据探针全目录 `verifier-probes/overall-r2-dynamic-*`。
- 方法：真 `run_server.py`（:8099 / :8152 / :8170-8172 暖机竞速）+ 桩识别器启动器 :8150/:8160（仅 `FaceRecognizer.sample_faces`/`recognize` 在类边界替换，标注为桩；名单持久化复查用**未打桩的 stock `run_server.py`** 重启完成）。同源 iframe 驱动页 `value=`+`click()`，真实 fetch 到真实 handler。桩/真逐条标注见 `overall-r2-dynamic-evidence.md`。
- 我若偷懒会在这 5 处省事：①拿 r1 截图/读数充本轮证据；②注册只看状态行不查落盘文件与 API 镜像；③用 `--window-size` 冒充精确视口（改用钉死 iframe 的 vp 页）；④三条 Important 只跑静态断言不实测量间隙；⑤不测 DELETE 是否真可达（`.`,`..`,`a\b` 各打了真实 400 且 `Alice Ng.` 真删了一次）。

## AS-1 面板注册闭环 — 满足

- 真 201 三次（桩取样+全真链路）：`Saved as Gate Two, 3 frames averaged` / `Saved as Alice Ng., 3 frames averaged` / `Saved as Shot Person, 3 frames averaged`，`class="status ok"`，`samples=3`，名单立即刷新（00-r2-003/004/023；dom-reg*.html，reg-ok.png）。
- 文件真写：`data/known_faces.json` = `{"version":1,"faces":{name:[1434-dim]}}`，与 `GET /api/faces/known` 及渲染名单三者一致（每次 checkpoint 均核）。
- 不阻塞：桩 `sample_delay=0.35s`×3（POST 1429ms→201）期间，159 次 `/api/status` 全通 max gap 0.216s、MJPEG 持续输出 16384B（00-r2-019，noblock.py）。

## AS-2 识别展示 — 满足

- 名字+相似度：`ids="Gate Two · 0.97"`（00-r2-012，ids.png）。
- 低于阈值不显名：`running, seen=1, identities=[]` → `ids="no face"`（00-r2-013）；阈值过滤在服务端 `recognition.py:336`，变异 `<`→`<=` 被两个定向测试杀死（gate-kit mutate）。
- 名单空+有人脸：`ids="2 faces, none known"`（00-r2-014）；无人脸+空名单 → `"0 faces, none known"`（:8099 实测）；无人脸+名单非空 → `"no face"`（00-r2-020 重启后实测）。

## AS-3 持久化 — 满足

- 杀进程后以**未打桩的** `run_server.py --known-faces data/known_faces.json` 重启：`GET` 返回 3 名、页面渲染 3 行带 ×（00-r2-020/021，restart.png）；身份行正确 `ids="no face"`（名单非空+无脸规则）。
- 删除即消失+文件同步：真实点 × → `before=3 after=2`、DOM 行消失、磁盘同步为 2 名（00-r2-022/042，deleted.png）；`DELETE Alice%20Ng.` → `{"removed":true}`（带点名字可寻址可删）。

## AS-4 失败与降级 — 满足

- 409：`no-face`（真）→ `no face in frame, hold still` err（00-r2-002，noface.png）；`multiple-faces`（桩取样 2 脸→真 409）→ `more than one face in frame` err（00-r2-006，multi.png）；`name-exists`（真 409）→ `Gate Two is already saved` warn（00-r2-005，dup.png）。
- 503：`analysis-disabled`（真 `--no-analysis`）→ `analysis is off` + ids=`off`（00-r2-008，off.png）；`models-loading`（真，暖机竞速连续 3 发 503）→ API `{"reason":"models-loading"}`（00-r2-010），UI 文案经真实 `faceFailure` 渲染 `models still loading`（00-r2-011，loading.png）；`unavailable`（桩 raise→真 503）→ 服务端原文错误文案（00-r2-007，unavail.png）。
- 400 `bad-name` 全契约面：`.`、`..`（dot segment）、`a/b`、`a\b`、`../x`（path separator）、`\x08`/`\x7f`/`\t`（single line）、空名、纯空白、60 字符、非 JSON 体，各 400 `bad-name`（00-r2-015/016 + curl 实测）；`DELETE Nobody` → 404 `bad-name`。不误伤：`..a`、`a..b`、`%2F`、`张小英`、`J. Smith`、`Alice Ng.`、`O'Brien` 通过校验落到真 409 `no-face`。
- 失败不写文件：`.od2/empty/`、`.od2/empty2/` 全程 0 文件。
- 六态文案（含预热补一条）逐字命中上屏原文。

## AS-5 不回归 — 满足

- 无远程资源：netlog 13 条页面发起请求全为 127.0.0.1（/static、/api/*、/ws）；`REMOTE page-initiated: none`（00-r2-038/039）。
- 无 page error：16 份 `.err` 捕获 0 Uncaught / 0 net::ERR / 0 SEVERE。
- 控件与读数齐全：两档视口 `opsOffscreen=[]`（apply/clear-roi/2 view/snapshot/record/metrics/remember 全可见）；所有 PROBE 读数无 `<missing:` id。
- pytest 全套在干净 worktree 重跑：594 dots 至 [100%]，exit 0（00-r2-043）。

## AS-6 可读性 — 满足（r1 F-1 已关闭）

- 1440×1000：`docW=1440/1440 docH=1000`（无溢出、一屏到底）；`minFont=12`（仅 OSD/peak）、`labelMin=13`、`valueMin=15`、`minLH=1.5`、`minSectionGap=20`、`clippedDD=0`（00-r2-031，desktop.png）。
- 390×844：`docW=375/375`（竖滚动条，无横向溢出）、`labelMin=14`、`valueMin=15`、`minLH=1.5`、`minSectionGap=24`、`clippedDD=0`（00-r2-032，mobile.png）。
- **r1 F-1 复测**：≤900 下 FACE REGISTRY→STREAM 实测 `SEAM box=24px visual=25px line=1px solid rgb(37,44,48)`，与其余四条分区界线同为 `24/25/1`（00-r2-033/034，seam-390.png 截图可见分隔线）；变异撤规则 → 定向测试红。
- 对比度：正文/读数 ≥7.73（`c1.70` 仍为告警叠层半透明底的测量伪影，第二跑/移动端告警熄灭时 min=7.73，截图肉眼可读——同 r1 口径）。
- 顺序：390 下 画面→控件→提示→FACE REGISTRY→STREAM→TRANSPORT→ANALYSIS→CLIPS（00-r2-037）。

## AS-7 简洁与观感 — 满足

- 5 个分区（≤6）；画面为最大面积第一焦点；OSD 两角；`peak x.xx Mbps` 角标在屏；1440×1000 无截断操作；390 控件首屏全可见。
- **r1 static Important-2 复测**：`docs/DESIGN-dashboard.md` §8 与 `app.js` 逐字一致——`no face in frame, hold still`/`more than one face in frame`/`Alice Ng is already saved`/`analysis is off`/`models still loading`/`loading` 六条文案两侧同字；旧说法 `Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING` 均不再出现；`REMEMBER FACE` 置灰条款已改回「只在请求在途时 disabled」；「录制中」改为 `Recording` 读数 `recording` + 按钮告警态。
- **r1 static Important-1 复测**：`.`、`..`、含 `/` `\` 的名字全部 400 `bad-name` 且零写入；合法带点名字（`Alice Ng.`、`..a`、`a..b`、`J. Smith`）可注册且 `Alice Ng.` 真实 DELETE 成功。

## review-leads 逐条复验

1. **Soundness（409 reason↔文案缝）**：**未复现为缺陷**。六态逐一亲核：no-face/multiple-faces/name-exists/analysis-disabled/models-loading/unavailable 的 reason 与屏上文案逐字对应；`samples-missing` 在暖机竞速中实测到契约形状。
2. **Repo-fit（原地改名单断流）**：**未复现为缺陷**。慢注册期间 status max gap 0.216s、MJPEG 16KB 持续；文件/镜像/页面三处在每个 checkpoint 一致；删改整体替换由 DELETE 真删 + 文件同步亲证。
3. **Fidelity（低于阈值误显示名）**：**未复现为缺陷**。`identities=[]`+seen=1 → `no face`；阈值分支 `_match` 的 `<`→`<=` 变异被两个定向测试杀死。越约造假 0.59 会显名是契约边界外行为，与 r1、04 门同口径，诚实披露不算缺陷。

## FINDINGS

无新缺陷。三条 r1 Important 全部关闭且各有实测证据；两档视口与契约面无回退。

- **[FYI]** — 告警叠层对比度读数 1.70 为半透明底测量伪影（r1 已披露，本轮复现同读数）。confidence: HIGH
- **[FYI]** — `dom-order` 的 `scrollW=511/511` 是驱动页 iframe 宽度伪影；权威视口读数取钉死 iframe 的 vp 页（`docW=375/375`、`docW=1440/1440`）。confidence: HIGH

## 收编清单

无存活的未收编变异需要收编（三族变异均被既有定向测试杀死）；不新增正式测试文件。

## NOT RUN / 转述

- 真 UI 点击落在 ~2s 暖机窗内的 `models still loading`：Chrome 启动+iframe 接线开销大于窗口，沿用 r1 方案——暖机竞速拿真实 503 reason（API 层，连中 3 发）+ 真实 `faceFailure` 渲染拿屏上文案，两处均已标注。
- 无其他依赖转述项；全部结论来自本轮新跑（HEAD `4dc0ace`、新 worktree、新探针输出）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 4dc0ace | reports/overall-r2-dynamic.md | 无 | AS-1..7 全数亲核通过；r1 三条 Important 逐条实测关闭；594 全绿、返工变异被杀、leads 未复现 |
