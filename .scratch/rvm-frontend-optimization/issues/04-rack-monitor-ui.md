# 04 — 监控页视觉与响应式优化

Status: resolved
Blocked by: (none)

## 交付什么

把现有 RVM 页面升级为“演播室机架监视器”风格：画面优先、状态清楚、报警醒目、遥测易读；桌面与手机均可操作。保留所有现有 ID、API 和 JavaScript 行为，不加外部资源或依赖。

## Acceptance criteria

完整验收以 `../spec.md` 的 AS-1～AS-6 为准：

1. [AS-1][AS-6] JavaScript 引用的现有元素 ID 不缺失，既有 373 项测试不回归；source/decoded 切换、码率应用、灵敏度、清除选区、录像、快照、指标导出和片段列表保持原行为，浏览器无新增 page error。
2. [AS-2][AS-3] 1440×1000 与 390×844 真实浏览器视口无横向溢出；手机单列且关键控件可用；报警与选区不遮挡关键操作。
3. [AS-4] 连接状态是 polite live region，运动报警是 assertive alert；键盘焦点可见；减少动画偏好关闭脉冲动画。
4. [AS-5][AS-2] 页面无远程前端资源；视觉达到 spec 第 5 行的机架监视器锚点，画面为第一视觉焦点。

## 测试命令

- 红→绿：`.venv\Scripts\python.exe -m pytest tests/test_app.py -q`
- 全量：`.venv\Scripts\python.exe -m pytest`
- 动态：启动 `.venv\Scripts\python.exe run_server.py --no-camera --port 8099`，桌面与手机视口验收并截图。

## 写域

- `src/rvm/web/index.html`
- `src/rvm/web/style.css`
- `tests/test_app.py`

## 开工包

- 尺寸上限：只改写域内 3 个现有文件，实现 diff（含测试、增+删）不得超过 300 行；超限就停止轻量路线，不靠扩文件规避。
- 视频锚点：`tests/test_delivery.py:48-52` 要求 `<img>` 标签内有 `id="stream"`、内联 `src=` 和 `stream.mjpg`；禁止改为延迟注入或换标签。
- DOM 锚点：保留 `view-source`、`view-decoded`、`roi`、`sensitivity`、`clear-roi`、`clips`、`spark` 的 HTML 字面 ID；CSS 保留 `.layout`（`tests/test_app.py:57`）。
- 行为锚点：`app.js` 只读；ROI、灵敏度、双视图、片段和录像均沿用既有事件与 API。

## 验收包

- 判据：spec AS-1～AS-6，静态审查与动态门各自独立重建。
- 首攻靶：stream 内联 src、字面 ID 合约、390px 横向溢出、live region、减少动画、远程资源和八项既有操作。
- 相关 AS：AS-1 DOM/回归；AS-2 视觉；AS-3 响应式；AS-4 可访问性；AS-5 自包含；AS-6 功能与 page error。

## 完成条件

测试先红后绿，实现提交包含对应测试；独立动态验收 VERIFIED 后才能改 `Status: resolved`。

## Verdicts

2026-10-26 r1 VERIFIED 6efdc57 独立副本 377/377、3 个变异全杀、桌面/手机 23 步与八项操作通过；既有图片原生拖拽问题在基线同现，非本票回归，转 ROADMAP 跟踪（证据：课程工作区 out/rvm-frontend-acceptance/VERIFICATION-REPORT.md）。
