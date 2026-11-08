# 09 — 补合法名字含点的参数用例

**Status:** claimed
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

### 1. AC → 证据

- **AS-4「合法含点名字注册返回 201，不写坏文件；被过拒时测试必红」** → 新增参数落在 `tests/test_face_api.py:335-348`（参数列），断言在 `:365-374`：
  - 含点参数四条：`Alice Ng.`（`tests/test_face_api.py:343`）、`J. Smith`（`:344`）、`..a`（`:345`）、`a..b`（`:346`）。
  - 真 HTTP：`tests/test_face_api.py:365` `client.post("/api/faces/known", json={"name": legal})`、`:371` `client.delete("/api/faces/known/" + quote(legal.strip(), safe=""))`；`client` 来自 `build` fixture 的 aiohttp TestClient，测试文件不 import `validated_face_name`（全文件无该符号），没有直调校验函数。
  - 名单文件未损坏：`tests/test_face_api.py:368-369` 用 `json.loads(list_file(tmp_path).read_text())` 重读磁盘，断言 `list(stored) == [legal.strip()]`（只落一条、键是 trim 后原名）；`:373-374` 再用同名 URL 段删除，断言 200 且 `known == []` —— 存下的含点名仍可寻址、不是死条目。
  - 过拒必红（两次实测，输出见报告 `reports/09-r1-worker.md` TESTS 段）：`session.py` 的 `cleaned in (".", "..")` 改成 `"." in cleaned`（拒绝任意含点）→ 四条新参数全红、旧五条仍绿；改成 `cleaned.startswith(".")`（08 门原样存活变异）→ `..a` 一条红、其余八条绿。
- **AS-5「定向与全套通过，其它名字校验行为不变」** → 定向 `pytest tests/test_face_api.py -q` exit 0，计数口径 48 passed；全套 `pytest -q` exit 0，计数口径 594 passed（08 门基线 590 + 本票新增 4 参数 = 594，无其它增减）。拒绝面零改动：`UNREACHABLE_NAMES`（`tests/test_face_api.py:304-315`）与 `test_a_useable_name_is_required`（`:276-296`）本票一行未动，随定向/全套绿。

### 2. 假设

- 假定 `DELETE /api/faces/known/<name>` 对 `..a` / `a..b` / `Alice Ng.`（经 `quote(safe="")` 编码后）解析到同一 handler 且落在同一名字段：这是实测结论（`:371-374` 200 且名单清空），不是静态推断。
- 假定 `list_file(tmp_path)` 指向的正是产品写路径落盘的 `known_faces.json`（名单路径已由 `build` fixture 隔离到 tmp），故「文件未损坏」测的是产品写盘而不是测试桩。
- 假定 08 门的存活变异形态是 `cleaned.startswith(".")`；我复现并按该形态验证。若门改用别的过拒形态（如 `endswith(".")` 或「含点即拒」），覆盖由四条参数分摊，不依赖单条。

### 3. 我知道没覆盖什么

- 没测含点名与普通名**混存**时名单文件形状（本条 test 每个参数独立 `tmp_path`，只验单条落盘）。
- 没测含点的重复注册（409 `name-exists`）：`name-exists` 已有独立用例（`tests/test_face_api.py:250` 起）但参数是 `Alice`，不含点形态。
- 没测未编码请求（如把空格原样塞进 URL 段）——那是客户端行为，不在校验契约内。
- `a..b`（点在中间）钉不住 08 那发「点开头」变异，真正杀死它的是 `..a`；若日后有人只留一条，请留 `..a`。
- 「没动 X」逐条给路径：`UNREACHABLE_NAMES` `tests/test_face_api.py:304-315` 未改；`test_a_useable_name_is_required` `:276-296` 未改；产品 `src/rvm/server/session.py` 两次变异后已还原，sha1 `5F8A55A9804712A5730C50855E387BF20F0F5D2B` 与动手前一致、`git diff` 为空；`src/rvm/server/app.py`、`tests/test_app.py`、`src/rvm/web/*` 本票零改动（`git status` 无这些路径）。
- `node tools/coverage-tests.mjs` 在本仓库不存在（`tools/` 只有 `benchmark.py`、`build_report.py`、`inspect_template.py`、`make_block_diagram.py`、`make_zip.py`、`render_report.py`、`verify_report.py`），派发消息里的「无覆盖：tests/test_face_api.py」无法本地复跑 —— 标 UNVERIFIED，不做替代推断。

### 4. 复现命令

```powershell
cd <repo>; .\.venv\Scripts\python.exe -m pytest tests/test_face_api.py -q -k can_be_deleted_again
```
预期 9 passed（绿）。然后把 `src/rvm/server/session.py` 的 `if cleaned in (".", ".."):` 改成 `if cleaned.startswith("."):` 再跑同一条 → `FAILED ...[..a]`；还原后 sha1 回到 `5F8A55A9…`、同一条复绿。

### 5. 我认为最脆的一处

`..a`（`tests/test_face_api.py:345`）这一条参数。它是「合法」与「看起来像目录穿越」的唯一交集：任何一次以安全为名的收紧（点开头就拒）都会先打红它；反过来，为了让红转绿而把它删掉或放宽，08 门那发 `startswith(".")` 变异立刻重新存活。换了我是攻击者，第一刀砍这里。

### 6. 票面外的决定

- 决定：参数列放 4 条（`Alice Ng.`、`J. Smith`、`..a`、`a..b`）而不是票面举例的 2 条 / 理由：票面举例只钉「含点」，钉不住 08 门实际的「点开头」形态，`..a` 是唯一能杀它的可寻址形态 / 影响面：同一 test 多 2 个参数（全套 590→594），产品零改动。
- 决定：`"." in cleaned` 与 `startswith(".")` 两个变异都亲手跑 / 理由：票面自证要的是前者，08 门存活的是后者，只测前者会漏掉真正的盲区 / 影响面：只多两次定向运行。
- 决定：把「只有 `.` 与 `..` 是死段，故含点名必须可存」写进 docstring / 理由：下一个收紧校验的人先读到的是 docstring，这是唯一带方向的反向约束 / 影响面：只改注释，不改断言。

## Verdicts
