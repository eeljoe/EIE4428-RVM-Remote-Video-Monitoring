# 02 服务端人脸注册 — worker 报告（r2 返工）

票号：02 ｜ 轮次：r2（门打回后的返工） ｜ 代码提交：`3486a02`
门报告：`.scratch/face-recognition/reports/02-r1-verifier.md`（REJECTED，[test]1 [impl]2）
本轮失败探针：`.scratch/face-recognition/verifier-probes/02-mirror-sync-verifier-test.py`（镜像同步杀手测试，已收编）

## 1 做了什么（对着门报告 REMEDIATION 三条）

| # | 标签 | 整改原文 | 本轮改动 |
|---|---|---|---|
| 1 | [test] | 收编杀手测试钉住 `_publish_faces` 的 `replace_known_faces(faces)`；变异描述「该行 → `pass`」；命令跑收编文件 | 三条镜像同步测试收编进 `tests/test_face_api.py:519/538/552`（`registering_session` 夹具在 `:507`），直接驱动 `StreamSession.register_face` / `remove_face`，断言 `face_recognizer.known_faces` 与 `face_store.faces` 同步。变异自证见 §4-M1：删该行 → 3 红；还原 → 3 绿，文件 sha1 前后一致 |
| 2 | [impl] | `face_store._parse` 校验所有向量等长（不等长整体按损坏降级为空名单+告警），或 `_nearest` 对维度失配条目 try/except 跳过 | 两处都做：`face_store.py:185-191` 等长校验（→`load` 的 `corrupt` 告警、空名单）；`recognition.py:347-362` `_nearest` 跳过宽度失配条目。测试 `tests/test_face_store.py:76/95`、`tests/test_recognition.py:261/280`、`tests/test_face_api.py:574`（真 pump 任务存活） |
| 3 | [impl] | `register_face` 增删与发布之间加名单锁，消除并发同名双 201 | `session.py:204` `_faces_lock = threading.RLock()`；`session.py:670` 采样后复检 + 发布同临界区；`session.py:718` `_publish_faces` 自身取锁（删除路径同进同退）。测试 `tests/test_face_api.py:242`（两并发同名 POST → 恰一个 201、一个 409 `name-exists`，文件只有一条） |

未改：AC、判据、spec、`src/rvm/web/*`、`tests/test_app.py`（03 号票并行写域，本工作区里它们的改动不是我的，未暂存）。

## 2 TESTS — 命令与退出码（原文）

票面定向命令：

```
.venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py -q
73 passed in 10.32s
TARGETED_EXIT=0
```

票面全套命令：

```
.venv\Scripts\python.exe -m pytest
560 passed in 25.68s
FULL_EXIT=0
```

（r1 的定向基线是 64 passed；本轮 +9 条新测试 = 73。全套 560 与本机 r1 之后的既有套件规模一致，非本轮引入。）

typecheck：本仓库没有 mypy/ruff 配置，`.venv` 里也没有 `mypy`（`Test-Path .venv/Scripts/mypy.exe` → False；`pyproject.toml`/`requirements*.txt` 无 `mypy|ruff|typecheck` 命中）→ 不适用，非跳过。

覆盖清单：派发消息未附带 `node tools/coverage-tests.mjs` 输出，仓库里也没有该文件（`no tools/coverage-tests.mjs`）→ 无可跑，非跳过。

## 3 每条 AS 的测试对应（本轮新增部分）

| AS | 判定 | 测试（文件:行） |
|---|---|---|
| AS-1（注册闭环、当场见效、流不中断） | r1 已证 + 本轮补镜像同步面 | `tests/test_face_api.py:519`（注册后 recogniser 镜像立刻有该名字与该向量）、`:538`（删除后镜像立刻没有）、`:552`（每次变更后 store 与 recogniser 相等）；r1 的 `:459`/`:481`（status/MJPEG 不中断、同一把推理锁）未动 |
| AS-3（持久化、整体替换） | r1 已证 + 本轮补损坏面 | `tests/test_face_store.py:76`（混维按损坏降级，空名单+告警）、`:95`（同宽正常载入） |
| AS-4（失败与降级不崩服务） | 本轮新增关键一条 | `tests/test_recognition.py:261`（坏条目跳过、好条目仍命中并给出置信度 0.6）、`:280`（全是坏条目 → `(None, 0.0)`）、`tests/test_face_api.py:574`（混维/过时宽度名单下 pump 任务与 `/api/status` 都活着） |
| AS-5（不回归） | 定向 73 + 全套 560 绿 | 见 §2 |

## 4 变异自证（撤修复即红，还原即绿，sha1 对照）

每次变异只改产品文件一行/一块，跑定向选择，然后还原并比对 `Get-FileHash -Algorithm SHA1`。还原哈希与变异前记录逐字一致。

### M1 — 删除 `_publish_faces` 的 `self.face_recognizer.replace_known_faces(faces)`（门 FINDINGS-1 的原变异）

`src/rvm/server/session.py` sha1 变异前 `555933D2FA3EDA05A507E1067246409582FFD6EB`。

变异态（该行 → `pass  # MUTANT: the recogniser mirror is not updated`）：

```
.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k "mirror or store_and_the_recogniser"
>               assert set(session.face_recognizer.known_faces) == set(
E               AssertionError: assert set() == {'Ada'}
E                  Extra items in the right set:
E                  'Ada'
FAILED tests/test_face_api.py::test_registering_updates_the_recogniser_mirror_immediately
FAILED tests/test_face_api.py::test_deleting_updates_the_recogniser_mirror_immediately
FAILED tests/test_face_api.py::test_the_store_and_the_recogniser_agree_after_every_change
EXIT=1
```

还原后：

```
Get-FileHash src/rvm/server/session.py -Algorithm SHA1 -> 555933D2FA3EDA05A507E1067246409582FFD6EB
.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k "mirror or store_and_the_recogniser"
...                                                                      [100%]
EXIT=0
```

sha1 与变异前一致 → 还原是真的还原，不是「改了个近似版本」。

### M2 — 撤掉名单锁与采样后复检（`register_face` 回到未加锁的「检查→发布」）

`session.py` 变异前同一哈希 `555933D2...`。变异态（`with self._faces_lock:` 块换回未加锁的三行）：

```
>       assert sorted([first.status, second.status]) == [201, 409]
E       assert [201, 201] == [201, 409]
E         At index 1 diff: 201 != 409
FAILED tests/test_face_api.py::test_two_registrations_of_one_name_leave_one_entry
EXIT=1
```

还原后：sha1 `555933D2FA3EDA05A507E1067246409582FFD6EB`，`-k "two_registrations"` → `.` / `EXIT=0`。
红态与门的 FINDINGS-3 现象同形（两个 201），说明这条测试打的正是那个竞态。

### M3 — 撤掉 `_nearest` 的宽度守卫（门 FINDINGS-2 的致死路径）

`src/rvm/analysis/recognition.py` sha1 变异前 `879A08E41762DF17F9E9DF9C07610488A52A265C`。

变异态：

```
>           assert not pump.done(), f"the picture pump stopped: {pump.exception()!r}"
E           AssertionError: the picture pump stopped: ValueError('operands could not be broadcast together with shapes (9,) (8,) ')
FAILED tests/test_recognition.py::test_a_registered_vector_of_another_width_is_skipped_rather_than_raised
FAILED tests/test_recognition.py::test_matching_against_only_wrong_width_vectors_reports_nobody
FAILED tests/test_face_api.py::test_a_hand_written_list_of_the_wrong_width_does_not_stop_the_stream
EXIT=1
```

异常文本与门报告 `recognition.py:347` 的推断逐字同形（`(9,) (8,)`：三关键点 → 9 维 vs 手写 8 维），并且死在**真 `run_forever` 任务**上，不是死在一个直接调用里。

还原后：sha1 `879A08E41762DF17F9E9DF9C07610488A52A265C`，同选择 3 passed / `EXIT=0`。

### M4 — 撤掉 `_parse` 的等长校验

`src/rvm/analysis/face_store.py` sha1 变异前 `6128736639C5083E1B2630B72A9E6F103D0ABF50`。

变异态：

```
>       assert faces == {}
E       AssertionError: assert {'Alice': arr...[1., 2., 3.])} == {}
E         Left contains 2 more items:
E         {'Alice': array([1., 2.]), 'Bob': array([1., 2., 3.])}
FAILED tests/test_face_store.py::test_vectors_of_different_lengths_are_treated_as_corrupt
EXIT=1
```

还原后：sha1 `6128736639C5083E1B2630B72A9E6F103D0ABF50`，`tests/test_face_store.py` 14 passed / `EXIT=0`。

### 测试自身的稳定性（诚实记录）

`test_a_hand_written_list_of_the_wrong_width_does_not_stop_the_stream` 的第一版用 4 次「注入帧 + 固定 `sleep(0.06)`」，三次里有一次以 `assert 0 >= 1`（`_frames` 还是 0）失败 —— 是测试在机器忙时等不到第一帧，不是产品问题。改成「注入帧直到 `_frames >= 1`，5 s 上限」后连跑 5 次全绿（`1..5 | ForEach-Object { pytest -k 选择 }` → 5×`EXIT=0`）。红态仍由 `assert not pump.done()` 承担，M3 的复现就是在新写法下跑的。

## 5 真机自检（票面「真机自检：必须」）

新鲜读数落盘：`.scratch/face-recognition/verifier-probes/02-face-registry-backend-selfcheck-r2.md`（原文副本 `_r2-selfcheck-run.txt`）。r1 的自检文件未改动。

命令：

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8123 --known-faces "$env:TEMP\rvm-r2-selfcheck\known_faces.json"
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\02-face-registry-backend-selfcheck-r2.py --base http://127.0.0.1:8123 --list-file "$env:TEMP\rvm-r2-selfcheck\known_faces.json"
```

关键读数（退出码 0）：

```
source=synthetic frames=21
status baseline (idle): n=36 median=3.6ms p95=19.7ms max=27.7ms
status during burst: n=71 median=4.5ms p95=9.9ms max=27.1ms
mjpeg baseline: 27 frames in 2.0s (13.5 fps)
mjpeg during burst: 27 frames in 4.25s (6.4 fps)
registration burst: 329 requests in 4.09s
registration outcomes: 409 no-face x329
list file after burst: exists=False
```

混维名单的启动降级（端口 8124，仓库外临时文件）：

```
GET known -> 200 {"known": []}
GET status -> 200
known-face list C:\Users\joe\AppData\Local\Temp\rvm-r2-wrongwidth\known_faces.json is corrupt (embedding for 'Bob' has 3 values, the others have 2); starting with an empty list
```

同一场景 `frames` 从 15 涨到 41（间隔 2 s）→ 降级后画面泵仍在跑。

端口说明：8099 当时被 03 号票的服务器占用（本机 `Get-NetTCPConnection -LocalPort 8099` 有监听，进程起始时间早于我的启动），所以我换 8123/8124，并在结束时按监听 PID 精确停掉自己的两个进程（`port 8123/8124 open=False`）。我没有动别人的进程。

## 6 我在收尾时的自检（逐条回对）

| 声明 | 回对结果 |
|---|---|
| 镜像同步测试已收编且能杀 M1 | 命中：`git show HEAD -- tests/test_face_api.py` 含 `:519/538/552`；M1 红=3，绿=3 |
| `_parse` 校验等长 | 命中：`face_store.py:185-191` 在 `HEAD` diff 内；M4 红/绿各一次 |
| `_nearest` 跳过宽度失配 | 命中：`recognition.py:347-362`；M3 红态异常文本 `(9,) (8,)` |
| 名单锁消除并发双 201 | 命中：`session.py:204/670/718`；M2 红态 `[201, 201] == [201, 409]` |
| 定向 73 / 全套 560 绿 | 命中：两条命令与退出码见 §2（本轮跑过，非转录） |
| 未改 web 文件与 `tests/test_app.py` | 命中：`git show --stat HEAD` 的 10 个文件里没有它们；工作区里那 4 个文件的改动属 03 号票，未暂存 |
| 真机自检落盘 | 命中：`02-face-registry-backend-selfcheck-r2.md` 已在提交内，读数带命令原文 |

共 7 条命中、0 条落空。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 02 | 交票 | 3486a02 | .scratch/face-recognition/reports/02-r2-worker.md | 三条整改全落：镜像同步测试收编（M1 三红三绿）、等长校验＋宽度守卫（M3 复现泵死）、名单锁（M2 复现双 201），定向 73／全套 560 绿 |
