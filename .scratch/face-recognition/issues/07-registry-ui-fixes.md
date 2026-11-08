# 07 — 收口 04 门留下的两处缺陷

**Status:** claimed
**Blocked by:** 04
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/07-registry-ui-fixes-selfcheck.md`）
**UI:** yes

## What to build

修掉 04 号票门判出的两处非阻断缺陷：README 里与实现相反的「按钮不可用」断言，以及 `loadNames` 晚到 GET 覆盖新名单的 stale-write；顺带清理 `tests/test_report.py` 的孤儿 docstring。

## Acceptance criteria

- [ ] [AS-2, AS-5] README 描述与实现一致：pending/disabled 时按钮仍可点，状态行给出 `analysis is off` / `models still loading`
- [ ] [AS-2, AS-3] `loadNames` 在名单已被本地写操作更新后丢弃晚到响应（版本戳或 dirty 标志），race 探针转绿并补一条测试
- [ ] [AS-5] `tests/test_report.py` 的孤儿 docstring 清理，断言仍在有效位置
- [ ] [AS-5] 定向与全套测试通过，03 的可读性数值与 390 顺序不回退

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 真机：`run_server.py --no-camera --port 8099` + 浏览器 fetch 拦截做 race 探针。

## 写域

- `README.md`
- `src/rvm/web/app.js`
- `tests/test_app.py`
- `tests/test_report.py`

## 开工包

- **写域**：`README.md`, `src/rvm/web/app.js`, `tests/test_app.py`, `tests/test_report.py`
- **锚点**：`grep -n "unavailable for exactly those two states" README.md`、`grep -n "loadNames" src/rvm/web/app.js`。
- **race 复现**：GET 延迟 400ms、POST 即时 201；期望状态行报成功后名单不被回写成 `No names saved yet`。探针原文见 04 门报告 FINDINGS-2。
- **尺寸上限**：≤300 行 / 4 文件。
- **估算**：预计 30 分钟 / 140 步。

## 验收包

- **判据**：AS-2、AS-3、AS-5；race 探针在旧实现上必须红。
- **首攻靶**：README 是否只改这一句、dirty 标志是否会误伤正常首次加载、删除路径是否同样受保护。
- **相关 AS 摘录**：AS-2 展示；AS-3 持久化与一致性；AS-5 不回归。

## 完成条件

race 探针红→绿、全套通过；独立动态门在干净副本里亲手复现旧行为并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

### 1. AC → 证据

- **AC1 [AS-2, AS-5] README 与实现一致** — `README.md:126-128` 现写「the button
  stays clickable in both of those states, and pressing it puts `analysis is off`
  or `models still loading` on the status line instead of saving」。原句
  `the button is unavailable for exactly those two states` 已无命中（`grep -n
  "unavailable for exactly those two states" README.md` → 空）。实现侧不动：
  `src/rvm/web/app.js:577-600`（`rememberFace`）只在请求在途时 `disabled`，与 04
  号票 §6 的决定一致。
- **AC2 [AS-2, AS-3] 晚到 GET 不得覆盖写后的名单** — `src/rvm/web/app.js:495-508`
  是版本戳与写路径；`:593`/`:608` 保存与删除都走 `renderWrittenNames`；`:618-627`
  的 `loadNames` 在 `await` 前取 `stamp`、`await` 后 `if (stamp !== namesStamp) return;`
  再渲染。测试：`tests/test_app.py:731`
  （`test_a_late_list_read_cannot_overwrite_a_written_list`）。真机：探针
  `verifier-probes/07-race-green.png`（list=`Race Person`）对
  `07-race-red-old.png`（旧字节 list=`No names saved yet`、ids=`0 faces, none known`）。
- **AC3 [AS-5] 孤儿 docstring** — `tests/test_report.py:274` 的死语句已变回类文档
  字符串：`TestMeasuredClaimsMatchTheImplementation`（`:276-297`）重新承载
  `The report quotes measured numbers…` 与那两条与注册无关的断言；它们不再挂在
  `TestFaceRegistrationIsDescribed` 名下。
- **AC4 [AS-5] 测试与 03 数值** — 定向 `pytest tests/test_app.py
  tests/test_report.py -q`：67 tests / 0 failures（junit 计数，见报告 TESTS 段）；
  全套：573 tests / 0 failures / 0 errors / 0 skipped。`style.css` 与 `index.html`
  对 HEAD 的 diff 为空，03 的 13px/15px/7.7:1/390 顺序由 4 条既有测试重跑全绿。

### 2. 假设

- `renderNames` 是名单唯一的 DOM 渲染入口：全文件只有 3 处调用（`loadNames`、
  `rememberFace`、`forgetFace`），新增的 `renderWrittenNames` 只是在它前面加戳。
- 写响应体里的 `known` 就是服务端落盘后的最新名单（02 号票契约），因此写答案
  可以无条件压过任何更早发出的读。
- 页面只在启动时读一次名单（`app.js:679` 的 `loadNames()`），没有定时重读；
  守卫因此不需要「重读复位」逻辑。
- 版本戳只在写成功后自增：一次失败的 POST/DELETE 不改变屏幕上的名单，也不该
  挡住随后到达的读。

### 3. 我知道没覆盖什么

- race 探针里的 `POST` 是**桩**（201 + 合成 `known`）：合成场景没有真人脸，真
  201 产生不了。真实保存路径由 02 号票测试覆盖。
- 「DELETE 与晚到 GET」的交错没有单独跑真机探针：删除与保存共用同一个
  `renderWrittenNames`，静态测试断言两处都走它（`count == 2`），但没有第二张截图。
- 没有在 jsdom/Node 里真跑 `app.js`（本项目无该依赖，AS-5 禁止新增依赖），
  所以 AC2 的自动化测试是静态断言，行为证据来自真机探针。
- 「读在写完成后才开始」（stamp 已变，这次读应当被接受）没有专门测试；逻辑上
  读在自己的调用点取戳，必然取到新值。
- UNVERIFIED：Firefox/Safari 的 fetch 时序未测；只在 Chromium 上跑过探针。

### 4. 复现命令

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099 --known-faces %TEMP%\v07\empty\known_faces.json
chrome --headless=new --disable-gpu --virtual-time-budget=20000 --window-size=1440,1000 --screenshot=%TEMP%\race-green.png "http://127.0.0.1:8099/static/07-driver.html?case=race"
```

（驱动页与三份 DOM dump、两张截图在 `verifier-probes/`，完整命令见
`verifier-probes/07-registry-ui-fixes-selfcheck.md`。）

### 5. 我认为最脆的一处

静态测试钉的是标识符 `namesStamp` / `renderWrittenNames` 与它们的顺序。换成
一个 dirty 布尔、或给函数改名，测试会红而行为可能仍然正确——也就是说它可以被
「合法重构」绕过，真正的判据是那三张真机截图。反过来，把 `loadNames` 的守卫
删掉一定会红（本轮已跑：旧 `app.js` 上该测试 FAILED）。

### 6. 票面外的决定

- 决定：把两条与注册无关的断言移进独立类 `TestMeasuredClaimsMatchTheImplementation`，
  而不是只删掉孤儿 docstring / 理由：门 FINDINGS-4 同时点了「docstring 是死语句」
  与「无关断言混入新类名下」两件事，只删注释会留下后半句 / 影响面：
  `tests/test_report.py` +3 行，两条测试的断言与执行不变。
- 决定：版本戳由**写路径**自增（`renderWrittenNames`），读路径只比较不自增 /
  理由：只有写拥有更新的真相，读自增会让两次并发读互相作废 / 影响面：任何绕过
  `renderWrittenNames` 的新写路径都会失去保护。
- 决定：守卫用 `stamp !== namesStamp` 而不是 `<` / 理由：戳是单调计数器，相等即
  「这段时间没有写」，比较值比比较大小更难写错 / 影响面：无。

## Verdicts
