# Overall gate r2 — static axis: Spec 对照 (AS-1..AS-7)

VERDICT: VERIFIED — 7 条 AS 逐条拿到本轮新鲜证据；上一轮两条 Important（`.`/`..` 不可删名字、DESIGN §8 文案漂移）已由 08 修好且各有定向测试钉死；接口契约九枚 reason 与响应体逐字对上。
HEAD: 4dc0acedb86393fc91c2eb9df487c371fc2d9252
LEDGER: 无账本条目（静态轴不在逐票轮次体系内；证据为本轮亲手运行的只读命令与逐字引用）

- 范围：`git diff 8db38f4..HEAD -- src tests tools README.md docs/FEATURES.md docs/DESIGN-dashboard.md` — 17 文件，+3641/-258；相对上轮锚点 `01d08b7` 的增量仅 08/09 两票：`session.py` 的 `validated_face_name`、`style.css` 一条媒体规则、`DESIGN-dashboard.md` §4.4/§8、`test_face_api.py`/`test_app.py` 新断言（`git diff 01d08b7..HEAD` 亲核，+171/-10）。
- 基线锚定：`git rev-parse HEAD` = 4dc0ace；`git status` 仅 `.scratch` 报告/探针新增与 `07-r1-verifier.md` 修改，外加 0 字节游离文件 `nul`（工作区噪音，非产品面）。
- 本轮亲手运行：`./.venv/Scripts/python.exe -m pytest` → **594 passed, exit 0**；`pytest --collect-only` 计 594 条；定向 `-k "could_never_be_deleted or can_be_deleted_again or registry_to_stream_boundary or design_copy_matches or threshold"` → 21 passed。

## 上轮两条 Important 复核（首要任务）

**① `.`/`..` 名字可注册不可删 — 已修好**
- `src/rvm/server/session.py:104-109`：`validated_face_name` 新增 `cleaned in (".", "..")` 拒（`bad-name` 400）、`/` `\` 拒、控制字符从 `<32` 扩到 `<32 or ==127`；判定收在唯一既有校验函数内，docstring 写明「名字必须保持可寻址」的反向约束。
- 测试钉死：`tests/test_face_api.py:304-332` `UNREACHABLE_NAMES` 10 参数（`.`/`..`/` . `/`../x`/`a/b`/`a\b`/`/etc/passwd`/`tab\there`/`nul\u0000byte`/`del\u007fchar`）各断言 400 + `bad-name` + 名单文件不存在；本轮定向跑绿。
- 不误伤：`tests/test_face_api.py:335-374` 9 个合法名（含 09 票补的 `Alice Ng.`/`J. Smith`/`..a`/`a..b`）各走真 POST→201→真 DELETE→200，`..a`/`a..b` 证明只拒死段不误杀含点名。上轮存活的 `startswith(".")` 过拒变异现已被 `..a` 杀死。

**② DESIGN §8 五态文案漂移 — 已修好**
- `docs/DESIGN-dashboard.md:173-195` 表格五态文案与 `app.js` 逐字一致：`no face in frame, hold still`/`more than one face in frame`/`Alice Ng is already saved`/`analysis is off` ↔ `app.js:481-484,565`；`Saved as Alice Ng, 3 frames averaged` ↔ `:591`。
- 顺带修正（票面外决定，有记录）：§4.4 `warming up`→`loading`（`app.js:46,75`）且 `REMEMBER FACE` 不置灰改为「按下得到 `models still loading`」；「录制中画面 3px 外框」改为 `Recording` 读数 `recording` + `#record.active` 告警态（`app.js:112,370-371`、`style.css:161`）。
- 测试钉死：`tests/test_app.py:524` 双向断言——6 条逐字串必须同时在 `app.js` 与文档中，`Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING` 五个旧说法不得再出现。本轮定向跑绿。

## 接口契约复核（Soundness 缝）

- 响应形体逐字对上：`POST` 成功 `session.py:695` `{"name","samples","known"}` + `app.py:398` `status=201`；`GET` `app.py:378` `{"known": ...}`；`DELETE` `session.py:718` `{"removed": True, "known": ...}`；失败一律 `app.py:361-371` `_fail` → `{"error","reason"}` JSON（含 404）。
- reason 枚举：9 枚全部被 `tests/test_face_api.py:34 CONTRACT_REASONS` 钉死并被 `assert_contract`（`:60-61`）校验；实测断言分布 `bad-name`(×4 处)、`name-exists`、`no-face`、`multiple-faces`、`samples-missing`、`analysis-disabled`、`models-loading`、`unavailable`、`write-failed`——九枚各有测试证据。
- 失败不写文件：所有 `FaceRequestError` 抛出点（`session.py:94-109,645-678`）在唯一写盘路径 `_publish_faces`（`:742-749`）之前；写失败回滚旧映射（`:747-748`）。
- 整体替换：`faces = dict(...)` 副本改后 `_publish_faces`→`face_store.replace`→`replace_known_faces` 新 dict（`session.py:692,711`、`recognition.py:255-260`），无原地改。

## AS 逐条判定

**AS-1 注册闭环 — 满足**
- 三帧各取一脸取平均：`session.py:657-679`（`frames[-3:]`、每帧非恰一脸即拒、`:693 np.mean(np.stack)`）；非阻塞：`app.py:394 asyncio.to_thread` + `session.py:723` 每次取样单独取 `_inference_lock`；`test_face_api.py:538` 慢取样下 `/api/status` 与 `/api/snapshot.jpg` 仍 200、`:560` 同锁断言。产品面自上轮锚点零改动，套件 594 绿为新证据。

**AS-2 识别展示 — 满足（一处已记录取舍见 F-2）**
- 低阈值分支（重点核）：`recognition.py:336-337` `confidence < self.threshold → (None, confidence)`，低于阈值的脸不进 `identities`；`test_recognition.py:241` 直接钉死该分支（distance 4.0 → confidence -3）；`:251` 阈值内报名。review-leads 预测的「有名单就显示」未发生。
- 名字+相似度：`app.js:84-87` `name · confidence.toFixed(2)`；名单空→`recognition.py:309-310` `no-known-faces`+`seen` → `app.js:81` `N faces, none known`。
- 杀死它的变异：`confidence < threshold` 改为 `<=` 或删除 → `test_a_face_further_than_the_threshold_is_not_reported` 红。

**AS-3 持久化 — 满足**
- `face_store.py:44` `data/known_faces.json`、`:118-126` mkstemp+`os.replace` 原子写、`:75` FileNotFoundError→空名单、损坏告警不崩；`session.py:206-207` 启动时 load→`replace_known_faces`；删除 `:710-718` 锁内复制+`_publish_faces` 即落盘；`.gitignore:15` 已加；`test_integration_faces.py` 3 条跨进程用例绿。文件自上轮零改动。

**AS-4 失败与降级 — 满足**
- 409 无脸/多脸/重名/缺样本：`session.py:670,673,645/688,658`；503 分析关/未就绪/不可用：`:648,652,726`；500 写失败：`:749`；404 未知名：`:713`。全部经 `_fail` 成形。四分析器状态词表不在 diff 内，不回退。

**AS-5 不回归 — 满足（一处已记录取舍见 F-1）**
- DOM ID 保留、八项操作、无远程资源、无新增依赖：`test_app.py` 45 条静态断言全绿（含 kept-ID 清单、`.onclick`/`onchange`/`pointerdown` 钉点、`http(s)//` 禁令）；`requirements*.txt` 不在 diff；390/1440 两档 CSS 媒体规则在场。

**AS-6 可读性 — 满足**
- 标签 `--fs-label:13px`≥12（`style.css:29`）；数值 `--fs-body:15px`≥15（`:30,:195`）；≤560px `--fs-label:14px`+`select,button 15px`≥14（`:320,:323`）；行高全部 `/1.5`；灰字 `#9aa5aa` on `#0b0d0e` 本轮手算 ≈7.7:1≥4.5（placeholder `#7d888d` on `#101416` ≈5.10:1）；分组间距 `.section+.section` 20+18=38px（`:169`）、≤900px 8+16=24px（`:297`）；12px 仅 OSD/track/peak 角标，仍 ≥12。
- 新增缝：`.rail>.section:first-child`（`:302-304`）补 registry↔STREAM 界线，与 `.section+.section` 同值；`test_the_registry_to_stream_boundary` 断言 margin+padding≥20 且带 1px `var(--line)`。

**AS-7 简洁与观感 — 满足**
- 分区 `class="section"` 计 **5** ≤6（`index.html:73,85,97,111,122`）；`test_app.py:500` `==5`；画面第一焦点 `grid-template-columns: minmax(0,1fr) 460px`（`style.css:73`）；1440×1000 截断由 `.rail{max-height:calc(100vh-102px);overflow-y:auto}`（`:280`）以栏内滚动消解，操作控件不在裁剪路径（仅 `.who`/`.clip` 文本 ellipsis）；冗余 `data-channel`/`overlay-bottom` 已去（`test_the_redundant_frames_and_duplicate_labels_are_gone` 绿）。
- DESIGN §8 与实现逐字一致（见上轮 Important②复核）。

## FINDINGS

- [Important] `src/rvm/web/index.html` — AS-5「保留全部既有元素 ID」与 `overlay-bottom` 移除的张力仍在（由 AS-7 去重复标签调和，`src-label`/`time-label`/`view-label` 均在）；context.md 票 3 已记录、测试按新结构钉住。自上轮裁决后状态未变，沿记。confidence: HIGH
- [Important] `src/rvm/web/app.js:78-79` — `no-faces` 且名单非空显示 `no face`；AS-2 字面另一读法要求 `0 faces, none known`。context.md 票 4 记录了取舍理由（有名单时谎报 none known 更糟），规格文字本身有歧义。自上轮裁决后状态未变，沿记。confidence: HIGH
- [FYI] `src/rvm/server/session.py:709` — `remove_face` 不复用 `validated_face_name`（自做 `strip()`），手改文件塞入的 `a/b` 仍不可删（路由层限制，非新缺陷；08 实现说明已声明该不对称）。confidence: HIGH
- [FYI] 仓库根有 0 字节游离文件 `nul`（untracked，疑为早前会话重定向产物），在 diff 与 zip 白名单之外。confidence: HIGH
- [Nit] `src/rvm/server/session.py:644-655` — 重名检查先于 `analysis-disabled`/`models-loading`：名单已有该名且分析关闭时回 409 `name-exists` 而非 503；契约未钉优先级，两枚均合法枚举。confidence: HIGH（沿记）

## 变异杀伤映射（每条判据对应杀死它的变异）

- `.`/`..` 校验删除 → `UNREACHABLE_NAMES` 参数 1/2 红；`/`-校验删除 → `a/b`、`/etc/passwd` 红；`ord==127` 删除 → `del\u007fchar` 红；过拒（`startswith(".")`）→ `..a`/`a..b`/`Alice Ng.`/`J. Smith` 红（09 票已杀该变异）。
- 移动缝规则删除 → `test_the_registry_to_stream_boundary`（rule 缺失即 assert fail）。
- §8 文案回漂 → `test_the_design_copy_matches` 双向断言红。
- 阈值分支删除/改号 → `test_recognition.py:241/251` 红。
- `_publish_faces` 原地改 dict → `test_face_store.py` 并发接缝（ObservedLock）红。
- `_fail` 改形体 → `assert_contract` 全失败路径红。

## NOT RUN（本轴范围外）

- 真机浏览器端到端演示与两档视口截图（整体动态门职责；08 票真机自检读数 `box=24/visual=25/line=1px` 见 `verifier-probes/08-overall-cleanup-selfcheck.md`，本轴未复跑，标 `[转述-未核]`）。
- 注册进行中 MJPEG 逐帧连续性人工观测（有确定性代理测试）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 4dc0ace | .scratch/face-recognition/reports/overall-r2-static-spec.md | - | 上轮两条 Important 均修好且有定向测试；AS-1..7 逐条亲核满足，594 套件绿 |
