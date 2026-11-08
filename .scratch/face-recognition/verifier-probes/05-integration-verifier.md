# 05 r1 独立验收门 — 证据记录

- 门：05-integration-tests，r1 verifier（独立动态验收）
- 靶：`7671388`（`git rev-parse HEAD` = `767138845b3adbfb1df1b86c83e73ffeeb55cf93`，与票面提交一致）
- 环境：干净副本 `C:\Users\joe\AppData\Local\Temp\verify-05-7671388`（gate-kit worktree，已 cleanup）；python 用主仓 `.venv`；副本里 `rvm` 经 `pythonpath=["src"]` 解析到副本代码
- 账本：`.scratch/face-recognition/ledger/05-r1.jsonl`（05-r1-001/002/003/005；004 是路径笔误的失败调用，无证据价值）

## 1. 真实服务端，不是 mock

证据来源三重：

- 读代码：`tests/test_integration_faces.py:126-128` 真 `web.AppRunner` + `web.TCPSite(runner, "127.0.0.1", 0)`；`:213-218` 真 `subprocess.Popen([sys.executable, "run_server.py", "--no-camera", "--no-analysis", "--port", <port>, "--known-faces", <tmp>, ...])`；`:206-209` 用 `socket.bind(("127.0.0.1",0))` 取自由高位端口，`:209` 断言 `port > 1024`；名单路径 `:144` `tmp_path / "data" / "known_faces.json"`，不碰仓库 `data/`
- 独立探针 `05-integration-verifier.py`（本会话新写，自己的驱动，非 worker 代码）：每个实例先 `socket.create_connection` 直连证明真监听，再 HTTP 断言。输出原文：

```
LISTENING 127.0.0.1:65282 (peer ('127.0.0.1', 65282), port>1024=True)
LISTENING 127.0.0.1:58976 (peer ('127.0.0.1', 58976), port>1024=True)
LISTENING 127.0.0.1:58979 (peer ('127.0.0.1', 58979), port>1024=True)
```

- 真机自检复跑（账本 05-r1-005）：4 个真 `run_server.py` 进程、分析开、真 MediaPipe 模型；日志含 `landmark_projection_calculator.cc:81`，证明真 landmarker 推理跑过。`11 passed, 0 failed`。

## 2. 四步链路（注册→识别→重启→删除），每步证据

账本 05-r1-003（独立探针输出原文）：

```
STEP1 register status=201 body={'name': 'Carol Wu', 'samples': 3, 'known': ['Carol Wu']}
STEP2 identities=[{'name': 'Carol Wu', 'confidence': 1.0, 'bbox': [80, 48, 0, 0]}]
FILE1 {"version": 1, "faces": {"Carol Wu": [0.5, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.5, 0.0]}}
STEP3 after-restart identities=[{'name': 'Carol Wu', 'confidence': 1.0, 'bbox': [80, 48, 0, 0]}]
STEP4 delete status=200 body={'removed': True, 'known': []}
FILE2 {"version": 1, "faces": {}}
POST-DELETE identities=[]
POST-DELETE /api/status=200
```

第二实例与第一实例无共享内存（独立 `StreamSession`+`FaceStore`），STEP3 只能由重启重读文件解释；FILE2 证明删除落盘。

真机侧同一链路（05-r1-005）：`--known-faces` 名单跨 3 个真进程 `['Alice Ng'] → []`，DELETE 后 `disk faces={}`。

## 3. 失败路径后服务仍可响应

账本 05-r1-003 原文：

```
FAILPATH duplicate status=409 body={'error': "'Dan' is already registered", 'reason': 'name-exists'}
FAILPATH file-unchanged=True
FAILPATH no-face status=409 body={'error': 'no face was found in the recent frames', 'reason': 'no-face'}
FAILPATH file-unchanged=True
FAILPATH /api/status=200
FAILPATH retry status=201 body={'name': 'Eve', 'samples': 3, 'known': ['Dan', 'Eve']}
```

两种拒绝都断言文件字节不变；retry 201 区分「服务还能干活」与「只是错误处理器活着」。

## 4. 变异证据（干净副本内，gate-kit mutate）

| # | 变异（产品代码一处） | 定向测试 | 红签名（本轮实跑） | 还原 sha1 |
|---|---|---|---|---|
| Ma | `session.py:193` `replace_known_faces(self.face_store.load())` → `pass` | 四步链测试 | `AssertionError: timed out after 15.0s waiting for 'Alice Ng' to be recognised`（test:82，慢红，worker 已披露） | EF759A7B…92A8 一致 |
| Mb | `session.py:732` `self.face_store.save()` → `pass` | 四步链测试 | `FileNotFoundError: …\data\known_faces.json`（test:154 磁盘断言） | 同上 |
| Mc | `session.py:655` `if not faces:` → `if False:` | 失败路径测试 | `IndexError` → aiohttp 500，断言 `== 409` 失败 | 同上 |
| Md | `app.py:603` `known_faces=args.known_faces,` → `known_faces=None,` | 子进程测试 | `assert {'known': []} == {'known': ['Alice Ng', 'Bob']}`（test:274） | FD47B487…955 一致 |

四条变异各只杀对应测试（-x 首红即停，红签名与 worker 预测逐字吻合）；还原后定向+全套复绿（05-r1-001/002 即还原后读数）。每条测试都有杀得死它的变异，咬合力成立。

## 5. 探针收编核查

- 收编对象 `02-r2-verifier-persist.py`（184 行探针）→ `test_integration_faces.py:258`：是**重写**不是照抄——改 pytest/`tmp_path`/`ServerProcess` 自由端口，合并两阶段并新增「第三进程回读删除后名单」（原探针只查磁盘）。原探针第 8 腿（uniform 错宽度仍加载，`:164-178`）未搬进新测试，但等价断言已在套件 `tests/test_face_store.py:105 test_a_list_of_one_width_still_loads`——无遗漏断言。
- 「已在套件不收编」逐项复验（worktree grep 行号）：
  - mirror-sync 探针 → `test_face_api.py:519,538,552` 三条镜像同步测试均在 ✓
  - pumpguard → `test_face_api.py:574` ✓
  - race part_a → `test_face_api.py:242`；part_b → `test_face_store.py:290`；另有 `:330` remove-vs-remove ✓（02/06 并发族在方法级有确定性测试；HTTP 端点级并发未覆盖，worker 已披露为已知缺口，与 06 报告口径一致）
  - 端点级 reason 枚举 → no-face:198 / multiple-faces:212 / name-exists:226 / bad-name:294,306 / analysis-disabled:322 / models-loading:326 / unavailable:340 / 404:389 / write-failed:398 / samples-missing:194 ✓
- 不收编类目核对：01-* 设计产物、03-* 可读性数值（属 `test_app.py` 写域）、04-* UI 交互（属 04/07 票）、运行残留（`_t.err` 0 字节、`__pycache__`、`04-verifier-probe-lines.txt`）、`04-warmup-probe.py`（无断言一次性探针）——分类成立，无「该收未收」项。

## 6. 套件读数（本轮新鲜）

- 定向：`pytest tests/test_integration_faces.py -q --durations=10` → **3 passed**（7.91s/0.59s/0.22s，真进程那条最慢符合预期），账本 05-r1-001
- 全套：`pytest` → **573 passed in 47.87s**，账本 05-r1-002；与 worker 自报 573 一致
- 提交 `git show --stat 7671388`：仅 `tests/test_integration_faces.py`（+300）与票据（+53）；`src/` 零改动；新 import 仅 aiohttp/cv2/numpy/pytest + 标准库，无新增依赖
- 仓库 `data/` 目录不存在，名单文件只在 `tmp_path`/tempdir 产生
