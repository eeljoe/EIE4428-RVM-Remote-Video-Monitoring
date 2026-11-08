# Spec — 人脸识别闭环 + 监控页可读性重做（严格融合单会话）

## 背景与已批准方向

人脸检测与识别器已经在仓库里，但注册只有代码路径：`FaceRecognizer.add_known_face()` 只在测试里被调用。面板因此永远显示 `no-known-faces` 加一个人脸数，演示时无法把「认出是谁」做出来。

第一版参照图被用户判为「可读性太差」，并要求同时更简洁、更好看。于是本次范围扩成两块：人脸注册闭环，加整页可读性与结构简化。

用户已确认的方向：一，演示现场在面板上注册，当场见效；二，名单存 `data/known_faces.json`，只存名字与嵌入向量，不进 git、不进 zip；三，注册取三帧平均，保留 0.6 阈值，面板同时显示相似度；四，整页重做可读性，同时更简洁更好看。

## 范围

服务端：

- `src/rvm/analysis/recognition.py` 增加取样本接口，返回一帧里每张脸的嵌入向量。
- 新增 `src/rvm/analysis/face_store.py`：名单加载、原子保存、增加、删除。
- `src/rvm/server/session.py` 保留最近三次分析帧，提供注册入口与名单快照。
- `src/rvm/server/app.py` 增加三个端点与 CLI 参数 `--known-faces`。
- `.gitignore` 增加 `data/known_faces.json`。

前端：

- 整页可读性与结构重做：字号阶梯、对比度、行距、分组间距、去冗余框线与重复标签。
- 保留全部既有元素 ID、控件与读数；画面仍是第一视觉焦点。
- `src/rvm/web/index.html`、`style.css`、`app.js` 增加注册控件与展示。
- 分析面板新增名字输入、记住按钮、状态行、名单与删除。

文档：`README.md`、`docs/FEATURES.md`、`tools/build_report.py` 同步注册能力与限制。

不做：音频上行、跟踪、编解码、录像、其他分析器、报告人数信息、zip 打包脚本。

## 约束

- 不新增依赖，只用标准库、NumPy 与既有 MediaPipe。
- 不改既有端点行为与状态词表；`no-known-faces`、`no-faces`、`mediapipe` 的语义不变。
- 名单文件只存名字与嵌入向量，不存照片；文件不存在按空名单处理，损坏时告警并按空名单启动，不崩服务。
- 页面不加载远程字体、脚本、图片或样式；不引入前端框架或构建步骤。
- 既有元素 ID 与八项操作保持可用；响应式两档视口不横向溢出。
- 注册采样只在分析开启且模型就绪时可用；不满足时返回明确错误，不改任何文件。

## Acceptance Statements

AS-1: 面板注册闭环。输入名字并点按钮后，服务端从最近三帧各取一张脸求平均并写入名单；成功返回样本数，失败返回可读原因。注册请求期间 MJPEG 与 `/api/status` 不被阻塞，画面流不中断。
AS-2: 识别展示。已注册人脸在分析面板显示名字与相似度；低于阈值或名单为空时不显示名字；无人脸时显示 `no-known-faces` 与人数（`N faces, none known`）。
AS-3: 持久化。名单写入 `data/known_faces.json`；重启服务后仍能识别；删除后立即从名单消失并落盘。
AS-4: 失败与降级。无脸、多脸、重名返回 409 且不写文件；分析关闭、模型未就绪或识别器不可用返回 503；既有四个分析器状态不变。
AS-5: 不回归。既有 DOM ID、八项操作、响应式与无远程资源保持；390×844 与 1440×1000 视口可用；全套测试通过，无新增依赖。
AS-6: 可读性。全页最小标签字号 12px、数值 15px 起，手机正文 14px 起；灰字与近黑底对比度至少 4.5:1；行高至少 1.5；分组间距至少 20px。两档视口截图上，遥测与控件不必凑近才能读。
AS-7: 简洁与观感。去掉冗余框线与重复标签，分区不超过 6 个；画面为第一焦点；控件与读数一个不少；页面在 1440×1000 内不出现被截断的操作。

## 接口契约

- `POST /api/faces/known` 请求体 `{"name": "Alice Ng"}`。成功 201：`{"name", "samples", "known": ["..."]}`。
- `GET /api/faces/known` 返回 `{"known": ["Alice Ng", "..."]}`。
- `DELETE /api/faces/known/{name}` 返回 `{"removed": true, "known": [...]}`，不存在返回 404。
- 失败一律返回 `{"error": "<人可读文案>", "reason": "<枚举>"}`。枚举只允许：`bad-name`（400）、`name-exists`（409）、`no-face`（409）、`multiple-faces`（409）、`samples-missing`（409）、`analysis-disabled`（503）、`models-loading`（503）、`unavailable`（503）、`write-failed`（500）。
- 失败路径不写名单文件；名单每次变更用整体替换，不在原 dict 上原地改。

## Testing Decisions

- 单元与端点测试：`.venv\Scripts\python.exe -m pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py -q`
- 全套回归：`.venv\Scripts\python.exe -m pytest`
- 动态验收：`.venv\Scripts\python.exe run_server.py --no-camera --port 8099`，在真实浏览器里注册、删除、重启后复查，并截图。
- 静态 UI 检查沿用 `tests/test_app.py` 的文本断言，不引入浏览器测试框架。
- 可读性证据：1440×1000 与 390×844 截图，加一段把字号、对比度、间距与现有值对照的说明。
- 集成测试票 `tests/test_integration_faces.py` 覆盖跨票接缝：注册→识别→重启→删除。

### Verification Seams

- SEAM-1: 浏览器注册一张脸到名字出现、重启后仍在、四类失败都走通，且两档视口的字号与对比度达标 | AS: AS-1, AS-2, AS-3, AS-4, AS-5, AS-6, AS-7

## 阶段切片

- 01 号票——设计规范（designer）：产出 `docs/DESIGN-dashboard.md`，含字号阶梯、颜色与对比度、间距、组件规则与参照图路径。
- 02 号票——服务端注册与持久化（worker）：嵌入取样、名单文件、三个端点、CLI 参数、测试。
- 03 号票——整页可读性与结构重做（worker，Blocked by: 01）：字号、对比度、间距、分组、去冗余；保留 ID 与操作。
- 04 号票——注册控件与文档（worker，Blocked by: 01, 02, 03）：面板控件、身份展示、样式衔接、文档与报告文案、静态测试。
- 05 号票——集成测试与探针收编（worker，Blocked by: 02, 03, 04）：跨票 happy path（注册→显示→重启→删除）与 `.scratch/face-recognition/verifier-probes/` 的持久探针收编。

## 完成条件

审票 3×1 个 verifier；每票一次独立动态门；整体门 = 2×1 静态加一个独立集成动态；05 号票的集成用例是整体门的证据来源；全部 AS 在范围内拿到新鲜证据并判 `VERIFIED` 后才可标 `resolved`。
