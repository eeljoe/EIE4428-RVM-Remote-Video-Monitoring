# 04 — 注册控件与文档

**Status:** claimed
**Blocked by:** 01, 02, 03
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/04-face-registry-ui-selfcheck.md`）
**UI:** yes

## What to build

在面板上新增独立的 FACE REGISTRY 分区：名字输入、REMEMBER FACE 按钮、两态状态行、名单与删除；Face IDs 显示「名字 · 相似度」。同步 README、FEATURES 与报告生成器的文案，并补静态测试。

## Acceptance criteria

- [ ] 新增独立 FACE REGISTRY 分区，含名字输入、记住按钮、状态行、名单与删除按钮 [AS-1, AS-2]
- [ ] Face IDs 显示「名字 · 相似度」；名单为空且无人脸时显示 `no-known-faces` 与 `N faces, none known`；相似度低于阈值时不显示名字 [AS-2]
- [ ] 五态文案与 spec「接口契约」一致：成功 `Saved as <name>, 3 frames averaged`；无脸 `no face in frame, hold still`；多脸 `more than one face in frame`；重名 `<name> is already saved`；503 `analysis is off` 或 `models still loading` [AS-1, AS-4]
- [ ] 注册成功后名单与 Face IDs 立刻刷新，删除后立刻消失；名字做转义，不拼 HTML [AS-1, AS-2]
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

- **写域**：`src/rvm/web/index.html`, `src/rvm/web/app.js`, `src/rvm/web/style.css`, `tests/test_app.py`, `README.md`, `docs/FEATURES.md`, `tools/build_report.py`, `tests/test_report.py`

- **端点契约**：以 02 号票交付为准，失败体 `{"error","reason"}`；`reason` → 文案映射见 spec「接口契约」。
- **视觉**：`docs/DESIGN-dashboard.md` 与 `.scratch/face-recognition/design/v2/mock.html`（含五态文案注释）。
- **锚点**：`grep -n "function analysisText" src/rvm/web/app.js`（扩写身份行）；`grep -n "m-identities" src/rvm/web/index.html`。
- **删除绑定**：用 `data-name` 属性与 `textContent`，不拼 HTML 字符串。
- **刷新**：注册与删除成功后只刷新名单与身份行，不整页刷新。
- **尺寸上限**：8 个文件、预计超 300 行；按 OVER-LIMIT 分级走额外静态实例。
- **估算**：预计 45 分钟 / 210 步。

## 验收包

- **判据**：AS-1、AS-2、AS-4、AS-5；每条 AC 有截图或测试断言。
- **首攻靶**：名字特殊字符是否安全、四类失败文案是否真被触发、低于阈值是否真的不显示、空名单是否回显人数、文档是否与实现一致。
- **相关 AS 摘录**：AS-1 注册闭环；AS-2 展示；AS-4 失败；AS-5 不回归。

## 完成条件

实现提交含测试；独立动态门在真实浏览器里完成注册、删除、失败与刷新四步并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
