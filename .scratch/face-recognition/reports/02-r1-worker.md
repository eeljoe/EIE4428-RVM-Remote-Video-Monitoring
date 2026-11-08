# 02 服务端人脸注册与持久化 — worker r1 报告

票：`.scratch/face-recognition/issues/02-face-registry-backend.md`（Status: claimed）
实现提交：`5adcede feat: 服务端人脸注册（三帧平均、名单落盘、409/503 零写入）`

## 概览

新增 `rvm.analysis.face_store`（名单加载/原子保存/增删/整体替换），识别器加 `sample_faces` 与「复制后换引用」的名单写法，会话层加 `_inference_lock`（`_analyse` 与注册共用）与 `register_face`/`remove_face`，`app.py` 加三个端点与 `--known-faces`。失败一律 `{"error","reason"}` + 契约枚举；409/503 在写盘前拦下。

## IMPLEMENTED（AC → 证据）

AC 原文逐条对应见票面 `## 实现说明` §1 的表（代码行号 + `文件:行号`），这里是摘要：

| AC | 证据 |
|---|---|
| 取样本接口，无脸 → 空列表 | `recognition.py:262`；`tests/test_recognition.py:266`、`:282` |
| 推理离开事件循环、与 `_analyse` 共用串行锁、期间 status/MJPEG 不中断 | `session.py:447/679`、`app.py:381`（`asyncio.to_thread`）；`tests/test_face_api.py:389`、`:436`、`:414`；真机读数 §1 |
| `known_faces` 整体替换（不原地改、无 dict 迭代冲突） | `recognition.py:234/246/255/285`；`tests/test_recognition.py:296`、`:308`、`:321`、`:333`；`tests/test_face_store.py:124`、`:136` |
| 名单加载/原子保存/增/删；缺失空名单、损坏告警空启动 | `face_store.py:71/101/137/143/152`；`tests/test_face_store.py:35`、`:54`、`:65`、`:81`、`:93`、`:106` |
| `POST /api/faces/known` 三帧平均落盘、返回样本数、失败契约体 | `session.py:611`、`app.py:361`；`tests/test_face_api.py:155`（4 帧 → 只平均后 3 帧，磁盘 `20.0` = 手算）、`:240`、`:253` |
| 409 / 503 分类且零写入 | `tests/test_face_api.py:173`、`:186`、`:200`、`:214`（409 + 文件不存在/字节未变）、`:269`、`:281`、`:295`（503 + 文件不存在）、`:353`（500 写失败，内存回滚） |
| `GET`/`DELETE` 可用、删除落盘、缺失 404 | `app.py:375/401`、`session.py:663`；`tests/test_face_api.py:318`、`:330`、`:344`；真机 §2 |
| `--known-faces` 默认 `data/known_faces.json` + 进 `.gitignore` | `face_store.py:44`、`app.py:567/603`；`tests/test_face_store.py:162`、`:166`；`tests/test_face_api.py:462`、`:472`；真机 §2 显式传参 |
| 全套不回归 | 541 passed（见 TESTS） |

## COMMITS

- `3eae186 chore: 认领 02 服务端人脸注册`（只含票文件）
- `53fcae0 feat: 人脸名单存储（原子落盘、缺失与损坏降级）`（`face_store.py` + `test_face_store.py` + `.gitignore`）
- `6e9e1da feat: 识别器单帧取样接口与名单整体替换`（`recognition.py` + `test_recognition.py`）
- `5adcede feat: 服务端人脸注册（三帧平均、名单落盘、409/503 零写入）`（`session.py` + `app.py` + `test_face_api.py` + 真机探针 md/py）

票面 `## 实现说明` 六节被并行会话的提交 `02c80b3` 顺手带进历史（该提交同时改了 01 号票面字段）。内容已入库，可用 `git show HEAD:.scratch/face-recognition/issues/02-face-registry-backend.md` 核对；`5adcede` 里没有它是因为索引在提交前已被那次并行提交清空。工作树里没有本票遗留的未提交改动。

## TESTS

### 票面命令与退出码

```
$ .venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py -q
................................................................         [100%]
exit=0
```
（同一命令去掉尾部 `-q` 的汇总：`64 passed in 7.96s`，exit 0）

```
$ .venv\Scripts\python.exe -m pytest
........................................................................ [ 79%]
........................................................................ [ 93%]
.....................................                                    [100%]
541 passed in 20.60s
exit=0
```

### 撤修复即红（三处，均先备份 → 改 → 跑 → 还原 → 核哈希）

**1) 名单复制后换引用 → 改回原地插入**

```
>       assert held is not recognizer.known_faces, "in-place insert is the bug this pins"
E       AssertionError: in-place insert is the bug this pins
E       assert {'joe': array([0., 0., 0., 0.]), 'amy': array([1., 1., 1., 1.])} is not
E              {'joe': array([0., 0., 0., 0.]), 'amy': array([1., 1., 1., 1.])}
tests/test_recognition.py:303: AssertionError
FAILED tests/test_recognition.py::test_registering_a_face_leaves_the_previous_mapping_untouched
exit=1
```

**2) `POST` 的 `asyncio.to_thread` → 改成在事件循环里直接调**

```
>       assert ticks >= 10, f"the loop only turned {ticks} times during the request"
E       AssertionError: the loop only turned 1 times during the request
E       assert 1 >= 10
tests/test_face_api.py:411: AssertionError
FAILED tests/test_face_api.py::test_registration_does_not_block_the_event_loop
exit=1
```

**3) `_analyse` 与 `_sample_faces` 去掉 `_inference_lock`**

```
>           assert not posting.done(), "registration must wait for the inference lock"
E           AssertionError: registration must wait for the inference lock
E           assert not True
tests/test_face_api.py:448: AssertionError
FAILED tests/test_face_api.py::test_registration_and_analysis_take_the_same_lock
exit=1
```

**还原核哈希**（三份文件与变异前逐字节相同）：

```
632657A9E851340606D1917BB14729D4C3289FB22B015F41E02347F6B0F706EB  recognition.py
81EFD90350F312FF7470A6AF0FA75A7BB354699AF1B1A788A470468A97E118C6  session.py
6EA20C051084FADFDF998B5A852282B4E10D5F46C1C3D2F8CC2E5B67181CB926  app.py
```
还原后定向 64 passed、exit 0；全套 541 passed、exit 0。

### 真机自检（票面标「必须」）

证据落盘：`.scratch/face-recognition/verifier-probes/02-face-registry-backend-selfcheck.md`
驱动脚本：`.scratch/face-recognition/verifier-probes/02-face-registry-backend-selfcheck.py`

命令：

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099
.venv\Scripts\python.exe .scratch\face-recognition\verifier-probes\02-face-registry-backend-selfcheck.py
```

读数（原文摘录，全文见探针 md）：

```
analysis: enabled=True ready=True face_recognition=True
status baseline (idle): n=36 median=3.1ms p95=21.0ms max=25.1ms
status during burst: n=73 median=4.2ms p95=14.3ms max=19.6ms
mjpeg baseline: 16 frames in 2.0s (8.0 fps)
mjpeg during burst: 38 frames in 4.97s (7.6 fps)
registration burst: 513 requests in 4.06s
registration outcomes: 409 no-face x513
list file after burst: exists=False
```

即：4.06 s 内 513 次注册（每次 3 次 landmarker 推理，共 1539 次）期间 `/api/status` p95 与 MJPEG 帧率都不劣于空闲基线，画面连续；失败路径零写入。另两项真机读数（`--known-faces` 加载 → DELETE 立即改盘 → 重启后只剩 `Bob`；损坏文件告警后空名单启动、43 帧照出）见探针 md §2、§3。

### 环境发现（与票内代码无关）

`tests/test_face_api.py` 顶部有 `cv2.ocl.setUseOpenCL(False)`。原因：本机 OpenCV 4.14 在**工作线程**里跑 Haar 级联后，进程退出时 `clReleaseDevice` 报 `CL_INVALID_OPERATION` 并 abort，整份 pytest 在所有用例通过之后以 `0xC0000409` 退出。最小复现（不含本票任何代码，`src/rvm/analysis/detect.py` 未改）：

```
async def main():
    await asyncio.to_thread(FaceDetector().detect, np.full((96, 160), 10, dtype=np.uint8))
asyncio.run(main())
→ OpenCV: terminate handler is called! ... clReleaseDevice(handle) ... exit=-1073740791
```
关掉 OpenCL 后同一探针 exit=0。该开关只作用于测试进程，产品行为不变。

## 未覆盖

- 真机「注册一张真脸 → 重启 → 识别」：合成场景没有脸，本机无真人素材；留给 05 号集成票的动态门。
- 端点测试里 MediaPipe 被桩替换（边界桩），取样几何本身只由空帧用例与模型加载用例背书。
- 两个进程同时写同一名单文件没有互斥；注册与删除的交错顺序（检查与保存在同一把锁外）未测。
- 非 320×240 分辨率的注册未测。

## 风险 / 门可能先打的地方

1. `_inference_lock` 粒度：删掉 `_analyse` 的 `with` 不会立刻红，而是偶发错误结果或 MediaPipe 崩溃。想打就打这里。
2. `DELETE` 缺失名字的 404 用的是 `bad-name`（枚举里没有 not-found），若门按「404 应带 not-found」判，会记一条口径分歧。
3. 注册与删除共用 `_publish_faces`，但「同名先查后写」不在锁内；两个并发注册同名理论上都能过检查，后写的覆盖前者（同机单操作员场景不会遇到）。

## 收尾自检

逐条回对 diff 与文件，**12 条命中、0 条落空**：

1. 注册推理在 `asyncio.to_thread`（`app.py:381`）——命中。
2. 注册/删除与 `_analyse` 共用 `_inference_lock`（`session.py:447/679`）——命中。
3. `known_faces` 只整体换引用，无原地 `[]=`/`pop`（`recognition.py:234/246/255`）——命中。
4. 失败体 `{"error","reason"}` + 九枚举（`app.py:361`、测试 `assert_contract`）——命中。
5. 409/503 在写盘前返回、文件零写入（`session.py:611` 检查顺序 + 测试断言）——命中。
6. 名单落盘为临时文件 + `os.replace`（`face_store.py:101`）——命中。
7. `GET`/`DELETE` 端点与 404（`app.py:104/106/375/401`）——命中。
8. `--known-faces` 默认 `data/known_faces.json` 且进 `.gitignore`（`face_store.py:44`、`app.py:567`、`.gitignore`）——命中。
9. 只改写域 8 个文件；未动 `docs/DESIGN-dashboard.md`、`tests/test_app.py`（`git show --stat`）——命中。
10. 未改 `src/rvm/analysis/detect.py`（OpenCL 结论归属的依据）——命中。
11. 全套 541 passed、定向 64 passed，exit 0——命中。
12. 真机探针 md/py 已落盘并随实现提交——命中。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 02 | 交票 | 5adcede | reports/02-r1-worker.md | 名单存储+取样+三端点+CLI 全落，定向 64/全套 541 绿，真机 513 次注册零写入且流不断 |
