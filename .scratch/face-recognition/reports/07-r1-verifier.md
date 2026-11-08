# Verifier report — 07 registry-ui-fixes (r1)

VERDICT: VERIFIED — 三处整改全部亲核闭环：README 与实现一致（两态真机点击实测）、loadNames 版本戳在旧字节上亲手复现红、新字节绿且删除路径同护；docstring 归位、定向 67/0、全套 570/0、03/04 回归不回退。
HEAD: 171b9bc714751a548384a17a3ca6fe0e7dcc0d24
LEDGER: 07-r1-001,07-r1-002,07-r1-003,07-r1-004,07-r1-005,07-r1-006,07-r1-011,07-r1-012,07-r1-013,07-r1-014,07-r1-015,07-r1-016,07-r1-018,07-r1-019,07-r1-020,07-r1-021,07-r1-023,07-r1-024

## 定靶

- 票面写域 4 文件；实现 diff（基线 `fdf03c9`…`171b9bc`）：`README.md` +2/-1、`src/rvm/web/app.js` +19/-3、`tests/test_app.py` +27、`tests/test_report.py` +3。规模 ≪ 票面 ≤300 行上限；外加票文件两处（认领/实现说明）属允许面。
- 提交 `ef1da0a`（实现）+ `171b9bc`（实现说明行号回对，仅票文件，产品零字节变化）。**验证靶 = `171b9bc`**（07 范围顶端）。
- 验证期间主仓 tip 前进到 `7671388`（05 号票并行落地，`tests/test_integration_faces.py` 等），不在本靶；worktree `C:\Users\joe\AppData\Local\Temp\verify-gate-7671388` 已 checkout 钉在 `171b9bc`。
- 证据落盘：`.scratch/face-recognition/verifier-probes/07-registry-ui-fixes-verifier.md` + `07v-dom-*.html`（12 份）+ `07v-shot-*.png`（4 张）+ `07v-probe-lines.txt`。驱动页 `v07-driver.html` 是我本轮在副本里新写的（非 worker 那份），同法不同文。

## 我若偷懒会省的 5 处

只读 diff 不点开页面就断言 README「与实现一致」；拿 worker 的 `07-*.png`/selfcheck 当自己的 race 证据；只在修后字节上跑 race 不回放旧字节（红态不成立则「修复」无对照）；相信实现说明「573」而不在 171b9bc 上重跑全套（该数含 05 未跟踪文件，靶内应为 570）；忽略删除路径只验保存路径的戳。以下全部是本轮新跑。

## 判据逐条

| 判据 | 证据 | 判定 |
|---|---|---|
| AC1 [AS-2,AS-5] README 不再断言「pending/disabled 按钮不可用」，新描述与实现一致 | 旧句 `the button is unavailable for exactly those two states` 全库无命中（grep，含 FEATURES.md 复查）；新句 `README.md:126-128`「stays clickable … `analysis is off` / `models still loading`」。真机：`--no-analysis` 实点击 → `analysis is off`（07-r1-003，`disabled=false`）；预热窗内实点击 → `models still loading`（`07v-dom-loadingclick2.html`，哈希见 07-r1-023）；`app.js:576-600` 只在请求在途置灰。失败 POST 全程不写文件（`%TEMP%\v07v\empty` 始终为空） | PASS |
| AC2 [AS-2,AS-3] 晚到 GET 不得覆盖写后名单 | **红**：副本内换 `fdf03c9` 版 `app.js`（sha256 `e443c812…`，无 `namesStamp`）→ race 探针 `list="No names saved yet"`（07-r1-015）。**绿**：修后字节同探针 `list="Race Person"`（07-r1-001，截图亲见）。**删除同护**：`racedel` 晚到 GET 带删前两行、真 DELETE 已答 → 被丢弃，名单保持删后一行（07-r1-006）。**首载不误伤**：种子页正常渲染两行（07-r1-004）。静态钉 `tests/test_app.py:731` 由真 HTTP 取 `/static/app.js` 断言 | PASS |
| AC3 [AS-5] 孤儿 docstring 归位、断言原位 | `tests/test_report.py:276` `TestMeasuredClaimsMatchTheImplementation` 恢复为独立类，docstring 重新成为类文档串，两条无关断言归其名下；junit（07-r1-024 输入哈希）按类名归集：`TestFaceRegistrationIsDescribed` 恰 3 条注册断言、新类恰 2 条 | PASS |
| AC4 [AS-5] 定向/全套绿；03 可读性与 390 顺序、04 五态不回退 | 定向 67/0/0/0（07-r1-024 哈希的 `junit-directed2.xml`，exit=0）；全套 **570/0/0/0 exit=0**（07-r1-019；570+05 的 3 条集成用例=worker 的 573，一致）。`style.css`/`index.html` 对 `fdf03c9` diff 为空 → 03 数值无回归路径；四条可读性钉与五态文案钉均在 junit 绿列；真机 390：`scrollW=390 clientW=390 regOrder=4 regTop=656`（07-r1-014，与 04 门读数一致）。五态本轮实见：no-face 真409（07-r1-002）、analysis-off 真503（003）、models-loading 真503（loadingclick2）、multi/dup/success 桩（011-013） | PASS |

## FINDINGS

1. **[FYI] src/rvm/web/app.js:602-613 — 写-写交错的残余 stale-render** / `namesStamp` 只防读-写交错：保存请求在途时点 `×`（删除钮不置灰），两条写响应按到达序各 `renderWrittenNames` 一次，后到达者赢——若 POST 先于 DELETE 落盘却后于 DELETE 渲染，已删名字会短暂复活至下一次渲染源。与 FINDINGS-2 同族但在写-写路径，先于本票存在、非本票引入、票面范围外；localhost 时序下很难自然触发。分析性结论，未动态复现。confidence: MEDIUM
2. **[Nit] 探针目录** — 我第一批 stub 命令把 `CAZ` 占位符写进了 URL，产出无用的 `07v-dom-CAZ.html` 数秒后被我删除（该文件是我本轮自产、非既入库探针）；ledger 07-r1-007..010 为对应噪声条目，如实披露。
3. **[Nit] `loadingclick` 首跑未命中预热窗**（server 起后 sleep 2s 已超时）→ 落点得到的是真 409 `no face in frame, hold still`（07-r1-016），仍佐证可点击性；pending 态证据以 `loadingclick2` 为准。

## REMEDIATION

- 无阻断项。可选跟进（建议新票，不在本票路由）：`[impl]` 写-写交错 stale-render——两条写路径可共用「响应携带提交序」或串行化前端写，或给 `×` 在写在途时同样置灰。

## 攻击族（逐族）

1. **并发/时序**：race（GET 迟 400ms vs 即时 stub 201）在旧字节红、新字节绿；`racedel` 把同型 stale-read 扩展到删除路径 → 绿；首载不误伤 → 绿。
2. **环境状态（全真）**：`--no-analysis` 真 503 `analysis is off`；预热窗真 503 `models still loading`；合成场景真 409 `no face in frame, hold still`。五态中三态零桩。
3. **契约外/桩载荷（标注）**：stub 201/409×2 全真渲染路径，文案逐字命中。
4. **注入/XSS**：种子名 `<img src=x onerror=…>` 经真 GET 渲染为纯文本（dom dump `&lt;` 转义、截图亲见字面文本，无注入元素）；删除走 `encodeURIComponent` 路由（真 DELETE Alice 命中，服务端文件核对一致）。
5. **变异杀伤**：2/2 被杀——守卫行 `→ if(false)`（07-r1-020）、两条写路径去戳（07-r1-021），均 sha1 一致还原。每条判据均有可指认的杀死变异；静态测试钉的是语义结构（取戳→await→守卫→渲染 的顺序与两条写路径同戳），换名会红属已知局限（工人自陈 §5），行为判据由真机红/绿兜底。
6. **边界/首载**：空名单初始 `No names saved yet`；种子名单正常渲染；失败 POST 不落盘（空目录全程为空，含我额外 curl 的真 409）。
7. **回归**：`style.css`/`index.html` 零 diff + 四条可读性钉 + 真机 390 `order=4` + 五态文案钉与实见。

## NOT RUN

- 真 201 / 真 `multiple-faces` / 真 `name-exists`（合成场景无真人脸 → 桩标注，与 04 门同限）。
- Firefox/Safari 时序（仅 Chromium headless）。
- XSS 名的 DELETE（04 门已覆盖且该路径本轮未改）；`deletexss` 类二次删除未复跑。
- 写-写交错的动态复现（FINDINGS-1 为分析性结论）。
- 账本噪声：07-r1-007..010（CAZ 占位符，产物不存）、07-r1-017（引号崩坏 exit 2）、07-r1-018（定向 pytest 撞上本机已知 `0xC0000409` 间歇性关机崩溃 exit 127；同命令未包裹重跑 exit=0、junit 67/0，其哈希由 07-r1-024 收录）、07-r1-022（sed 引号崩坏 exit 255）、07-r1-024（命令部分失败但 junit 哈希已录）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 171b9bc | reports/07-r1-verifier.md | [impl]1（可选跟进） | 三处整改亲核闭环：race 旧字节红/新字节绿、两态真机点击实测、全套 570/0 不回退 |
