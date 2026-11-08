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
