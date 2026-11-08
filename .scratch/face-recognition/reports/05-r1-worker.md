# 05 — 跨票集成测试与探针收编（r1 worker 报告）

- 票：`.scratch/face-recognition/issues/05-integration-tests.md`（Status 保持 `claimed`，`resolved` 是门的动作）
- 提交：`7671388`（`feat: 05 跨票集成测试与 02 持久化探针收编`），只含 2 个文件：`tests/test_integration_faces.py`（新增 300 行）、票据（实现说明 53 行）
- 认领提交：`fdf03c9`（`chore: 认领 05 集成测试`）
- 写域：`tests/test_integration_faces.py`、`.scratch/face-recognition/verifier-probes/` —— 未越界；`src/` 无改动（`git diff --name-only src/` 为空）
- 尺寸：测试文件 300 行（票面上限 300）；探针目录新增 3 个文件（自检脚本/读数/文档），未改历史探针原文

## 做了什么

`tests/test_integration_faces.py` 三条测试，全部走真实监听端口：

1. `test_a_face_is_registered_recognised_across_a_restart_and_forgotten`（`:138`）——真 `AppRunner` + `TCPSite(127.0.0.1, 0)`，端口断言 >1024；HTTP 注册（201 + `samples: 3`）→ `/api/faces/known` 与 `/api/faces/identities` 出现名字、`confidence == 1.0` → **第二个 app 实例**（同一临时名单）仍能认出 → `DELETE` 200、文件变 `{}`、下一 tick 无人被认出、`/api/status` 仍 200。识别走真代码：只桩了 landmarker 的 `_detect`（库边界），嵌入展平、均值、欧氏距离、阈值、锁、原子写、HTTP 全跑。
2. `test_a_refused_registration_leaves_the_file_alone_and_the_server_working`（`:167`）——重名 409 `name-exists` + 无脸 409 `no-face`，两次都断言**文件字节不变**；随后 `/api/status` 200、名单仍正确、同一实例再注册 201（证明服务还能干活，不是只有错误处理器活着）。
3. `test_real_processes_carry_the_registry_and_survive_a_corrupt_one`（`:258`，`slow`）——真 `run_server.py` 子进程 ×4：`--known-faces` 首次生效 → 重启仍生效 → `DELETE` 200 且磁盘同步 → 第三个进程读到删除后的名单；再起一个进程喂混合宽度名单，降级为 `{"known": []}`、泵仍在出帧、日志含 `corrupt`。

真机自检：`.scratch/face-recognition/verifier-probes/05-integration-selfcheck.md`（脚本 `05-integration-selfcheck.py`，原始读数 `05-integration-selfcheck-run.txt`）——4 个真进程、分析开、真 MediaPipe 模型，`11 passed, 0 failed`，exit 0。变异原始输出：`05-mutation-run.txt`。

## 探针收编清单（逐条判定）

目录里 70 个条目（含 3 个子目录、`__pycache__`、2 个运行残留）。判定：**收编 1 个探针文件**，其余按「已在套件」「属别票写域」「一次性」三类不收编。

| 探针 | 判定 | 依据 |
|---|---|---|
| `02-r2-verifier-persist.py` | **收编**（重写为 `tests/test_integration_faces.py:258`） | 真 `run_server.py` + `--known-faces` + 跨进程重启 + 删除落盘 + 混合宽度降级，套件里原先一条都没有 |
| `02-mirror-sync-verifier-test.py` | 已收编，不重复 | 三条断言逐字在 `tests/test_face_api.py:519,538,552` |
| `02-r2-verifier-pumpguard.py` | 已收编，不重复 | `tests/test_face_api.py:574`（同一接缝：坏宽度名单不得杀死泵） |
| `02-r2-verifier-race.py` | 已收编，不重复 | part_a → `tests/test_face_api.py:242`；part_b → `tests/test_face_store.py:290` |
| `02-face-registry-backend-verifier-probes.py` / `-selfcheck*.py` / `-selfcheck*.md` / `02-r2-verifier.md` | 端点级断言已收编；真进程部分由上条新测试覆盖 | name-exists/no-face/multiple-faces 文件不变 → `test_face_api.py:226,198,212`；404 → `:389`；write-failed → `:398`；models-loading → `:326`；unavailable → `:340`；`corrupt registry did not crash the server` → 本票 `:291-300` |
| `06-face-store-race-verifier.md` + `06-det/detrun-{1..20}.log` | 已收编，不重复 | 两条确定性测试在 `tests/test_face_store.py:290,330`；日志是那两条的 20 轮稳定性读数 |
| `01-*`（selfcheck×2 套 + py） | 不收编 | 设计票产物，无可执行断言属本票接缝 |
| `03-*`（verifier.py/md、2 张 png、measure.json、selfcheck.py/md/json） | 不收编 | 页面可读性数值，断言归 `tests/test_app.py`（03/07 号票写域）；本票写域不含该文件 |
| `04-*`（`04-dom/*.html` 16 个、截图 17 张、`04-verifier-*.md/html`、`04-selfcheck-harness.html`、selfcheck md ×2） | 不收编 | 面板交互与五态文案属 04 号票；其中 stale-write race 是 07 号票的 AC（本会话另有 agent 在做） |
| `04-warmup-probe.py` | 不收编（一次性） | 对固定 `127.0.0.1:8099` 打一发 POST 的手工探针，无断言、无清理、依赖别人的进程 |
| `04-verifier-probe-lines.txt`、`_r2-selfcheck-run.txt`、`_t.err`（0 字节） | 不收编 | 运行残留/输出重定向，不是探针 |

结论：目录**非空**，因此按 AC-3 收编了其中唯一有持久价值且套件未覆盖者；其余不收编的理由都指到了具体文件:行号，不是「看过没问题」。

## TESTS

### 票面命令（原样）

```
.venv\Scripts\python.exe -m pytest tests/test_integration_faces.py -q
```

```
...                                                                      [100%]
```
exit code **0**，3 passed。`--durations`：跨进程那条 4.90 s，另两条 0.48 s / 0.22 s。

```
.venv\Scripts\python.exe -m pytest
```

```
573 passed in 30.20s
```
exit code **0**（本票 +3：570 → 573；无新依赖、无 skip）。570 是同一套件加 `--ignore=tests/test_integration_faces.py` 的点数读数（7×72 + 66 = 570，exit 0）。

### 变异证据（改一处 → 定向测试必须红 → 还原核哈希 → 复绿）

原始输出 `.scratch/face-recognition/verifier-probes/05-mutation-run.txt`。脚本：先 `sha256` 记账，写变异，跑定向测试，再用备份字节原样写回，再核 `sha256`。

| 变异体（产品代码一行） | 目标测试 | 红签名（原文） | 还原 sha256 |
|---|---|---|---|
| M1 `session.py:193` 去掉 `replace_known_faces(self.face_store.load())` | `test_a_face_is_...restart...` | `AssertionError: timed out after 15.0s waiting for 'Alice Ng' to be recognised`（`test_integration_faces.py:82`） | `3011D369…13FCC` 与变异前一致 |
| M2 `session.py:732` 把 `self.face_store.save()` 换成 `pass` | 同上 | `FileNotFoundError: ...\data\known_faces.json`（磁盘断言，第一次生命周期） | 同上 |
| M3 `session.py:655` 把 `if not faces:` 换成 `if False:` | `test_a_refused_registration_...` | `IndexError: list index out of range`（`register_face` 取样处；响应不再是 409） | 同上 |
| M4 `app.py:603` 把 `known_faces=args.known_faces` 换成 `None` | `test_real_processes_...` | `AssertionError: assert {'known': []} == {'known': ['Alice Ng', 'Bob']}`（`test_integration_faces.py:274`） | `6EA20C05…CB926` 与变异前一致 |

四个变异体各自只让**对应**那条测试红，另两条不动；还原后 `git diff --name-only src/` 为空，复跑定向 + 全套均绿（上面的读数即为还原后的复绿读数）。

### AC → 证据（每条 AC 指得出文件:行号）

- AC-1（注册/识别/重启/删除四步，自起停真实服务端）→ `tests/test_integration_faces.py:138`（起停 `:123`，端口断言 `:131`；注册 `:147-151`；识别 `:152`；重启 `:157`；删除 `:159-163`）
- AC-2（一条失败路径 + 服务仍可响应）→ `:167`（`name-exists` `:178-181`；`no-face` `:185-188`；仍响应 `:191`；再注册成功 `:193-196`）
- AC-3（探针收编）→ `:258`（首次 `:274`；重启 `:277`；DELETE+落盘 `:278-282`；第三次进程 `:284`；混合宽度 `:291`；泵 `:293-297`；`corrupt` `:300`）+ 上面的清单
- AC-4（全套绿、无新依赖）→ `573 passed`，新增 import 只有既有依赖与标准库

### 真机自检

`.scratch/face-recognition/verifier-probes/05-integration-selfcheck.md`：**4 个真 `run_server.py` 进程、分析开、真 MediaPipe 模型**，`11 passed, 0 failed`，exit 0。关键读数原文：`features` 四项 `True`、`frames=12`、无脸注册 `status=409 reason=no-face registry_exists=False`、拒绝后 `known={'known': []}`、未知名字 `404 bad-name`、跨三个进程的名单 `['Alice Ng'] → []`、`disk faces={}`。真 landmarker 推理的直接旁证：日志里出现 `landmark_projection_calculator.cc:81` 告警。

### 收尾自检（逐条回对 diff 与文件）

命中 12 条、落空 0 条：

1. 只改 2 个文件 → `git show --stat HEAD` 显示 `tests/test_integration_faces.py`(300) 与票据(53)，命中。
2. `src/` 未动 → `git diff --name-only src/` 空，命中。
3. 未改历史探针 → `git status --short` 中 `01-*`/`02-*`/`03-*`/`04-*`/`06-*` 全是 `??`（从未被本票写），命中。
4. 未碰仓库 `data/known_faces.json` → 该文件不存在（`git status` 无它，`.gitignore` 也拦），命中。
5. 端口全随机高位 → `:131` 断言 `port > 1024`、`:203-207` 用 `bind(0)` 取端口，命中。
6. 每条测试都有「改哪一行会红」 → 四个变异体逐一对应，命中。
7. 期望值来自票面/独立来源 → `EMBEDDING` 是手算的 (0.5,0.5,0.0)×3、`samples: 3` 来自 spec 契约、`{"removed": true, "known": []}` 来自 spec 接口契约，命中。
8. 失败路径不写文件 → `:181`/`:188` 断言 `read_bytes()` 不变，命中。
9. 真机自检有命令 + 读数 + 落盘路径 → 见上，命中。
10. 尺寸上限 → 300 行 ≤ 300，命中。
11. 无新增依赖 → `pyproject.toml` 未改，`git show --stat` 只有 2 个文件，命中。
12. 报告/回执在指定路径 → 本文件 + 下方 `## 回执`，命中。

## BLOCKERS

无。

## 我知道的风险

- `wait_for_identity` 对「镜像没更新」是慢红（15 s 超时），看起来像挂起（见票面实现说明第 5 段）。
- 损坏名单那条咬的是日志子串 `corrupt`，措辞一变就红。
- 子进程用 `--no-analysis`：CLI + 分析开启的真机路径只在自检探针里跑，不在套件里。
- HTTP 端点级并发（注册 vs 删除交错）未测，06 号票报告已把该族列为未覆盖，本票未扩大范围。
- 写本报告时另有一个 agent 在推进 07 号票（HEAD 前一条 `171b9bc` 是它的提交）。本报告的读数取自 `7671388` 工作树；若 07 之后改动 `src/rvm/web/*`、`tests/test_app.py`，全套读数需以门自己的重跑为准。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 05 | 交票 | 7671388 | reports/05-r1-worker.md | 三条集成测试真实起服走通注册/识别/重启/删除与失败路径，收编 02 持久化探针，定向 3 passed、全套 573 passed |