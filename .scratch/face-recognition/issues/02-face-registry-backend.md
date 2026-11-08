# 02 — 服务端人脸注册与持久化

**Status:** claimed
**Blocked by:**
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

### 1. AC → 证据

| AC | 代码 | 测试 |
|---|---|---|
| 取样本接口，无脸返回空列表 | `src/rvm/analysis/recognition.py:262` `sample_faces`（`FaceSamplingError` 与空列表分开，`recognition.py:66`） | `tests/test_recognition.py:266`（空帧 → `[]`）、`:282`（无模型 → 异常） |
| 注册/删除推理不在事件循环，与 `_analyse` 共用串行锁，期间 status/MJPEG 不中断 | `session.py:611` `register_face`；`session.py:447` `_analyse` 取 `self._inference_lock`；`session.py:679` `_sample_faces` 同锁；`app.py:381` 用 `asyncio.to_thread` | `tests/test_face_api.py:389`（0.6 s 推理期间循环转了 ≥10 次）、`:436`（测试线程持锁时注册与分析都卡住 → 同一把锁）、`:414`（请求在飞时 `/api/status` 与 `/api/snapshot.jpg` 均 200）；真机读数见 `verifier-probes/02-face-registry-backend-selfcheck.md` §1（513 次注册 / 4.06 s，p95 状态延迟 14.3 ms vs 基线 21.0 ms，MJPEG 7.6 fps vs 8.0 fps） |
| 名单整体替换，encode 线程迭代不出 `dictionary changed size` | `recognition.py:234/246/255` 复制后换引用；`recognition.py:285` 每帧只取一次引用；`session.py:689` `_publish_faces` 整体替换 | `tests/test_recognition.py:296`、`:308`、`:321`（换引用而非原地改）、`:333`（400 次迭代 vs 并发增删不抛异常）；`tests/test_face_store.py:124`、`:136` |
| 名单模块加载/原子保存/增/删；缺失空名单、损坏告警空启动 | `face_store.py:71` `load`、`:101` `save`（临时文件 + `os.replace` + `fsync`）、`:137` `add`、`:143` `remove`、`:152` `replace` | `tests/test_face_store.py:35`（缺失不建文件）、`:54`、`:65`（损坏告警）、`:81`（无残留临时文件）、`:93`、`:106`（写失败保留旧文件） |
| `POST /api/faces/known` 取最近三帧各一张脸求平均落盘，成功返回样本数，失败 `{"error","reason"}` | `session.py:611`（取 `_recent_frames[-3:]`，每帧 0 张 → `no-face`、多张 → `multiple-faces`，`np.mean` 后 `_publish_faces`）；`app.py:361` `_fail` | `tests/test_face_api.py:155`（喂 4 帧、只平均后 3 帧，磁盘向量 == 手算 `20.0`）、`:240`、`:253`（失败体形状与枚举） |
| 无脸/多脸/重名 409，分析关闭/模型未就绪/识别器不可用 503；两类都不写文件 | `session.py:611` 的检查顺序；`session.py:689` 先存后换、失败回滚 | `tests/test_face_api.py:173`、`:186`、`:200`、`:214`（409，且文件不存在或字节未变）、`:269`、`:281`、`:295`（503，且文件不存在）、`:353`（写失败 500，内存名单不变） |
| `GET`/`DELETE` 可用，删除落盘，缺失 404 | `app.py:375`、`:401`；`session.py:663` `remove_face` | `tests/test_face_api.py:318`、`:330`（返回后磁盘只剩另一个名字）、`:344`（404 + 契约体）；真机 §2（真实 HTTP 删除后磁盘立即变化，重启后只剩 `Bob`） |
| `--known-faces` 默认 `data/known_faces.json`，进 `.gitignore` | `face_store.py:44` `DEFAULT_KNOWN_FACES`；`app.py:567` CLI；`app.py:603` 传入 `create_app` | `tests/test_face_store.py:162`、`:166`（`.gitignore` 含该路径）、`tests/test_face_api.py:462`、`:472`（路径真的到 session） |
| 全套不回归 + 新增测试 | — | 定向 64 passed；全套 541 passed；命令与读数见报告 TESTS 段 |

### 2. 假设

- 名单文件由本程序写、由本程序读：损坏 = bug，不是输入，所以「结构不对就整份当空」是可接受的降级。
- 一帧里「多脸」就拒绝注册：两个人在画面里时，取「一张脸」没有唯一解；宁可 409 让人单独站到镜头前。
- 「最近三次分析帧」= `_analyse` 真正跑过的帧（`analysis_interval` 节流后的），不是最近三张相机帧；注册取样与面板上看到的分析结果来自同一批帧。
- 名单里的向量维度一致（同一 landmarker 产出），因此不在加载时校验长度，只校验「非空、有限、一维」。
- 名字是标签不是身份键：去空白、≤40 字符、单行；不做 Unicode 归一化。

### 3. 我知道没覆盖什么

- **真机注册一张真脸**：`--no-camera` 的合成场景没有人脸，本机也没有可用的真人脸素材，真机证据止于「513 次注册全部 409 且零写入」与「预置名单 → 删除 → 重启」。真脸注册 → 重启 → 识别的闭环留给 05 号集成票的动态门。（UNVERIFIED at 真机层；测试层用桩替换 MediaPipe 覆盖）
- 端点测试里 MediaPipe 被桩替换（`recognize`/`detect`/`sample_faces`），因此「landmarker 在真实人脸上一帧返回 1 个嵌入」只有 `tests/test_recognition.py:266` 的空帧与模型加载用例背书，维度/数值本身没测。
- 并发写同一名单文件的两个服务进程没有互斥（同机双开才会遇到），`os.replace` 只保证单进程内原子。
- 没有测「注册请求进行到一半时名单被另一请求删除同名」这类交错；顺序检查与保存不在同一把锁里。
- 未测 320×240 以外分辨率的注册（平均逻辑与分辨率无关，取样走同一 landmarker）。

### 4. 复现命令

```
.venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py -q
.venv\Scripts\python.exe run_server.py --no-camera --port 8099
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\02-face-registry-backend-selfcheck.py
```

第三条在服务起来后跑，30 秒内给出「注册期间 status / MJPEG 是否掉」的读数。

### 5. 我认为最脆的一处

`_inference_lock` 的粒度：`_analyse` 一次持锁跑三个识别器（一个 tick ≈ 40–60 ms），注册按帧取锁。如果换成「注册持锁跑完三帧再放」，编码线程会被按住 60 ms 以上；反过来如果谁把 `_analyse` 的锁去掉，注册与识别会同时用同一个 landmarker——这不会立刻炸，而是偶发错误结果或 MediaPipe 内部崩溃，最难查。攻击点：把 `_analyse` 那行 `with self._inference_lock:` 删掉，然后跑高频注册 + 分析，看是否出现 `error` 状态或进程退出。

### 6. 票面外的决定

- **`DELETE` 缺失名字回 404 时 reason 用 `bad-name`** / 理由：契约枚举里没有 `not-found`，而 404 状态由契约固定 / 影响面：前端要按 404 + `bad-name` 判「这个名字不在名单里」。
- **每次取样单独取锁，而不是整个注册持锁** / 理由：把编码线程的最长阻塞压到一次推理（约 20 ms），仍保证「两处不同时推理」 / 影响面：注册总耗时可能被分析 tick 插队拉长几十毫秒。
- **注册要求最近三帧每帧恰好一张脸** / 理由：多脸时「取一张」没有唯一解，静默选第一张会把错误的人注册进去 / 影响面：双人入镜时必须单独站到镜头前。
- **`FaceStore` 与 `FaceRecognizer` 各持一份映射，由 `_publish_faces` 同步** / 理由：识别路径不能每次识别都读文件 / 影响面：任何绕过 `_publish_faces` 的写名单都会让两份分叉（目前只有加载与这两个端点写）。
- **`tests/test_face_api.py` 里 `cv2.ocl.setUseOpenCL(False)`** / 理由：本机 OpenCV 4.14 在**工作线程**里跑 Haar 级联后，进程退出时 `clReleaseDevice` 失败并 abort，整份 pytest 在全部通过后以 0xC0000409 退出；用只调用 `FaceDetector().detect` 的三行探针即可复现，与票内代码无关（`src/rvm/analysis/detect.py` 未改）/ 影响面：测试进程不用 GPU 路径，产品行为不变；这是环境绕行，不是功能的一部分。
- **名单 JSON 形状 `{"version": 1, "faces": {name: [..]}}`** / 理由：留版本位以便以后迁移；`faces` 包一层避免与未来元数据键冲突 / 影响面：其他票（05 集成）直接读写该文件时要按此形状。

## Verdicts

- 2026-11-09 r1 REJECTED 5adcede — 动态证据全面通过，但一处「名单→识别器镜像同步」变异在全套 541 测试下存活（非等价：注册后本会话识别不到新脸），套件对此行为无牙；另发现混维名单文件可致死 pump 任务的降级缺陷。｜报告：.scratch/face-recognition/reports/02-r1-verifier.md｜模型路线：swe-2-high
