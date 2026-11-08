# 02 — 服务端人脸注册与持久化

Status: ready-for-agent
Blocked by:

## 交付什么

把「注册一张脸」做成服务端能力：从最近三次分析帧各取一张脸的嵌入求平均，写入 `data/known_faces.json`；提供增、查、删三个端点与 `--known-faces` 参数；名单加载失败可降级，删除后立即落盘。

## Acceptance criteria

- [ ] 识别器提供取样本接口，返回一帧内每张脸的嵌入向量；无脸返回空列表 [AS-1, AS-4]
- [ ] 名单模块支持加载、原子保存、增加、删除；文件缺失按空名单，损坏时告警并按空名单启动 [AS-3, AS-4]
- [ ] `POST /api/faces/known` 取最近三帧各一张脸求平均并落盘；成功返回样本数；无脸、多脸、重名返回 409 且不改文件 [AS-1, AS-4]
- [ ] 分析关闭、模型未就绪或识别器不可用返回 503；既有状态词表不变 [AS-4]
- [ ] `GET /api/faces/known` 与 `DELETE /api/faces/known/{name}` 可用，删除后落盘 [AS-3]
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

- 端点写法照 `src/rvm/server/app.py` 现有只读端点；错误用 `web.HTTPBadRequest` / `web.HTTPConflict` / `web.HTTPServiceUnavailable`。
- 会话已有 `_latest` 帧与分析节拍 `_analyse()`；最近帧只在该节拍里留，别每帧拷贝。
- 识别器 `FaceRecognizer.add_known_face(name, embedding)` 已存在，扩展它而不是另起一套。
- 名单文件不存照片；嵌入用 JSON 列表存，写入用临时文件 + `os.replace` 原子替换。
- 新端点测试放 `tests/test_face_api.py`，**不要改 `tests/test_app.py`**（03/04 号票的写域）。

## 验收包

- 判据：AS-1、AS-3、AS-4、AS-5。
- 首攻靶：三帧取样是否真取三帧、409 时文件是否零写入、重启后能否识别、损坏文件是否降级、分析关闭是否 503。
- 相关 AS：AS-1 注册闭环；AS-3 持久化；AS-4 失败与降级；AS-5 回归。

## 完成条件

实现提交含测试；独立动态门对 409/503/重启三条路径给出新鲜证据并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
