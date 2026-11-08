# 02 — 服务端人脸注册与持久化

Status: claimed
Blocked by:
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/02-face-registry-backend-selfcheck.md`）

## What to build

把「注册一张脸」做成服务端能力：从最近三次分析帧各取一张脸的嵌入求平均，写入 `data/known_faces.json`；提供增、查、删三个端点与 `--known-faces` 参数；名单加载失败可降级，删除后立即落盘；注册期间不阻塞画面流与遥测。

## Acceptance criteria

- [ ] 识别器提供取样本接口，返回一帧内每张脸的嵌入向量；无脸返回空列表 [AS-1, AS-4]
- [ ] 注册与删除的推理不在事件循环里跑：与 `_analyse` 共用同一把串行锁，或复用分析结果；请求期间 `/api/status` 与 MJPEG 不中断 [AS-1]
- [ ] 名单变更用整体替换（复制后换引用）或加锁，encode 线程迭代 `known_faces` 时不出现 `dictionary changed size during iteration` [AS-3, AS-5]
- [ ] 名单模块支持加载、原子保存、增加、删除；文件缺失按空名单，损坏时告警并按空名单启动 [AS-3, AS-4]
- [ ] `POST /api/faces/known` 取最近三帧各一张脸求平均并落盘；成功返回样本数；失败返回 `{"error","reason"}` 契约 [AS-1, AS-4]
- [ ] 无脸、多脸、重名返回 409，分析关闭、模型未就绪、识别器不可用返回 503；两类都不写名单文件 [AS-4]
- [ ] `GET /api/faces/known` 与 `DELETE /api/faces/known/{name}` 可用，删除后落盘，缺失返回 404 [AS-3]
- [ ] CLI 参数 `--known-faces` 可改路径，默认 `data/known_faces.json`，该文件进 `.gitignore` [AS-3]
- [ ] 全套既有测试不回归，且新增测试覆盖上述行为 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`

## 写域

- `src/rvm/analysis/recognition.py`
- `src/rvm/analysis/face_store.py`（新增）
- `src/rvm/server/session.py`
- `src/rvm/server/app.py`
- `tests/test_face_store.py`（新增）
- `tests/test_recognition.py`
- `tests/test_face_api.py`（新增）
- `.gitignore`

## 开工包

- **写域**：`src/rvm/analysis/recognition.py`, `src/rvm/analysis/face_store.py`, `src/rvm/server/session.py`, `src/rvm/server/app.py`, `tests/test_face_store.py`, `tests/test_recognition.py`, `tests/test_face_api.py`, `.gitignore`

- **线程纪律**：`_analyse` 在 encode 线程里调用同一个 landmarker；注册请求必须 `asyncio.to_thread` 且与 `_analyse` 串行（session 里加一把 `threading.Lock`），不允许两处同时推理。
- **快照纪律**：`status()` 从别的线程切片同一份数据；`known_faces` 变更一律复制后整体换引用，不在原 dict 上 `[]=` 或 `pop`。
- **端点写法**：错误用 `web.HTTPBadRequest` / `web.HTTPConflict` / `web.HTTPServiceUnavailable`；失败响应体 `{"error": "...", "reason": "<枚举>"}`，枚举见 spec「接口契约」。
- **落盘**：临时文件 + `os.replace` 原子替换；文件缺失按空名单，损坏时 `log.warning` 后按空名单启动。
- **测试文件**：端点测试放 `tests/test_face_api.py`，不要改 `tests/test_app.py`（03/04 号票写域）。
- **尺寸上限**：目标 ≤300 行 / ≤3 文件，但本票最小面是 5 个产品文件 + 3 个测试文件；超限时按 OVER-LIMIT 分级走额外静态实例，不靠扩文件规避。
- **估算**：预计 55 分钟 / 260 步（略超甜点，超限由门计级）。

## 验收包

- **判据**：AS-1、AS-3、AS-4、AS-5；每条 AC 对应定向测试或真机读数。
- **首攻靶**：三帧是否真取三帧、注册是否卡住事件循环、409/503 是否零写入、重启后能否识别、`known_faces` 是否原地改、损坏文件是否降级。
- **相关 AS 摘录**：AS-1 注册闭环且画面流不中断；AS-3 持久化；AS-4 失败与降级；AS-5 不回归。

## 完成条件

实现提交含测试；独立动态门对「注册期间流不中断」「409/503」「重启后仍在」三条路径给出新鲜证据并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
