# Overall gate — integration dynamic axis

VERDICT: VERIFIED — AS-1..AS-7 逐条拿到本轮新鲜证据（干净 worktree + 真服务器 + 真 Chrome）；全部六类失败端到端走通、持久化/删除/重启亲核、两档视口实测达标；仅一处 mobile 分区界线缺分隔线且间隙 16<20（[Important][visual]，非阻断）。
HEAD: 01d08b75d838c7aeb48d24e3ecbaedfba4919ec0
LEDGER: 00-r1-001,003,004,005,007,008,009,010,011,012,013,014,015,016,017,018,019,020,021,022,023,025,026,027（00-r1-002/024 为探针自身调用错误，非产品失败）

- 定靶：HEAD `01d08b7`；范围 `git diff 8db38f4..HEAD`；产品 diff（除 .scratch）18 文件 +3482/−258（>1000 行，集成门按 WARN 标注，非驳回项）；7 票全部 `resolved`。
- 环境：gate-kit worktree `verify-overall-01d08b7`；主仓 `.venv` Python 3.13；系统 Chrome 156 `--headless=new`；证据探针全目录 `verifier-probes/overall-dynamic-*`。
- 方法：真 `run_server.py`（:8099 / :8152 / :8153+ / :8170 暖机竞速）+ 桩识别器启动器 :8150（`sample_faces`/`recognize` 在类边界替换，标注为桩；其余链路全真）。同源 iframe 驱动页 `value=`+`click()`，真实 fetch 计费节奏。桩/真逐条标注见 `overall-dynamic-evidence.md`。
- 我若偷懒会在这 5 处省事：①把逐票门旧截图/读数当本轮证据；②成功注册只用桩 fetch 骗 UI 不验证落盘与镜像；③用 `--window-size` 冒充精确视口；④只断言状态码不核 reason↔文案映射与文件真写；⑤跳过重启持久化、删除只看 DOM 不看文件、不做变异。

## AS-1 面板注册闭环 — 满足

- 真 201 两次（桩取样+全真链路）：`Saved as Gate Person, 3 frames averaged` / `Saved as Second Person…`，`class="status ok"`，`samples=3`，名单立即刷新（00-r1-009/026；dom-reg*.html，reg-ok.png）。
- 文件真写：`data/known_faces.json` = `{"version":1,"faces":{name:[1434-dim]}}`，与 `GET /api/faces/known` 及渲染名单三者一致。
- 不阻塞：桩 `sample_delay=0.35s`×3（POST 1161ms→201）期间，34 次 `/api/status` 全通 max gap 0.167s、MJPEG 持续输出 65536B；`/api/faces/known` 同步可用（noblock.py）。
- 界面不中断：截图显示 LIVE + MOTION DETECTED + 遥测照常更新。

## AS-2 识别展示 — 满足

- 名字+相似度：`ids="Gate Person · 0.97"`（桩 recognize 出真实 running+identity → 真实渲染；00-r1-012，ids.png）。
- 低于阈值不显名：`running, seen=1, identities=[]` → `ids="no face"`（00-r1-013）。阈值过滤在服务端 `recognition.py:336` 的 `_match`，变异 `<`→`<=` 被定向测试杀死（00-r1-023）。注：`w.render` 喂造假 0.59 会照显示（`"Low Conf · 0.59"`）——出契约载荷，UI 信任服务端契约，与 04 门同一裁决口径；诚实记录不算缺陷。
- 名单空+有人脸：`ids="2 faces, none known"`（00-r1-014）；无人脸+名单空 → `"0 faces, none known"`（8099 实测）；无人脸+名单非空 → `"no face"`（8150 实测）。

## AS-3 持久化 — 满足

- 落盘默认路径 `data/known_faces.json`（worktree cwd）；杀进程重启后 `GET` 返回 4 名、页面渲染 4 行（00-r1-019，restart.png）。
- 删除即消失+文件同步：真实点 × → `before=4 after=3`、DOM 行消失、磁盘文件同步为 3 名（00-r1-020，deleted.png）；`DELETE Nobody` → `404 bad-name`。

## AS-4 失败与降级 — 满足

- 409：`no-face`（真）→ `no face in frame, hold still` err（00-r1-007，noface.png）；`multiple-faces`（桩取样 2 脸→真 409）→ `more than one face in frame` err（00-r1-011，multi.png）；`name-exists`（真 409）→ `Gate Person is already saved` warn（00-r1-010，dup.png）。
- 503：`analysis-disabled`（真 `--no-analysis`）→ `analysis is off` + ids=`off`（00-r1-016，off.png）；`models-loading`（真，暖机竞速 1.66s）→ API `{"reason":"models-loading"}`（00-r1-017），UI 文案经真实 `faceFailure` 渲染 `models still loading`（00-r1-018，loading.png）；`unavailable`（桩 raise→真 503）→ 服务端原文错误文案（00-r1-015，unavail.png）。
- 400 `bad-name`：空名 / 50 字符名 / 非 JSON 体，各 400（curl 实测）。
- 失败不写文件：`.od/empty/` 全程空目录。
- 五态文案逐字命中票面字面量。

## AS-5 不回归 — 满足

- 无远程资源：netlog 20 条页面发起请求全为 127.0.0.1（/static、/api/*、/ws、favicon）；`REMOTE page-initiated: none`（00-r1-001，netlog.json+scan.py）。
- 无 page error：stderr 扫描 0 Uncaught / 0 net::ERR / 0 SEVERE。
- 控件与读数齐全：两档视口 `opsOffscreen=[]`（apply/clear-roi/2 view/snapshot/record/metrics/remember 全部可见）；全部 DOM id 在（driver 逐 id 读取）。
- pytest 全套在干净副本重跑：满屏 `.` 至 100%，exit 0（00-r1-021）。

## AS-6 可读性 — 满足（一处边界缺陷记 F-1）

- 1440×1000：`docW=1440/1440 docH=1000`（无溢出、一屏到底）；`minFont=12`（仅 OSD/peak）、`labelMin=13`、`valueMin=15`、`minLH=1.5`、`minSectionGap=20`、`clippedDD=0`（00-r1-003，desktop.png）。
- 390×844：`docW=375/375`（竖滚动条 15px，无横向溢出）、`labelMin=14`、`valueMin=15`、`minLH=1.5`、`clippedDD=0`（00-r1-004/005，mobile pngs）。
- 对比度：正文/读数 16.65、标签 7.73、h2 11.94、控件 8.97，全 ≥4.5；`c1.7` 为告警叠层半透明底的测量伪影（第二跑告警熄灭时 minContrast=7.73）。
- 顺序：390 下 画面→控件→提示→FACE REGISTRY→遥测四区，`registry@645 < Stream@849` 实测。

## AS-7 简洁与观感 — 满足

- 5 个分区（≤6）；画面为最大面积第一焦点；冗余框线/重复标签已去；OSD 两角；`peak x.xx Mbps` 角标在屏。
- 1440×1000 无截断操作；390 顺序正确、控件首屏全可见。

## review-leads 逐条复验

1. **Soundness（409 reason↔文案缝）**：**复现校验=未发现缺陷**。五态逐一亲核：no-face/multiple-faces/name-exists/analysis-disabled/models-loading 的 reason 与屏上文案逐字对应（含服务端 unmapped 文案兜底）。reason 枚举与契约一致。
2. **Repo-fit（原地改名单断流）**：**未复现为缺陷**。慢注册期间 status 0.167s 最大间隔、MJPEG 65KB 持续；`_publish_faces` 整体替换由 文件/镜像/页面三处一致亲证；测试 `test_status_and_snapshot_stay_available_while_registering` 同向。
3. **Fidelity（低于阈值误显示名）**：**未复现为缺陷**。`identities=[]`+seen=1 → `no face`；阈值分支在 `_match`，变异杀死（00-r1-023）。造假越约载荷会显名是契约边界外行为，与 04 门同口径。

## FINDINGS

- **[Important] [visual] `src/rvm/web/style.css:297`** — ≤900px 时 `.section + .section`（margin 8 + border-top 1px + padding 16）对 Stream 不生效（Stream 是 `.rail` 首个 `.section`），而 mobile 顺序把 FACE REGISTRY 排在它前面：registry→Stream 边界实测只有 `.layout` row-gap 16px、无分隔线，其余分区边界为 24px+1px 线。违反设计 §3「分区之间 … 1px --line」一致性与 AS-6「分组间距至少 20px」的字面值（16<20）。为何重要：五条分区界线少一条且间隙短 8px，是签字版设计系统内的真实不一致；桌面不受影响。建议修法：`@media ≤900` 下给 `.registry` 之后的 `.section` 或 `main.layout > .section` 补 `border-top+margin-top`，或让 `.section + .section` 的选择器换成 `main .section ~ .section` 之外的等价覆盖。confidence: HIGH
- **[Nit] [env]** — 证据伪影：dump-dom 与 screenshot 为两次 Chrome 调用，同名注册在截图跑时会命中「already saved」；`dom-reg*.html` 内是真实 201 读数，`reg-ok.png`（Third Person）携带 ok 文案。已在 evidence.md 披露。confidence: HIGH
- **[FYI]** — 告警叠层 `#ffb3a6`/`#f0715a14` 在对比度测量中读 1.7（半透明底被探针当不透明），截图肉眼可读，非缺陷。confidence: MEDIUM

## 收编清单

无存活的未收编变异需要收编（三条变异均被既有定向测试杀死：00-r1-022/023/025）；不新增正式测试文件。

## NOT RUN / 转述

- 真 UI 点击落在 ~1.6s 暖机窗内的 `models still loading`：Chrome 启动+iframe 接线开销大于窗口，改用暖机竞速拿真实 503 reason（API 层）+ 真实 `faceFailure` 渲染拿屏上文案（两处均已标注）。
- 无其他依赖转述项；结论全部来自本轮新跑。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 01d08b7 | reports/overall-dynamic.md | [visual]1 | 七条 AS 全部亲核新鲜证据通过；唯一缺陷为 mobile 一处分区界线缺分隔线且间隙 16<20px，记 Important 非阻断 |
