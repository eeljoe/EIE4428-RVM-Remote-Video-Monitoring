# 09 — 补合法名字含点的参数用例（r1 worker）

票号：09-dotted-name-test
认领：`13e1b89 chore: 认领 09 含点名字测试`（只暂存票文件）
交票 commit：`1659aaf test: 09 合法名字参数列补含点名字（Alice Ng./J. Smith/..a/a..b）`（`tests/test_face_api.py` + 票文件的 `## 实现说明`）
基线：`efd0c1e`（08 门 VERIFIED 落盘、09 票已开）
真机自检：不需要（票面）

## 改动

- `tests/test_face_api.py:335-348` 合法名参数列由 5 条扩到 9 条，新增 `Alice Ng.`(:343)、`J. Smith`(:344)、`..a`(:345)、`a..b`(:346)；`:349-361` docstring 补「只有 `.` 与 `..` 是死段」的反向约束。
- 断言体一行未改：`:365` POST 真端点、`:367` 201、`:368-369` 重读磁盘断言单条原名、`:371-374` 同名 URL 段 DELETE 200 + 名单清空。
- 净增 18 行 / 1 文件（710 → 727 行），尺寸上限 ≤50 行未触。产品零改动。

## TESTS

### 1) 定向（票面命令原文）

```
.\.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q
................................................                         [100%]
EXIT=0   （addopts 已含 -q，再传 -q 变 -qq，摘要行被吞，故另跑同文件不带额外 -q 取计数）
.\.venv\Scripts\python.exe -m pytest tests/test_face_api.py
48 passed in 8.13s        EXIT=0
```

### 2) 全套（票面命令原文）

```
.\.venv\Scripts\python.exe -m pytest -q
..................................................                       [100%]
EXIT=0
.\.venv\Scripts\python.exe -m pytest
594 passed in 29.46s      EXIT=0
```

08 门基线 590 + 本票 4 参数 = 594，无其它增减（`git diff efd0c1e..1659aaf --stat` 只有 `tests/test_face_api.py` 18(+)/1(-) 与票文件）。

### 3) 撤修复即红（变异 A：拒绝任意含点名字，票面自证要求的那一发）

`src/rvm/server/session.py`：`if cleaned in (".", ".."):` → `if "." in cleaned:`

```
.\.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k can_be_deleted_again
>       assert response.status == 201
E       AssertionError: assert 400 == 201
E        +  where 400 = <ClientResponse(http://127.0.0.1:56783/api/faces/known) [400 Bad Request]>
tests\test_face_api.py:367: AssertionError
FAILED tests/test_face_api.py::test_a_name_that_can_be_deleted_again_is_still_accepted[Alice Ng.]
FAILED tests/test_face_api.py::test_a_name_that_can_be_deleted_again_is_still_accepted[J. Smith]
FAILED tests/test_face_api.py::test_a_name_that_can_be_deleted_again_is_still_accepted[..a]
FAILED tests/test_face_api.py::test_a_name_that_can_be_deleted_again_is_still_accepted[a..b]
EXIT=1
```

旧 5 条参数仍绿（新增 4 条全红）——红是新增参数带来的，不是套件本身红。

### 4) 撤修复即红（变异 B：08 门原样存活变异 `cleaned.startswith(".")`）

```
.\.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k can_be_deleted_again
FAILED tests/test_face_api.py::test_a_name_that_can_be_deleted_again_is_still_accepted[..a]
EXIT=1        （1 failed, 8 passed —— 只有 ..a 能杀这一发）
```

### 5) 还原核哈希 → 复绿

```
SHA1_SESSION=5F8A55A9804712A5730C50855E387BF20F0F5D2B     （= 动手前基线 5F8A55A9…）
git diff --stat -- src/rvm/server/session.py              （空）
.\.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k can_be_deleted_again
.........                                                 [100%]     EXIT=0
```

产品文件最终 sha1 与基线一致，两次变异都被还原，提交里不含 `session.py`。

### 6) 自检：10 条命中 / 0 条落空

1. 票面 `Status:` 已 `claimed` 且认领单独提交 `13e1b89` — 命中（`git show --stat 13e1b89` 只含票文件）。
2. 新参数 4 条、断言 201 — 命中（`tests/test_face_api.py:343-346`、`:367`）。
3. 断言名单文件未损坏（重读磁盘 + 单条 + trim）— 命中（`:368-369`）。
4. 走真 HTTP、不直调校验函数 — 命中（`:365`/`:371`；`Select-String validated_face_name tests/test_face_api.py` 计数 0）。
5. 变异 A（任意含点）新用例必红 — 命中（TESTS-3，4 failed）。
6. 变异 B（点开头，08 存活态）必红 — 命中（TESTS-4，`..a` failed）。
7. 还原 sha1 一致后复绿 — 命中（TESTS-5）。
8. 定向 48 passed exit 0 — 命中（TESTS-1）。
9. 全套 594 passed exit 0 — 命中（TESTS-2）。
10. 实现说明六节插在 `## Verdicts` 之前、与测试同提交 — 命中（票文件；`git show --stat 1659aaf` 两文件）。

## 我知道没覆盖什么（与本票判据相关）

- 含点名字与普通名混存、含点名字重复注册 409 未测（详见票面 `## 实现说明` §3）。
- `tools/coverage-tests.mjs` 不存在于本仓库，派发消息的覆盖读数无法本地复跑 —— UNVERIFIED。
- 环境坑沿用 08 记录：`-k` 跑 `tests/test_app.py` 子集时 OpenCV `clReleaseDevice` 会 0xC0000409 abort；本票两条命令均不涉及该子集，未触发。

## COMMITS

- `13e1b89` chore: 认领 09 含点名字测试
- `1659aaf` test: 09 合法名字参数列补含点名字（Alice Ng./J. Smith/..a/a..b）

## IMPLEMENTED

- [test] 收编 08-r1 FINDINGS-1：合法名参数列补 `..a`（并附 `a..b`、`Alice Ng.`、`J. Smith`），变异 `cleaned.startswith(".")` 由存活转为 `[..a]` 变红。

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 09 | 交票 | 1659aaf | reports/09-r1-worker.md | 合法名参数补 4 条含点名字，任意含点与点开头两发变异实测变红、sha1 还原复绿，定向 48 / 全套 594 绿 |
