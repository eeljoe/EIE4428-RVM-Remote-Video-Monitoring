# 04 — 注册控件与文档

**Status:** resolved
**Blocked by:** 01, 02, 03
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/04-face-registry-ui-selfcheck.md`）
**UI:** yes

## What to build

在面板上新增独立的 FACE REGISTRY 分区：名字输入、REMEMBER FACE 按钮、两态状态行、名单与删除；Face IDs 显示「名字 · 相似度」。同步 README、FEATURES 与报告生成器的文案，并补静态测试。

## Acceptance criteria

- [ ] 新增独立 FACE REGISTRY 分区，含名字输入、记住按钮、状态行、名单与删除按钮 [AS-1, AS-2]
- [ ] Face IDs 显示「名字 · 相似度」；名单为空且无人脸时显示 `no-known-faces` 与 `N faces, none known`；相似度低于阈值时不显示名字 [AS-2]
- [ ] 五态文案与 spec「接口契约」一致：成功 `Saved as <name>, 3 frames averaged`；无脸 `no face in frame, hold still`；多脸 `more than one face in frame`；重名 `<name> is already saved`；503 `analysis is off` 或 `models still loading` [AS-1, AS-4]
- [ ] 注册成功后名单与 Face IDs 立刻刷新，删除后立刻消失；名字做转义，不拼 HTML [AS-1, AS-2]
- [ ] README、`docs/FEATURES.md` 与 `tools/build_report.py` 同步注册能力与「不存照片、名单不进仓库」的限制 [AS-2, AS-4]
- [ ] 静态测试钉住新 DOM ID 与无远程资源；全套测试通过 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 目视：`run_server.py --no-camera --port 8099`，注册、删除、刷新页面各走一遍。

## 写域

- `src/rvm/web/index.html`
- `src/rvm/web/app.js`
- `src/rvm/web/style.css`
- `tests/test_app.py`
- `README.md`
- `docs/FEATURES.md`
- `tools/build_report.py`
- `tests/test_report.py`

## 开工包

- **写域**：`src/rvm/web/index.html`, `src/rvm/web/app.js`, `src/rvm/web/style.css`, `tests/test_app.py`, `README.md`, `docs/FEATURES.md`, `tools/build_report.py`, `tests/test_report.py`

- **端点契约**：以 02 号票交付为准，失败体 `{"error","reason"}`；`reason` → 文案映射见 spec「接口契约」。
- **视觉**：`docs/DESIGN-dashboard.md` 与 `.scratch/face-recognition/design/v2/mock.html`（含五态文案注释）。
- **锚点**：`grep -n "function analysisText" src/rvm/web/app.js`（扩写身份行）；`grep -n "m-identities" src/rvm/web/index.html`。
- **删除绑定**：用 `data-name` 属性与 `textContent`，不拼 HTML 字符串。
- **刷新**：注册与删除成功后只刷新名单与身份行，不整页刷新。
- **尺寸上限**：8 个文件、预计超 300 行；按 OVER-LIMIT 分级走额外静态实例。
- **估算**：预计 45 分钟 / 210 步。

## 验收包

- **判据**：AS-1、AS-2、AS-4、AS-5；每条 AC 有截图或测试断言。
- **首攻靶**：名字特殊字符是否安全、四类失败文案是否真被触发、低于阈值是否真的不显示、空名单是否回显人数、文档是否与实现一致。
- **相关 AS 摘录**：AS-1 注册闭环；AS-2 展示；AS-4 失败；AS-5 不回归。

## 完成条件

实现提交含测试；独立动态门在真实浏览器里完成注册、删除、失败与刷新四步并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明(r1)

改动：6 个文件、+397/−10 行（`README.md`、`docs/FEATURES.md`、`src/rvm/web/app.js`、
`tests/test_app.py`、`tests/test_report.py`、`tools/build_report.py`）。分区外壳与
`#face-name` / `#face-remember` / `#face-status` / `#face-list` 由 03 号票建好，
本票只接线，没有改结构；`style.css` 未动（`.status.ok/.err/.warn`、`.names .x` 已在
03 的样式里）。

### 1 AC → 证据

| AC | 代码 | 测试 | 目视 |
|---|---|---|---|
| 独立分区 + 输入/按钮/状态行/名单/删除 | `src/rvm/web/index.html:111-122`（既有结构）、`app.js:565`、`app.js:586`、`app.js:493` | `tests/test_app.py:641`、`tests/test_app.py:676`、`tests/test_app.py:690` | `04-selfcheck-3b-list.png` |
| Face IDs 名字 · 相似度；阈值以下不带名字 | `app.js:71-93` | `tests/test_app.py:731` | `04-selfcheck-3b-list.png`（名单非空但无人脸 → `no face`，不编名字） |
| 空名单且无人脸回显 `N faces, none known` | `app.js:71-93` | `tests/test_app.py:731` | `04-selfcheck-1-empty.png` → `0 faces, none known` |
| 五态文案（成功/无脸/多脸/重名/503） | `app.js:480-485`、`app.js:565` | `tests/test_app.py:703` | 2/3/5 真 409、503；6/7 为桩 201/409 |
| 注册/删除后立刻刷新，名字转义不拼 HTML | `app.js:493`（`textContent` + `dataset.name`）、`app.js:565-579`、`app.js:586-596` | `tests/test_app.py:690` | `04-selfcheck-4-deleted.png`（真 DELETE）、`04-selfcheck-6-saved-stub.png`（桩 201 后名单与身份行刷新） |
| README / FEATURES / build_report 同步 | `README.md`（What it does 行、`### Face registration`、API 表、Known limitations）、`docs/FEATURES.md`（端点表、`## Face registration`、Limitations）、`tools/build_report.py` 的 `SPECIAL_FEATURES` / `UI_DESIGN` | `tests/test_report.py:251`、`:258`、`:268` | — |
| 静态测试钉新 DOM ID 与无远程资源；全套通过 | `tests/test_app.py:607`（既有 ID 清单仍全在）、`:641`、`:96`（app.js 也断言无 `http(s)://`） | 全套 `569 passed` | — |

### 2 假设

- 02 号票的契约已冻结：`POST` 201 体 `{name, samples, known}`，失败体 `{error, reason}`，
  `reason` 只取 spec 的九个枚举。前端不再自己校验名字（空名由服务端 400 `bad-name` 的
  `error` 原样上屏）。
- `FaceRecognition.snapshot()["identities"][].confidence` 是 `1−距离`；阈值在服务端，
  低于阈值的脸根本不在 `identities` 里，所以「不显示名字」在数据层就成立，前端不重算阈值。
- 名单顺序取 `FaceStore.names()` 的顺序，前端不排序。
- `GET`/`DELETE` 路径用 `encodeURIComponent(name)`，名字含空格、`/`、`#` 时仍命中同一路由。
- 页面能区分「有人但一个都没注册」(`no-known-faces`, `seen>0`) 与「没人」(`no-faces`)：
  前者显示 `seen + " faces, none known"`，后者在名单为空时显示 `0 faces, none known`。

### 3 我知道没覆盖什么

- **models-loading 没有截图**：只有后端探针读数
  （`2.61s status=503 body={"reason": "models-loading"}`，见
  `verifier-probes/04-warmup-probe.py`），状态行该分支只由静态测试钉住文本，
  浏览器侧未目视确认（多次开新窗口后 Edge 只给空白页）。标 UNVERIFIED（UI 呈现部分）。
- **成功（201）与多脸（409）两态的响应体是桩**：合成场景没有真人脸。这两张截图只证明
  前端渲染、文案与名单刷新，不证明服务端采样；采样由 02 号票的测试覆盖。
- 没有 JS 单元测试框架，`faceIdentitiesText` / `renderNames` 的行为由静态文本断言 +
  目视截图证明；「相似度 0.59 时无名字」没有前端断言（该分支在服务端）。
- 未做 XSS 浏览器实测：名字含 `<`/`&` 的安全性只靠 `textContent`、`dataset.name` 与
  「registry 块内无 innerHTML/insertAdjacentHTML/outerHTML」的静态断言。
- 未测 390px 窄屏下注册区外观（本票不改 CSS，顺序由 03 的测试钉住）。
- `refreshIdentities()` 失败时无重试，只等下一帧遥测。

### 4 复现命令

```powershell
.\.venv\Scripts\python.exe run_server.py --no-camera --port 8099 `
    --known-faces $env:TEMP\rvm04\known_faces.json
```

打开 `http://127.0.0.1:8099/`：在 FACE REGISTRY 输入名字点 `REMEMBER FACE` —— 合成场景
无人脸，得到真实 409 与 `no face in frame, hold still`；再加 `--no-analysis` 起一台看
`analysis is off`；名单演示：把 `{"version":1,"faces":{"Alice Ng":[0.1,...]}}` 写进
`--known-faces` 指向的临时文件后重启，再点行尾 `×`，服务端 `GET /api/faces/known` 立即少一个名字。

### 5 我认为最脆的一处

`faceIdentitiesText` 的 `no-faces` 分支用模块级 `knownNames` 判断名单是否为空
（`app.js:71-93`）。页面刚打开、`loadNames()` 的 GET 还没回来时 `knownNames` 是 `[]`，
于是一个「名单非空、当前无人脸」的服务器会被短暂写成 `0 faces, none known`，直到
GET 返回（通常几十毫秒，下一帧遥测也会纠）。攻击方式：慢网络下打开页面立刻截图。
修法二选一：GET 完成前该分支显示 `no face`；或把已知名单放进遥测 payload（要改服务端，
越界）。

### 6 票面外的决定

- 决定：五态文案逐字取票面 AC 的字面量（`no face in frame, hold still`、
  `more than one face in frame`、`<name> is already saved`、`analysis is off`、
  `models still loading`），不用 `DESIGN-dashboard.md` §8 的句子式写法
  （`Two faces in frame, show one`、`... add a surname`、`Analysis is off`）。
  / 理由：票面是唯一需求源且 AC 明写「五态文案」；DESIGN 与票面冲突以票面为准。
  / 影响面：与 §8 的大小写和两处措辞不同，若门按 §8 比对会判不一致；改文案只动
  `app.js:480`。
- 决定：`REMEMBER FACE` 在预热(`pending`)与分析关闭(`disabled`)时**不置灰**，只在请求
  在途时 `disabled`。 / 理由：票面要求「models still loading」「analysis is off」两种文案
  能被真正触发，置灰会堵掉唯一入口；DESIGN §4.4/§8 的置灰条款因此未实施。
  / 影响面：预热 2-3 秒内可点，点后得到一行 503 文案；没有测试钉住置灰。
- 决定：`no-faces` 且名单为空时 Face IDs 显示 `0 faces, none known`（票面 `N faces,
  none known` 取 N=0），名单非空时显示 `no face`。 / 理由：票面要求「名单为空且无人脸」
  时回显人数，同时不能在有名单时谎报 none known。 / 影响面：与 03 号票的
  `no known faces` / `no face` 不同，只影响这一行。
- 决定：票面里「显示 `no-known-faces`」按**状态词**理解，不上屏。 / 理由：DESIGN §8
  的五态表没有把状态词作为文案，AS-2 同句给的可见文案是 `N faces, none known`。
  / 影响面：页面上不出现字符串 `no-known-faces`；若门要求它可见，需要新增一行文案。
- 决定：删除成功后把状态行清空，不加「已删除」文案。 / 理由：五态表只定义注册结果，
  票面没给删除文案，多写一句等于发明。 / 影响面：删除后回到空状态行（高度不变，
  `.status:empty::before` 隐点）。
- 决定：注册/删除成功后额外 `GET /api/faces/identities` 刷新 Face IDs 行。
  / 理由：票面 AC 要「Face IDs 立刻刷新」，等遥测最多 0.5 s。 / 影响面：每次写操作多一个
  GET，失败时静默等下一帧。
- 决定：真机自检用**同源 iframe 驱动页**代替人工键鼠（临时文件，截图后删除）。
  / 理由：本会话的桌面输入只能后台投递，Chromium 的 `text_input` 后台不可用、前台被拒；
  同源 iframe 可以像人一样 `value=` + `click()` 点到真实页面。 / 影响面：产品文件未改；
  驱动页副本留在 `verifier-probes/04-selfcheck-harness.html`，并在自检文档里写明哪几张图是桩。

## Verdicts

- 2026-11-09 r1 VERIFIED f13f0dc — 全部 AC 在真实浏览器里拿到本轮新鲜证据；两条 Important 缺陷（README 一句与实现相反的描述、loadNames 晚到 GET 覆盖新名单的 stale-write）均不阻断票面判据。｜报告：.scratch/face-recognition/reports/04-r1-verifier.md｜模型路线：未标注（派发未带 --model）
