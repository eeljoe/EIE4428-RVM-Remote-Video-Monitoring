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

- 404 缺名字用 `bad-name`（契约无 not-found）；每次取样单独取锁；三帧每帧须恰一张脸；FaceStore 与 FaceRecognizer 两份映射由 `_publish_faces` 同步；测试里 `cv2.ocl.setUseOpenCL(False)` 绕开 OpenCV 退出 abort；名单形状 `{"version":1,"faces":{name:[..]}}`。
- r2：`_parse` 等长校验与 `_nearest` 宽度守卫双做；锁改 `RLock`；同名检查保留在采样前；真机自检换端口与临时名单。

### 票 6

- 越出票面写域改 `session.remove_face`（锁外复制缺陷只在该文件）；并发测试放 `tests/test_face_store.py`；`ObservedLock` 作确定性接缝；测试直接填 `_recent_frames`；补 remove-vs-remove；`FaceStore.add/replace` 判为无同类漏洞。

### 票 3

- 本票只做静态外壳（分区标题、输入、按钮、空状态行、名单空态），接线留 04；390 读数改单列；折线单样本也画点与角标；未到读数用 `-` 加 `.pending`；CLIPS 日期人读化；删 `#stage` 的 `data-channel` 与底部 overlay；≥901 右栏 `max-height` 加栏内滚动；八项操作按七控件加 ROI 拖拽计；`#record` 仍用 `active` 类。

### 票 4

- 五态文案取票面字面量，与 DESIGN §8 句子式写法不同，票面优先；`REMEMBER FACE` 不置灰，仅请求在途 disabled；`no-faces` 且空名单显示 `0 faces, none known`，有名单时显示 `no face`；状态词不上屏；删除后清空状态行；写后额外 GET identities；真机自检用同源 iframe 驱动页，产品文件未改。

### 票 5

- 持久化与混合宽度降级合成一条测试省一次进程启动；桩 `_failure` 避免加载 MediaPipe；失败路径末尾补成功注册；子进程测试标 `slow`；不收编 02/06 探针（断言已落在正式套件）；测试压到 300 行，真机读数放探针。

### 票 7

- 两条无关断言移入独立类而非只删 docstring；版本戳由写路径自增、读路径只比较；守卫用 `stamp !== namesStamp`。

### 票 8

- 决定：改 `src/rvm/server/session.py`，而不是写域列出的 `src/rvm/server/app.py` / 理由：开工包要求「把名字合法性判断收进现有校验函数」，唯一的现有校验函数是 `session.py:83` 的 `validated_face_name`；`app.py` 只做「请求体形状」的 `bad-name`（:387-389），在那里加路径规则等于开第二份判定 / 影响面：写域 5 个文件里 `app.py` 未改，`session.py` 只动一个函数体 + docstring，其余零改动（与 06 号票同类偏差，处置同前例）。
- 决定：DESIGN 顺带改 §4.4 的 loading 段（:127）与 §8「录制中」（:193）/ 理由：静态门 FINDINGS-2 原文点名 `:127`、`:189` 与表格同属一处漂移，只改表格会留下一句现存的假话 / 影响面：只改文档，产品无改动。
- 决定：把「`REMEMBER FACE` 置 disabled」改成「不置灰」写入文档 / 理由：04 号票已明确否决置灰且实现如此（`app.js` 只在请求在途时 disabled），文档是唯一错的一方 / 影响面：新测试只钉文案，不钉这条行为描述；门若要更强约束需另加断言。
- 决定：§8 新增 `models still loading` 与 `loading` 两条字面量，但保留「五态」标题不改「六态」/ 理由：这是状态行真实能出现的第 6 条文案（原文档完全没写），而票面 AS-7 用「五态」指称 §8 / 影响面：§8 现在读起来是「五态表 + 预热补一条」，不是重新定义状态数。
- 决定：真机自检把驱动页临时放进 `src/rvm/web/08-vp.html`（截图后删除，`git status` 无该文件）/ 理由：只有同源 iframe 才能读到真实页面的 `getBoundingClientRect`；前序 04 票与整体动态门用的是同一做法 / 影响面：产品文件未改，探针副本存 `verifier-probes/08-overall-cleanup-viewport.html`。
- 决定：自检读数同时给出两种口径（`box` 与 `visual`）/ 理由：门报告用 `b.top - a.bottom` 量出 16，而设计 §6 的「视觉间隔 24」是 `margin + padding`；只报一种口径容易被读成「24 其实还是 16」/ 影响面：`box=24` 与其余四条界线同值，`visual=25`（多算 1px 边框）也同值。
