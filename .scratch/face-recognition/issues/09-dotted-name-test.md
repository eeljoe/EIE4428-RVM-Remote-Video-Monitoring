# 09 — 补合法名字含点的参数用例

**Status:** ready-for-agent
**Blocked by:** 08
真机自检：不需要

## What to build

08 的门发现一个存活的测试盲区：名字校验的合法参数表里没有「含点」的名字，导致「拒绝所有以点开头的名字」这种过拒变异在全套测试下存活。补一条合法含点名字的用例，让过拒立刻变红。

## Acceptance criteria

- [ ] [AS-4] 合法含点名字（如 `Alice Ng.`、`J. Smith`）注册返回 201，不写坏文件；被 `startswith(".")` 类过拒时测试必红
- [ ] [AS-5] 定向与全套测试通过，其它名字校验行为不变

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`

## 写域

- `tests/test_face_api.py`

## 开工包

- **写域**：`tests/test_face_api.py`
- **锚点**：`grep -n "bad-name" tests/test_face_api.py`、`grep -n "parametrize" tests/test_face_api.py`。
- **自证**：把实现临时改成拒绝任意含点名字，新用例必须红；还原（sha1 核对）后绿。
- **尺寸上限**：≤50 行 / 1 文件。
- **估算**：预计 10 分钟 / 60 步。

## 验收包

- **判据**：AS-4、AS-5；新用例在过拒变异下必红。
- **首攻靶**：用例是否真走 HTTP 而不是直接调校验函数、是否连带断言名单文件未损坏。
- **相关 AS 摘录**：AS-4 失败与降级；AS-5 不回归。

## 完成条件

变异红、还原绿、全套通过；独立动态门亲手复现变异并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
