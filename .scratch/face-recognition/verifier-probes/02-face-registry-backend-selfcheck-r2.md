# 02 服务端人脸注册 — 真机自检（r2 返工，新鲜读数）

日期：2026-11-09 ｜ 代码：本票 r2 提交（`face_store._parse` 等长校验、`FaceRecognizer._nearest` 宽度守卫、`register_face` 名单锁）
说明：r1 的 `02-face-registry-backend-selfcheck.md` 未改动；本文件是 r2 代码的新鲜读数，端口与名单路径都与 r1 不同（8099 当时被 03 号票的服务器占用）。

## 1 注册爆发期间 status / MJPEG（端口 8123，自有服务器）

命令（两条，第二条在服务器起来后跑）：

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8123 --known-faces "$env:TEMP\rvm-r2-selfcheck\known_faces.json"
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\02-face-registry-backend-selfcheck-r2.py --base http://127.0.0.1:8123 --list-file "$env:TEMP\rvm-r2-selfcheck\known_faces.json"
```

读数（退出码 0，原文另存 `_r2-selfcheck-run.txt`）：

```
source=synthetic frames=21
analysis: enabled=True ready=True face_recognition=True
list file before: C:\Users\joe\AppData\Local\Temp\rvm-r2-selfcheck\known_faces.json exists=False
status baseline (idle): n=36 median=3.6ms p95=19.7ms max=27.7ms
status during burst: n=71 median=4.5ms p95=9.9ms max=27.1ms
status after burst: n=35 median=4.3ms p95=23.6ms max=27.0ms
mjpeg baseline: 27 frames in 2.0s (13.5 fps)
mjpeg during burst: 27 frames in 4.25s (6.4 fps)
mjpeg after burst: 27 frames in 2.0s (13.5 fps)
registration burst: 329 requests in 4.09s
registration outcomes: 409 no-face x329
GET /api/faces/known -> 200 {"known": []}
POST empty name -> 400 {"error": "the name must not be empty", "reason": "bad-name"}
list file after burst: exists=False
DELETE unknown -> 404 {"error": "'Nobody' is not registered", "reason": "bad-name"}
snapshot: 200 image/jpeg
```

`frames=21` 说明这是刚起的进程（不是别处遗留的服务器）；`--known-faces` 指向仓库外临时路径，未碰仓库 `data/`。
结论：329 次注册请求期间 status p95 = 9.9 ms（空闲 19.7 ms），MJPEG 未停流（6.4 fps vs 空闲 13.5 fps，帧持续到达，4 个注册线程与 4 次推理并发时掉到一半是预期代价）；失败路径零写入（文件始终不存在）。

## 2 混维名单文件：启动降级而不是崩服务（端口 8124）

名单文件（仓库外）：`%TEMP%\rvm-r2-wrongwidth\known_faces.json`
内容：`{ "version": 1, "faces": { "Alice": [0.5, 0.25], "Bob": [0.5, 0.25, 0.125] } }`

命令：

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8124 --known-faces "$env:TEMP\rvm-r2-wrongwidth\known_faces.json"
```

读数：

```
server pid=10972 alive=True
GET known -> 200 {"known": []}
GET status -> 200
RVM serving on http://0.0.0.0:8124/  (320x240 @ 15 fps, source: synthetic)
known-face list C:\Users\joe\AppData\Local\Temp\rvm-r2-wrongwidth\known_faces.json is corrupt (embedding for 'Bob' has 3 values, the others have 2); starting with an empty list
```

同一场景下连续两次 `/api/status` 的 `frames` 从 15 涨到 41（间隔 2 s），说明名单被判损坏后画面泵仍在跑。

## 3 这次真机没证到什么（UNVERIFIED）

- 真脸注册 → 识别闭环：`--no-camera` 的合成场景没有人脸，201 路径在真机上仍是 409 `no-face`（与 r1 同一边界，05 号集成票承接）。
- 同名并发双 POST 的真机读数：合成场景下两个请求都会先撞 `no-face` 409，走不到重名检查；这条由 `tests/test_face_api.py::test_two_registrations_of_one_name_leave_one_entry` 在进程内证明（`asyncio.to_thread` + 真 HTTP，变异删除锁后该测试红）。
- 宽度守卫的真机读数同上：没有人脸就没有 `_nearest` 调用；由 `tests/test_recognition.py` 与 `tests/test_face_api.py::test_a_hand_written_list_of_the_wrong_width_does_not_stop_the_stream` 证（变异后泵任务以 `ValueError: operands could not be broadcast` 死亡）。
