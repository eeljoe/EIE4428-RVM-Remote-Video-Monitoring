# Review — SEAM-1 / Fidelity

单元：SEAM-1（浏览器注册→名字出现→重启仍在→四类失败走通→两档视口字号与对比度达标）。
范围：票 01–04 对照 spec.md AS-1..AS-7、context.md 已定决策、design/v2 签字参照。静态只读。

## Findings

### F1 [Blocking] 02 — AS-1「画面流不中断」无判据，且开工包指向会违反它的写法

- spec.md:43 AS-1 末句「画面流不中断」；02:12-18 的判据只覆盖返回码与落盘，无一条涉及画面流或事件循环。
- 02:38 开工包「端点写法照 `app.py` 现有只读端点」——只读端点全是同步返回（app.py:126-128、321-336）。注册要对存下的三帧各跑一次 FaceLandmarker.detect，照此写法在事件循环上推理会卡住 `/api/stream.mjpg` 与 `/ws` 遥测，正中 AS-1 破坏点；改放 `asyncio.to_thread` 又会与 `_analyse` 在 `_encode_once` 工作线程里的 `face_recognizer.recognize(frame)`（session.py:282, 389-411）并发打同一个 landmarker 实例——该实例并非为并发 detect 设计。
- 仓库已有正确先例：重活走 `asyncio.to_thread`（app.py:368-371 `handle_audio_control`）。
- 建议：02 增判据「注册期间画面流与遥测不中断」；开工包指明取样必须在 worker 线程串行（或在 `_analyse` 节拍内直接缓存每帧嵌入、注册时只做平均），并写明与 `_analyse` 的互斥约束。

### F2 [Important] 02 — 端点测试落点悄悄改写了 Testing Decisions

- spec.md:53 的「单元与端点测试」命令只列 `test_face_store.py test_recognition.py test_app.py`。
- 02:22,33 新建 `tests/test_face_api.py`，02:42 又明令「不要改 `tests/test_app.py`」——按票执行后，spec 定向命令跑不到任何新端点测试。
- 建议：spec Testing Decisions 增补 `test_face_api.py`（保留独立文件以避开与 03/04 的 test_app.py 写域冲突）。

### F3 [Important] 02/04 — AS-2 低于阈值分支无判据无测试

- spec.md:44「低于阈值或名单为空时不显示名字，保持 `no-known-faces` 与人数」。
- 04:14 判据只写「空名单时保持 `no-known-faces` 与人数」，低于阈值零引用。现状：非空名单 + 低于阈值时 `state=running, count=0`，`analysisText` 落到 `emptyLabel` 显示 "no face"（app.js:41,68），`seen` 不回显——若「保持人数」覆盖该分支，现状即不达标且无人认领；即使不覆盖，04 重写身份行文案时也无判据钉住「不显示名字」。
- 建议：04 加判据与静态测试钉住低于阈值的渲染（含 `seen` 是否回显的明确口径）；02 可在识别器/端点测试钉阈值过滤。

### F4 [Important] 01/03 — 已签字的手机档重排序无判据

- mock.html:282-293：`≤900px` 时 `.registry` 用 `order:4` 提到 `.section`(order:5) 遥测之前，注释明说这是为了让「命名一张脸不用滚过遥测」；mock-mobile.png 实锤（控件后即 FACE REGISTRY）。
- 01:13 要求的五节（字号/颜色/间距/组件/分区）不含布局/响应式顺序；03:13-18 判据也无「手机档注册区先于遥测」。
- 建议：01 规范补布局节写清两档顺序；03 加判据钉住。

### F5 [Important] 01/04 — 失败态与空名单态只在 mock.html 注释里，两票来源都够不着

- NOTES.md:12 + mock.html:424-428：签字文案「No face in frame, hold still」与「No names saved yet」仅存注释。
- 01:29「NOTES.md 与两张截图，作为唯一视觉来源」排除 mock.html；04:39 视觉只按 `DESIGN-dashboard.md` 与 `mock-desktop.png`。设计文档若不收编这两态，04 只能自创失败文案与样式，偏离签字参照。
- 建议：01 把 mock.html 列入来源并要求记录两态；04 开工包引用对应条目。

### F6 [Nit] 04 —「Analysis 面板」措辞与签字的 FACE REGISTRY 分区不一致

- spec.md:26「分析面板新增…」；签字 mock 是独立 FACE REGISTRY 分区（NOTES.md:6、mock.html:429）；04:13「Analysis 面板出现…」字面读与参照冲突。
- 建议：改为「FACE REGISTRY 分区」。

### F7 [Nit] 02 — spec.md:39「不改任何文件」对 503 同样适用

- 02:14 只钉「409 不改文件」；02:15 的 503 判据未写不改文件。
- 建议：把「不写文件」扩到全部失败返回。

### F8 [FYI] — 范围蔓延核对（无蔓延）

- 峰值标注不在 AS 列表但是用户点名的已定决策（context.md:11），01/03 覆盖它属正确而非蔓延。
- 03:14「正文 ≥7:1」严于 spec.md:48 的 4.5:1 下限，与签字 mock 一致（NOTES.md:4 正文 16.65:1）。
- spec.md:30 不做清单（音频上行/跟踪/编解码/录像/其他分析器/报告人数/zip 脚本）未被任何票触碰；「不进 zip」结构上已成立——make_zip.py 白名单不含 `data/`（make_zip.py:54-59）。

## AS 覆盖速查

| AS | 覆盖票 | 缺口 |
|----|--------|------|
| AS-1 | 02+04 | 「画面流不中断」无判据（F1） |
| AS-2 | 04 | 低于阈值分支无判据（F3） |
| AS-3 | 02+04 | 全 |
| AS-4 | 02+04 | 全（F7 为措辞补强） |
| AS-5 | 02/03/04 | 全 |
| AS-6 | 01+03 | 全 |
| AS-7 | 01+03 | 全（F4/F5 为签字细节补强） |
