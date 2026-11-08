# Overall static review — Standards axis (face-recognition)

VERDICT: VERIFIED — 命名分层、锁纪律、错误契约与测试杀伤力均达标；两条 Important（可注册不可删的名字、DESIGN §8 文案过期）不构成 Blocking。
HEAD: 01d08b75d838c7aeb48d24e3ecbaedfba4919ec0
BASE: 8db38f4
SCOPE: `git diff 8db38f4..HEAD -- src tests tools README.md docs/FEATURES.md docs/DESIGN-dashboard.md` — 17 files, +3480/-258。

规模说明：本 diff 是 7 张 resolved 票的并集，超出单票审查惯例但属整体验收门的预期范围；功能票与门落盘 chore 提交混在同一历史（mixed concerns 已由 `chore:`/`feat:`/`fix:`/`docs:` 前缀区分）。工作区另有一处未提交改动 `.scratch/face-recognition/reports/07-r1-verifier.md`（M），在 diff 范围外，仅记录。

## FINDINGS

1. `[Important] src/rvm/server/session.py:83-98 + src/rvm/server/app.py:106` — `validated_face_name` 拒绝空名/超长/控制字符，但放行 `"."` 与 `".."`：这两个名字能经 POST JSON body 正常注册并出现在 `GET /api/faces/known`，却永远无法删除——yarl 在路由前把 `DELETE /api/faces/known/..`（或 `%2E%2E`）归一化为 `/api/faces/`，aiohttp 回 text/plain `404: Not Found`，不是契约的 `{"error","reason"}` JSON。本轮实测（aiohttp 3.14.5 TestClient）：`DELETE /api/faces/known/..` → 404 text/plain，`/a%2Fb` → 200 `{"name":"a/b"}`（含 `/` 的名字可删）。为何重要：名单里出现一个 API 够不着的条目，只能手改文件；且 404 形状违约。建议修法：`validated_face_name` 里加 `cleaned in (".", "..")`（或路径归一化前后不等）即拒。confidence: HIGH（本机复现）。

2. `[Important] docs/DESIGN-dashboard.md:127,180-183,189` — §8 五态文案与行为与实现已漂移，文档未回写票 4 的偏差决定：`Two faces in frame, show one`（:181）实现为 `more than one face in frame`（app.js:482）；`Alice Ng is already saved, add a surname`（:182）实现为 `name + " is already saved"`（app.js:565）；`Analysis is off`/`No face in frame`（:183/:180）大小写与 `analysis is off`/`no face in frame` 不同；`REMEMBER FACE` 在预热与分析关闭时置 disabled（:127,:183）被票 4 明确否决后未改回；读数 `warming up`（:127）实现为 `loading`（app.js:46,75）；「录制中画面外框换 --alarm 3px」（:189）在 style.css 中不存在对应规则。为何重要：该文档自称「设计变量可直接抄」「每个数值都能在 mock 上指到位置」，照 §8 实现会得到错误文案与错误按钮行为。建议修法：把 §8 改为上屏逐字文案并注明置灰条款已否。confidence: HIGH。

3. `[Nit] src/rvm/web/style.css:200` — `#m-identities { color: var(--text); }` 是无效重复：`.readouts dd` 已声明同色，该行无实际作用。confidence: HIGH。

4. `[Nit] src/rvm/server/app.py:33,361` — `import typing` 只为 `_fail` 一处 `typing.NoReturn`；按常规 `from typing import NoReturn` 即可。confidence: HIGH。

5. `[Nit] src/rvm/server/session.py:83,695` — `validated_face_name` 是模块内部辅助函数却没有下划线前缀；`remove_face` 不复用它而自己 `cleaned = str(name).strip()`，于是超限名 DELETE 得 404 而非注册的 400——可辩护但与注册路径不对称。confidence: MEDIUM。

6. `[Nit] src/rvm/server/session.py:728-735` — `_publish_faces` 先 `face_store.replace(faces)` 再 `save()`：写盘失败窗口内（毫秒级、会回滚），不持锁的读方（`known_face_names` / GET handler）可能看到未提交的名字。识别镜像在 save 成功后才换，所以后果仅为一次瞬时 GET 读数；值得在注释里点明或调整顺序。confidence: HIGH。

7. `[Nit] src/rvm/web/app.js:530` — `remove.dataset.name = name` 写入后无人读取（删除走闭包 `forgetFace(name)`），而 `tests/test_app.py` 的 `assert "dataset.name = name" in registry` 把这个死属性钉进了套件。要么读它，要么两边一起删。confidence: HIGH。

8. `[Nit] src/rvm/web/index.html + app.js` — `#face-name` 不在 form 内也无 keydown，输入框里按 Enter 不触发注册，只能点 `REMEMBER FACE`；演示现场容易踩。confidence: MEDIUM。

9. `[Nit] git history` — 门落盘提交成对重复：`356f963`/`c8c97c5`、`a52275c`/`153fc54`、`fde0417`/`f664a01`、`9681d6c`/`77bc044`、`6a8e554`/`28d21b3`（同一 `chore(gate): 落盘 … VERIFIED` 提交两次）。历史噪音，无内容问题。confidence: HIGH。

10. `[Nit] src/rvm/analysis/recognition.py:328-352` — `_match`/`_nearest` 的 `known=None` 参数在缺省时回落到实时 `self.known_faces`，把「整帧一份快照」的纪律又开了一道口：只有 `recognize` 传了快照，未来任何忘传参的调用方都会静默拿到移动中的名单。测试性接缝可留，但 docstring 未写明该语义。confidence: MEDIUM。

## 轴内核面（未见问题的项）

- **命名与分层**：`FaceStore`（文件+镜像，analysis 层）、`StreamSession`（锁+发布，server 层）、`app.py`（纯 HTTP 翻译）三层干净；`FaceRequestError` 把 status/reason 绑定在抛出点，HTTP 层只翻译不决策（app.py:349-367）。`__init__.py` 均为空，无导出约定被破坏。
- **错误处理**：坏名单告警并按空启动（face_store.py:67-92）、写失败整体回滚（session.py:728-735）、采样失败→503 `unavailable`、事件循环外推理（`asyncio.to_thread`）。未发现被吞的异常。
- **并发与锁**：`_inference_lock` 串行全部 MediaPipe 推理（含逐样本注册取样）；`_faces_lock` RLock 覆盖「复检+发布」与「复制+删除+写回」；名单与识别镜像均为整体换引用，encode 线程迭代安全；`_recent_frames` 快照读。
- **测试质量**：期望值全部手写（均值 20.0、EMBEDDING 字面量、排序名单）；契约枚举 `CONTRACT_REASONS` 钉死；八种失败各测 `reason`+不写文件；并发测试用 `ObservedLock` 确定性接缝而非 sleep 猜（test_face_store.py:237-274）；CSS 测试真算 WCAG 对比度而非抄值。本轮亲跑 `pytest tests/test_face_store.py tests/test_recognition.py tests/test_face_api.py tests/test_integration_faces.py -q`：78 passed，exit 0。未见永真断言、skip/xfail/TODO 充数。
- **依赖与打包**：`requirements*.txt` 零改动（无新增依赖，符合 spec 约束）；`slow` marker 已在 pyproject.toml 注册且 `--strict-markers` 开启；无前端框架/构建步骤；远程资源禁令测试扩展到 app.js。
- **个人数据纪律**：`.gitignore` 含 `data/known_faces.json` 且 `git ls-files` 无该文件；`tools/make_zip.py` 白名单（TREE_DIRS=src/tests/tools/docs/figures）不含 `data/`。
- **上游 lead 复验**（review-leads.md 三条全部坐实为已落地）：错误契约缝——reason 枚举两端逐字对齐且有测试；Repo-fit——注册/删除整体换引用，无原地改；Fidelity——Face IDs 只读 `result.identities`，阈值以下不上名，`knownNames` 仅用于空态文案。

## NOT RUN

- 全套件其余测试（静态轴以代码证据为主；人脸相关 78 条已亲跑绿，全套绿以各票动态门与账本为准）。
- 视觉族（本派发未带 `ui: true`）：排布面五点评审不属于本轴；CSS/DOM 静态断言已覆盖结构面。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 01d08b7 | .scratch/face-recognition/reports/overall-static-standards.md | [impl]1 [spec]1 | 锁纪律、错误契约与测试杀伤力均达标；`.`/`..` 名字可注册不可删与 DESIGN §8 文案漂移为两条 Important，无 Blocking |
