# 02 服务端人脸注册 — r2 复验探针与账本说明

日期：2026-11-09 ｜ 被验提交：`3486a02` ｜ 验收副本：`C:\Users\joe\AppData\Local\Temp\verify-02-r2-3486a02`（gate-kit worktree，detach）
账本：`.scratch/face-recognition/ledger/02-r2.jsonl`（条目 02-r2-001 … 02-r2-024）

## 本轮新写探针（verifier 自有，非收编）

| 文件 | 用途 |
|---|---|
| `02-r2-verifier-persist.py` | 真进程持久化/降级重证：等宽名单加载→重启→删除落盘；混维名单降级空名单+告警+画面泵前进；单条 8 维名单载入（由 `_nearest` 守卫在匹配时跳过）。环境变量 `VERIFY_WT`/`VERIFY_PY`/`VERIFY_PORT`。结果：9/9（条目 02-r2-014） |
| `02-r2-verifier-pumpguard.py` | 真 `StreamSession.run_forever` 泵任务 + 磁盘载入的 8 维条目 + 桩 landmarker（3 关键点→9 维嵌入）：HEAD 下泵存活、tick 照跑、坏条目不产生身份；`--expect-dead` 在变异态证泵死。结果：HEAD 6/6（02-r2-011）、变异态 2/2（02-r2-012） |
| `02-r2-verifier-race.py` | Part A 独立重推「两线程同名注册 → 恰一 201 一 409 name-exists、文件一条、store=mirror」；Part B 用预持 `_faces_lock` 把 register 排在 remove 的过期副本之前，实证 register-vs-remove 丢更新（201 确认的 Carol 消失，file/store/mirror 一致地缺它）。结果：6/6（02-r2-013） |

## 复跑的上轮探针（不转录，全部本轮新跑）

| 探针 | 条目 | 结果 |
|---|---|---|
| `02-mirror-sync-verifier-test.py`（r1 杀手探针本体） | 02-r2-022 | 3/3 绿（HEAD 真码） |
| `02-face-registry-backend-verifier-probes.py sample` | 02-r2-015 | 7/7（真 MediaPipe：空帧/噪声→[]，两张脸→2×1434 维互异） |
| 同上 `api` | 02-r2-016 | 34/34（201 契约、均值 20.0、取样恰 3 次、409/400/404/503 逐类零写入） |
| 同上 `churn` | 02-r2-017 | 3/3（3000 增删 ×4 迭代线程 + 120 注册/删除周期零 dict-changed-size） |
| 同上 `live` | 02-r2-018 | 12/13；唯一 FAIL 是探针时序——POST 落在第 1 个分析帧时得 `samples-missing`（契约内合法 409，零写入），非产品缺陷；同一真机上后跑的 burst 379×`no-face`（02-r2-021）佐证 |
| 同上 `persist` | 02-r2-019 | 5/8；3 个 FAIL 全是 r1 探针的混维种子文件在新契约下**按设计**降级——r1 整改本身要求「不等长按损坏降级」；等宽重证由 02-r2-014 补齐 |
| 同上 `stress` | 02-r2-020 | 3/3（爆发期 status p95 15.9ms、MJPEG 持续出帧） |
| `02-face-registry-backend-selfcheck-r2.py`（worker 自检脚本，我本人重跑） | 02-r2-021 | 379 并发注册全 409 `no-face`、名单文件零写入、爆发期 status p95 16.1ms、MJPEG 7.4fps 不断流 |

## 变异取证（全部亲手在副本里做，sha1 记→变→红→还原→核 sha1）

| 条目 | 变异 | 结果 |
|---|---|---|
| 02-r2-003/004 | `session.py::_publish_faces` 删 `replace_known_faces(faces)` | 3 条收编测试全红；还原 sha1 一致（工作树字节 `555933D2…`）；复跑 3 绿 |
| 02-r2-006 | `recognition.py::_nearest` `except ValueError` → `except KeyError` | 3 红，含真 `run_forever` 泵死于 `ValueError (9,) (8,)`；sha1 `879A08E4…` 一致 |
| 02-r2-007 | `face_store.py::_parse` `elif vector.shape[0] != width:` → `elif False:` | 混维测试红；sha1 `2BF7C73B…` 一致 |
| 02-r2-009 | `session.py::register_face` 锁内复检 `if name in ...` → `if False:` | `[201,201]==[201,409]` 双 201 复现；sha1 一致 |
| 02-r2-012 | 手工施加 02-r2-006 同款变异跑 `--expect-dead` | 泵以同款 `ValueError` 死亡（自证探针的红态路径），随后字节级还原并 sha1 复核一致 |
| 02-r2-023 | 自选变异：`width = int(vector.shape[0])` → `width = 0` | `test_a_list_of_one_width_still_loads` 红（等长名单被冤判损坏）；sha1 一致 |

变异存活：0/5。

## 运行环境注记

- 全部测试/探针用主仓 `.venv` 解释器 + 副本 `src/`（pyproject `pythonpath`），副本与主工作区互相不可见；主仓 HEAD 为 `9f142f7`（目标之上仅 docs），工作区未提交改动属 03 号票写域，不影响 3486a02 副本。
- worker 报告里的 face_store sha1（`61287366…`）是 **git blob** 字节哈希；gate-kit/sha1sum 量的是工作树检出字节（CRLF），`2BF7C73B…`。两者各自一致，非矛盾。
- 全套在 3486a02 实为 **550**（collect 复核）；worker 报 560 是在含 03 票未提交 `test_app.py`（+10）的主工作区测得，差值恰好对账，非虚报。
- 账本条目 02-r2-008 是多行 `--find` 被 cmd 截断的用法失败记录（exit 1），由 02-r2-009 的单行变异取代；02-r2-010 是我探针判词字面值写错（`STATE_RUNNING` 字面是 `mediapipe`）的一次失败记录，改探针后 02-r2-011 全绿。
