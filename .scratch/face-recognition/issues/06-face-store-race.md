# 06 — 名单删除与注册的互斥

**Status:** resolved
**Blocked by:** 02
真机自检：不需要

## What to build

消除名单 `remove_face` 与 `register_face` 之间的丢更新：02 r2 门实测到「注册确认的 Carol 被一次并发删除的过期副本覆盖丢失」。把删除的复制—修改—写回放进同一把名单锁，补一条可确定复现旧交错顺序的并发测试。

## Acceptance criteria

- [ ] [AS-3, AS-4] `remove_face` 的读—改—写全程持 `_faces_lock`，与 `register_face` 并发时不丢更新
- [ ] 新增并发测试能稳定复现旧实现的丢失（旧代码红、新代码绿），不是概率性 sleep [AS-3, AS-4]
- [ ] 定向与全套测试通过，其它行为不变 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_face_store.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`

## 写域

- `src/rvm/analysis/face_store.py`
- `tests/test_face_store.py`

## 开工包

- **写域**：`src/rvm/analysis/face_store.py`, `tests/test_face_store.py`
- **锚点**：`grep -n "def remove_face" src/rvm/analysis/face_store.py`、`grep -n "_faces_lock" src/rvm/analysis/face_store.py`。
- **复现方式**：用两个事件/屏障把 remove 的复制与写回卡在中间，让 register 插进去；旧实现断言丢更新，新实现断言两条都在。
- **尺寸上限**：≤300 行 / 2 文件。
- **估算**：预计 20 分钟 / 90 步（原子缺陷，无同域相邻票可并）。

## 验收包

- **判据**：AS-3、AS-4、AS-5；并发测试在旧实现上必须红。
- **首攻靶**：锁是否真的覆盖读—改—写、测试是否只是 sleep 碰运气、删除与注册交错是否还有第二条路径（`replace`）。
- **相关 AS 摘录**：AS-3 持久化与一致性；AS-4 失败与降级；AS-5 不回归。

## 完成条件

并发测试红→绿、全套绿；独立动态门在干净副本里重跑并亲手还原旧实现验证测试咬得住，判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

### 1. AC → 证据

- **AC1 `remove_face` 读—改—写全程持 `_faces_lock` [AS-3, AS-4]** → 实现 `src/rvm/server/session.py:683-704`（`with self._faces_lock:` 在 696 行，复制、存在性检查、`del`、`_publish_faces` 全在其内）；证据 `tests/test_face_store.py:290` 与 `:330`：两条测试把删除线程停在锁入口，只有在「复制发生在锁内」时删除才会等另一方的提交落盘后再读。
- **AC2 并发测试稳定复现旧实现的丢失（旧红新绿，非 sleep 碰运气）** → `tests/test_face_store.py:290`（register-vs-remove，02 r2 门的原始形状）、`:330`（remove-vs-remove）。自证：把 `remove_face` 还原成票前写法（sha1 `36C1F089…`）→ `2 failed, 14 passed`；还原新实现（sha1 `EF759A7B…` 逐字节相同）→ `16 passed`；新实现下两条测试连跑 20 轮 20/20 绿。接缝是 `ObservedLock`（`:237`）：它就是同一个 `RLock`，只在**非持有者即将阻塞**时释放一个信号量，因此卡住的是真线程等真锁，不是计时。
- **AC3 定向与全套通过 [AS-5]** → 定向 `16 passed`；全套 `562 passed in 45.66s`（含 03 号票未提交的 +10 条 `tests/test_app.py`，基线 550 + 本票 2 = 552，账对得上）；`tests/test_face_api.py` 的删除/404/写失败/镜像/并发同名既有测试全绿。

### 2. 假设

- 名单在进程内的唯一写者是 `StreamSession`：`register_face`（锁内 `:673` 起）、`remove_face`（锁内 `:696` 起）、`_publish_faces`（锁内 `:728`），加 `__init__` 里线程启动前的 `load()`。`grep -n "face_store\."` 全仓只有这些点。
- `_publish_faces` 是「一次提交」的全部：整体替换 store、落盘、整体替换识别器镜像；写失败用锁内读到的 `previous` 回滚。持锁者在同一线程里再取锁（`RLock`）不会自死锁，这是 `remove_face` 现在依赖的既有性质。
- 测试里「注册的临界区」等价于 `dict(face_store.faces)` → 加入 → `_publish_faces`，即 `register_face:673-677` 的原样三行；测试因此在持锁线程里复用它，而不是另造一条写路径。
- `ObservedLock` 与被替换的 `threading.RLock` 语义等价：可重入、按线程记 owner、只在「非持有者将要阻塞」时发一次信号。
- 响应里的 `known` 在锁外读（`:703`），可能包含响应生成前几微秒刚提交的名字；这是改前行为，未改。

### 3. 我知道没覆盖什么

- **真 HTTP 层并发未重跑**：02 r2 门的 Part B 是经 `POST`/`DELETE` 复现的；本票证据是进程内真线程真锁，不是 aiohttp 端到端。
- **未测 remove 与 `FaceStore.load()` 并发**：`load()` 只在 `__init__` 单线程调用，产品里没有第二条路径。
- **未测识别器镜像的读方竞争**：`replace_known_faces` 是整体替换、读方遍历旧映射；既有 02 票测试覆盖，本票不动。
- **测试不覆盖「注册取样与分析 tick 并发」**：测试直接填 `_recent_frames`，不走 `run_once`/Haar，因此推理互斥（`_inference_lock`）不在本票证据里。
- **`tools/coverage-tests.mjs` 在本仓不存在**（`tools/` 下只有 benchmark/build_report 等脚本）：派发消息里的覆盖清单无法亲跑，标 UNVERIFIED；两侧文件按派发读数均为「无覆盖」。
- **没测锁持有时间**：`remove_face` 现在把文件写也纳进自己的临界区（原本 `_publish_faces` 也在同一把锁内写文件），持有时间与改前同一量级，但本轮没有读数。

### 4. 复现命令

```powershell
.venv\Scripts\python.exe -m pytest tests/test_face_store.py -o addopts="" -q
```

想看红：把 `src/rvm/server/session.py` 的 `remove_face` 换回「锁外复制 + 检查」的六行（票前写法），同一条命令 → `2 failed, 14 passed`。

### 5. 我认为最脆的一处

换了我是攻击者，第一个打**锁的边界是否被下一张票悄悄挪走**：只要有人把 `dict(self.face_store.faces)` 移回 `with` 之外（或让 `_publish_faces` 接收调用方在锁外构造的副本），丢更新会无声回归，而两条测试恰好咬住这种写法——它们把删除线程停在锁入口，锁外复制必然在那一刻之前发生。第二处：把 `RLock` 换成普通 `Lock` 会让 `register_face` 嵌套取锁自死锁，这一条测试覆盖不到（只会表现为挂起）。

### 6. 票面外的决定

- **决定：改 `src/rvm/server/session.py`，越出票面写域一行** / 理由：缺陷（`remove_face` 的锁外复制）与 `_faces_lock` 都只在该文件；票面锚点 `grep -n "def remove_face" src/rvm/analysis/face_store.py` 无命中（`face_store.py` 只有 store 层 `remove`），照写域做无法修 / 影响面：改动仅 `remove_face` 一个方法体 + `_faces_lock` 的注释，未碰 `src/rvm/web/*`、`tests/test_app.py` 等其它文件；门若判越界请以此处置。
- **决定：并发测试放 `tests/test_face_store.py`（而不是 `tests/test_face_api.py`）** / 理由：票面写域与定向命令只指该文件 / 影响面：该文件新增 `from rvm.server.session import StreamSession`（连带 cv2），定向跑从 0.4s 量级变为约 1.6s。
- **决定：用 `ObservedLock` 替换 `_faces_lock` 作确定性接缝** / 理由：旧实现的坏交错唯一可观测点就是「锁入口之前已完成复制」，sleep 只能猜 / 影响面：测试依赖「`_faces_lock` 是实例属性且以 `with` 使用」；换成模块级锁或非上下文管理器时测试需同步改。
- **决定：测试直接填 `_recent_frames`，不跑 `run_once`** / 理由：这三帧就是注册要平均的内容，跑 `run_once` 只为生成同样三帧，却引入 Haar 与 OpenCL 退出问题 / 影响面：本票证据不含分析 tick 路径（已由 02 票测试覆盖）。
- **决定：多写一条 remove-vs-remove 测试** / 理由：门首攻靶点名「删除与注册交错是否还有第二条路径」，同类缺陷在两条删除之间同样成立 / 影响面：多一条测试，产品代码不变。
- **决定：`FaceStore.add`/`replace` 不加锁，判为无同类漏洞** / 理由：它们的生产写点只有 `_publish_faces`（锁内）与 `__init__` 的 `load()`（线程启动前），`FaceStore.add/remove` 只被测试直接调用 / 影响面：若以后有人在 session 之外直接调 `FaceStore.add`，丢更新会以新路径回归，测试不覆盖。

## Verdicts

- 2026-11-09 r1 VERIFIED 2af49cd — 干净副本亲手复现：`remove_face` 读—改—写全程持同一把 `_faces_lock`；全还原与「仅复制行出锁」两个变异各产出确定性红（sha1 与 worker 自证逐字节一致），还原后 16 绿；20 连跑零抖动；全套 552 绿。｜报告：.scratch/face-recognition/reports/06-r1-verifier.md｜模型路线：未标注（派发未带 --model）
- 2026-11-09 r1 VERIFIED 2af49cd — 干净副本亲手复现：`remove_face` 读—改—写全程持同一把 `_faces_lock`；全还原与「仅复制行出锁」两个变异各产出确定性红（sha1 与 worker 自证逐字节一致），还原后 16 绿；20 连跑零抖动；全套 552 绿。｜报告：.scratch/face-recognition/reports/06-r1-verifier.md｜模型路线：swe-2-high
