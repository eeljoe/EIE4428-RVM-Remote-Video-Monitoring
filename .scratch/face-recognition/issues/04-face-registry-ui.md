# 04 — 注册控件与文档

Status: ready-for-agent
Blocked by: 02, 03
**UI:** yes

## 交付什么

把注册能力接到面板上：名字输入、REMEMBER FACE 按钮、两态状态行、名单与删除；Face IDs 显示「名字 + 相似度」。同步 README、FEATURES 与报告生成器的文案，并补静态测试。

## Acceptance criteria

- [ ] Analysis 面板出现名字输入、记住按钮、状态行（成功绿 / 失败红）、名单与删除按钮 [AS-1, AS-2]
- [ ] Face IDs 显示「名字 · 相似度」；空名单时保持 `no-known-faces` 与人数 [AS-2]
- [ ] 失败文案覆盖无脸、多脸、重名、503 四类，页面不崩、不静默失败 [AS-4]
- [ ] README、`docs/FEATURES.md` 与 `tools/build_report.py` 同步注册能力与「不存照片、名单不进仓库」的限制 [AS-2, AS-4]
- [ ] 静态测试钉住新 DOM ID 与无远程资源；全套测试通过 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 目视：`run_server.py --no-camera --port 8099`，注册、删除、刷新页面各走一遍。

## 写域

- `src/rvm/web/index.html`
- `src/rvm/web/app.js`
- `src/rvm/web/style.css`
- `tests/test_app.py`
- `README.md`
- `docs/FEATURES.md`
- `tools/build_report.py`
- `tests/test_report.py`

## 开工包

- 端点契约以 02 号票交付为准：`POST/GET/DELETE /api/faces/known`，失败码 409/503。
- 视觉按 `docs/DESIGN-dashboard.md` 与 `.scratch/face-recognition/design/v2/mock-desktop.png`。
- 现有 `analysisText()` 负责身份行文案，扩它而不是另写一份。
- 名单删除用 `data-name` 属性绑定，名字要转义，别拼 HTML 字符串。
- 注册成功后刷新名单与 Face IDs，不整页刷新。

## 验收包

- 判据：AS-1、AS-2、AS-4、AS-5。
- 首攻靶：注册后名字是否立刻出现、删除是否立刻消失、四类失败文案是否真的被触发、名字特殊字符是否安全、报告文案是否与实现一致。
- 相关 AS：AS-1 注册闭环；AS-2 展示；AS-4 失败；AS-5 不回归。

## 完成条件

实现提交含测试；独立动态门在真实浏览器里完成注册、删除、失败与刷新四步并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
