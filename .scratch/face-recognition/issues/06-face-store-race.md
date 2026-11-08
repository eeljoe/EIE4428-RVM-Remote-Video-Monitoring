# 06 — 名单删除与注册的互斥

**Status:** ready-for-agent
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

（由 worker 在交票前补写）

## Verdicts
