# 02 真机自检 — 服务端人脸注册与持久化

机器：Windows，`.venv`（Python 3.13.11，mediapipe 1.2.2，OpenCV 4.14.0）。
日期：2026-11-09。分析默认开启（`run_server.py` 不传 `--no-analysis`）。

**结论**：注册请求期间 `/api/status` 与 MJPEG 都在正常出数；4.06 s 内连续 513 次注册请求全部 `409 no-face` 且零写入；名单经 `--known-faces` 启动读取、删除立即落盘、重启后反映文件内容；损坏文件告警后按空名单启动，画面流不中断。

## 1 注册请求期间画面流与遥测不中断

启动（服务端终端一）：

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099
RVM serving on http://0.0.0.0:8099/  (320x240 @ 15 fps, source: synthetic)
```

驱动（终端二）：

```
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\02-face-registry-backend-selfcheck.py
```

读数（原文）：

```
source=synthetic frames=460
analysis: enabled=True ready=True face_recognition=True
list file before: data\known_faces.json exists=False
status baseline (idle): n=36 median=3.1ms p95=21.0ms max=25.1ms
status during burst: n=73 median=4.2ms p95=14.3ms max=19.6ms
status after burst: n=36 median=3.9ms p95=22.2ms max=26.5ms
mjpeg baseline: 16 frames in 2.0s (8.0 fps)
mjpeg during burst: 38 frames in 4.97s (7.6 fps)
mjpeg after burst: 16 frames in 2.0s (8.0 fps)
registration burst: 513 requests in 4.06s
registration outcomes: 409 no-face x513
GET /api/faces/known -> 200 {"known": []}
POST empty name -> 400 {"error": "the name must not be empty", "reason": "bad-name"}
list file after burst: exists=False
DELETE unknown -> 404 {"error": "'Nobody' is not registered", "reason": "bad-name"}
snapshot: 200 image/jpeg
```

怎么读：

- 4.06 s 里 4 个并发线程发了 513 次注册，每次注册在锁内做 3 次 landmarker 推理（共 1539 次推理），`/api/status` 的中位数 4.2 ms、p95 14.3 ms，不比空闲基线（3.1 / 21.0 ms）差——事件循环没有被注册占住。
- 同一个窗口 MJPEG 交出 38 张图（7.6 fps），空闲基线 8.0 fps，结束后 8.0 fps：画面连续，没有断流或积压。
- 全程 `data\known_faces.json` 不存在：合成场景没有人脸，每次注册都在写盘前被 `no-face` 拒绝，失败路径零写入。
- `404` 的 reason 用 `bad-name`（契约枚举里没有 not-found，见实现说明「票面外的决定」）。

## 2 名单加载、删除落盘、重启后仍在（真实 HTTP + 真实重启）

预置名单（模拟彩排期已注册的名字，用同一模块写文件）：

```
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from rvm.analysis.face_store import FaceStore; s=FaceStore('data/known_faces.json'); s.replace({'Alice Ng':[0.1,0.2,0.3],'Bob':[0.4,0.5,0.6]}); s.save()"
```

启动（显式给 `--known-faces`，验证 CLI 参数）：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099 --known-faces data/known_faces.json`

```
GET after start (loaded from --known-faces): {"known":["Alice Ng","Bob"]}
DELETE Alice Ng: {"removed":true,"known":["Bob"]}
file on disk after delete: {"version": 1, "faces": {"Bob": [0.4, 0.5, 0.6]}}
DELETE again: 404 {"error": "'Alice Ng' is not registered", "reason": "bad-name"}
```

停进程，用同一条命令重启：

```
GET after restart: {"known":["Bob"]}
```

怎么读：启动时读文件（两个名字）→ 删除接口返回后磁盘上已只剩 `Bob`（立即落盘，不是退出时才写）→ 重复删除 404 → 重启后仍是 `Bob`（删掉的名字没有复活）。

## 3 损坏文件降级

`data/known_faces.json` 写入 `{ this is not json` 后启动同一命令：

```
GET with corrupt file: {"known":[]}
status: 43 frames served
known-face list data\known_faces.json is corrupt (Expecting property name enclosed in double quotes: line 1 column 3 (char 2)); starting with an empty list
```

怎么读：服务照常启动、画面照常出（43 帧），名单为空并有 WARNING，没有崩。

## 复现

1. 上述三个终端命令按序执行即可；探针脚本只依赖标准库。
2. 自检后已删除 `data/known_faces.json` 与 `data/`（`.gitignore` 忽略的运行期数据，不进仓库）。
3. 未验证：真实摄像头前注册一张真脸再重启识别——本机没有可用的真人脸素材，`--no-camera` 的合成场景没有人脸，这一条留给 05 号集成票的动态门。
