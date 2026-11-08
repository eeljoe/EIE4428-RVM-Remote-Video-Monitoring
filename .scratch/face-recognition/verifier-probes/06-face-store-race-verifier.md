# 06-face-store-race — verifier 探针（r1）

验收副本：`C:\Users\joe\AppData\Local\Temp\verify-06-r1-2af49cd`（gate-kit worktree，detach `2af49cd`，已 cleanup）。
Python：主仓 `.venv\Scripts\python.exe`；`pyproject.toml` 的 `pythonpath=["src"]` 使 pytest 解析副本自身的 `src/`（变异转红实证了这一点——副本文件被改才变红）。
账本：`.scratch/face-recognition/ledger/06-r1.jsonl`，条目 06-r1-001…008。

## 变异协议（亲跑）

| 步 | 操作 | session.py sha1 | 结果 | 账本 |
|---|---|---|---|---|
| 基线 | worktree @2af49cd | `EF759A7BE7AE8DA23FA5EFCD956370798FCD92A8` | `16 passed` | 001/002 |
| M1 全还原 | `remove_face` 换回票前六行（复制/检查/del/publish 全在锁外） | `36C1F089EF1247D29DEC003A4C673364CC2227BF`（与 worker 自证值逐字节一致） | `2 failed, 14 passed` | 003 |
| M2 自选 | 只把 `faces = dict(self.face_store.faces)` 移出 `with`（检查/del/publish 留在锁内） | `7f1a3f4c…`(sha256 前缀) | `2 failed, 14 passed` | 004 |
| 还原 | `git checkout -- src/rvm/server/session.py` | `EF759A7B…`（与变异前逐字节一致） | `16 passed` | 005 |

M1 与 M2 的红灯签名逐字为：

- `test_a_registration_that_lands_during_a_removal_is_not_lost`：`assert ['Alice'] == ['Alice', 'Carol']`（已 201 的 Carol 被过期副本抹掉——02 r2 FINDINGS-1 的原始现象）
- `test_two_removals_of_different_names_both_take_effect`：`assert ['Alice', 'Carol'] == ['Alice']`（已删的 Carol 复活）

M2 证明测试咬的是「复制那一行在锁内还是锁外」这个**边界本身**，不是只咬整段回退。

## 确定性

- 测试无 `sleep`（grep 全文件 0 命中，仅 docstring 提到「sleep 是猜」）；`waiting.acquire(timeout=5)` 与 `join(timeout=5)` 是死锁保险，不制造交错。
- `ObservedLock`（test_face_store.py:237）是同一个 `RLock` 加信号量：非持有者即将阻塞时 `waiting.release()`。测试持锁→等信号（真线程等真锁）→以注册临界区原样三行发布 Carol→放行。顺序由锁决定，与调度无关。
- 连跑 20 轮 `-k "lands_during_a_removal or two_removals_of_different"`：**20/20 绿，0 红**；日志存 `verifier-probes/06-det/detrun-{1..20}.log`（账本 008：20 份含 `2 passed, 14 deselected`、0 份含 `failed`）。

## 其它路径同类漏洞审计

`grep` 全 `src/`：`face_store` 的写点只有 `register_face`(:673 锁内)、`remove_face`(:696 锁内)、`_publish_faces`(:728 锁内)、`__init__` 的 `load()`(:193，线程启动前)。`FaceStore.add/remove` 无生产调用方（仅测试直调）。`faces` 属性全仓均为读（`in`/`dict()`/`.get`/迭代），无原地改；所有写入是整体替换，锁外读者见到的是一致快照。`known_face_names()`、GET `/api/faces/known`（app.py:378）为只读，安全。

## 已知未覆盖族（不构成判据违反）

- `RLock`→`Lock` 换锁变异：`register_face` 在 `with` 内重入 `_publish_faces` 会自死锁；两新测试在 `session.register_face("Alice")` 装机步即挂起（该直调无 timeout），表现为套件挂起而非干净红——属既有设计约束（02 r2 决策：必须 RLock），CI 超时兜底。FYI。
- `_publish_faces` 若改用第二把锁：本测试形状不可见（remover 仍被 `_faces_lock` 拦住）。当前代码 :728 确为同一把 `self._faces_lock`；若未来分锁丢更新会无声回归。FYI。
- 端点级（aiohttp→`to_thread`）并发本轮未端到端重跑；测试直调的就是端点调用的同一对方法，锁纪律相同。

## 命令读数汇总

| 账本 | 命令 | 读数 | exit |
|---|---|---|---|
| 002 | `pytest tests/test_face_store.py -o addopts= -q`（副本基线） | 16 passed | 0 |
| 003 | 同上（M1 全还原） | 2 failed, 14 passed | 1 |
| 004 | 同上（M2 复制行出锁） | 2 failed, 14 passed | 1 |
| 005 | 同上（还原后） | 16 passed | 0 |
| 006 | `pytest tests/test_face_store.py -q`（票面原文） | 16 点 | 0 |
| 007 | `pytest -o addopts= -q`（副本全套） | **552 passed in 29.53s** | 0 |
| 008 | 20 份 detrun 日志统计 | 20×`2 passed` / 0×`failed` | 0 |

552 = 基线 550 + 本票 2，与 worker 账一致（其主工作区 562 含 03 票未提交 +10，副本不含）。
