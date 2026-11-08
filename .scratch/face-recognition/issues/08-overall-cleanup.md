# 08 — 整体门收口：移动端间隙、名字校验、设计文案

**Status:** claimed
**Blocked by:** 07
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/08-overall-cleanup-selfcheck.md`）
**UI:** yes

## What to build

收掉整体门三条 Important：≤900px 下 FACE REGISTRY 与 STREAM 之间的视觉间隔不足 20px 且缺分隔；`.`、`..`、含路径分隔符的名字可注册但删除无路由；DESIGN §8 的五态文案与实现逐字不一致。

## Acceptance criteria

- [ ] [AS-6] ≤900px 下 FACE REGISTRY 与 STREAM 之间的视觉间隔 ≥20px，或补一条与其它分区一致的分隔线
- [ ] [AS-4] 名字校验拒绝 `.`、`..`、含 `/` 或 `\`、控制字符与纯空白的输入，返回 400 `reason=bad-name`，不写文件
- [ ] [AS-7] `docs/DESIGN-dashboard.md` §8 五态文案与 `app.js` 实现逐字一致
- [ ] [AS-5] 定向与全套测试通过；03/04/07 的可读性、五态、race 行为不回退

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_face_api.py tests/test_app.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 真机：`run_server.py --no-camera --port 8099`，390×844 截图核对间隙。

## 写域

- `src/rvm/web/style.css`
- `src/rvm/server/app.py`
- `docs/DESIGN-dashboard.md`
- `tests/test_face_api.py`
- `tests/test_app.py`

## 开工包

- **写域**：`src/rvm/web/style.css`, `src/rvm/server/app.py`, `docs/DESIGN-dashboard.md`, `tests/test_face_api.py`, `tests/test_app.py`
- **锚点**：`grep -n "@media (max-width" src/rvm/web/style.css`、`grep -n "bad-name" src/rvm/server/app.py`、`grep -n "## 8" docs/DESIGN-dashboard.md`。
- **校验位置**：把名字合法性判断收进现有校验函数，别在新地方重复一份。
- **尺寸上限**：≤300 行 / 5 文件。
- **估算**：预计 25 分钟 / 120 步。

## 验收包

- **判据**：AS-6 移动端间隔、AS-4 名字校验、AS-7 文档一致、AS-5 回归。
- **首攻靶**：390 实测间隙是否真到 20、`.` 与 `..` 是否 400 且零写入、DESIGN 文案是否逐字一致、是否误伤合法名字（含空格、中文、单引号）。
- **相关 AS 摘录**：AS-4 失败与降级；AS-6 可读性；AS-7 简洁与观感；AS-5 不回归。

## 完成条件

三处修复各有测试或截图证据；独立动态门在干净副本里复验并判 `VERIFIED` 后才可标 `resolved`；随后整体门按新 HEAD 重跑。

## 实现说明

### 1. AC → 证据

- **AS-6（≤900px 间隔 ≥20px 或补分隔线）** — `src/rvm/web/style.css:298-304`：在既有的 `@media (max-width: 900px)` 里给 `.rail > .section:first-child` 加 `margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--line)`，与同档 `.section + .section` 逐字同值。证据两条：`tests/test_app.py:505` `test_the_registry_to_stream_boundary_keeps_its_rule_and_20px`（margin+padding ≥20 且带 1px `var(--line)` 线）；真机读数见 `.scratch/face-recognition/verifier-probes/08-overall-cleanup-selfcheck.md`（390×844：`SEAM box=24px visual=25px line=1px solid rgb(37,44,48)`，其余四条界线同为 `24/25/1`；撤掉该规则后同一探针读 `box=16px visual=0px line=0px none`）。
- **AS-4（`.`、`..`、含 `/` `\`、控制字符、纯空白 → 400 `bad-name` 且零写入）** — `src/rvm/server/session.py:83-110`，全部判定收进既有的 `validated_face_name`；纯空白仍由 `cleaned` 空判定拦下，控制字符从 `ord < 32` 扩到 `< 32 或 == 127`，新增点段与路径分隔符两条。证据：`tests/test_face_api.py:319` `test_a_name_that_could_never_be_deleted_is_refused_before_it_is_stored`（10 个参数：`.`、`..`、` . `、`../x`、`a/b`、`a\b`、`/etc/passwd`、`tab\there`、`nul\u0000byte`、`del\u007fchar`，每条断言 400 + `bad-name` + 文件不存在）；不误伤由 `tests/test_face_api.py:338` `test_a_name_that_can_be_deleted_again_is_still_accepted`（`Alice Ng`、`张小英`、`O'Brien`、`Zoë`、`  Mary Ann  ` 各 201，落盘为 trim 后原名，且能再被 DELETE 删掉）。
- **AS-7（DESIGN §8 与 app.js 逐字一致）** — `docs/DESIGN-dashboard.md:173-195`：五态表改成上屏原文（`no face in frame, hold still`、`more than one face in frame`、`Alice Ng is already saved`、`analysis is off`），`REMEMBER FACE` 由「置 disabled」改为「不置灰，按下即得到这一行」；非错误态补 `loading` 与 `models still loading`；「录制中」由不存在的画面 3px 外框改为 `Recording` 读数 `recording` + 按钮告警态。证据：`tests/test_app.py:524` `test_the_design_copy_matches_the_served_status_line_verbatim`（6 条文案同时出现在 `app.js` 与文档；`Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING` 五条旧说法不得再出现在文档里）。
- **AS-5（不回归）** — 定向 `pytest tests/test_face_api.py tests/test_app.py` 89 passed / exit 0；全套 `pytest` 590 passed / exit 0（改前 573，新增 17 = 10 + 5 + 2）。未改 `app.js`、`recognition.py`、`face_store.py`、`index.html`；03/04/07 的静态断言（类型阶、五态文案、`namesStamp` 守卫）原样通过。

### 2. 假设

- **注册只有一条入口**：`POST /api/faces/known` 必过 `validated_face_name`（`src/rvm/server/app.py:387-389` 只处理「体不是 JSON / 不是对象」，名字本身不另判）。若以后有人在 handler 里先 strip 再传，本票的拒法仍成立（函数内部再 strip 一次）。
- **`.rail` 的 `display: contents` 不影响选择器**：`.rail > .section:first-child` 走 DOM 树，不走布局树；≤900px 下 `.rail` 盒子消失但子节点关系不变。
- **STREAM 是 `.rail` 的第一个元素子节点**，视觉次序由 `order` 重排；若有人往 `.rail` 前插新分区，这条规则会跟着挪到新首节（那时应重新判断要画哪条界线）。
- **「可寻址」是名字合法的口径**：被拒的名字就是「存进去也再也删不掉」的那些；反过来，接受的每个名字都能用 `quote(name, safe="")` 作最后一段删掉（`test_a_name_that_can_be_deleted_again_is_still_accepted` 真发了一次 DELETE）。
- **探针读数与产品同源**：`run_server.py --no-camera --port 8099` 服务的就是工作区 `src/rvm/web/` 下的文件（自检时 `/static/style.css` 已确认含新规则）。

### 3. 我知道没覆盖什么

- **DELETE 侧没复用这个校验**：`remove_face`（`session.py:695` 一带）仍是自己的 `str(name).strip()`。手改文件塞进 `a/b` 仍能删，塞进 `.` 仍删不掉（路由在 handler 之前就归一化了）。本票 AC 只要求拒绝注册，这条不对称仍在，静态门 FINDINGS-5 也没被本票收掉。
- **分隔符只按 ASCII `/` `\` 判**：全角 `／`、`%2F` 字面量、Unicode 方向控制符（U+202E 等，`ord >= 32`）都不拦；`%` 字符本身可注册（`encodeURIComponent` 会转义，能删）。
- **没测「被拒的名字不在名单响应里」这条读路径**：只断言了「文件不存在」，注册失败时连内存镜像都没进，但测试没有显式 GET 一次。
- **桌面 1440 档没有重测**：新规则只在 `@media (max-width: 900px)` 内，桌面档依赖既有 `.section + .section`（门报告 `minSectionGap=20`）。
- **≤560px 档没单独量**：390 已落在该档内（`--fs-label: 14px` 生效），但没在 560 附近取第二点。
- **文档一致性只钉了 6 条文案与 5 个旧说法**：§8 里其余句子（颜色值、行为描述、`off` 读数）没有自动化对照，靠人读。

### 4. 复现命令

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099
```
然后在 `.scratch/face-recognition/verifier-probes/08-overall-cleanup-viewport.html` 的说明下把它临时拷到 `src/rvm/web/08-vp.html`，用
`chrome --headless=new --window-size=390,844 --virtual-time-budget=12000 --screenshot=<png> "http://127.0.0.1:8099/static/08-vp.html?w=390&h=844&scroll=seam"`
30 秒内可看到 FACE REGISTRY 与 STREAM 之间那条线与图内读数（`box=24px visual=25px line=1px`）。只想看测试：

```
.venv\Scripts\python.exe -m pytest tests/test_face_api.py tests/test_app.py -q -k "could_never_be_deleted or can_be_deleted_again or registry_to_stream_boundary or design_copy_matches"
```

### 5. 我认为最脆的一处

`.rail > .section:first-child`。它绑的是**DOM 首节点**而不是视觉顺序：本票的缺陷正是「视觉顺序里 STREAM 在 registry 之后，但 DOM 里它是第一个」。若以后有人往 `.rail` 前插一个分区、或把 registry 移出 `.rail`，这条规则会去给错的分区画线；而 `box=24` 这个数字仍然成立（`.section + .section` 会接管），`test_the_registry_to_stream_boundary_keeps_its_rule_and_20px` 的正则也仍然匹配——**只有截图能发现**。攻击顺序：先插一个 `.section` 到 `.rail` 首位，再跑定向测试（应该全绿），然后看图（界线会跑到 hint 与新区之间）。

### 6. 票面外的决定

- 决定：改 `src/rvm/server/session.py`，而不是写域列出的 `src/rvm/server/app.py` / 理由：开工包要求「把名字合法性判断收进现有校验函数」，唯一的现有校验函数是 `session.py:83` 的 `validated_face_name`；`app.py` 只做「请求体形状」的 `bad-name`（:387-389），在那里加路径规则等于开第二份判定 / 影响面：写域 5 个文件里 `app.py` 未改，`session.py` 只动一个函数体 + docstring，其余零改动（与 06 号票同类偏差，处置同前例）。
- 决定：DESIGN 顺带改 §4.4 的 loading 段（:127）与 §8「录制中」（:193）/ 理由：静态门 FINDINGS-2 原文点名 `:127`、`:189` 与表格同属一处漂移，只改表格会留下一句现存的假话 / 影响面：只改文档，产品无改动。
- 决定：把「`REMEMBER FACE` 置 disabled」改成「不置灰」写入文档 / 理由：04 号票已明确否决置灰且实现如此（`app.js` 只在请求在途时 disabled），文档是唯一错的一方 / 影响面：新测试只钉文案，不钉这条行为描述；门若要更强约束需另加断言。
- 决定：§8 新增 `models still loading` 与 `loading` 两条字面量，但保留「五态」标题不改「六态」/ 理由：这是状态行真实能出现的第 6 条文案（原文档完全没写），而票面 AS-7 用「五态」指称 §8 / 影响面：§8 现在读起来是「五态表 + 预热补一条」，不是重新定义状态数。
- 决定：真机自检把驱动页临时放进 `src/rvm/web/08-vp.html`（截图后删除，`git status` 无该文件）/ 理由：只有同源 iframe 才能读到真实页面的 `getBoundingClientRect`；前序 04 票与整体动态门用的是同一做法 / 影响面：产品文件未改，探针副本存 `verifier-probes/08-overall-cleanup-viewport.html`。
- 决定：自检读数同时给出两种口径（`box` 与 `visual`）/ 理由：门报告用 `b.top - a.bottom` 量出 16，而设计 §6 的「视觉间隔 24」是 `margin + padding`；只报一种口径容易被读成「24 其实还是 16」/ 影响面：`box=24` 与其余四条界线同值，`visual=25`（多算 1px 边框）也同值。

## Verdicts
