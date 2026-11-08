# Repo-fit — SEAM-1（票 01–04）

对照物：spec.md、context.md、README.md、docs/FEATURES.md、DELIVERY.md、tests/test_app.py、tests/test_delivery.py、src/rvm/web/style.css、src/rvm/server/{app,session}.py、src/rvm/analysis/{recognition,states}.py、tools/make_zip.py。

## Findings

### Important

1. **票 02 — 端点测试落点偏离 spec 的 Testing Decisions。** spec.md:53 钉死「单元与端点测试：`pytest tests/test_face_store.py tests/test_recognition.py tests/test_app.py -q`」；票 02:22 把定向命令改成 `tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py`，且 02:42 明令「不要改 `tests/test_app.py`（03/04 号票的写域）」。按 spec 声明的命令跑 SEAM-1 的单元/端点门，三个新端点零覆盖——票 02 在 spec 之外另立了测试布局却没回填 spec。写域切分本身合理（02 与 03/04 并行、test_app.py 归后两票），建议改 spec.md:53 把端点测试文件换成 `test_face_api.py`（保留 test_app.py 静态 UI 断言归 03/04），而不是改票的写域。

2. **票 02 — 注册路径的共享状态写纪律缺席，撞上仓库明文的 swap-not-mutate 约定。** `FaceRecognizer.known_faces` 在 encode 线程里被 `_nearest` 迭代（recognition.py:282–285，经 `_analyse` → `recognize` → `_match`），而 POST/DELETE 注册端点必然从事件循环改这个 dict——迭代中改 dict 会抛 `RuntimeError` 并杀死 `_encode_once`，画面流中断，正撞 AS-1「画面流不中断」。仓库对此有明文约定：session.py:152–153「One tuple, swapped atomically: readers never see a half-applied tick」、session.py:425–426「Rebind rather than mutate … a half-updated list」。票 02 的开工包与判据都没提这条纪律。建议加一句：名单更新沿用现有 swap/copy 纪律（整体替换 `known_faces` 或经 encode 节拍串行化），并在 02 判据里点明「注册/删除不得在迭代中改 dict」。同理「最近三次分析帧」缓冲也是事件循环读、encode 线程写，同一纪律适用。

3. **票 03 — AC 下限低于已签字的 v2 设计值。** context.md:10 记录用户已签字的 v2：标签 13px、读数 15px、对比度 7.7:1、行高 1.5；design/v2/NOTES.md:2,4 给出同组数值（灰标签 7.73:1、正文 16.65:1）。票 03:13–14 的 AC 写成「标签 ≥12px」「正文 ≥7:1」——照抄 AS-6 底线，低于签字值。verifier 从票文重建判据时，12px 标签、7:1 正文都判得过，却违反已签字设计。建议：AC 改为「按 `docs/DESIGN-dashboard.md`（01 票产出）的数值，AS-6 数值为硬下限」，或直接在 AC 引用签字值；峰值角标 12px 与 NOTES.md:17 一致，无需动。

### Nit / FYI

4. **票 04 — 文档同步范围漏 DELIVERY.md（spec 授意的漏）。** spec.md:28 只点 README/FEATURES/build_report.py；DELIVERY.md §1 交付物树（DELIVERY.md:28–30 列 `analysis/ quality.py, detect.py`）本就落后于现有模块，`face_store.py` 落地后更旧。该文件随 zip 交付（make_zip.py:41）。无需改票，知道即可；顺带：派发给的 `docs/DELIVERY.md` 实际在仓库根 `DELIVERY.md`。

5. **（c) 术语轴：干净。** 名单/嵌入/相似度/峰值标注/读数/八项操作用词与 context.md:14–19 一致；票 04「名字 · 相似度」对应载荷字段 `confidence`（recognition.py:98），正是 context.md:17「1 − 欧氏距离，不是概率」的措辞；状态词表（states.py:40–47）无新增无改写，`no-known-faces` 语义（states.py:18–22、FEATURES.md:115）与票 02/04 一致。

## 核过无冲突（防复读，列证据）

- 路由命名：`POST/GET/DELETE /api/faces/known` 与既有 `/api/faces/identities`（app.py:96）同族，"known faces" 词族与 `known_faces`、`add_known_face`、`no-known-faces` 一致。
- 识别器接口：`add_known_face`/`remove_known_face` 已存在（recognition.py:222、226），票 02「扩展它」方向对；嵌入 ~1434 维（recognition.py:27）与 context.md:16 一致。
- 折线数据源：`history = { bitrate: [], max: 60 }`（app.js:13）与票 03「history.bitrate 最多 60 点」一致；峰值用 `Math.max` 同源数组即可。
- `analysisText()`（app.js:31–46）确为身份行文案入口，票 04「扩它」可行。
- 票 03 列的字面 ID 全部存在：`.layout`、`view-source`、`view-decoded`、`roi`、`sensitivity`、`clear-roi`、`clips`、`spark`（index.html、style.css:50、123）。
- `#stream` 内联 `src="/api/stream.mjpg"`（index.html:22）由 test_delivery.py:40–52 钉住，票 03:36 已声明遵守。
- 远程资源禁令与 DOM 契约测试（test_app.py:87–110）被各票遵守。
- 「不进 zip」天然成立：make_zip.py 白名单 TREE_DIRS（make_zip.py:54–59）不含 `data/`；`.gitignore` 目前无 `data/known_faces.json`，票 02 补。
- 新测试文件 `test_face_*.py` 被 pyproject `python_files = ["test_*.py"]` 与 `asyncio_mode = "auto"`（pyproject.toml:49–52）自动收编。
- 错误码风格 `web.HTTPBadRequest/HTTPConflict/HTTPServiceUnavailable` 与现有 handler 一致（app.py:140、264、271）。
- seam 选择无被违：注册门在分析开启（spec:39 ↔ 02 判据 503）；TDD 约定（README.md:257–258）被 02/03/04 的「含测试」「先红后绿」沿用；被否方案（context.md:21–27）无一复活。
