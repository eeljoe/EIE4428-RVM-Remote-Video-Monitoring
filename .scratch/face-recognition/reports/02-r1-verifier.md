# 02 服务端人脸注册票 — 独立验收报告（r1）

VERDICT: REJECTED — 动态证据全面通过，但一处「名单→识别器镜像同步」变异在全套 541 测试下存活（非等价：注册后本会话识别不到新脸），套件对此行为无牙；另发现混维名单文件可致死 pump 任务的降级缺陷。
HEAD: 5adcede07609c557afe5a1a18b2199aaece37edc
LEDGER: 02-r1-001,02-r1-002,02-r1-003,02-r1-004,02-r1-006,02-r1-008,02-r1-009,02-r1-010,02-r1-011

## 定靶

- 目标提交 `5adcede`（派发方指定）；验收副本 `C:\Users\joe\AppData\Local\Temp\verify-02-r1-5adcede`（gate-kit worktree，detach 于 5adcede）。
- 本票代码面跨多提交（`53fcae0` face_store、`6e9e1da` recognition、`5adcede` 端点与测试）；其后 `478b879`/`67270fc` 仅文档，`git diff 5adcede..HEAD -- src tests .gitignore` 为空 → 副本与当前 HEAD 代码等价。工作树未提交改动属 01 票并行 rework，不计入。
- 尺寸：本票面 diff 8 文件 +1269/−15（产品 ~524 + 测试 ~745，条目 02-r1-001）。票面开工包已声明「本票最小面 5 产品 + 3 测试、超限按 OVER-LIMIT 分级」，派发清单列全 8 文件 → WARN，单一关切，非 mixed concerns。

## 判据重建（票面 AC → 判定）

| 判据 | 判定 | 证据 |
|---|---|---|
| C1 取样接口：无脸空表 / 一帧多脸多条 / 维度一致 | PASS | 探针 sample 7/7（02-r1-004）：真 landmarker 空帧+噪声帧→`[]`；两张 478 关键点脸→2 条各 1434 维互异向量；无模型→`FaceSamplingError` |
| C2 注册=最近三帧各一脸平均、201 契约、落盘 | PASS | 探针 api（02-r1-008）：201 `{name,samples:3,known}`；磁盘向量==手算均值 20.0；4 帧只取后 3（取样恰 3 次） |
| C3 无脸/多脸/重名 409 + bad-name 400，全部零写入 | PASS | 探针 api 34/34（02-r1-008）：409 三态 + 8 种 bad-name + 非 JSON/非 dict 体 400；每类前后文件 sha256 一致或不存在；真进程 no-face 409（02-r1-009） |
| C4 503：analysis-disabled / models-loading / unavailable | PASS | 真进程：暖机窗口抓到 503 `models-loading`；`--no-analysis` → `analysis-disabled`；副本模型文件改名 → `unavailable`（02-r1-009）；进程内桩推理失败 → `unavailable` 且不写文件（02-r1-008） |
| C5 GET/DELETE/404 + 重启持久化 + 损坏降级 | PASS | GET 有序、DELETE 立即落盘、404 契约体（02-r1-008）；真进程重启名单仍在、删除文件同步、`--known-faces` 与默认 `data/known_faces.json` 均生效、坏 JSON/坏结构降级空名单+告警不崩（02-r1-010） |
| C6 注册期间 status/MJPEG 不中断；100+ 注册无 dict-changed-size | PASS | stress（02-r1-011）：24 次 POST 真推理爆发期间 status p95=27.4ms、MJPEG 6s 收 68 帧；churn（02-r1-006）：3000 次增删 ×4 迭代线程 + 120 次 register/remove 周期零异常 |
| C7 注册与 `_analyse` 同锁串行、不经事件循环 | PASS | 代码核 `session.py:478/682`；变异 M2（锁换 `_audio_lock`）被 `test_registration_and_analysis_take_the_same_lock` 杀死；`asyncio.to_thread`（app.py:394）+ C6 实测延迟 |
| C8 名单整体替换非原地改 | PASS | `add/remove/replace` 复制后换引用（face_store.py:137-157、recognition.py:234-260）；churn 探针实证无迭代异常（02-r1-006） |
| C9 `--known-faces` 生效 / 默认路径 / `.gitignore` | PASS | 真进程 `--known-faces` 自定义路径读写生效；cwd 默认 `data/known_faces.json`（02-r1-010）；`.gitignore:15` 命中 `git check-ignore` |
| C10 定向+全套 pytest 绿、测试非永真 | **FAIL** | 定向 64 绿（02-r1-002）、全套 541 绿（02-r1-003）；但变异 M4 在全套下存活 → 套件对镜像同步无牙（FINDINGS-1） |

## FINDINGS

1. [Blocking] tests/ — `_publish_faces` 的 `self.face_recognizer.replace_known_faces(faces)`（session.py:703）无任何测试钉住：变异 M4 删除该行后定向 64 与全套 541 全绿。非等价——FaceStore 与文件更新但识别器镜像陈旧：注册的脸本会话 `recognize()` 认不出（重启才生效）、删除的脸继续被认出，「当场见效」静默失效。建议收编 `verifier-probes/02-mirror-sync-verifier-test.py`（已在副本实证：真码 3 绿、变异 3 红、sha1 还原）。confidence: HIGH
2. [Important] src/rvm/analysis/face_store.py:176 — `_parse` 只校验向量「非空、有限、一维」，不校验各条目维度一致：`{"faces":{"Bob":[0.75]*8}}` 合法载入后，首个检出人脸的分析 tick 在 `recognition.py:347` `np.linalg.norm(embedding - registered)` 抛 `ValueError` → `_analyse`→`run_once`→`run_forever`（session.py:784-797 无兜底）→ pump 任务死亡、画面流永久停摆，违反 spec「损坏时…不崩服务」。触发面：手改文件或 landmarker 升级换维度后的旧名单。建议加载时校验全体向量等长（或等长于模型产出），不等长按损坏降级；或 `_nearest` 内 try/except 跳过坏条目。confidence: HIGH
3. [Nit] src/rvm/server/session.py:621 — `register_face` 的 name-exists 检查与 `_publish_faces` 之间无锁：两个并发同名 POST 可双双 201（实现说明 §3 已自陈）。演示面影响小，建议 `register_face` 整体取一把名单锁或在接受前复检。confidence: MEDIUM
4. [FYI] `DELETE` 404 复用 `reason=bad-name`（实现说明 §6 已声明）：契约枚举无 `not-found`，状态语义靠 404 承担，前端要按此判「不在名单」。confidence: MEDIUM

## RED-TEAM ATTEMPTS

- 「我若偷懒会在哪 5 处省事」预测清单：① 平均取全部帧而非后三帧（→M1 被杀）；② 更新名单忘同步识别器镜像（→M4 **存活**，即 FINDINGS-1）；③ 字典原地改省复制（→churn 探针 + `test_identifying_while_the_list_changes_never_raises`）；④ 推理直接跑事件循环（→M2 锁变异被杀 + stress 实测）；⑤ 失败路径顺手写文件（→api 探针逐类 sha256 对零写入）。
- 畸形/边界输入：8 种 bad-name、非 JSON 体、JSON 数组体、41 字超长名、控制字符名、含 `/` 名（%2F 可删，无路由死角）→ 全部按契约 400/404，零写入。
- 负向路径：409×3、404、503×3、`samples-missing` 409（直调实证）、损坏/坏结构文件降级 → 全部实测通过。
- 时序/阻塞/竞态：真进程爆发期间 status p95 27.4ms、MJPEG 不断流；3000 增删 ×4 迭代线程零异常；锁变异被杀。
- 状态残留与幂等：重名 409 文件不变；删除后再删 404；重启名单仍在；写失败回滚（套件 test_a_failed_write 背书）。
- 序列化形状：坏 JSON、坏结构、非 dict 请求体 → 降级或 400。
- 环境投毒：模型文件缺失 → `unavailable` 降级不崩；名单路径指向不存在目录 → mkdir 后正常写。
- 变异等价性：4 变异 3 杀 1 存活，存活者非等价（对拍：killer test 变异态 3 红/真码 3 绿）。
- 未选族：权限/沙箱（名单路径为操作者自选 CLI 参数，无越权面）、宿主契约（无宿主解析算法可重放）、跨包接缝（进程内与真进程契约已两边对拍）。
- 安全扫描：`git diff 3eae186~1..5adcede` 密钥/私钥/令牌正则 0 命中。

## NOT RUN / UNVERIFIED

- 真人脸注册→识别闭环：合成场景与仓库素材均无真人脸，真机层只能证到「无脸 409 + 各 503 + 持久化」；201 路径在真 HTTP 上由桩 landmarker 走完。实现说明 §3 已自陈同一边界，05 集成票承接。
- 账本条目 02-r1-005（churn 首跑维度笔误崩溃）与 02-r1-007（api 首跑撞 OpenCV 退出 abort，0xC0000409——实现说明 §6 已记的环境怪癖，探针已加同款 `cv2.ocl.setUseOpenCL(False)` 绕行）为失败记录，分别由 02-r1-006/008 的干净重跑取代。

## REMEDIATION

- [test] 收编杀手测试钉住 `_publish_faces` 的识别器镜像同步：目标套件路径 `tests/`；变异描述「`src/rvm/server/session.py` `_publish_faces` 内 `self.face_recognizer.replace_known_faces(faces)` → `pass`」；测试命令 `.venv\Scripts\python.exe -m pytest tests/<收编文件名> -q`；探针测试文件 `.scratch/face-recognition/verifier-probes/02-mirror-sync-verifier-test.py`（真码绿/变异红已实证）。
- [impl] `face_store._parse` 校验所有向量等长（不等长整体按损坏降级为空名单+告警），或在 `FaceRecognizer._nearest` 对维度失配条目 try/except 跳过——堵「合法形状文件致死 pump 任务」的降级缺口。
- [impl]（可并入整改）`register_face` 增删与发布之间加名单锁，消除并发同名双 201。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| REJECTED | 5adcede | .scratch/face-recognition/reports/02-r1-verifier.md | [impl]2 [test]1 | 动态证据全过，但镜像同步变异全套 541 存活（无牙），且混维名单可致死 pump 任务 |
