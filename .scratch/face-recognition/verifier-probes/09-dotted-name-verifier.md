# 09-r1 verifier probes — 含点合法名字用例验收

Target: HEAD `26b75ad4fd30a1b885cc1a44f5e82f7491c54fe4`（票面声称 1659aaf；26b75ad = 1659aaf + 仅 worker 报告落盘，产品 diff 相同）。
Baseline: `c15b659`（08 门 VERIFIED HEAD）。
Worktree: `C:\Users\joe\AppData\Local\Temp\verify-09-r1-26b75ad`（gate-kit worktree --ref 26b75ad，detached；所有 pytest 与变异只在此副本内跑，主仓 src/ tests/ 零写入）。
Ledger: `.scratch/face-recognition/ledger/09-r1.jsonl`，条目 09-r1-001…009。

## 静态核对（读代码）

- 新参数 4 条落在 `tests/test_face_api.py:343-346`：`"Alice Ng."`、`"J. Smith"`、`"..a"`、`"a..b"`；diff 全文两处 hunk：参数列 +4、docstring +6 行，共 +18/-1。
- 真 HTTP：`tests/test_face_api.py:365` `client.post("/api/faces/known", json={"name": legal})`；`client` 来自 `build` fixture（`:121-145`）：`create_app(session=session)` → `TestClient(TestServer(app))` → `client.start_server()` —— aiohttp TestServer 绑真 127.0.0.1 端口。请求链路：`app.py:105` `add_post("/api/faces/known", handle_register_face)` → `app.py:394` `session.register_face(body.get("name"))` → `session.py:643` `validated_face_name(name)`（`session.py:83-110` 单一校验函数）。
- 不直调校验函数：`grep -n "validated_face_name" tests/test_face_api.py` 零命中；测试文件 import 面（`:11-31`）为 asyncio/json/time/quote/cv2/numpy/pytest/aiohttp TestClient·TestServer/rvm 包，无 `validated_face_name`、无 `register_face`。
- 名单文件断言测产品写路径：`list_file(tmp_path)` = `tmp_path / "data" / "known_faces.json"`（`:159-160`）；`build` 把同一路径作为 `known_faces` 传给 `StreamSession`（`:95`、`:106`），即产品 FaceStore 的落盘路径，隔离进 tmp。断言 `:368-369` `json.loads(list_file(tmp_path).read_text())["faces"]` + `list(stored) == [legal.strip()]`：文件不存在 → read_text 抛错红；JSON 坏 → loads 抛错红；多写条目 → 列表相等失败红。
- 可寻址断言 `:371-374`：`DELETE /api/faces/known/` + `quote(legal.strip(), safe="")` → 200 + `{"known": []}`。`quote` 不编码点号，`..a`/`a..b` 原样成单 URL 段，钉住「含点但非 `.`/`..` 的名字仍可寻址」这一被保护性质。

## 运行证据（全部本轮亲手跑，账本可查）

| 条目 | 命令（worktree cwd） | 结果 |
|---|---|---|
| 09-r1-001 | `.venv python -m pytest tests/test_face_api.py -q` | 48 passed，exit 0 |
| 09-r1-002 | `.venv python -m pytest` | **594 passed in 30.85s**，exit 0（基线 590 + 新 4 参数） |
| 09-r1-003 | 变异① `cleaned in (".", "..")` → `"." in cleaned`（拒绝任意含点），测试 `-k can_be_deleted_again` | exit 1，**4 FAILED**：`[Alice Ng.]` `[J. Smith]` `[..a]` `[a..b]`；RESTORE sha1 一致 |
| 09-r1-004 | 变异②（cmd 引号转义吃掉 `"."` → `startswith(.)` 语法错） | exit 2 收集期 SyntaxError，**无效证据**，记账如实保留 |
| 09-r1-005 | 变异②重做 `cleaned.startswith('.')`（08 门真实存活形态） | exit 1，**仅 `[..a]` FAILED**，其余 8 绿；RESTORE sha1 一致 |
| 09-r1-006 | 变异③ `cleaned.endswith('.')` | exit 1，**仅 `[Alice Ng.]` FAILED**；RESTORE sha1 一致 |
| 09-r1-007 | 还原后 `-k can_be_deleted_again` 复跑 | 9 passed，exit 0；sha1 `5F8A55A9804712A5730C50855E387BF20F0F5D2B` |
| 09-r1-008 | `git diff c15b659..HEAD --stat -- src/ tests/` | 仅 `tests/test_face_api.py` +18/-1；src/ 零改动 |
| 09-r1-009 | `coverage-tests.mjs --ticket 09` | 输出 `无覆盖：tests/test_face_api.py`（工具 TEST_RE 只认 `*.test|spec.[jt]s*`，Python `test_*.py` 不在扫描面 —— 工具口径假象，非真实缺口） |

变异态红名细节（09-r1-003）：失败行是 `assert response.status == 201 → 400`，响应对象 `ClientResponse(http://127.0.0.1:56487/api/faces/known) [400 Bad Request]` —— 真端口真 HTTP 往返，不是 in-process 直调。

sha1 基线：变异前后 `src/rvm/server/session.py` = `5F8A55A9804712A5730C50855E387BF20F0F5D2B`，与 worker 自陈的动手前值一致，且 `git diff c15b659..HEAD -- src/` 为空（产品与 08 基线逐字节相同）。

## 攻击族账本

- **变异族 ×3**：全部杀死且杀伤范围正确（含点即拒 → 恰 4 新参数红；点开头 → 恰 `..a`；点结尾 → 恰 `Alice Ng.`）。
- **直调绕过族**：import 面无 `validated_face_name`，链路经 aiohttp TestServer 真端口；变异红响应体带 `http://127.0.0.1:*` URL 佐证。
- **断言无牙族**：断言是具体值比较（status / 文件 JSON 键列表 / DELETE 200 + 空名单），变异下逐参数 FAILED 证明执行而非 skip。
- **边界/等价类族**：含点空间三向覆盖 —— 点前缀 `..a`、点后缀 `Alice Ng.`、点中嵌 `a..b`/`J. Smith`；再叠加 `'. '`（点+空格，`J. Smith`）与 `strip('.')` 不等价类，常见过拒形态全被参数列摊到。
- **环境坑**：未触发 OpenCV `clReleaseDevice` abort（08 门 FYI 记录的本机坑）；全部 pytest exit 0 干净返回。

## NOT RUN

- 真服务器 `run_server.py` 未起：本票为纯测试增补，TestClient 是 08 门同款认可表面，变异在 HTTP 层已证。
- 桌面/移动视口：非 UI 票。
