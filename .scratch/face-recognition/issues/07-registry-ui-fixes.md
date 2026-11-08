# 07 — 收口 04 门留下的两处缺陷

**Status:** claimed
**Blocked by:** 04
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/07-registry-ui-fixes-selfcheck.md`）
**UI:** yes

## What to build

修掉 04 号票门判出的两处非阻断缺陷：README 里与实现相反的「按钮不可用」断言，以及 `loadNames` 晚到 GET 覆盖新名单的 stale-write；顺带清理 `tests/test_report.py` 的孤儿 docstring。

## Acceptance criteria

- [ ] [AS-2, AS-5] README 描述与实现一致：pending/disabled 时按钮仍可点，状态行给出 `analysis is off` / `models still loading`
- [ ] [AS-2, AS-3] `loadNames` 在名单已被本地写操作更新后丢弃晚到响应（版本戳或 dirty 标志），race 探针转绿并补一条测试
- [ ] [AS-5] `tests/test_report.py` 的孤儿 docstring 清理，断言仍在有效位置
- [ ] [AS-5] 定向与全套测试通过，03 的可读性数值与 390 顺序不回退

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 真机：`run_server.py --no-camera --port 8099` + 浏览器 fetch 拦截做 race 探针。

## 写域

- `README.md`
- `src/rvm/web/app.js`
- `tests/test_app.py`
- `tests/test_report.py`

## 开工包

- **写域**：`README.md`, `src/rvm/web/app.js`, `tests/test_app.py`, `tests/test_report.py`
- **锚点**：`grep -n "unavailable for exactly those two states" README.md`、`grep -n "loadNames" src/rvm/web/app.js`。
- **race 复现**：GET 延迟 400ms、POST 即时 201；期望状态行报成功后名单不被回写成 `No names saved yet`。探针原文见 04 门报告 FINDINGS-2。
- **尺寸上限**：≤300 行 / 4 文件。
- **估算**：预计 30 分钟 / 140 步。

## 验收包

- **判据**：AS-2、AS-3、AS-5；race 探针在旧实现上必须红。
- **首攻靶**：README 是否只改这一句、dirty 标志是否会误伤正常首次加载、删除路径是否同样受保护。
- **相关 AS 摘录**：AS-2 展示；AS-3 持久化与一致性；AS-5 不回归。

## 完成条件

race 探针红→绿、全套通过；独立动态门在干净副本里亲手复现旧行为并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
