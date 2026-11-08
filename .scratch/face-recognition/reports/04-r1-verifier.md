# Verifier report — 04 face-registry-ui (r1)

VERDICT: VERIFIED — 全部 AC 在真实浏览器里拿到本轮新鲜证据；两条 Important 缺陷（README 一句与实现相反的描述、loadNames 晚到 GET 覆盖新名单的 stale-write）均不阻断票面判据。
HEAD: f13f0dc2140f54a0dad59b8a44bb4989a02ab0a8
LEDGER: 04-r1-001,04-r1-002,04-r1-004,04-r1-005,04-r1-006,04-r1-007

## 定靶

- 基线 `9681d6c`（04 认领），HEAD `f13f0dc` = `44fb4c9`（实现）+ 一处 docs 提交。`git status` 只有 `.scratch` 未跟踪条目。
- 产品面 diff：6 文件（`src/rvm/web/app.js` +193、`tests/test_app.py` +94、`tests/test_report.py` +28、`README.md` +29、`docs/FEATURES.md` +43、`tools/build_report.py` +19）。`style.css` 与 `index.html` 零改动（ledger 04-r1-007）。规模在票面预估内（>300 行属票面已声明的 OVER-LIMIT 分级）。
- 证据落盘：`.scratch/face-recognition/verifier-probes/04-face-registry-ui-verifier.md` + `04-verifier-*.png` + `04-dom/*.html` + `04-verifier-driver.html`。

## 我若偷懒会省的 5 处

只截一张空分区图就声明控件齐全；用 stub 冒充真 409/503；只查 innerHTML 不在源码而不真的喂恶意名字；相信「阈值在服务端」而不实测；拿实现的自检 PNG 复用当自己的截图。以下全部是本轮新跑。

## 判据逐条

| AC | 证据 | 判定 |
|---|---|---|
| 独立 FACE REGISTRY 分区（输入/按钮/状态行/名单/删除） | `empty` 探针：`input=true btn=true btnText="REMEMBER FACE" status="" list="No names saved yet" xButtons=0`（04-verifier-empty.png）；`list` 探针 3 行 × 3 × 按钮（04-verifier-list.png） | PASS |
| Face IDs `名字 · 相似度`；空名单+无人脸 → `N faces, none known`；低阈值不显示名字 | 格式路径经真 `render()`：`subthresh` → `Low Conf · 0.59`（见 FINDINGS-3）；空名单+no-faces → `0 faces, none known`；名单非空+no-faces → `no face`；`no-known-faces` 分支 `(seen)+" faces, none known"`（recognition.py:301-310 语义核对） | PASS（附注见 FINDINGS-3） |
| 五态文案逐字 | 无脸 **真** 409 → `no face in frame, hold still`(err)；多脸 桩409 → `more than one face in frame`(err)；重名 桩409 → `Alice Ng is already saved`(warn)；503 analysis-disabled **真** → `analysis is off`；503 models-loading **真**（预热窗内点击）→ `models still loading`；成功 桩201 → `Saved as Stub Person, 3 frames averaged`(ok)。与票面 AC 字面量逐字一致；与 DESIGN §8 差异（`No`/`Two faces`/`add a surname`/大写）属票面优先，已在实现说明 §6 声明 | PASS |
| 注册/删除后立刻刷新；名字转义不拼 HTML | 桩201 后名单两行+`ids="no face"`（refreshIdentities 真 GET）；真 DELETE `<img…>`与`Bob O'Neil "Q"` 均即时消失且服务端 GET 一致；XSS 名字 `injectedElems=0 pwned=0`，`.who` 是文本节点；`delete` 用 `data-name`+闭包 | PASS |
| README/FEATURES/build_report 同步注册能力与限制 | 三处均写注册闭环、`data/known_faces.json`、不存照片、不进仓库/zip；`.gitignore:15` 与 make_zip 白名单核对一致；**但 README 一句与实现矛盾** → FINDINGS-1 | PARTIAL → FINDINGS-1 |
| 静态测试钉 DOM ID/无远程资源；全套通过 | 569 collected / 569 pass（ledger 04-r1-004）；新增静态断言覆盖三端点、五 reason+文案、textContent/dataset、`name · conf` 格式；app.js 也被纳入无远程资源断言 | PASS |
| 回归：03 可读性与 390 顺序不回退 | `style.css`/`index.html` 对 9681d6c diff 为空（ledger 04-r1-007 同 sha）；390×844 实测 `scrollW=390=clientW` 无横向溢出、`.registry` computed `order=4`（04-verifier-mobile390.png） | PASS |

## FINDINGS

1. **[Important] README.md:124 — `the button is unavailable for exactly those two states` 与实现相反** / 实现明确不在 `pending`/`disabled` 置灰（app.js:561-583，只在请求在途时 disabled；票面 §6 明文声明该决定），loading.png 与 real-off.png 里按钮均可点、点击后正确显示 503 文案。文档断言了不存在的行为。建议改为「按钮保持可点，状态行告知 analysis is off / models still loading」。confidence: HIGH
2. **[Important] src/rvm/web/app.js:612-619 (`loadNames`) — 晚到的 startup GET 覆盖更新名单的 stale-write** / `race` 探针（GET 延迟 400ms、POST 即时 201）复现：状态行报 `Saved as Race Person, 3 frames averaged` 后名单被回写成 `No names saved yet`、`knownNames` 被重置使 ids 显示 `0 faces, none known`。现实中 GET 在页面加载即发、毫秒返回，人为几乎打不进窗口，但属真实的 last-write-wins 缺陷；同一根因使 `knownNames` 在首个 GET 返回前为空（实现者自述的瞬时 `0 faces, none known`）。建议：GET 响应带版本戳/`dirty` 标志，名单被写过之后丢弃或忽略该次渲染。confidence: HIGH（存在性）/ MEDIUM（现实触发面）
3. **[Nit] app.js:84-87 — 前端对 `confidence` 不做二次阈值判断** / 构造出契约外的 `identities:[{name,confidence:0.59}]` 会如实显示 `Low Conf · 0.59`。服务端在 recognition.py:336 保证低阈值不入 `identities`（mutation 杀掉 `<=` 变体，test_recognition 边界钉死），契约内不可能出现，故判据在系统层面成立；如实记录「前端信任载荷」这一事实。confidence: HIGH
4. **[Nit] tests/test_report.py:274 — 孤儿 docstring** / `TestMeasuredClaimsMatchTheImplementation` 被改名为 `TestFaceRegistrationIsDescribed`，旧 docstring `"""The report quotes measured numbers…"""` 残留为死语句，且原类的两条与注册无关的断言混入新类名下。测试照跑照绿，仅整洁度。confidence: HIGH

## REMEDIATION

- [spec] README.md:124 — 按 FINDINGS-1 改写一句，去掉「按钮不可用」的错误断言。
- [impl] app.js `loadNames` — 按 FINDINGS-2 加写后防回写保护（版本戳或 dirty 标志），并建议补一条静态或探针断言。
- [test] tests/test_report.py:274 — 删除孤儿 docstring；或把无关断言挪回原类名/独立类。
- [impl] 可选：前端对 `confidence` 低于阈值恒不显示名字加一道冗余守卫（契约已保证，非必须）。

## 攻击族（逐族）

1. 注入/XSS：种子名单含 `<img src=x onerror=…>` 与 `Bob O'Neil "Q"`，经**真 GET** 渲染为纯文本（injectedElems=0、无 img/svg/b 节点、pwned=0），真 DELETE 两个名字均命中 `encodeURIComponent` 路由。→ 安全
2. 边界/空值：空名字真 POST → 400 `bad-name`，上屏服务端原文 `the name must not be empty`；失败不写文件（v04-empty 目录始终无文件）。→ PASS
3. 并发/时序：loadNames 与 POST 交错 → **FINDINGS-2 命中**；`until` 全部用真 fetch 计时，排除虚拟时间假阳性。
4. 契约外载荷：fabricated `confidence:0.59` 与 stubbed 错误体 → FINDINGS-3 记录；`samples-missing`/`bad-name`/`write-failed`/`unavailable` 走 `err.body.error` 兜底文案（代码核对）。
5. 环境状态：预热窗（~1.5s）真 503 `models still loading`；`--no-analysis` 真 503 `analysis is off`；两态均**非桩**。→ PASS
6. 变异杀伤：3/3 被杀（阈值边界、五态文案、innerHTML 禁令；ledger 04-r1-005/006 + 一条未记账同法复跑）。race 缺陷无测试能杀 → 已列 REMEDIATION。

## NOT RUN

- 真 201 成功体（合成场景无真人脸，无法产生真采样）→ 桩标注，服务端采样路径由 02 票测试覆盖。
- 真 `multiple-faces` / `name-exists` 409 → 桩标注。
- 注册后**重启持久化**的 UI 级复核（删除持久化已实测；注册持久化属 02 票、该票测试覆盖）。
- 03 可读性数值重测：`style.css`/`index.html` sha 未变（ledger 04-r1-007），无回归路径，未重测。
- `deletexss` 探针返回 `ERROR row not found`：探针自身顺序问题（`delete` 已先行删该行），非产品缺陷；XSS 名的真 DELETE 已由 `delete` 覆盖。
- DESIGN §8 文案差异（大小写与两处措辞、§4.4 `warming up`、置灰条款）：票面优先原则已由实现者声明，本条仅作记录。
- 账本条目 04-r1-001（输入哈希已录，声明产物当时尚未生成）与 04-r1-003（命令 quoting 失败 exit 127）为记账噪声，不作证据引用。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | f13f0dc | reports/04-r1-verifier.md | [impl]2 [spec]1 [test]1 | 五态与转义实测全对，README 一句与实现相反、loadNames 有 stale-write，均不阻断判据 |
