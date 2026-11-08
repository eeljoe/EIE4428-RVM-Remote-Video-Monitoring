# 08 r1 — 整体门收口（移动端间隙 / 名字校验 / 设计文案）

- 票：`.scratch/face-recognition/issues/08-overall-cleanup.md`（`claimed`）
- 基线：`6abf9cc`；本轮实现提交：`cbca0dc`
- 写域：`src/rvm/web/style.css`、`src/rvm/server/app.py`、`docs/DESIGN-dashboard.md`、`tests/test_face_api.py`、`tests/test_app.py`
  （实际改动 `src/rvm/server/session.py` 替代 `app.py`，理由见票面 `## 实现说明` 第 6 段与本文「越界声明」）
- 规模：5 文件 +154/−10（票面上限 ≤300 行 / 5 文件）

## 做了什么

1. **AS-6**：`@media (max-width: 900px)` 内新增 `.rail > .section:first-child`，给视觉上紧跟在 FACE REGISTRY 之后的 STREAM 补上与同档其它界线逐字相同的 `margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--line)`（`src/rvm/web/style.css:298-304`）。
2. **AS-4**：把「存进去就再也删不掉」的名字判定收进既有 `validated_face_name`（`src/rvm/server/session.py:83-110`）：拒绝 `.`、`..`、含 `/` 或 `\`、控制字符（`< 32` 或 `== 127`）与纯空白，一律 400 `bad-name`、零写入；中文、空格、单引号、重音与首尾空格仍照收（trim 后入库）。
3. **AS-7**：`docs/DESIGN-dashboard.md` §8（:173-195）改成上屏逐字文案，并同步修 §4.4 的 `loading` 段（:127）与「录制中」一行（:193）。

## COMMITS

| 哈希 | 内容 |
|---|---|
| `7de90f5` | `chore: 认领 08 整体门收口`（只暂存票文件） |
| `cbca0dc` | `fix: 08 收口移动端分隔线、不可删名字与 DESIGN 五态文案`（5 文件 + 票面 `## 实现说明`） |
| 本报告与探针 | 随后一条 `chore:` 提交（只暂存 `.scratch/face-recognition/reports/08-r1-worker.md` 与本票探针文件） |

## IMPLEMENTED

- **[AS-6][impl]** `src/rvm/web/style.css:298-304` — 新规则与 `.section + .section` 同值；真机 390×844 读数 `SEAM box=24px visual=25px line=1px solid rgb(37,44,48)`，其余四条界线 `24/25/1`，五条完全一致。
- **[AS-6][test]** `tests/test_app.py:505` `test_the_registry_to_stream_boundary_keeps_its_rule_and_20px` — margin+padding ≥ 20 且规则里带 `border-top: 1px solid var(--line)`。
- **[AS-4][impl]** `src/rvm/server/session.py:83-110` — 新增点段与路径分隔符两条拒绝、控制字符扩到 DEL；消息保持「一句话、不含路径/参数」。
- **[AS-4][test]** `tests/test_face_api.py:319`（10 个不可寻址名字，各 400 `bad-name` + 文件不存在）与 `tests/test_face_api.py:338`（5 个合法名字各 201、落盘 trim 后原名、再 DELETE 成功）。
- **[AS-7][impl]** `docs/DESIGN-dashboard.md:173-195` — 五态表 + 非错误态逐字对齐 `app.js`；「置 disabled」条款按 04 票的实际行为改写。
- **[AS-7][test]** `tests/test_app.py:524` `test_the_design_copy_matches_the_served_status_line_verbatim` — 6 条文案必须同时出现在 `app.js` 与文档；`Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING` 五条旧说法不得再出现。
- **[AS-5][test]** 未改 `app.js`、`recognition.py`、`face_store.py`、`index.html`；定向 89 passed / 全套 590 passed，均 exit 0。

## TESTS

### 票面给的命令（原样）

```
.venv\Scripts\python.exe -m pytest tests/test_face_api.py tests/test_app.py -q
........................................................................ [ 80%]
.................                                                        [100%]
TARGETED_EXIT=0

.venv\Scripts\python.exe -m pytest
..............                                                           [100%]
590 passed in 22.80s
FULL_EXIT=0
```

计数用的同一条命令加 `-o addopts="--strict-markers"`（`pyproject.toml` 的 `addopts = "-q"` 与本行的 `-q` 叠成 `-qq`，摘要行会被吞掉）：定向 `89 passed`、全套 `590 passed`。改前全套 573，新增 17 条 = 10 + 5 + 2。

### 变异证据（撤修复即红 → 还原核哈希 → 复绿）

**M1 — 撤掉名字守卫（`session.py` 删掉点段/分隔符两条 + DEL 检查）**

```
FAILED tests/test_face_api.py::test_a_name_that_could_never_be_deleted_is_refused_before_it_is_stored[.]
FAILED ...[:/etc/passwd]  FAILED ...[del\x7fchar]   （共 8 条）
8 failed, 7 passed, 29 deselected in 3.09s
RESTORED_HASH_MATCH=True
15 passed, 29 deselected in 1.66s
EXIT=0
```

（`tab\there` 与 `nul\u0000byte` 两条在改前就被 `ord < 32` 拦下，属既有行为，不算本票杀伤力。）

**M2 — 删掉 `style.css` 的 7 行新规则**

```
E       AssertionError: STREAM has no boundary rule once the registry leads
tests\test_app.py:517: AssertionError
FAILED tests/test_app.py::test_the_registry_to_stream_boundary_keeps_its_rule_and_20px
1 failed, 88 deselected in 1.01s
RED_EXIT=1
RESTORED_HASH_MATCH=True
1 passed, 88 deselected in 0.84s
GREEN_EXIT=0
```

**M3 — 把 `Two faces in frame, show one` 写回 DESIGN §8**

```
E           AssertionError: DESIGN-dashboard.md does not quote 'more than one face in frame'
tests\test_app.py:549: AssertionError
FAILED tests/test_app.py::test_the_design_copy_matches_the_served_status_line_verbatim
1 failed, 88 deselected in 0.87s
RED_EXIT=1
RESTORED_HASH_MATCH=True
1 passed, 88 deselected in 0.94s
GREEN_EXIT=0
```

三次变异都先 `Copy-Item` 备份、改后跑定向、再还原并比对 sha256（三次均 `RESTORED_HASH_MATCH=True`）。

### 真机自检（票面写「必须」）

- 命令：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099`；启动横幅 `RVM serving on http://0.0.0.0:8099/  (320x240 @ 15 fps, source: synthetic)`。
- 证据文件（票面占位）：`.scratch/face-recognition/verifier-probes/08-overall-cleanup-selfcheck.md`
- 读数（390×844，逐字）：`SEAM registry.bottom=845 stream.top=869` / `SEAM box=24px visual=25px line=1px solid rgb(37, 44, 48)` / `ALL box/visual/line: Stream=24/25/1  Transport=24/25/1  Analysis=24/25/1  Clips=24/25/1`
- 同一探针撤掉新规则后：`SEAM box=16px visual=0px line=0px none`，其余界线仍是 `24/25/1` —— 与整体动态门 FINDINGS 的读数（16px、无分隔线）逐字吻合。
- 截图（亲眼看图，非代码推断）：
  - `.scratch/face-recognition/verifier-probes/08-overall-cleanup-mobile-390x844-seam.png`（390×844）：`No names saved yet` 与 `STREAM` 之间一条与页面同宽的分隔线，底部黄条印着上面那三行读数。
  - `.scratch/face-recognition/verifier-probes/08-overall-cleanup-mobile-390x844-top.png`（390×844）：顶栏 → 画面（两角 OSD）→ 七项控件与提示行首屏全在 → FACE REGISTRY 开头；无横向溢出。
- 探针：`08-overall-cleanup-viewport.html`（存档副本），自检期间临时拷进 `src/rvm/web/08-vp.html` 以便同源，取完截图已删除（`git status` 无该文件）。

### 覆盖测试清单

`node tools/coverage-tests.mjs` 在本仓**不存在**（`Test-Path tools/coverage-tests.mjs` = False，直接跑报 `MODULE_NOT_FOUND`，exit 1；全盘 glob `**/coverage-tests*` 无命中）。派发消息给的读数按原样采用：`src/rvm/web/style.css`、`src/rvm/server/app.py`、`docs/DESIGN-dashboard.md`、`tests/test_face_api.py`、`tests/test_app.py` 均为「无覆盖」，因此没有既有覆盖行被我改红；其中 `app.py` 本票未改。

## 越界声明（与票面写域不一致之处）

- 改了 `src/rvm/server/session.py`（不在写域），**没有**改写域里的 `src/rvm/server/app.py`。理由：开工包要求「把名字合法性判断收进现有校验函数」，唯一的现有校验函数是 `session.py:83` 的 `validated_face_name`；`app.py:387-389` 只判「请求体不是 JSON / 不是对象」。改动范围是一个函数体 + docstring，文件其它 20 行未动（`git show cbca0dc -- src/rvm/server/session.py` 可核）。与 06 号票的同类偏差同处置。文件数仍是 5。

## 收尾自检

逐条声明回对 diff 与文件，**13 条命中、0 条落空**：

1. `style.css` 新规则在 `@media (max-width: 900px)` 内 — 命中（:285 起，:302 为规则行）
2. 规则值与同档 `.section + .section` 同值（8 / 16 / 1px `var(--line)`）— 命中（:297 与 :302-304）
3. 桌面档未被影响 — 命中（规则只在 max-width:900px 块内）
4. `session.py` 拒绝 `.`/`..` — 命中（:104-105）
5. 拒绝 `/` 与 `\` — 命中（:106-109）
6. 拒绝控制字符（含 DEL）— 命中（:102）
7. 纯空白仍拒 — 命中（:96-97，改前既有）
8. 失败路径零写入 — 命中（测试 `assert not list_file(tmp_path).exists()`）
9. 合法名字不误伤 — 命中（`test_a_name_that_can_be_deleted_again_is_still_accepted` 5 参数）
10. DESIGN §8 五条文案与 `app.js` 逐字一致 — 命中（:179-185 对 `app.js:481-484,565,591`）
11. 旧说法不再出现在文档 — 命中（:524 测试的 stale 名单）
12. 票面 `## 实现说明` 六段在同一次提交里 — 命中（`cbca0dc` 含票文件 +49 行）
13. 工作区干净（仅门留下的 untracked 探针与 `07-r1-verifier.md` 的 M，不在本票范围）— 命中

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 08 | 交票 | cbca0dc | reports/08-r1-worker.md | 三处收口各有测试与 390 真机读数，定向 89 / 全套 590 绿 |
