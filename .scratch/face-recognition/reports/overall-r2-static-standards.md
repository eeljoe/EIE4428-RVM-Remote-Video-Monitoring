# Overall static review r2 — Standards axis (face-recognition)

VERDICT: VERIFIED — 上一轮两条 Important（`.`/`..` 可注册不可删、DESIGN §8 文案漂移）已真修好且各有测试钉死；本轮新增与沿用的发现均为 Nit，无 Blocking。
HEAD: 4dc0acedb86393fc91c2eb9df487c371fc2d9252
BASE: 8db38f4
SCOPE: `git diff 8db38f4..HEAD -- src tests tools README.md docs/FEATURES.md docs/DESIGN-dashboard.md` — 17 files, +3641/-258（9 张 resolved 票的并集，整体门预期范围）。

规模说明：与 r1 同范围，新增 161 行主要是 08/09 两票的修复与测试。`git diff 01d08b7..HEAD`（r1 靶点以来）的 src/tests/docs 增量为 5 文件 +171/-10，全部属 08（session.py 校验、style.css 缝隙线、DESIGN §8）与 09（含点名字参数列）。本轮亲跑 `.venv/Scripts/python.exe -m pytest tests/test_face_api.py tests/test_face_store.py tests/test_recognition.py tests/test_app.py -q` → 139 passed，exit 0。工作区杂项：仓库根出现未跟踪的 0 字节文件 `nul`（见 FINDINGS-9），`.scratch/` 下报告与探针为门产物，不计。

## 上一轮 Important 复核（亲手重查，不凭票面）

**F-r1-1 `.`/`..` 可注册不可删 → 已修复（坐实）。** `src/rvm/server/session.py:103-108` 现有 `if cleaned in (".", "..")` 与 `if "/" in cleaned or "\\" in cleaned` 两条硬拒，收在 `validated_face_name`（:83）内——即票面要求的「收进现有校验函数」，未开第二份判定；控制字符判定从 `ord < 32` 扩到 `< 32 or == 127`（:99）。测试不是纸面：`tests/test_face_api.py:304-315` `UNREACHABLE_NAMES` 十个参数（`.`, `..`, ` . `, `../x`, `a/b`, `a\b`, `/etc/passwd`, `tab\there`, `nul\x00byte`, `del\x7fchar`）逐一断言 400 + `reason=bad-name` + 文件不存在；:335-374 的反向测试真发 `DELETE /api/faces/known/<quote(name)>` 并断言 200，`..a`/`a..b`/`Alice Ng.`/`J. Smith` 全部可注册且可删——这正是 r1 实测的「yarl 只归一化恰为 `.`/`..` 的段」边界，钉对了位置。残留（手改文件塞入 `.` 仍删不掉、DELETE 路径不复用校验）属文件外注入，见沿用的 FINDINGS-6，不构成新缺陷。

**F-r1-2 DESIGN §8 文案漂移 → 已修复（坐实）。** `docs/DESIGN-dashboard.md:179-195`：五态表改为上屏逐字——`more than one face in frame`（:183，原 `Two faces in frame, show one`）、`Alice Ng is already saved`（:184，原带 `add a surname` 尾）、`analysis is off`（:185，原 `Analysis is off`）、`no face in frame, hold still`（:182）；:187「`REMEMBER FACE` 只在自己那一次请求在途时 `disabled`」把被否决的置灰条款改回来了；:192 补 `models still loading`；:127 的 `warming up` 改 `loading`；:193「录制中」改为 `Recording` 读数 `recording` + 按钮告警态、「画面不加外框」——与 `app.js`（FACE_REASONS :483-488、`rememberFace` :581-600、`.alarm`/`.osd` 结构）逐字对上。`tests/test_app.py:524-558` `test_the_design_copy_matches_the_served_status_line_verbatim` 双向钉：6 条文案必须同时出现在 app.js 与文档，5 条旧说法（`Two faces in frame`/`add a surname`/`Analysis is off`/`warming up`/`RECORDING`）不得在文档出现——文档再漂移会当场红。

**08 号票第三条（≤900px FACE REGISTRY→STREAM 缝隙）→ 已修复。** `style.css` 的 `@media (max-width: 900px)` 内新增 `.rail > .section:first-child { margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--line); }`，与其余四条界线同值；`test_app.py:505-521` 断言 margin+padding ≥20 且带 1px `--line` 规则。

## FINDINGS（本轮，含沿用；按严重度排序）

Blocking：无。Important：无。以下全为 Nit。

1. `[Nit] src/rvm/server/app.py:573 + src/rvm/analysis/recognition.py:181 + src/rvm/server/session.py:735` — 未映射的失败原因把服务端原文带上屏：`unavailable` 透传 `self._failure = f"{type(exc).__name__}: {exc}"`（recognition.py:181，可含异常类名与路径），`write-failed` 透传 `str(exc)`（FaceStoreError 内含绝对路径与 errno）。app.js:573 `setStatus("err", (err.body && err.body.error) || "the face was not saved")` 是有意的「用服务端原话」兜底；DESIGN §8 的禁项行（`docs/DESIGN-dashboard.md:195`「不出现…异常类名…文件路径…HTTP 码」）严格说只管辖五态文案，五态全部合规，但 §8 未承认这条兜底存在——边缘失败路径上「FileNotFoundError: [Errno 2]」这类串可能上屏。要么 §8 补一句「未枚举原因显示服务端文案」，要么服务端把类名/路径收敛进日志。confidence: MEDIUM。

2. `[Nit] src/rvm/analysis/face_store.py:105,160` — `save()` 写入 `"version": FORMAT_VERSION` 但 `_parse`（:160）从不读 `payload.get("version")`：一份 `{"version": 2, ...}` 文件会静默被当 v1 加载。docstring 说该字段是「future format change can be detected rather than guessed at」，当前形同装饰；要么载入时拒 `version > FORMAT_VERSION`，要么承认它只是占位。confidence: HIGH。

3. `[Nit] docs/FEATURES.md:116-117` — 「`no-face` and `multiple-faces` are `409` (nothing is sampled and no file is written)」：`no-face`/`multiple-faces` 的发现恰恰发生在三次取样推理之后，取样是做了的，只是没入库；「nothing is sampled」应读作「nothing is stored」。confidence: HIGH。

4. `[Nit] src/rvm/web/app.js:530 + tests/test_app.py:754`（沿用 r1-7）— `remove.dataset.name = name` 写入后无人读取（删除走闭包 `forgetFace(name)`），而测试断言 `"dataset.name = name"` 把这个死属性钉进了套件。要么读它，要么两边一起删。confidence: HIGH。

5. `[Nit] src/rvm/web/index.html + app.js`（沿用 r1-8）— `#face-name` 不在 form 内也无 keydown，输入框按 Enter 不触发注册，只能点 `REMEMBER FACE`。confidence: MEDIUM。

6. `[Nit] src/rvm/server/session.py:83,697-704`（沿用 r1-5）— `validated_face_name` 是模块内部辅助函数却无下划线前缀；`remove_face` 不复用它而自己 `str(name).strip()`，注册 400 与删除 404 仍不对称（手改文件塞进 `a/b` 可删、塞进 `.` 删不掉——注册入口已堵死，只剩文件外注入）。confidence: MEDIUM。

7. `[Nit] src/rvm/server/session.py:730-736`（沿用 r1-6）— `_publish_faces` 先 `face_store.replace` 再 `save`：写失败回滚前的毫秒级窗口内，不持锁的读方（`known_face_names`/GET handler）可能读到未提交的名字；识别镜像在 save 成功后才换，后果仅一次瞬时 GET 读数。confidence: HIGH。

8. `[Nit] src/rvm/analysis/recognition.py:325-352`（沿用 r1-10）— `_match`/`_nearest` 的 `known=None` 参数缺省回落实时 `self.known_faces`，给「整帧一份快照」纪律留了口；只有 `recognize` 传快照，未来忘传参的调用方会静默拿到移动中的名单，docstring 未写明语义。confidence: MEDIUM。

9. `[Nit] 仓库根 / git status`（本轮新增）— 未跟踪的 0 字节文件 `nul`（`?? nul`，11-09 05:32），疑为 shell 重定向 `> nul` 误产物；Windows 上常规手段删不掉（需 `\\?\` 前缀），`git add -A` 时是个隐患。confidence: HIGH。

10. `[Nit] git history`（沿用 r1-9，计数更新）— 门落盘提交成对重复增至 6 对：`356f963`/`c8c97c5`、`a52275c`/`153fc54`、`fde0417`/`f664a01`、`9681d6c`/`77bc044`、`6a8e554`/`28d21b3`、`3d5ed21`/`4dc0ace`（同一 `chore(gate): 落盘 … VERIFIED` 提交两次）。历史噪音，无内容问题。confidence: HIGH。

沿用 r1-3 `#m-identities` 冗余色声明（`style.css:200`，`.readouts dd` 已同色）与 r1-4 `import typing` 只为单处 `typing.NoReturn`（`app.py:33,361`）仍在，同 Nit 级，不重复占条。

## 轴内核面（未见问题的项）

- **命名与分层**：`FaceStore`（文件+镜像，analysis 层）/ `StreamSession`（锁+发布，server 层）/ `app.py`（纯 HTTP 翻译）三层干净；`FaceRequestError` 把 status/reason 绑定在抛出点，`_fail`/`_CONTRACT_ERRORS`（app.py:349-367）只翻译不决策。`validated_face_name` 单一校验入口，名字可寻址性注释（session.py:84-93）把「为何拒」写在拒的地方。
- **错误处理**：坏名单告警按空启动（face_store.py:75-96）、原子写 mkstemp+fsync+`os.replace`（:104-127）、写失败整体回滚（session.py:732-735）、事件循环外推理（`asyncio.to_thread`）。未发现被吞的异常；`_nearest` 的宽度守卫（recognition.py:344-356）把「手改名单」降级为不匹配而非断流。
- **并发与锁**：`_inference_lock` 串行全部 MediaPipe 推理；`_faces_lock` RLock 覆盖复检+发布与复制+删除+写回，register 的二次 name 检查在锁内（session.py:674-694）——两重检查+一把锁把「同名双 201」压成不可能，无锁序环（`_analyse` 持 `_inference_lock` 从不取 `_faces_lock`）。
- **测试质量**：期望值全手写（均值 20.0、EMBEDDING 字面量、排序名单）；`CONTRACT_REASONS` 枚举钉死；并发测试用 `ObservedLock` 确定性接缝（test_face_store.py:237-274）与慢取样放窗（test_face_api.py:243-273）而非裸 sleep 猜；CSS 测试真算 WCAG 对比度、真查 §8 逐字文案与旧说法黑名单；含点名字测到「能删回来」而不是「能存进去」。未见永真断言、skip/xfail/TODO 充数。
- **文档与注释**：新代码注释解释「为何」而非「是什么」；README/FEATURES/build_report 与实现同步（三帧平均、只存名字与嵌入、不进 git/zip 均属实）。`.gitignore` 含 `data/known_faces.json`（`git check-ignore` 实测命中），`git ls-files` 无该文件。
- **依赖与打包**：`requirements*.txt`/`pyproject.toml` 零改动；`slow` marker 已注册且 `--strict-markers`；无前端框架/远程资源（data: URI 的 favicon 与 select 箭头不受禁令约束且 test 只禁 `http(s)://`）。
- **死代码与重复**：除 FINDINGS 所列死属性/死字段外未见投机抽象；`face_store`/`recognition` 两份「整体替换映射」实现是有意的跨层镜像而非可合并重复。

## NOT RUN

- 全套件其余测试（本轮亲跑人脸相关 139 条绿；全套绿以各票动态门与 r1 基线 573→594 为准）。
- 视觉族（本派发未带 `ui: true`）：排布面五点评审不属于本轴；≤900px 缝隙修复以 CSS 规则与静态断言为证据，截图以 08 票动态门为准。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 4dc0ace | .scratch/face-recognition/reports/overall-r2-static-standards.md | [impl]0 [spec]0 | 上轮两条 Important 已带测试坐实修复；本轮无 Blocking/Important，残留 10 条 Nit |
