# 04 注册控件与文档 — r1 worker 报告

- 票面：`.scratch/face-recognition/issues/04-face-registry-ui.md`（AC 未改）
- 状态：claimed（`resolved` 是门的动作）
- 提交：认领 `71ef5f1`，交付见文末 `## 回执`
- 契约：`.scratch/face-recognition/spec.md`「接口契约」（02 号票已实现，端点已存在）
- 规范：`docs/DESIGN-dashboard.md`；参照图 `.scratch/face-recognition/design/v2/mock.html`
- 真机证据：`.scratch/face-recognition/verifier-probes/04-face-registry-ui-selfcheck.md`

## 交付了什么

FACE REGISTRY 分区接线（分区外壳与四个 id 由 03 号票建好，本票不改结构、不改
`style.css`）：

- 打开页面即 `GET /api/faces/known` 渲染名单；空名单显示 `No names saved yet`。
- `REMEMBER FACE` → `POST /api/faces/known`，201 时状态行绿字
  `Saved as <name>, <samples> frames averaged`、清空输入框、按响应里的 `known` 重绘名单、
  再 `GET /api/faces/identities` 立刻刷 Face IDs 行。
- 失败按 `reason` 上一条文案：`no-face` → 红 `no face in frame, hold still`；
  `multiple-faces` → 红 `more than one face in frame`；`name-exists` → 琥珀
  `<name> is already saved`；`analysis-disabled` → 灰 `analysis is off`；
  `models-loading` → 灰 `models still loading`；其余 reason 回落到服务端 `error` 原文。
- 名单每行 = 名字（`textContent`）+ `×`（`dataset.name` 绑定、`Delete <name>` 无障碍名），
  点 `×` → `DELETE /api/faces/known/<encodeURIComponent(name)>`，成功后名单与身份行立刻刷新、
  状态行清空。整块 **没有一处 innerHTML**。
- Face IDs 改为 `name · 0.82`（最多三条），空名单无人脸时 `0 faces, none known`，
  名单非空且无人脸时 `no face`，`no-known-faces` 状态按 `seen` 回显
  `N faces, none known`；阈值以下的脸在服务端就不在 `identities` 里，前端不重算阈值。

文档与报告生成器同步：`README.md`（What it does 新行、`### Face registration` 段、
三个 API 行、Known limitations 补「只存名字与嵌入、不存照片」）；`docs/FEATURES.md`
（三个端点、`## Face registration` 段含失败原因表与文件形状、Limitations 改写）；
`tools/build_report.py` 的 `SPECIAL_FEATURES` 与 `UI_DESIGN` 各加一段；`tests/test_report.py`
新增三条测试钉住这些文案。

规模：6 个文件、+397/−10 行（票面写域 8 个文件内，行数如预计超 300）。

## AC → 证据

| AC | 证据 |
|---|---|
| 独立分区：名字输入、记住按钮、状态行、名单与删除 | `index.html:111-122`（03 建的结构，本票未动）+ `app.js:565`（`rememberFace`）、`app.js:586`（`forgetFace`）、`app.js:493`（`renderNames`）；测试 `tests/test_app.py:641`、`:676`、`:690`；截图 `04-selfcheck-3b-list.png`（两行名字 + 行尾 `×`） |
| Face IDs 显示「名字 · 相似度」 | `app.js:71-93`；测试 `tests/test_app.py:731`（钉 `item.name + " · " + Number(item.confidence).toFixed(2)`，并钉身份行只读 `result.identities`、不读名单） |
| 空名单且无人脸 → `N faces, none known` | `app.js:71-93`；截图 `04-selfcheck-1-empty.png` 实测 `0 faces, none known`（真遥测，名单 `{"known": []}`） |
| 相似度低于阈值不显示名字 | 阈值在服务端；`04-selfcheck-3b-list.png` 实测「名单有两个名字、画面无人脸」时 Face IDs 是 `no face`，没有出现任何名字；测试 `tests/test_app.py:731` 钉住身份行不以名单为数据源 |
| 五态文案 | `app.js:480-485` + `app.js:565`；测试 `tests/test_app.py:703` 钉五个 reason 与六段文案；截图 2（真 409 无脸）、3（真 409 重名）、5（真 503 分析关闭）、6（桩 201 成功）、7（桩 409 多脸）；`models-loading` 见下 |
| 注册成功/删除后立刻刷新、名字转义不拼 HTML | `app.js:493`（`createElement` + `textContent` + `dataset.name`）、`:565-579`、`:586-596`；测试 `tests/test_app.py:690`；截图 4（真 DELETE 后只剩一个名字，服务端 `{"known": ["Marcus Foo"]}`）、6（桩 201 后名单立刻两个名字） |
| README / FEATURES / build_report 同步注册能力与「不存照片、名单不进仓库」 | `README.md:56`（能力行）、`### Face registration`（`data/known_faces.json`、只存名字与嵌入、git-ignore、`tools/make_zip.py` 白名单不含 `data/`、预热/关闭时按钮行为）、API 表三行、Known limitations；`docs/FEATURES.md` 端点表三行、`## Face registration`、Limitations 第一条；`tools/build_report.py` 的 `SPECIAL_FEATURES` 末段与 `UI_DESIGN` 末段；测试 `tests/test_report.py:251`、`:258`、`:268` |
| 静态测试钉新 DOM ID 与无远程资源；全套通过 | `tests/test_app.py:607`（既有 48 个 id 清单仍全在）、`:641`（registry 结构）、`:96`（新增 app.js 里也不许出现 `http(s)://` 资源）；全套 **569 passed, exit 0** |

## TESTS

票面两条命令，原样：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q
..................................................................       [100%]
exit=-1073740791
```

66 条全过，但进程在 **全部通过之后** 以 `0xC0000409` 退出。这不是本票的失败，是这台机器
上 OpenCV 4.14 的退出期 abort（`test_app.py` 的 fixture 让 cv2 在采集线程里跑，进程退出时
`clReleaseDevice` 失败）。取证：把同一棵树在 **认领提交 `71ef5f1` 的干净 worktree** 里跑单条
测试，退出码一致：

```
$ git worktree add --detach $env:TEMP\rvm-head-04 71ef5f1
$ cd $env:TEMP\rvm-head-04 ; ...\.venv\Scripts\python.exe -m pytest tests/test_app.py -q -k test_index_page_is_served
.                                                                        [100%]
pristine_exit=-1073740791
```

即：与本票改动无关，且与选中的测试模块有关。把 02 号票那个设了
`cv2.ocl.setUseOpenCL(False)` 的模块一起选上，同样的用例退出码就是 0：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py tests/test_face_api.py -q
........................................................................ [ 75%]
.......................                                                  [100%]
exit=0
```

全套（含所有模块，`test_face_api.py` 的 OpenCL 开关生效）：

```
$ .venv\Scripts\python.exe -m pytest
569 passed in 26.68s
exit=0
```

`node --check src/rvm/web/app.js` → `exit=0`（脚本语法）。

### 先红：写测试、后实现

新加的静态测试在接线前跑（`app.js` 还是 03 的版本）：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "registry or face_ids or remote_frontend"
FAILED tests/test_app.py::test_the_registry_calls_the_three_contract_endpoints
FAILED tests/test_app.py::test_the_registry_writes_a_name_as_text_never_as_markup
FAILED tests/test_app.py::test_the_registry_status_line_carries_the_five_outcomes
FAILED tests/test_app.py::test_face_ids_print_the_name_with_its_similarity
4 failed
```

实现后同一组：全绿（见上）。

### 撤修复即红（转义这条主张）

把 `app.js` 的 `who.textContent = name;` 改成 `who.innerHTML = name;`（其余不动）：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "registry_writes_a_name"
E       assert 'innerHTML' not in ' ----------...'
E         'innerHTML' is contained here:
E                 who.innerHTML = name;
FAILED tests/test_app.py::test_the_registry_writes_a_name_as_text_never_as_markup
exit=1
```

还原后：

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "registry_writes_a_name"
.                                                                        [100%]
$ node --check src/rvm/web/app.js ; echo $LASTEXITCODE
0
```

（还原后 `app.js` SHA256 `1EB710AC…B0CAE`，与撤销前一致；之后的改动只是把一段注释挪到
`rememberFace` 上方，语义无关。）

### 真机自检（票面要求「必须」）

证据文件：`.scratch/face-recognition/verifier-probes/04-face-registry-ui-selfcheck.md`
（含命令原文、哪一张是桩、读数）。

图片（同目录）：

- `04-selfcheck-1-empty.png` — 真：空名单 + `0 faces, none known`
- `04-selfcheck-2-noface.png` — 真 409：`no face in frame, hold still`
- `04-selfcheck-3-exists.png` / `04-selfcheck-3b-list.png` — 真 409 重名 + 名单两行带 `×`
- `04-selfcheck-4-deleted.png` — 真 DELETE：行消失、服务端名单同步
- `04-selfcheck-5-analysis-off.png` — 真 503：`analysis is off`，Face IDs/Expressions/Gestures `off`
- `04-selfcheck-6-saved-stub.png` — **桩 201**：`Saved as Ada Lovelace, 3 frames averaged` + 名单刷新
- `04-selfcheck-7-multiple-stub.png` — **桩 409**：`more than one face in frame`

桩的部分写清了：合成场景没有真人脸，成功与多脸两个响应体由同源 iframe 驱动页替换
（`04-selfcheck-harness.html`，临时放进 `src/rvm/web/` 供服务器以 `/static/__selfcheck04.html`
提供，截图后已删除，`git status` 里没有它）。其余五张都是真后端：请求打到真实的
8099/8098，状态行文字来自真实的 409/503 响应体。

`models-loading` 没截到图（多次开新窗口后 Edge 只给空白页）。用真实 HTTP 探针补读数：

```
$ .venv\Scripts\python.exe %TEMP%\rvm04\warmprobe.py      # 服务器启动瞬间开始轮询 POST
2.61s status=503 body={"error": "the face models are still loading", "reason": "models-loading"}
```

## 收尾自检

逐条回对 diff 与文件，**9 条命中、0 条落空**：

1. 改动 6 个文件、+397/−10 —— `git diff --stat` 一致。
2. 未碰服务端代码 —— `git status` 只有写域内 6 个文件 + `.scratch` 证据文件。
3. 仓库内没有 `data/known_faces.json` —— 自检全程 `--known-faces` 指向 `%TEMP%\rvm04\`。
4. 驱动页没有留在产品目录 —— `src/rvm/web/` 下无 `__selfcheck04*.html`。
5. 全套 569 passed、exit 0 —— 上文原文。
6. 新增静态测试 4 条、报告测试 3 条 —— `tests/test_app.py:676/690/703/731`、
   `tests/test_report.py:251/258/268`。
7. 五态文案逐字在 `app.js:480-485` —— 与票面 AC 字面量一致。
8. 名字只走 `textContent` / `dataset.name`，registry 块内无 `innerHTML` —— 测试钉住，
   且撤修复会红。
9. 8 张截图与自检文档落盘在 `verifier-probes/` —— 上文列表。

## COMMITS

- `71ef5f1` chore: 认领 04 注册控件（只暂存票文件）
- `44fb4c9` feat: 04 注册控件接线与五态文案、文档同步（`src/rvm/web/app.js`、
  `tests/test_app.py`、`tests/test_report.py`、`README.md`、`docs/FEATURES.md`、
  `tools/build_report.py`、票文件、本报告、`verifier-probes/04-*`）

## IMPLEMENTED

- AC1 分区与控件接线 — 完成
- AC2 Face IDs 名字·相似度 / 空名单计数 / 阈值以下无名 — 完成
- AC3 五态文案 — 完成（`models-loading` 仅后端读数 + 静态测试，UI 未截图，见 §3 UNVERIFIED）
- AC4 注册/删除后立即刷新、名字转义 — 完成
- AC5 README / FEATURES / build_report 同步 — 完成
- AC6 静态测试与全套通过 — 完成（票面定向命令的进程退出码是既有 OpenCV 退出期 abort，
  已在 TESTS 段取证）

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 04 | 交票 | 44fb4c9 | reports/04-r1-worker.md | 注册控件接线 + 五态文案 + 文档同步，全套 569 passed |
