# 05 — 集成测试与探针收编

**Status:** resolved
**Blocked by:** 02, 03, 04
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/05-integration-selfcheck.md`）

## What to build

写一张把多张票能力串起来压一遍的集成测试：注册一张脸 → 身份行出现名字 → 重启服务后仍能识别 → 删除后消失。并把实现期各票验收门留在 `.scratch/face-recognition/verifier-probes/` 的持久探针按红绿纪律收编进正式套件。

## Acceptance criteria

- [ ] 新增跨票集成测试：注册、识别、重启、删除四步走通，测试自己起停真实服务端 [AS-1, AS-2, AS-3]
- [ ] 集成测试覆盖一条失败路径（无脸或重名），断言服务仍可响应 [AS-4]
- [ ] 探针目录有持久探针时收编为正式测试（重写到套件标准），目录为空则在报告里声明 none [AS-5]
- [ ] 全套测试通过，无新增依赖 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_integration_faces.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`

## 写域

- `tests/test_integration_faces.py`（新增）
- `.scratch/face-recognition/verifier-probes/`（只读收编，不改历史探针原文）

## 开工包

- **写域**：`tests/test_integration_faces.py`, `.scratch/face-recognition/verifier-probes/`

- 复用 `tests/test_face_api.py` 的启动方式；端口用高位随机端口，避免与演示实例冲突。
- 名单路径用 `tmp_path` 注入，不碰仓库里的 `data/known_faces.json`。
- 重启用同一临时目录起第二个进程或第二个 app 实例，断言名单仍在。
- 收编探针时保留原始探针文件，新增套件测试另行命名。
- **尺寸上限**：≤300 行 / 2 文件。
- **估算**：预计 40 分钟 / 180 步。

## 验收包

- **判据**：AS-1、AS-2、AS-3、AS-4、AS-5；集成测试必须真实起服务端，不允许只 mock。
- **首攻靶**：重启是否真的重读文件、删除是否真的落盘、失败路径后服务是否还能响应、探针收编是否只是抄一遍。
- **相关 AS 摘录**：AS-1 注册闭环；AS-2 展示；AS-3 持久化；AS-4 失败；AS-5 不回归。

## 完成条件

集成测试绿、全套绿；独立动态门在干净副本里重跑同一命令并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

1. **AC → 证据**

   - AC-1（注册 → 识别 → 重启 → 删除四步、测试自己起停真实服务端）→
     `tests/test_integration_faces.py:138` `test_a_face_is_registered_recognised_across_a_restart_and_forgotten`：
     注册 `:147-151`（201 + `samples: 3` + 文件内容 `{"version":1,"faces":{"Alice Ng":[...]}}`）、识别 `:152`
     （`GET /api/faces/identities` 出现 `Alice Ng`、`confidence == 1.0`）、重启 `:157`（第二个 app 实例、同名同置信度）、
     删除 `:159-163`（`{"removed": true, "known": []}`、文件变 `{}`、下一 tick 无人被认出）。服务端由
     `:123` `running_server` 起停：真 `web.AppRunner` + `TCPSite(127.0.0.1, 0)`，端口断言 `:131` `port > 1024`。
   - AC-2（失败路径 + 服务仍可响应）→ `:167` `test_a_refused_registration_leaves_the_file_alone_and_the_server_working`：
     重名 409 `name-exists` 且文件字节不变 `:178-181`、无脸 409 `no-face` 且文件字节不变 `:185-188`、
     `GET /api/status` 200 与 `GET /api/faces/known` 仍正确 `:191-192`、随后同一实例再注册成功 201 `:193-196`。
   - AC-3（探针收编）→ `:258` `test_real_processes_carry_the_registry_and_survive_a_corrupt_one`，重写自
     `verifier-probes/02-r2-verifier-persist.py`（真 `run_server.py` + `--known-faces`）：第一次 `:274`、
     重启 `:277`、DELETE + 落盘 `:278-282`、第三次进程 `:284`、混合宽度降级 `:291` + 泵仍在跑 `:293-297` +
     `corrupt` 告警 `:300`。其余探针的分类见报告「探针收编清单」。
   - AC-4（全套绿、无新增依赖）→ `573 passed in 28.89s`（本票 +3）；新增 import 只有 `aiohttp`/`cv2`/`numpy`/
     `pytest` 与标准库，全部既有依赖。

2. **假设**（门可以逐条打破）

   - `runner.addresses[0][1]` 在 `setup()`+`start()` 之后给出真实绑定端口；`bind(("127.0.0.1",0))` 后立刻关闭的端口在子进程绑定前不会被别人抢走。
   - 泵产出的每一帧交给桩 landmarker 的答案都相同，所以「最近三帧平均」的均值就等于该向量，`1 - 距离` 精确为 `1.0`；这也是 `EMBEDDING` 字面量的来源。
   - `register_face` 的三帧取样发生在请求时刻而非分析时刻（`src/rvm/server/session.py:643-665`），因此在请求前把 `_detect` 换成「无脸」是确定性的。
   - `/api/status` 与 `/api/faces/identities` 都会经 `features()` 问 `available`（`src/rvm/server/session.py:582-593`），而 `available` 会真的加载模型（`src/rvm/analysis/recognition.py:157-183`）；测试因此预置 `_failure` 让答案是「不可用」。
   - 子进程 60 s 内能起来（本机 `--no-analysis` 实测 1.67 s，`05-integration-selfcheck.md`）。
   - `process.terminate()` 足够结束服务；本票不断言优雅退出。

3. **我知道没覆盖什么**

   - 没有摄像头：本文件里没有任何一次**真 landmarker** 注册，注册链路的取样本用桩 `_detect`（`:66`）。真模型的注册读数在 02 号票与本票自检探针（`05-integration-selfcheck.md`，那里真模型加载并给出 409 `no-face`）。
   - 子进程测试用 `--no-analysis`：CLI + 分析开启的真机路径只在自检探针里跑，不在套件里。
   - 面板 UI 未驱动：注册按钮/名单/删除的前端行为属 04 与 07 号票；本票只断言面板读的 `/api/faces/identities`。
   - HTTP 层并发（注册与删除在端点级交错）未测：06 号票的互斥只在方法级（`tests/test_face_store.py:290,330`）有确定性测试，其报告已列此族为未覆盖。
   - 损坏名单的断言咬的是日志里出现子串 `corrupt`（`:300`），换成别的措辞会红；这是有意的格式耦合，但不是行为契约。

4. **复现命令**

   - `.venv\Scripts\python.exe -m pytest tests/test_integration_faces.py -q`（3 passed，约 5.6 s）
   - `.venv\Scripts\python.exe .scratch/face-recognition/verifier-probes/05-integration-selfcheck.py`（11 passed，真进程 + 真模型）

5. **我认为最脆的一处**

   `:106` `wait_for_identity` 轮询的是**快照**端点：注册返回 201 时识别结果还是注册前那一 tick 的，必须等下一 tick 才看得到名字。所以这条断言对「镜像没更新」是**慢红**（15 s 超时后报 timeout）而不是快速断言失败——M1 变异体就是这么红的（`05-mutation-run.txt` 第 10 行）。攻击者若要打这张票，第一个动作应是删掉 `_publish_faces` 里的 `replace_known_faces`：它会红，但要等满超时，看起来像挂起而不是断言失败。其次是 `runner.addresses`/自由端口竞态：如果 8099 之类被演示实例占用，本测试不受影响（每次都取随机端口），但 `bind`-then-close 的窗口在极端负载下可能被抢。

6. **票面外的决定**

   - 决定：把 02-r2-verifier-persist 的两段（跨进程持久化、混合宽度降级）并进**一条**测试 / 理由：每次进程启动实测约 1.7 s，另立一条只是多一次启动 / 影响面：两段共享一次 `--no-analysis` 配置，失败靠断言文本区分阶段。
   - 决定：桩掉 emotion/gesture 的 `_failure` 而不只桩 `detect` / 理由：`features()` 会问 `available` 并真的加载两个 MediaPipe 模型，实测把这条测试从 0.48 s 拖到 2.76 s，且让「无模型机器」变成另一种未定义行为 / 影响面：测试依赖 `_failure` 这个内部失败缓存属性名。
   - 决定：失败路径测试末尾追加一次成功注册 / 理由：只断言 409 不能区分「服务还能干活」与「错误处理器还能回话」 / 影响面：多一次 201 POST，多钉住一条「拒绝后仍可写」。
   - 决定：子进程测试标 `pytest.mark.slow` / 理由：单条约 5 s，是套件里最慢的一条，标记只为可读性（默认不筛） / 影响面：`--strict-markers` 下 marker 已在 `pyproject.toml` 注册，无新增配置。
   - 决定：不收编 02-mirror-sync / 06-race / 02-pumpguard 探针 / 理由：它们的断言已逐条落在 `tests/test_face_api.py:519,538,552,574` 与 `tests/test_face_store.py:290,330` / 影响面：套件不新增重复测试；清单与逐条对应写在报告里。
   - 决定：测试文件压到 300 行（票面上限）而把真机读数放探针 / 理由：尺寸上限，且真机读数不属于套件回归 / 影响面：`05-integration-selfcheck.*` 三个文件在探针目录，不改历史探针。

## Verdicts

- 2026-11-09 r1 VERIFIED 7671388 — 四步链与失败路径经独立探针与全套件在干净副本重跑皆绿，四个变异全被杀死，收编清单逐项复验属实｜报告：.scratch/face-recognition/reports/05-r1-verifier.md｜模型路线：未标注（派发未带 --model）
- 2026-11-09 r1 VERIFIED 7671388 — 四步链与失败路径经独立探针与全套件在干净副本重跑皆绿，四个变异全被杀死，收编清单逐项复验属实｜报告：.scratch/face-recognition/reports/05-r1-verifier.md｜模型路线：swe-2-high
