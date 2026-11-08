# Spec — 人脸识别闭环（严格融合单会话）

## 背景与已批准方向

人脸检测与识别器已经在仓库里，但注册只有代码路径：`FaceRecognizer.add_known_face()` 只在测试里被调用。面板因此永远显示 `no-known-faces` 加一个人脸数，演示时无法把「认出是谁」做出来。

用户已确认三项方向：一，演示现场在面板上注册，当场见效；二，名单存 `data/known_faces.json`，只存名字与嵌入向量，不进 git、不进 zip；三，注册取三帧平均，保留 0.6 阈值，面板同时显示相似度。

## 范围

服务端：

- `src/rvm/analysis/recognition.py` 增加取样本接口，返回一帧里每张脸的嵌入向量。
- 新增 `src/rvm/analysis/face_store.py`：名单加载、原子保存、增加、删除。
- `src/rvm/server/session.py` 保留最近三次分析帧，提供注册入口与名单快照。
- `src/rvm/server/app.py` 增加三个端点与 CLI 参数 `--known-faces`。
- `.gitignore` 增加 `data/known_faces.json`。

前端：

- `src/rvm/web/index.html` 分析与名单控件。
- `src/rvm/web/app.js` 注册、删除、展示。
- `src/rvm/web/style.css` 新控件样式。

文档：`README.md`、`docs/FEATURES.md`、`tools/build_report.py` 同步注册能力与限制。

不做：音频上行、跟踪、编解码、录像、其他分析器、报告人数信息、zip 打包脚本。

## 约束

- 不新增依赖，只用标准库、NumPy 与既有 MediaPipe。
- 不改既有端点行为与状态词表；`no-known-faces`、`no-faces`、`mediapipe` 的语义不变。
- 名单文件只存名字与嵌入向量，不存照片；文件不存在按空名单处理，损坏时告警并按空名单启动，不崩服务。
- 页面不加载远程字体、脚本、图片或样式；不引入前端框架或构建步骤。
- 注册采样只在分析开启且模型就绪时可用；不满足时返回明确错误，不改任何文件。

## Acceptance Statements

AS-1: 面板注册闭环。输入名字并点按钮后，服务端从最近三帧各取一张脸求平均并写入名单；成功返回样本数，失败返回可读原因，画面流不中断。
AS-2: 识别展示。已注册人脸在分析面板显示名字与相似度；低于阈值或名单为空时不显示名字，保持 `no-known-faces` 与人数。
AS-3: 持久化。名单写入 `data/known_faces.json`；重启服务后仍能识别；删除后立即从名单消失并落盘。
AS-4: 失败与降级。无脸、多脸、重名返回 409 且不写文件；分析关闭、模型未就绪或识别器不可用返回 503；既有四个分析器状态不变。
AS-5: 不回归。既有 DOM ID、八项操作、响应式与无远程资源保持；390×844 与 1440×1000 视口可用；全套测试通过，无新增依赖。

## Testing Decisions

- 单元与端点测试：`.venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_app.py -q`
- 全套回归：`.venv\Scripts\python.exe -m pytest`
- 动态验收：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099`，在真实浏览器里注册、删除、重启后复查，并截图。
- 静态 UI 检查沿用 `tests/test_app.py` 的文本断言，不引入浏览器测试框架。

### Verification Seams

- SEAM-1: 浏览器注册一张脸到名字出现、重启后仍在、四类失败都走通的完整链路 | AS: AS-1, AS-2, AS-3, AS-4, AS-5

## 阶段切片

- 01 号票——分析面板设计规范（designer）：产出 `docs/DESIGN-analysis-panel.md` 与签字参照图的落实规则。
- 02 号票——服务端注册与持久化（worker）：嵌入取样、名单文件、三个端点、CLI 参数、测试。
- 03 号票——面板控件与文档（worker，Blocked by: 01, 02）：注册与删除控件、身份展示、样式、文档与报告文案、静态测试。

## 完成条件

审票 3×1 个 verifier；每票一次独立动态门；整体门 = 2×1 静态加一个独立集成动态；全部 AS 在范围内拿到新鲜证据并判 `VERIFIED` 后才可标 `resolved`。
