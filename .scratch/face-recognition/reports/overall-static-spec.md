# Overall gate — static axis: Spec 对照 (AS-1..AS-7)

VERDICT: VERIFIED — 7 条 AS 逐条拿到本轮新鲜证据，接口契约九枚 reason 与响应体逐字对上，发现的缺口均为 context.md 已记录、逐票门已裁决的解释性取舍，非静默放宽。
HEAD: 01d08b75d838c7aeb48d24e3ecbaedfba4919ec0
LEDGER: 无账本条目（静态轴不在逐票轮次体系内；证据为本轮亲手运行的只读命令与逐字引用）

- 范围：`git diff 8db38f4..HEAD -- src tests tools README.md docs/FEATURES.md docs/DESIGN-dashboard.md`
- 规模：17 文件，+3480/-258（7 票整体范围，超出单票尺寸闸门属预期，不援引尺寸驳回）
- 基线锚定：`git rev-parse HEAD` = 01d08b7；`git status --porcelain` 仅 `M .scratch/.../07-r1-verifier.md`（报告文件，与产品无关）
- 本轮亲手运行：`./.venv/Scripts/python.exe -m pytest` → **573 passed in 23.35s**（exit 0）

## AS-1 面板注册闭环 — 满足

- 取样平均：`src/rvm/server/session.py:653` `for frame in frames[-REGISTRATION_FRAMES:]`，每帧必须恰好一张脸（`:655` no-face、`:660` multiple-faces 即拒）；`:679` `faces[name] = np.mean(np.stack(embeddings), axis=0)`。
- 成功响应体：`session.py:681` `return {"name": name, "samples": len(embeddings), "known": self.known_face_names()}`；`app.py:398` `return web.json_response(result, status=201)` — 与契约 `201 {"name","samples","known"}` 逐字一致。
- 不阻塞：`app.py:394` `await asyncio.to_thread(session.register_face, body.get("name"))`；每次取样 `session.py:709` 单独取 `_inference_lock`（与 `_analyse` 同锁，`session.py:487`）。`tests/test_face_api.py:459` `test_status_and_snapshot_stay_available_while_registering` 在 0.15s×3 的慢取样下断言 `/api/status` 与 `/api/snapshot.jpg` 仍 200；`test_registration_and_analysis_take_the_same_lock` 钉住同锁。
- 前端闭环：`index.html:113-121` 输入框+`REMEMBER FACE`+状态行+名单；`app.js:581` `rememberFace` POST `{name}`，`app.js:591` 成功文案 `Saved as <name>, <n> frames averaged`。

## AS-2 识别展示 — 满足（一处已记录的解释性取舍，见 F-2）

- 名字+相似度：`app.js:84-87` `item.name + " · " + Number(item.confidence).toFixed(2)`；服务端 `recognition.py:110` snapshot 带 `name/confidence/bbox`。
- 低阈值不显示名字（重点核）：`recognition.py:336-337` `if name is None or confidence < self.threshold: return None, confidence` — 低于阈值的人脸不进 `identities`，前端无从编造；`tests/test_recognition.py:241` `test_a_face_further_than_the_threshold_is_not_reported` 直接钉死该分支。review-leads 预测的「有名单就显示」未发生。
- 名单为空：`recognition.py:309-310` `if not known: return FaceRecognition([], STATE_NO_KNOWN, seen=seen)` → `app.js:81` `return (result.seen || 0) + " faces, none known"` — 即契约文案 `N faces, none known`。
- 无人脸：`app.js:78-80` `no-faces` 态，名单空 → `"0 faces, none known"`（N=0），名单非空 → `"no face"`。

## AS-3 持久化 — 满足

- 落盘路径：`face_store.py:44` `DEFAULT_KNOWN_FACES = Path("data") / "known_faces.json"`；`app.py:566-570` CLI `--known-faces`；`app.py:603` `known_faces=args.known_faces`；`run_server.py` 直通 `main()`。
- 原子写：`face_store.py:118-127` mkstemp + fsync + `os.replace`。
- 重启识别：`session.py:192-193` `__init__` 内 `self.face_store = FaceStore(known_faces); self.face_recognizer.replace_known_faces(self.face_store.load())`。
- 删除即落盘：`session.py:696-704` 锁内复制-删除-`_publish_faces`（保存+镜像同步）后返回 `{"removed": True, "known": ...}`。
- 缺文件/损坏：`face_store.py:75-96` FileNotFoundError→空名单，OSError/解析失败→告警+空名单，不崩。
- 不进 git：`.gitignore` 新增 `data/known_faces.json`。
- 跨进程证据：`tests/test_integration_faces.py:258` `test_real_processes_carry_the_registry_and_survive_a_corrupt_one`（真实子进程重启），`:138` 注册→识别→重启→删除一条龙。

## AS-4 失败与降级 — 满足

- 409 无脸/多脸/重名：`session.py:631/657/662/675`；503 分析关/未就绪/不可用：`:636/640/713`；500 写失败：`:735`；全部经 `app.py:361` `_fail` → `{"error","reason"}` JSON。
- 不写文件：所有 `raise FaceRequestError` 都在 `_publish_faces`（唯一写盘点，`session.py:728-736`）之前；写失败时 `:734` 恢复旧映射。`tests/test_integration_faces.py:167` 断言被拒后文件不变且服务继续可用。
- 四分析器状态词表不变：`states.py` 不在 diff 内；`recognize()` 的 `STATE_NO_FACES/NO_KNOWN/RUNNING/UNAVAILABLE/ERROR` 与 baseline 逐行一致（`git show 8db38f4:...recognition.py` 核对，`seen` 字段为既有）；`app.py` diff 仅 1 行 import 改动，其余纯增。

## AS-5 不回归 — 满足（一处 ID 取舍，见 F-1）

- DOM ID：新旧 `index.html` id 集合 diff = 新增 `face-*`/`m-peak`、删除 `overlay-bottom`，其余全保留；`tests/test_app.py:612-620` 的 `kept` 清单（不含 `overlay-bottom`）全部断言通过。
- 八项操作：`test_app.py:622-634` 钉 7 控件 `.onclick` + `$("sensitivity").onchange` + 画面 `pointerdown/pointerup` 拖拽；`index.html:32-67` 全部控件在场。
- 无远程资源：`index.html` 只引 `/static/` 与 data: URL；`test_app.py:87-95` 正则禁 `http(s)//`、`@import`。
- 无新增依赖：`requirements*.txt`、`pyproject.toml` 不在 diff；`face_store.py` 仅用标准库+NumPy。
- 响应式：`style.css:285-310` ≤900px 单栏排序（stage→controls→hint→registry order:4→sections order:5）、`:312-318` ≤560px 读数单列；无横向溢出证据 `07v-shot-mobile.png` 探针量得 `scrollW=390 clientW=390`。
- 全套测试：573 passed（本轮新跑）。

## AS-6 可读性实际值 — 满足，全部超出下限

| 判据 | 规格下限 | 实际值（style.css，另由 test_app.py 计算钉住） |
|---|---|---|
| 最小标签字号 | 12px | `--fs-label:13px`（:29）；12px 仅 OSD(:95)/track-tag(:121)/peak(:210) |
| 数值字号 | ≥15px | `--fs-body:15px`（:30），读数 `font:500 var(--fs-body)/1.5 var(--mono)`（:195）|
| 手机正文 | ≥14px | ≤560px `--fs-label:14px`（:313），正文/读数/按钮仍 15px（:316）|
| 灰字对比度 | ≥4.5:1 | `--muted #9aa5aa`/`--bg #0b0d0e` = **7.73:1**（test_app.py:399-403 WCAG 2.1 实算）；`--text-2` 11.94:1；`--placeholder`/`--panel` 5.10:1 |
| 行高 | ≥1.5 | body `font:.../1.5`（:44），全部 font 速记均 /1.5，无例外 |
| 分组间距 | ≥20px | `.section+.section` margin 20+padding 18=38px（:169）；≤900px 8+16=24px（:297）|

- 对照表在 `tests/test_app.py:413-500`，断言精确值（7.73/16.65/5.10/≥12/5 sections）。

## AS-7 简洁与观感 — 满足

- 分区 ≤6：`index.html` `.rail` 内 5 个 `<section class="section">`（Stream/Transport/Analysis/Face registry/Clips），`test_app.py:500` `assert len(...) == 5`；`DESIGN-dashboard.md:131-147` 「全页 5 个分区(上限 6)」。
- 画面第一焦点：`style.css:73` `minmax(0,1fr) 460px` 画面占主列；截图 `07v-shot-firstload.png` 画面为最大面积元素。
- 控件读数一个不少：AS-5 的 ID/操作核对（上）+ 截图全部读数可见。
- 1440×1000 无被截断操作：`style.css:280` `rail max-height:calc(100vh-102px);overflow-y:auto`（栏内滚动而非裁切）；读数 `overflow:hidden;ellipsis` 只作用于值文本，操作控件不在裁剪路径上；桌面截图整栏在 1000px 内完整可见。
- 去冗余：`data-channel` 与 `overlay-bottom` 移除（重复标签），分隔线仅分区间 5 条。

## FINDINGS

- [Important] `src/rvm/web/index.html` — AS-5 字面「保留全部既有元素 ID」与 `overlay-bottom` 的移除存在张力；由 AS-7「去重复标签」调和（该容器承载的是 `src-label`/`time-label` 的第二份副本，两个内容 ID 仍在，`index.html:28-29`），context.md 票 3 明确记录、test_app.py:514-522 已按新结构钉住。非静默放宽，但属 AS 字面与实现的出入，留档。confidence: HIGH
- [Important] `src/rvm/web/app.js:78-80` — `no-faces` 且名单非空时 Face IDs 显示 `no face`；AS-2 字面「无人脸时显示 N faces, none known」的另一种读法要求 `0 faces, none known`。context.md 票 4 记录了「不能在有名单时谎报 none known」的取舍，04 门已按此 VERIFIED。规格文字本身有歧义，实现选了更诚实的读法。confidence: HIGH
- [FYI] `src/rvm/server/session.py:699-700` — DELETE 未知名回 404 配 `reason: bad-name`；契约枚举无 `not-found`，404 由契约固定，context.md 票 2 r1 记录此取舍。
- [FYI] `src/rvm/web/app.js:568-573` — `bad-name`/`samples-missing`/`unavailable`/`write-failed`/404 未入 `FACE_REASONS` 固定文案，回退到服务端 `body.error` 原文；票 4 五态文案（no-face/multiple-faces/name-exists/analysis-disabled/models-loading）全部逐字在场。
- [Nit] `src/rvm/server/session.py:679` — 若 `register_face` 抛出非 `FaceRequestError`（如 `np.stack` 形状异常），将产生非契约形体的 500；实际不可达（同一 landmarker 产出定宽向量），仅为鲁棒性观察。
- [Nit] `src/rvm/server/session.py:630-641` — 重名检查先于 analysis-disabled/models-loading：名单已有该名且分析关闭时回 409 `name-exists` 而非 503；契约未钉优先级，两者均为合法枚举。

## NOT RUN（本轴范围外）

- 真机浏览器注册→识别→重启→删除的端到端演示与两档视口实测截图（属整体动态门；本轴只以既有探针截图 `07v-shot-firstload.png`/`07v-shot-mobile.png` 作旁证）。
- 注册进行中 MJPEG 逐帧连续性的人工观测（有 `test_status_and_snapshot_stay_available_while_registering` 的确定性代理证据）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 01d08b7 | .scratch/face-recognition/reports/overall-static-spec.md | - | 7 条 AS 逐条亲核满足，九枚 reason 与响应体逐字对契约，两处出入均为已记录的歧义取舍而非静默放宽 |
