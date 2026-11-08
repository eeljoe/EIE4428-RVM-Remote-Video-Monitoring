# 05-integration-tests — 真机自检（r1）

工作区：`C:\Users\joe\Desktop\工作学习\study 2026-2027 sem1\EIE4428-Multimedia-Communications\mini-project\EIE4428-RVM\EIE4428-RVM`
Python：`.venv\Scripts\python.exe`（本机 3.13）
日期：2026 本会话；驱动脚本 `05-integration-selfcheck.py`，原始读数 `05-integration-selfcheck-run.txt`。

## 自检口径

本票是集成测试票，没有可点的新控件，所以「真机」= **真进程、真端口、真 HTTP、真模型**：
自检脚本不 import 产品，四个 `run_server.py` 进程各自绑定操作系统给的随机高位端口，全部读数取自
HTTP 响应与磁盘文件。与套件内那条跨进程测试的区别是：套件用 `--no-analysis` 压时间，自检用默认
（分析开、模型真加载），因此它是「CLI + 分析开启」这条真机路径的唯一读数。

## 命令与读数

### 1. 自检探针（真进程，分析开）

```
.venv\Scripts\python.exe .scratch/face-recognition/verifier-probes/05-integration-selfcheck.py
```

exit code 0，`11 passed, 0 failed`。逐条原文：

```
PASS  analysis reported ready before the probe registered  -- features={'enabled': True, 'ready': True, 'face_recognition': True, 'emotion_recognition': True, 'gesture_recognition': True, 'audio_monitoring': False, 'audio_available': True}
PASS  the picture pump is running  -- frames=12
PASS  registering with no face in view is refused and writes nothing  -- status=409 body={'error': 'no face was found in the recent frames', 'reason': 'no-face'} registry_exists=False
PASS  the same server still answers after the refusal  -- known={'known': []}
PASS  forgetting an unknown name is a 404 with the contract body  -- status=404 body={'error': "'Nobody' is not registered", 'reason': 'bad-name'}
PASS  the server shut down without a traceback  -- 00:00:1794168877.007201   28764 landmark_projection_calculator.cc:81] Using NORM_RECT without IMAGE_DIMENSIONS is only supported for the square ROI. Provide IMAGE_DIMENSIONS or use PROJECTION_MATRIX.
PASS  --known-faces list is served by the first process  -- known={'known': ['Alice Ng']}
PASS  a second process serves the same list  -- known={'known': ['Alice Ng']}
PASS  DELETE answers with the contract body  -- status=200 body={'removed': True, 'known': []}
PASS  the deletion reached the file before the reply  -- disk faces={}
PASS  a third process starts from the emptied file  -- known={'known': []}

11 passed, 0 failed
workdir: C:\Users\joe\AppData\Local\Temp\rvm05-selfcheck-ujw8faak
```

读数说明：

- `features` 四项 `True` 说明真模型（MediaPipe face/emotion/gesture）在本机加载成功，`audio_available: True`（麦克风存在，未被本票使用）。
- `landmark_projection_calculator.cc` 那行是 MediaPipe 的 native 告警，出现在真 landmarker 推理时，说明本自检确实跑了模型而不是桩。
- 生成场景里没有人，所以 `POST /api/faces/known` 的诚实回答是 409 `no-face`，且 `registry_exists=False`：失败路径不落盘，与 spec 契约一致。
- 4 个进程各自 200/409/404 全按契约回答；第二、三、四个进程读到的名单只可能来自文件。
- `workdir` 下的 `data/known_faces.json` 是临时目录内的文件，仓库的 `data/known_faces.json` 全程未创建（`git status` 无该文件）。

### 2. 套件内那三条（含跨进程）

```
.venv\Scripts\python.exe -m pytest tests/test_integration_faces.py -q
```

`...` 3 passed，exit 0。耗时见报告的 TESTS 段（跨进程那条 4.90 s，另两条 0.48 s / 0.22 s）。

### 3. 全套

```
.venv\Scripts\python.exe -m pytest
```

`573 passed in 28.89s`，exit 0。本票新增 3 条（570 → 573）。

## 变异读数（证明测试会红，不是只会在绿上躺着）

原始输出：`05-mutation-run.txt`。四个变异体各自只改产品一行，跑对应定向测试，红后从备份原样还原并核 sha256。

| 变异体 | 文件 | 定向测试的失败签名 | 还原 sha256 |
|---|---|---|---|
| M1 重启不再用文件喂识别器 | `src/rvm/server/session.py` | `AssertionError: timed out after 15.0s waiting for 'Alice Ng' to be recognised` | `3011D369…13FCC` 逐字节一致 |
| M2 发布改动不再写文件 | 同上 | `FileNotFoundError: ... data\known_faces.json`（第一次生命周期的磁盘断言） | 同上 |
| M3 无脸拒绝改成继续发布 | 同上 | `IndexError: list index out of range`（`register_face` 取样处，响应不再是 409） | 同上 |
| M4 `--known-faces` 被丢掉 | `src/rvm/server/app.py` | `assert {'known': []} == {'known': ['Alice Ng', 'Bob']}` | `6EA20C05…CB926` 逐字节一致 |

## 未做 / 做不到

- 本机没有摄像头（`--no-camera`），所以**真 landmarker 注册一张真人脸**这一步做不到；套件与自检都用桩 `_detect` 或预置名单。注册路径的真模型推理由 02 号票的端到端读数负责，本票不重复声明。
- 没有驱动浏览器面板：04/07 号票的面板断言与截图归那两张票；本票只断言 `/api/faces/identities` 这个面板读的端点。
