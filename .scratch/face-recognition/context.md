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
