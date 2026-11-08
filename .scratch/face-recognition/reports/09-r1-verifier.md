# 09 — 含点合法名字参数用例验收（r1）

VERDICT: VERIFIED — 新 4 条含点参数走真 HTTP（aiohttp TestServer 真端口）注册 201 且名单文件未损坏；亲手三发变异（含点即拒 / startswith / endswith）全部按正确范围变红，还原 sha1 一致后复绿；定向 48、全套 594 绿，产品面对 08 基线零改动。
HEAD: 26b75ad4fd30a1b885cc1a44f5e82f7491c54fe4
LEDGER: 09-r1-001,09-r1-002,09-r1-003,09-r1-005,09-r1-006,09-r1-007,09-r1-008,09-r1-009

- 定靶：票面「已交票，提交 1659aaf」；实际验收定靶 `26b75ad`（1659aaf 之后一个 commit，仅落盘 `reports/09-r1-worker.md`，产品 diff 相同——与 08 门同型偏差）；基线 `c15b659`（08 门 VERIFIED 的 HEAD）。
- 范围：`git diff c15b659..26b75ad` 产品面 = 仅 `tests/test_face_api.py` +18/-1（参数列 +4、docstring +6），其余为票面与 context/报告文档（09-r1-008）。+19 行 / 1 产品文件，远在 ≤50 行 / 1 文件上限内；无功能与重构混杂。
- 环境：gate-kit worktree `verify-09-r1-26b75ad`（Temp，detached @26b75ad，跑完后 cleanup）；主仓 `.venv` Python 3.13 + aiohttp 3.14.5；主仓 src/ tests/ 零写入（变异全部在副本内）。
- 我若偷懒会在这 5 处省事：①拿 worker 自陈的两次变异输出当证据、不亲手复跑；②只打票面要求的「含点即拒」变异、不打 08 门真实存活的 `startswith(".")` 形态；③断言「走真 HTTP」只看 `client.post` 字样不追 `build` fixture 与 import 面；④「文件未损坏」只看断言存在、不核 `list_file` 是否产品写路径；⑤全套计数只看 exit 0 不对 590→594 的口径。

## 判据 → 本轮证据

### AS-4 合法含点名字注册返回 201、不写坏文件、过拒变异下必红 — 满足

- **真 HTTP，非直调**：测试文件 `grep validated_face_name` 零命中，import 面无校验符号（`tests/test_face_api.py:11-31`）。链路逐跳核过：`client.post`（`:365`）→ aiohttp `TestServer(app)` 绑真端口（`build` fixture `:137-138`）→ `app.py:105` 路由 → `handle_register_face`（`app.py:381-394`）→ `session.register_face`（`session.py:634`）→ `validated_face_name`（`session.py:643`）。变异态失败响应体 `ClientResponse(http://127.0.0.1:56487/api/faces/known) [400]` 证明走了真 TCP 端口（09-r1-003）。
- **201 + 名单文件未损坏**：4 条新参数（`Alice Ng.`/`J. Smith`/`..a`/`a..b`，`:343-346`）在原样代码下全绿（09-r1-001、09-r1-007）；断言 `:368-369` 用 `json.loads(list_file(tmp_path).read_text())` 重读磁盘并 `list(stored) == [legal.strip()]` —— `list_file` 与传给 `StreamSession` 的 `known_faces` 是同一路径（`:95`、`:106`、`:159-160`），测的是产品 FaceStore 真实落盘，文件不存在/坏 JSON/多写条目三种坏法都会红。
- **可寻址性**：`:371-374` 用 `quote(legal.strip(), safe="")` 组 URL 段 DELETE，断言 200 + `known == []` —— `..a`/`a..b` 仍可寻址，正是本修复要保护的性质。
- **过拒必红（亲手三发）**：`"." in cleaned` → 恰 4 新参数全红、5 旧参数绿（09-r1-003）；`startswith('.')`（08 门原样存活形态）→ 恰 `[..a]` 一红（09-r1-005）；`endswith('.')` → 恰 `[Alice Ng.]` 一红（09-r1-006）。三发后 sha1 均还原 `5F8A55A9804712A5730C50855E387BF20F0F5D2B`（与 worker 动手前值一致），复跑 9/9 绿（09-r1-007）。每条判据都能指出杀死它的变异。
- **杀伤范围正确性**：三发变异的红名单恰好是语义上该被拒的子集（含点→4、点开头→1、点结尾→1），证明红来自断言语义而非测试脆性或收集错误。

### AS-5 定向与全套通过、其它名字校验行为不变 — 满足

- 定向 `pytest tests/test_face_api.py -q`：**48 passed，exit 0**（09-r1-001，口径 = 44 旧 + 4 新参数）。
- 全套 `pytest`：**594 passed in 30.85s，exit 0**（09-r1-002）= 08 基线 590 + 4，无其它增减。
- 拒绝面零改动：`git diff c15b659..HEAD -- src/` 为空、`session.py` sha1 与基线相同（09-r1-008）；`UNREACHABLE_NAMES` 与 `test_a_useable_name_is_required` 未动（diff 仅两处 hunk 均在合法参数侧），随全套绿。

## FINDINGS

无 Blocking / Important / Nit。

1. `[FYI] [env]` — 派发引用的 `无覆盖：tests/test_face_api.py` 是工具口径假象：`coverage-tests.mjs` 的 `TEST_RE` 只匹配 `*.test|spec.[cm]?[jt]sx?`（JS/TS），Python `test_*.py` 不在扫描面，任何 Python 写域都必然报「无覆盖」（09-r1-009 复跑确认；worker §3 说工具不存在是因为在仓内 `tools/` 找，实际工具在 gate 工具目录）。真实覆盖证据是三发变异全杀。confidence: HIGH。
2. `[FYI] [test]` — 账本 09-r1-004 是本门自身引号转义失败：cmd.exe 吃掉 `startswith(".")` 的内层双引号产出 `startswith(.)` 语法错，exit=2 红是收集期 SyntaxError 而非语义杀，已按无效证据处理并以 09-r1-005（单引号形态 `startswith('.')`）重做拿到真杀——与 08 门 011/012 同一坑同一解法。confidence: HIGH。

## 收编清单

不适用：本票自身就是收编动作（08 门 FINDINGS-1 的存活变异已收编进 `test_a_name_that_can_be_deleted_again_is_still_accepted` 参数列，且 `..a`/`a..b` 形态正是 08 收编清单建议的收编形式）；本轮无新存活变异。

## NOT RUN

- 真服务器 `run_server.py` 未起：本票为纯测试增补，aiohttp TestServer 真端口是 08 门同款认可表面，变异在 HTTP 层已证。
- 桌面/移动视口：非 UI 票。
- 拒面（`bad-name` 各参数）在变异态下的存活未逐条断言：`-k` 只选合法参数侧；拒面不回归由「产品 diff 为空 + 全套 594 绿」覆盖，判据不依赖它。

## 诚实说明

- 所有 pytest 与变异均在 Temp worktree 内跑；主仓 `git status -- src/ tests/` 干净，`session.py` 未被本门触碰（sha1 三次变异前后一致）。
- 账本 004 如实保留为失败记账（我自己的转义失误），不引用为证据；LEDGER 行不含 004。
- worker 报告 `reports/09-r1-worker.md` 的 TESTS 段读数未作为本轮证据（转述-未核）；与其一致处均由本轮条目独立取得。
- 每条逐字引用均可被内容搜索命中：`tests/test_face_api.py:343-346`（参数）、`:365-374`（断言）、`:95/:106/:121-145/:159-160`（fixture 与写路径）、`session.py:83-110/:643`（校验单点）、`app.py:105/:381-394`（路由与 handler）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 26b75ad | reports/09-r1-verifier.md | — | 4 条含点参数真 HTTP 201+文件完好断言，三发变异按正确范围全杀且还原复绿，全套 594 绿 |
