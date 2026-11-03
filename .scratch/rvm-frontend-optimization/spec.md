# Spec — RVM 机架监视器前端优化（单会话轻量路线）

## 背景与已批准方向

现有监控页功能完整，但视觉是普通深色后台：实时画面、报警、录像和遥测的层级接近，演示时重点不够突出。用户已批准一次单会话前端优化，方向为“演播室机架监视器”：近黑底色、信号青、警戒橙红、框线角标、等宽遥测数字和清晰的操作分区。

这是一项课程演示产品的前端优化，不是重新设计视频系统。页面必须在第二台电脑的普通浏览器中运行，不依赖 CDN、在线字体、前端框架或新增构建步骤。

## 范围

只改以下三个现有文件，实现 diff（含测试、增+删）不得超过 300 行：

- `src/rvm/web/index.html`
- `src/rvm/web/style.css`
- `tests/test_app.py`

不改 `app.js`、后端、API、WebSocket、编解码、录像格式、报告或 README。保留所有现有元素 ID 和现有操作；不新增功能。

## Acceptance Statements

- AS-1 DOM 合约不回归：现有 JavaScript 通过 `$("…")` 与 `setText("…", …)` 引用的字面元素 ID 在页面中全部存在，既有 373 项测试继续通过。
- AS-2 视觉层级清晰：真实浏览器中画面是第一视觉焦点；live、motion alarm、recording、ROI 和 decoded/source 状态可辨认，遥测数字易扫读，报警与选区不遮挡关键操作。
- AS-3 响应式可用：1440×1000 桌面与 390×844 手机视口均无页面级横向溢出；手机上单列布局，画面、控制按钮和遥测仍可见可操作。
- AS-4 可访问性基线：连接状态是 polite live region，运动报警是 assertive alert；键盘焦点可见；系统要求减少动画时关闭脉冲动画。
- AS-5 演示自包含：HTML/CSS 不加载远程字体、脚本、图片或样式；不增加依赖或构建配置。
- AS-6 功能不回归：source/decoded 切换、码率应用、灵敏度、清除选区、录像、快照、指标导出和片段列表保持原行为；浏览器无新增 page error。

## 测试接缝

- 静态回归：在 `tests/test_app.py` 用标准库正则/文本检查钉住 DOM ID 合约、live region、响应式/焦点/减少动画规则和远程资源禁令。
- 阶段测试：`.venv\Scripts\python.exe -m pytest tests/test_app.py -q`。
- 全套回归：`.venv\Scripts\python.exe -m pytest`。
- 真实浏览器：用 `--no-camera` 合成场景启动服务，在桌面与手机视口检查布局、控制台和关键操作并留截图。主会话截图只用于设计迭代，最终通过必须由独立动态验收亲自重跑。

## 阶段切片

- 04 号票——监控页视觉与响应式优化：静态测试先红，再完成 HTML/CSS 与测试转绿；无阻塞票。

## 完成条件

实现前 compact 审票无 blocking；实现后 compact 静态审查发现均已处理或转为动态门 lead；新的独立动态验收对全部 AS 给出 `VERDICT: VERIFIED`。若任一门非 VERIFIED，不把票标为 resolved。
