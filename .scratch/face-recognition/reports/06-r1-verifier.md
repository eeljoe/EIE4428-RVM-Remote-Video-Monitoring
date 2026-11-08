# 06 名单删除与注册的互斥 — 独立验收报告（r1）

VERDICT: VERIFIED — 干净副本亲手复现：`remove_face` 读—改—写全程持同一把 `_faces_lock`；全还原与「仅复制行出锁」两个变异各产出确定性红（sha1 与 worker 自证逐字节一致），还原后 16 绿；20 连跑零抖动；全套 552 绿。
HEAD: 2af49cd15c51addca9b749ad9abfa6ea45286550
LEDGER: 06-r1-001,06-r1-002,06-r1-003,06-r1-004,06-r1-005,06-r1-006,06-r1-007,06-r1-008

## 定靶

- 被验提交 `2af49cd`（派发方指定，提交含票文件 + `src/rvm/server/session.py` + `tests/test_face_store.py`；其上 `bbf0489`/`1380c3e` 为报告文档提交，不在被验范围）。
- 验收副本 `C:\Users\joe\AppData\Local\Temp\verify-06-r1-2af49cd`（gate-kit worktree，detach 于 2af49cd，验收后 cleanup）。`pythonpath=["src"]` 使副本 pytest 解析副本自身 `src/`——变异转红实证了这条 import 路径。
- 基线 = `5292721`（票开）；`git diff 5292721..2af49cd -- src tests` = 2 文件 +192/−8，远低于 300 行 / 2 文件上限。主工作区 `src/rvm/web/*`、`tests/test_app.py` 未提交改动属 03 票写域，副本不受影响。
- 写域越界：`session.py` 不在票面写域（票面锚 `def remove_face` 在 `face_store.py` 无命中——票面指错了文件）。缺陷与 `_faces_lock` 确实只在 `session.py`；worker 已声明越界理由，改动确为一个方法体 + 一处注释。判为票面失真的 FYI，不算代码问题（FINDINGS-3）。

## 判据重建 → 判定

| 判据 | 判定 | 证据 |
|---|---|---|
| C1 [AS-3,AS-4] `remove_face` 读—改—写全程持同一把 `_faces_lock` | PASS | 代码亲读 `session.py:696-703`：`with self._faces_lock:` 覆盖 `dict(faces)` 复制、存在性检查、`del`、`_publish_faces`；`:728` `_publish_faces` 重入同一 RLock。并发实测：register-vs-remove 与 remove-vs-remove 两测试绿（002/005/006），变异红见 C2 |
| C2 [AS-3,AS-4] 并发测试确定复现旧缺陷（旧红新绿，非 sleep） | PASS | M1 全还原（sha1 `36C1F089…` 与 worker 自证一致）→ `2 failed, 14 passed`，签名即丢更新原文（003）；M2 自选变异只移复制行出锁 → 同样 2 红（004）；还原 sha1 回 `EF759A7B…` → 16 绿（005）。`ObservedLock` 信号量接缝，测试无 sleep；20/20 连跑（008） |
| C3 [AS-5] 定向与全套通过，其它行为不变 | PASS | 票面原文定向 `16`（006）；副本全套 `552 passed in 29.53s`（007），= 基线 550 + 本票 2，与 worker 账一致；diff 无依赖改动 |
| C4 其它路径无同类丢更新 | PASS | `grep` 全 `src/`：名单写点仅 `register_face`(:673 锁内)、`remove_face`(:696 锁内)、`_publish_faces`(:728 锁内)、`__init__.load`(:193 线程启动前)；`FaceStore.add/remove` 无生产调用方；`faces` 属性全仓只读、写入全为整体替换，锁外读者见一致快照 |

## FINDINGS

1. [FYI] `src/rvm/server/session.py:704` — `remove_face` 响应里的 `known` 在锁外读，可能多带几微秒前刚提交的名字；改前即如此，worker 已声明，属响应生成时序非丢更新。confidence: HIGH
2. [FYI] `session.py:207` `RLock`→`Lock` 变异会让 `register_face` 在 `with` 内重入 `_publish_faces` 自死锁；两新测试会在装机步 `register_face("Alice")`（无 timeout 的直调）挂起，表现为套件挂起而非干净红。属 02 r2 已定的 RLock 约束，CI 超时兜底，非本票缺陷。confidence: HIGH
3. [FYI] 票面写域 `src/rvm/analysis/face_store.py` 失真——该文件没有 `remove_face`，实际缺陷与锁都在 `session.py`；worker 越界改动最小（一方法体 + 一注释）。建议派发方在票面补记，勿留错误锚点误导后续票。confidence: HIGH
4. [FYI] 若未来 `_publish_faces` 改用第二把锁，本测试形状不可见（remover 仍被 `_faces_lock` 拦住即认为安全）；当前 `:728` 确为同一把锁。confidence: MEDIUM

## RED-TEAM ATTEMPTS

- 「我若偷懒会在哪 5 处省事」清单：① 只信 worker 的红绿读数（→ 自己在干净副本全还原，sha1 亲手复算）；② 变异只做整段回退（→ 加做 M2 单移复制行，仍红，证明咬边界）；③ 不跑全套（→ 552 亲跑）；④ 不验确定性（→ 20 连跑 + sleep grep）；⑤ 不查其它写路径（→ 全 `src/` grep，逐点核对持锁）。
- 并发/竞态族：M1 全还原红（003）、M2 边界变异红（004）、确定性 20/20（008）。
- 边界/整形族：两测试断言 store+文件+识别器镜像三方一致，期望值手写字面量（20.0 均值、[7.0] Carol），非自洽构造。
- 永真断言核查：`assert lock.waiting.acquire(timeout=5)` 在 remover 不到锁时会红，非永真；`assert not remover.is_alive()` 死锁即红。
- 同锁身份：`_publish_faces` 用 `self._faces_lock`（:728 亲读）；若 remover 走别的锁 `waiting` 不会释放，测试红。
- 未选族：畸形输入/环境投毒（本票不动解析与降级路径，02 票已覆盖且本轮全套 552 含其回归）；UI（票面非 UI）；权限（无越权面）。

## NOT RUN / UNVERIFIED

- 端点级 aiohttp 并发端到端未重跑：测试直调 `session.remove_face`/`register_face`，即 `app.py:394/405` 经 `asyncio.to_thread` 调用的同一对方法，锁纪律相同；票面复现方式本就指进程内接缝。
- 锁持有时间读数：`_publish_faces` 的文件写现在在 `remove_face` 临界区内（改前也在 `_publish_faces` 自身临界区内），量级未实测——无判据要求。

## REMEDIATION

none

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 2af49cd | reports/06-r1-verifier.md | 0 | 干净副本亲证：两个变异（全还原、仅复制行出锁）各得确定性 2 红、还原 sha1 逐字节一致后 16 绿、20 连跑零抖动、全套 552 绿 |
