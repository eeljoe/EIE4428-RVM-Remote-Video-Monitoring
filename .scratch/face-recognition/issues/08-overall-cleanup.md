# 08 — 整体门收口：移动端间隙、名字校验、设计文案

**Status:** ready-for-agent
**Blocked by:** 07
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/08-overall-cleanup-selfcheck.md`）
**UI:** yes

## What to build

收掉整体门三条 Important：≤900px 下 FACE REGISTRY 与 STREAM 之间的视觉间隔不足 20px 且缺分隔；`.`、`..`、含路径分隔符的名字可注册但删除无路由；DESIGN §8 的五态文案与实现逐字不一致。

## Acceptance criteria

- [ ] [AS-6] ≤900px 下 FACE REGISTRY 与 STREAM 之间的视觉间隔 ≥20px，或补一条与其它分区一致的分隔线
- [ ] [AS-4] 名字校验拒绝 `.`、`..`、含 `/` 或 `\`、控制字符与纯空白的输入，返回 400 `reason=bad-name`，不写文件
- [ ] [AS-7] `docs/DESIGN-dashboard.md` §8 五态文案与 `app.js` 实现逐字一致
- [ ] [AS-5] 定向与全套测试通过；03/04/07 的可读性、五态、race 行为不回退

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_face_api.py tests/test_app.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 真机：`run_server.py --no-camera --port 8099`，390×844 截图核对间隙。

## 写域

- `src/rvm/web/style.css`
- `src/rvm/server/app.py`
- `docs/DESIGN-dashboard.md`
- `tests/test_face_api.py`
- `tests/test_app.py`

## 开工包

- **写域**：`src/rvm/web/style.css`, `src/rvm/server/app.py`, `docs/DESIGN-dashboard.md`, `tests/test_face_api.py`, `tests/test_app.py`
- **锚点**：`grep -n "@media (max-width" src/rvm/web/style.css`、`grep -n "bad-name" src/rvm/server/app.py`、`grep -n "## 8" docs/DESIGN-dashboard.md`。
- **校验位置**：把名字合法性判断收进现有校验函数，别在新地方重复一份。
- **尺寸上限**：≤300 行 / 5 文件。
- **估算**：预计 25 分钟 / 120 步。

## 验收包

- **判据**：AS-6 移动端间隔、AS-4 名字校验、AS-7 文档一致、AS-5 回归。
- **首攻靶**：390 实测间隙是否真到 20、`.` 与 `..` 是否 400 且零写入、DESIGN 文案是否逐字一致、是否误伤合法名字（含空格、中文、单引号）。
- **相关 AS 摘录**：AS-4 失败与降级；AS-6 可读性；AS-7 简洁与观感；AS-5 不回归。

## 完成条件

三处修复各有测试或截图证据；独立动态门在干净副本里复验并判 `VERIFIED` 后才可标 `resolved`；随后整体门按新 HEAD 重跑。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
