# 06 名单删除与注册的互斥 — worker 报告（r1）

HEAD: `2af49cd`（认领 `f2cebd4` + 实现/测试/实现说明 `2af49cd`）
结论：`remove_face` 的复制—检查—删除—写回现在全程持 `_faces_lock`；两条确定性并发测试在还原旧实现时**必红**（主工作区与干净副本各一次，sha1 对照），新实现 20/20 绿，全套 552 绿。

## 1 做了什么

- **缺陷与修法**：`src/rvm/server/session.py:683-704`。改前 `remove_face` 在锁外 `dict(self.face_store.faces)` 复制、检查存在性，再调 `_publish_faces(faces)`（锁内）写回——注册若在「复制之后、写回之前」提交，其 201 已被应答，却被这份过期副本整体覆盖，store/file/识别器镜像三方一致地丢掉它（02 r2 门 FINDINGS-1 的实证）。改后三件事进同一个 `with self._faces_lock:`（`:696`），`_publish_faces(faces)` 在其内重入同一把 `RLock`。
- **顺手核准的第二路径**：`register_face` 的复制/复检/发布本来就在锁内（`:673-677`），`_publish_faces` 的替换+落盘+镜像+失败回滚也在锁内（`:728`）。`FaceStore.add/remove/replace/save` 自身无锁，但生产写点只有 `_publish_faces` 与 `__init__` 里线程启动前的 `load()`；`grep -n "face_store\."` 全仓只列出这些点，`FaceStore.add/remove` 没有生产调用方（只在测试里直接用）。结论：`replace`/`add` **无**同类丢更新漏洞，本次不动它们。
- **测试**（`tests/test_face_store.py:190-360`）：
  - `ObservedLock`（`:237`）：同一个 `RLock` 外加一个信号量，只在**非持有者即将阻塞**时释放。测试先持锁，等这个信号（真线程等真锁），期间以注册临界区的原样三行（复制→加名→`_publish_faces`）发布 Carol，再放行删除线程。旧实现此时已复制完 → 写回过期副本 → Carol 丢失；新实现删除线程还没复制 → 复制到 Carol → 两条都在。**没有 sleep，没有概率。**
  - `test_a_registration_that_lands_during_a_removal_is_not_lost`（`:290`）：02 门原始形状（register-vs-remove）。
  - `test_two_removals_of_different_names_both_take_effect`（`:330`）：门首攻靶点名的第二路径（remove-vs-remove，旧实现会把已删的 Carol 复活）。
  - 期望值全部手写字面量：注册取样帧亮度 10/20/30 → 平均 20.0；测试插入的 Carol 向量写死 `[7.0]`；文件内容按字面量断言 `{"Alice": [20.0], "Carol": [7.0]}`。
- **越界声明（重要）**：票面「写域」只列 `src/rvm/analysis/face_store.py` 与 `tests/test_face_store.py`，但缺陷、`_faces_lock`、`remove_face` 都在 `src/rvm/server/session.py`；票面锚点 `grep -n "def remove_face" src/rvm/analysis/face_store.py` 在该文件**无命中**（那里只有 store 层 `remove`）。照字面写域做无法修这条缺陷，故按派发指令动 `session.py`，改动仅 `remove_face` 一个方法体 + `_faces_lock` 一处注释（diff +26/−9），未碰任何 web/其它后端文件。若门判越界，处置口径以此段为准。

## 2 TESTS — 命令与退出码（原文）

| # | 命令 | 读数 | 退出码 |
|---|---|---|---|
| T1 | `.venv\Scripts\python.exe -m pytest tests/test_face_store.py -q`（票面定向原文） | `................  [100%]`（repo `addopts` 自带 `-q`，叠加后 `-qq` 不打印汇总行；16 个点） | 0 |
| T2 | `.venv\Scripts\python.exe -m pytest tests/test_face_store.py -o addopts="" -q` | `16 passed in 1.56s` | 0 |
| T3 | `.venv\Scripts\python.exe -m pytest -o addopts="" -q`（主工作区全套） | `562 passed in 45.66s` | 0 |
| T4 | 干净副本（`git worktree` detach 于 `2af49cd`，临时目录）`pytest -o addopts="" -q` | `552 passed in 48.58s` | 0 |
| T5 | 干净副本定向 `pytest tests/test_face_store.py -o addopts="" -q` | `16 passed in 3.00s` | 0 |
| T6 | 新测试连跑 20 轮（`-k "lands_during_a_removal or two_removals_of_different"`） | 20×`..  [100%]`，0 次红 | 0 |

- T3 的 562 = 基线 550 + 03 号票未提交的 `tests/test_app.py` +10 + 本票 2；T4 的 552 = 550 + 本票 2，两者账对得上（T4 才是门在干净副本里能复现的数）。
- 所有 pytest 调用均显式 `timeoutMs=120000`；无一超时，最慢 T4 48.58s。无挂起、无残留进程。

## 3 每条 AS 的测试对应

| AS | 主张 | 测试（文件:行号） |
|---|---|---|
| AS-3 持久化与一致性 | 删除与注册交错后，名单在 store、文件、识别器镜像三方一致且不丢项 | 新增 `tests/test_face_store.py:290`（Carol 仍在，文件字面量 `{"Alice":[20.0],"Carol":[7.0]}`）、`:330`（两条删除都生效，文件只剩 Alice）；既有 `tests/test_face_api.py:538`（删除同步镜像）、`:375`（删除即落盘） |
| AS-4 失败与降级 | 删除不存在的名字仍 404 且不写文件；写失败仍回滚 | 既有 `tests/test_face_api.py:389`（404 且无文件）、`:398`（写失败 500 `write-failed`，名单不变）；锁内 404 分支改后同一断言仍绿（T1/T2 全套） |
| AS-5 不回归 | 定向与全套绿，无新增依赖，既有行为不变 | T2/T4/T5；`git diff HEAD~1 HEAD --stat` 只 3 文件；未改 `pyproject.toml`/依赖 |

## 4 撤修复即红 / 还原即绿（sha1 对照）

**主工作区**（`src/rvm/server/session.py`）：

- 新实现 sha1 = `EF759A7BE7AE8DA23FA5EFCD956370798FCD92A8`（备份到临时目录，备份 sha1 同值）
- 只把 `remove_face` 换回票前六行（锁外复制）→ sha1 = `36C1F089EF1247D29DEC003A4C673364CC2227BF`：

```
>       assert session.known_face_names() == ["Alice"]
E       AssertionError: assert ['Alice', 'Carol'] == ['Alice']
E         Left contains one more item: 'Carol'
tests\test_face_store.py:356: AssertionError
FAILED tests/test_face_store.py::test_a_registration_that_lands_during_a_removal_is_not_lost
FAILED tests/test_face_store.py::test_two_removals_of_different_names_both_take_effect
2 failed, 14 passed in 6.62s
```

（另一条同轮红灯，即 02 门的原始现象：）

```
>       assert session.known_face_names() == ["Alice", "Carol"]
E       AssertionError: assert ['Alice'] == ['Alice', 'Carol']
E         Right contains one more item: 'Carol'
tests\test_face_store.py:325: AssertionError
```

- 从备份拷回 → sha1 = `EF759A7BE7AE8DA23FA5EFCD956370798FCD92A8`（**与撤前逐字节相同**）→ `16 passed in 1.56s`，退出码 0。

**干净副本**（`git worktree` detach 于 `2af49cd`，同一套操作）：

```
clean-sha1=EF759A7BE7AE8DA23FA5EFCD956370798FCD92A8   → 16 passed in 3.00s
reverted-sha1=36C1F089EF1247D29DEC003A4C673364CC2227BF → 2 failed, 14 passed in 7.23s
restored-sha1=EF759A7BE7AE8DA23FA5EFCD956370798FCD92A8 → 16 passed in 1.31s
```

即门的「亲手还原旧实现验证测试咬得住」在干净副本里已复现一次，sha1 与主工作区一致（两处都是 LF 检出字节；注意 02 r2 报告 §FINDINGS-3 提到的 CRLF 口径差异，这里两侧同口径）。

**为什么这不是 sleep 碰运气**：卡的信号来自 `ObservedLock.__enter__`——只有当某线程**不持有**该锁、即将阻塞时才 `waiting.release()`。旧实现的坏交错唯一可观测点正是「复制已在锁入口之前完成」；新实现里删除线程根本到不了复制就被拦住。测试里的 `timeout=5` 只用作死锁保险（真死锁时报错而非挂死），不参与制造交错；T6 连跑 20 轮零抖动也说明顺序由锁决定而非调度竞态。

## 5 我知道没覆盖什么 / UNVERIFIED

- **真 HTTP 层并发未重跑**：02 r2 门 Part B 是经 `POST`/`DELETE` 打出来的；本轮证据是进程内真线程真锁（`StreamSession.remove_face`/`register_face` 直调），不是 aiohttp 端到端。功能一致，但「端点层」这一步本轮没有新鲜读数。
- **覆盖清单脚本在本仓不存在**：`tools/coverage-tests.mjs` 不存在（`tools/` 下只有 `benchmark.py`、`build_report.py`、`make_zip.py` 等），派发消息里的覆盖读数无法亲跑，标 UNVERIFIED（按派发读数为「两侧均无覆盖」）。
- **没有 typecheck 可跑**：本仓 `pyproject.toml` 无 mypy/ruff/black 配置，`mypy.ini`/`ruff.toml` 不存在，因此本轮只有 pytest 一套读数（报告不声称跑过 typecheck）。
- **未测 remove 与 `FaceStore.load()` 并发**：`load()` 只在 `__init__` 里线程启动前调用，产品没有第二条写路径。
- **未测识别器镜像读方竞争**：`replace_known_faces` 整体替换、读方walk旧映射；既有 02 票测试覆盖，本票未动。
- **未覆盖「注册取样与分析 tick 并发」**：测试直接填 `_recent_frames`（这三帧就是要平均的内容），不走 `run_once`/Haar，故 `_inference_lock` 的互斥不在本票证据里（02 票的 `tests/test_face_api.py:481` 覆盖）。
- **锁换成普通 `Lock` 会自死锁**：这条测试覆盖不到（表现为挂起而非红），见实现说明 §5。
- **非本票的工作区改动**：`src/rvm/web/*`、`tests/test_app.py`（03 号票未提交改动）与 `.scratch/face-recognition/verifier-probes/` 下若干文件的新增/删除，**不是我做的**，我既未编辑也未暂存；我的 commit 只含票面 3 个文件（`git show --stat HEAD` 亲核）。提交前这些探针文件曾存在、提交后出现删除，属于并发会话的工作痕迹，本报告只做记录。

## 6 收尾自检（逐条回对 diff 与文件）

| # | 声明 | 回对结果 |
|---|---|---|
| 1 | `remove_face` 的 `with self._faces_lock:` 覆盖复制/检查/del/publish | 命中：`src/rvm/server/session.py:696-702` |
| 2 | `register_face` 的复制仍在锁内 | 命中：`:673-677` 未改 |
| 3 | `_publish_faces` 本体未改（只有注释被删/补） | 命中：`git diff HEAD~1 HEAD -- src/rvm/server/session.py` 无该函数逻辑行变化 |
| 4 | 两条新测试在旧实现上必红 | 命中：主工作区与干净副本各一次，`2 failed, 14 passed` |
| 5 | 新实现连跑 20 轮全绿 | 命中：T6，20/20 |
| 6 | 全套干净副本 552 绿 | 命中：T4，`552 passed in 48.58s` |
| 7 | 无新增依赖 | 命中：diff 3 文件，不含 `pyproject.toml`/`requirements.txt` |
| 8 | 提交只含本票 3 文件、精确暂存 | 命中：`git show --stat HEAD` = 票文件 + `session.py` + `test_face_store.py`；`git diff --cached` 空 |
| 9 | 未触碰 web/其它后端文件 | 命中：我的两个 commit 文件清单（`f2cebd4` 1 文件、`2af49cd` 3 文件） |
| 10 | 交票后票仍 `claimed`（`resolved` 是门的动作） | 命中：票面 `**Status:** claimed` |
| 11 | 真机自检 | 票面写「不需要」，故未做、未占位 |
| 12 | 实现说明六段已写入票面 | 命中：`.scratch/face-recognition/issues/06-face-store-race.md` 的 `## 实现说明`（在 `## Verdicts` 之前） |

合计：**12 条命中、0 条落空**。

## COMMITS

- `2af49cd` fix: 06 名单删除的读改写入 `_faces_lock`，补确定性并发测试（票文件 + `src/rvm/server/session.py` + `tests/test_face_store.py`）

## IMPLEMENTED

- **AC1** [AS-3, AS-4]：`remove_face` 读—改—写全程持 `_faces_lock` → `src/rvm/server/session.py:683-704`（`with` 在 `:696`），证据 `tests/test_face_store.py:290`、`:330`。
- **AC2** [AS-3, AS-4]：新增确定性并发测试，旧实现红、新实现绿，非 sleep → `tests/test_face_store.py:237`（`ObservedLock`）、`:290`、`:330`；红/绿与 sha1 见本报告 §4。
- **AC3** [AS-5]：定向 16 绿、干净副本全套 552 绿、主工作区全套 562 绿，其它行为不变 → 本报告 §2、§3。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 06 | 交票 | 2af49cd | .scratch/face-recognition/reports/06-r1-worker.md | `remove_face` 复制—写回入同一把 `_faces_lock`；两条确定性测试在还原旧实现时必红（sha1 对照，干净副本复现），新实现 20/20 绿、全套 552 绿 |
