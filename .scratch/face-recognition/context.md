# Context — 人脸识别闭环 + 监控页可读性重做

## 规划段（执行期只读）

### 决策与理由

- 面板注册、当场见效：演示时老师看得见动作，比命令行注册更能说明系统完整。否掉了仅 API 与预置名单两条路。
- 名单存 `data/known_faces.json`，只存名字与嵌入向量，不进 git、不进 zip：名字属于个人数据，公开仓库不该带；现场注册即可。
- 注册取最近三次分析帧、每帧取一张脸求平均，保留 0.6 阈值并显示相似度：几何特征抖动大，单帧注册换角度就认不出；top-2 边际测试被否，漏认风险高于误认。
- 整页重做可读性并简化：第一版参照图被判「可读性太差」；第二版把标签升到 13px、读数 15px、对比度 7.7:1、行高 1.5、去掉冗余框线，用户已签字。
- 码率折线保留，加峰值虚线与 `peak x.xx Mbps` 角标：形状看不出量级，一个数把它钉住；用户点名要这个标注。

### 术语

- 名单：已注册人脸的名字与嵌入向量集合，落盘在 `data/known_faces.json`。
- 嵌入：MediaPipe 人脸关键点按 x/y/z 展平后的向量，约 1400 维。
- 相似度：`1 − 欧氏距离`，不是概率；阈值 0.6。
- 峰值标注：码率折线上缘的峰值虚线与右端数值角标。
- 读数：分析面板里 Face IDs、Faces 等一行行的监控数值。

### 被否方案

- 仅后端 API、面板只读：现场演示动作缺失。
- 预置名单：演示不了「注册」这一动作。
- 只存内存：重启后名单丢失，演示彩排与正式演示之间要重注册。
- top-2 边际测试：误认少一点，但漏认更多，演示时更难看。
- 删掉折线：用户要的是量级，不是删除。

### 相关坑的路径指针

- OpenCV 5 不带级联数据与 API，人脸检测会静默 unavailable：`docs/FEATURES.md`、`requirements.txt`。
- 分析默认关，`run_server.py` 打开、`--no-analysis` 关闭：`src/rvm/server/app.py`。
- 模型加载约 2–3 秒，期间状态是 `pending`：`src/rvm/server/session.py` 的预热线程。
- 右侧面板在 ≥901px 时自身滚动，`max-height: calc(100vh - 102px)`：`src/rvm/web/style.css`。
- 页面静态测试钉住 DOM ID 与远程资源禁令：`tests/test_app.py`。
- 视频 `<img id="stream">` 必须内联 `src=` 且含 `stream.mjpg`：`tests/test_delivery.py`。

### UI 参照图路径

- `.scratch/face-recognition/design/v2/mock-desktop.png`（1440×1000）
- `.scratch/face-recognition/design/v2/mock-mobile.png`（390×844）
- `.scratch/face-recognition/design/v2/mock.html`（自包含）
- 设计说明：`.scratch/face-recognition/design/v2/NOTES.md`

## 执行段

### 票 2

r1:
- **`DELETE` 缺失名字回 404 时 reason 用 `bad-name`** / 理由：契约枚举里没有 `not-found`，而 404 状态由契约固定 / 影响面：前端要按 404 + `bad-name` 判「这个名字不在名单里」。
- **每次取样单独取锁，而不是整个注册持锁** / 理由：把编码线程的最长阻塞压到一次推理（约 20 ms），仍保证「两处不同时推理」 / 影响面：注册总耗时可能被分析 tick 插队拉长几十毫秒。
- **注册要求最近三帧每帧恰好一张脸** / 理由：多脸时「取一张」没有唯一解，静默选第一张会把错误的人注册进去 / 影响面：双人入镜时必须单独站到镜头前。
- **`FaceStore` 与 `FaceRecognizer` 各持一份映射，由 `_publish_faces` 同步** / 理由：识别路径不能每次识别都读文件 / 影响面：任何绕过 `_publish_faces` 的写名单都会让两份分叉（目前只有加载与这两个端点写）。
- **`tests/test_face_api.py` 里 `cv2.ocl.setUseOpenCL(False)`** / 理由：本机 OpenCV 4.14 在**工作线程**里跑 Haar 级联后，进程退出时 `clReleaseDevice` 失败并 abort，整份 pytest 在全部通过后以 0xC0000409 退出；用只调用 `FaceDetector().detect` 的三行探针即可复现，与票内代码无关（`src/rvm/analysis/detect.py` 未改）/ 影响面：测试进程不用 GPU 路径，产品行为不变；这是环境绕行，不是功能的一部分。
- **名单 JSON 形状 `{"version": 1, "faces": {name: [..]}}`** / 理由：留版本位以便以后迁移；`faces` 包一层避免与未来元数据键冲突 / 影响面：其他票（05 集成）直接读写该文件时要按此形状。

r2:
- **同时做 `_parse` 等长校验与 `_nearest` 宽度守卫** / 理由：门给的整改是「或」两种；但只有等长校验时，一份「全部 8 维」的手改名单仍会杀死 pump（门 FINDINGS-2 的原始触发样例正是单条目 8 维），而只有守卫时又抓不到「两种宽度混在一份文件里」这种显然的损坏 / 影响面：坏名单在加载时降级为空，或在识别时被跳过，两条路径都不再抛异常。
- **`_faces_lock` 用 `RLock` 而不是普通 `Lock`** / 理由：`register_face` 需要「复检 + 发布」原子，而 `_publish_faces` 自己也要保护删除路径，嵌套取锁是最短写法 / 影响面：锁的持有者可重入，没有额外语义。
- **`register_face` 保留顶部那次重名检查** / 理由：让重复名字在推理前就被 409，不必等三次 landmarker 调用 / 影响面：同名并发时两次请求都跑完采样，浪费约 3 次推理，但结果仍是一个 201。
- **r2 真机自检换端口与临时名单路径，新开 `-r2` 文件** / 理由：8099 被 03 号票的服务器占用（本机实测），且 r1 的读数不能当 r2 证据（产品代码已变）/ 影响面：`data/known_faces.json` 未在仓库内产生，r1 证据文件保持原样。

### 票 6

- **决定：改 `src/rvm/server/session.py`，越出票面写域一行** / 理由：缺陷（`remove_face` 的锁外复制）与 `_faces_lock` 都只在该文件；票面锚点 `grep -n "def remove_face" src/rvm/analysis/face_store.py` 无命中（`face_store.py` 只有 store 层 `remove`），照写域做无法修 / 影响面：改动仅 `remove_face` 一个方法体 + `_faces_lock` 的注释，未碰 `src/rvm/web/*`、`tests/test_app.py` 等其它文件；门若判越界请以此处置。
- **决定：并发测试放 `tests/test_face_store.py`（而不是 `tests/test_face_api.py`）** / 理由：票面写域与定向命令只指该文件 / 影响面：该文件新增 `from rvm.server.session import StreamSession`（连带 cv2），定向跑从 0.4s 量级变为约 1.6s。
- **决定：用 `ObservedLock` 替换 `_faces_lock` 作确定性接缝** / 理由：旧实现的坏交错唯一可观测点就是「锁入口之前已完成复制」，sleep 只能猜 / 影响面：测试依赖「`_faces_lock` 是实例属性且以 `with` 使用」；换成模块级锁或非上下文管理器时测试需同步改。
- **决定：测试直接填 `_recent_frames`，不跑 `run_once`** / 理由：这三帧就是注册要平均的内容，跑 `run_once` 只为生成同样三帧，却引入 Haar 与 OpenCL 退出问题 / 影响面：本票证据不含分析 tick 路径（已由 02 票测试覆盖）。
- **决定：多写一条 remove-vs-remove 测试** / 理由：门首攻靶点名「删除与注册交错是否还有第二条路径」，同类缺陷在两条删除之间同样成立 / 影响面：多一条测试，产品代码不变。
- **决定：`FaceStore.add`/`replace` 不加锁，判为无同类漏洞** / 理由：它们的生产写点只有 `_publish_faces`（锁内）与 `__init__` 的 `load()`（线程启动前），`FaceStore.add/remove` 只被测试直接调用 / 影响面：若以后有人在 session 之外直接调 `FaceStore.add`，丢更新会以新路径回归，测试不覆盖。

### 票 3

- 决定：FACE REGISTRY 在本票只做静态外壳（分区标题、名字标签、输入框、`REMEMBER FACE`、空状态行、名单空态），不接任何请求 / 理由：本票 AC 的 390 顺序点名 FACE REGISTRY，没有这个分区就量不出顺序；行为、五态文案与删除属 04 号票 / 影响面：04 号票接线时只补 JS，不必动结构；本票动态门不应期待注册可用。
- 决定：390 的读数改单列（规范 §4.1 默认双列）/ 理由：双列时读数只剩 45px，9 条被截断，超过 §4.1 自己写的「超过三条」退让条件 / 影响面：仅 ≤560；字号未动。
- 决定：折线只有 1 个样本时也画点、也写角标 / 理由：否则开页第一秒是 `peak -` 加空白画布，容易被读成「折线坏了」；对 1 元素窗口峰值仍成立 / 影响面：多样本时的线形不变。
- 决定：未到的读数占位从 `&mdash;` 改成 `-` 并加 `.pending` 灰字 / 理由：规范 §4.1 要连字符、§10 禁长破折号 / 影响面：首帧视觉；`setText()` 多一步去 class。
- 决定：CLIPS 行把 `20261024_213812` 显示成 `2026-10-24 21:38` / 理由：规范 NOTES 第 8 条要求现场好念 / 影响面：只改可见文案，文件名与下载路径不变。
- 决定：删掉 `#stage` 的 `data-channel="CAM 01"` 与底部 overlay / 理由：它们是来源标签的第二份副本，规范把来源与时间移进画面两角 OSD / 影响面：`data-channel` 属性不再存在，`#src-label`/`#time-label`/`#view-label` 三个 id 保留。
- 决定：≥901px 右栏加 `max-height: calc(100vh - 102px)` 与栏内滚动 / 理由：规范 §6 说明这是本票新增规则 / 影响面：仅在内容超高时生效，1440x1000 实测不触发。
- 决定：八项操作按「七个控件 + 画面拖拽划区」计 / 理由：spec AS-5 与规范 §6 只列了七个按钮，第八项只能是 ROI 拖拽 / 影响面：测试按这八条钉住，若门另有口径只改测试一处。
- 决定：`#record` 仍用 `active` 类驱动 `Start/Stop recording` 文案，不并入 `.seg` / 理由：既有 app.js 依赖该 class 与文案切换，改它属行为变更 / 影响面：录制态样式改走 `#record.active` 的告警色。

### 票 4

- 决定：五态文案逐字取票面 AC 的字面量（`no face in frame, hold still`、
  `more than one face in frame`、`<name> is already saved`、`analysis is off`、
  `models still loading`），不用 `DESIGN-dashboard.md` §8 的句子式写法
  （`Two faces in frame, show one`、`... add a surname`、`Analysis is off`）。
  / 理由：票面是唯一需求源且 AC 明写「五态文案」；DESIGN 与票面冲突以票面为准。
  / 影响面：与 §8 的大小写和两处措辞不同，若门按 §8 比对会判不一致；改文案只动
  `app.js:480`。
- 决定：`REMEMBER FACE` 在预热(`pending`)与分析关闭(`disabled`)时**不置灰**，只在请求
  在途时 `disabled`。 / 理由：票面要求「models still loading」「analysis is off」两种文案
  能被真正触发，置灰会堵掉唯一入口；DESIGN §4.4/§8 的置灰条款因此未实施。
  / 影响面：预热 2-3 秒内可点，点后得到一行 503 文案；没有测试钉住置灰。
- 决定：`no-faces` 且名单为空时 Face IDs 显示 `0 faces, none known`（票面 `N faces,
  none known` 取 N=0），名单非空时显示 `no face`。 / 理由：票面要求「名单为空且无人脸」
  时回显人数，同时不能在有名单时谎报 none known。 / 影响面：与 03 号票的
  `no known faces` / `no face` 不同，只影响这一行。
- 决定：票面里「显示 `no-known-faces`」按**状态词**理解，不上屏。 / 理由：DESIGN §8
  的五态表没有把状态词作为文案，AS-2 同句给的可见文案是 `N faces, none known`。
  / 影响面：页面上不出现字符串 `no-known-faces`；若门要求它可见，需要新增一行文案。
- 决定：删除成功后把状态行清空，不加「已删除」文案。 / 理由：五态表只定义注册结果，
  票面没给删除文案，多写一句等于发明。 / 影响面：删除后回到空状态行（高度不变，
  `.status:empty::before` 隐点）。
- 决定：注册/删除成功后额外 `GET /api/faces/identities` 刷新 Face IDs 行。
  / 理由：票面 AC 要「Face IDs 立刻刷新」，等遥测最多 0.5 s。 / 影响面：每次写操作多一个
  GET，失败时静默等下一帧。
- 决定：真机自检用**同源 iframe 驱动页**代替人工键鼠（临时文件，截图后删除）。
  / 理由：本会话的桌面输入只能后台投递，Chromium 的 `text_input` 后台不可用、前台被拒；
  同源 iframe 可以像人一样 `value=` + `click()` 点到真实页面。 / 影响面：产品文件未改；
  驱动页副本留在 `verifier-probes/04-selfcheck-harness.html`，并在自检文档里写明哪几张图是桩。
