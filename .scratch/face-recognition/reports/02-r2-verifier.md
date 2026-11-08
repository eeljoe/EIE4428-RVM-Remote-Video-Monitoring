# 02 服务端人脸注册票 — 独立验收报告（r2 复验）

VERDICT: VERIFIED — 三条整改全部拿到本轮新鲜证据（杀手测试收编且杀变异、等长校验＋宽度守卫在真泵上堵住致死路径、并发同名恰一 201 一 409），r1 判据回归无回退，变异 5/5 被杀；新发现一条 register-vs-remove 丢更新残留（Important，非判据违反）。
HEAD: 3486a021687a687d9d457f6902391a74ff0838c6
LEDGER: 02-r2-001,02-r2-002,02-r2-003,02-r2-004,02-r2-005,02-r2-006,02-r2-007,02-r2-009,02-r2-011,02-r2-012,02-r2-013,02-r2-014,02-r2-015,02-r2-016,02-r2-017,02-r2-018,02-r2-019,02-r2-020,02-r2-021,02-r2-022,02-r2-023,02-r2-024

## 定靶

- 目标提交 `3486a02`（派发方指定）；验收副本 `C:\Users\joe\AppData\Local\Temp\verify-02-r2-3486a02`（gate-kit worktree，detach 于 3486a02）。
- 主仓 HEAD `9f142f7` 为目标之上的 docs-only 提交；主工作区未提交改动属 03 号票写域（`src/rvm/web/*`、`tests/test_app.py`），不计入本票，副本不受影响。
- 基线 = r1 被验提交 `5adcede`；`git diff 5adcede..3486a02 -- src tests` = 6 文件 +292/−14（产品 ~76 行：等长校验、宽度守卫、名单锁；测试 ~230 行：镜像同步收编×3、并发×1、泵存活×1、等长×2、守卫×2）（02-r2-001/024）。
- 尺寸：r2 增量远小于闸门；整票规模沿用 r1 定级（WARN、单一关切）。

## 判据重建（r1 整改 + 票面 AC 回归 → 判定）

| 判据 | 判定 | 证据 |
|---|---|---|
| R1 [test] 镜像同步测试收进套件且能杀变异：删 `_publish_faces` 内 `replace_known_faces(faces)` → 红；还原 → 绿 | PASS | 收编于 `tests/test_face_api.py:519/538/552`（行号亲核一致）。变异：3 红（02-r2-003）；还原 sha1 一致后 3 绿（02-r2-004）；r1 杀手探针本体本轮重跑 3/3 绿（02-r2-022） |
| R2 [impl] 等长校验＋宽度守卫：手写/混维名单降级空名单+告警，pump 存活画面不断；撤修复即死 | PASS | 真进程：混维文件→`{"known":[]}`+corrupt 告警+frames 0→13 泵在跑，单条 8 维→载入不误判（02-r2-014，我的探针 `02-r2-verifier-persist.py`）。真 `run_forever` 泵 + 磁盘 8 维条目 + 9 维嵌入：HEAD 泵存活、tick 照跑、坏条目无身份（02-r2-011，`02-r2-verifier-pumpguard.py`）；守卫变异（`except ValueError`→`KeyError`）→ 3 红含泵死 `ValueError (9,) (8,)`（02-r2-006），手工同款变异跑 `--expect-dead` 同款死亡（02-r2-012）；等长校验变异 → 红（02-r2-007） |
| R3 [impl] 并发同名：两同名 POST 并发 → 恰一 201 一 409 `name-exists`，文件一条 | PASS | 收编测试变异杀：锁内复检变异 → `[201,201]==[201,409]`（02-r2-009）；我的独立探针（真 session 方法、双线程、慢采样）→ 恰 `[201, 409 name-exists]`、文件仅 `Alice`、store=mirror（02-r2-013 Part A） |
| C1–C9 回归（取样、201 契约、409/400 零写入、503 三态、GET/DELETE/404、重启、`--known-faces`、status/MJPEG 不中断、锁串行、整体替换） | PASS | r1 探针全套本轮重跑：sample 7/7（015）、api 34/34（016）、churn 3/3（017）、live 12/13（018，唯一 FAIL 为探针时序，产品回 `samples-missing` 合法 409）、stress 3/3（020）；真机自跑：379 并发注册全 409 no-face、零写入、爆发期 status p95 16.1ms、MJPEG 7.4fps 不断（021）；持久化/默认路径/损坏降级由我的 r2 语义探针 9/9（014）与 r1 persist 的 5/8（019，3 个「FAIL」见下）合并覆盖；`.gitignore:15` 亲核仍在 |
| C10 定向/全套亲跑绿；新测试非永真 | PASS | 定向 73 绿（002）；全套 **550** 绿（005，commit 上 collect 复核=550；worker 报 560 系主工作区含 03 票未提交 test_app.py +10，差值恰好对账）；新增 9 条测试全部由变异证明有牙（003/006/007/009/023） |

## FINDINGS

1. [Important] `src/rvm/server/session.py:687-693` — `remove_face` 在 `_faces_lock` **外**复制 `face_store.faces` 并做存在性检查：与并发 `register_face`（异名）交错时，register 若在 remove 复制后、发布前提交，其已确认的 201 注册会被 remove 的过期副本整体覆盖而**静默丢失**（我实证：201 后 final={Bob}，file/store/mirror 三方一致地缺 Carol——02-r2-013 Part B）。这是 r1 Nit-3 要求加锁消除的同一竞态族在 remove 路径上的残留；判据 R3 只钉同名双 201（已修复），无 AC/AS 要求跨名串行，故按 Important 而非 Blocking 记。建议：`remove_face` 把复制+检查移入 `with self._faces_lock:` 内（或 `_publish_faces` 内按当前 store 复检差集），一行锁内移动即可；双 remove 异名同理。confidence: HIGH
2. [FYI] `_nearest` 守卫只捕 `ValueError`：名单条目经 `_parse`/`np.asarray(dtype=float64)` 恒为数值一维，非数值注入只能绕过公共写路径直接改 `known_faces`（实现说明已自陈该旁路无覆盖）。confidence: MEDIUM
3. [FYI] worker 报告 §4-M4 记的 face_store sha1（`61287366…`）是 git blob 字节哈希；gate-kit/sha1sum 量检出字节（CRLF）得 `2BF7C73B…`——两种口径各自一致，非矛盾，故本轮 sha1 证据以工作树字节为准。confidence: HIGH

## RED-TEAM ATTEMPTS

- 「我若偷懒会在哪 5 处省事」预测清单：① 复检放锁外（→M-recheck 被杀，02-r2-009）；② 守卫 try 了但不捕对异常（→`except KeyError` 变异被杀，02-r2-006）；③ 只校验首个向量宽度、后续不比（→`width=0` 自选变异被杀，02-r2-023）；④ 镜像更新照旧忘同步（→M-mirror 被杀，02-r2-003）；⑤ 测试只断言「不崩」不看泵任务（→我的 pumpguard 直开真 `run_forever`，变异态泵死坐实）。
- 畸形/边界输入：api 探针 34/34——8 种 bad-name、非 JSON、JSON 数组、41 字超长、控制字符、含 `/` 名，全部契约 400/404 且零写入（016）。
- 负向路径：409 四态、404、503 三态、`write-failed` 500 回滚（套件）逐类零写入（016/018/021）。
- 时序/阻塞/竞态：真机爆发期 status p95 16.1ms、MJPEG 持续（021/020）；3000 增删×4 迭代线程零异常（017）；同名竞态与跨名丢更新亲测（013）。
- 环境投毒：模型文件缺失→503 `unavailable`（018）；混维/坏 JSON/坏结构文件→降级不崩（014/019）；名单路径不存在目录→mkdir 后正常写（r1 覆盖，本轮 persist 探针 seed 目录同为新建）。
- 状态残留与幂等：重启名单仍在、删除即落盘、重复删 404、拒绝路径文件字节不变（014/016）。
- 序列化形状：bad JSON、`faces` 非对象、向量非数组、混维、统一宽——五类形状行为各异且正确（014/019/007）。
- 变异等价性：5 变异全杀无存活（003/006/007/009/023）。
- 永真断言核查：探针断言均为独立计算的期望（均值 20.0、精确名单、`[201,409]`、泵死/活），非自洽构造。
- 未选族：权限/沙箱（名单路径为操作者 CLI 参数，无越权面）；宿主契约（无宿主解析器可重放，JSON 形状已直接打）；跨包/真机接缝（进程内与真进程两边对拍过，无第三接缝）；缓存/失效（本面无缓存层）。
- 安全扫描：`git diff 5adcede..3486a02 -- src tests .gitignore` 密钥/令牌/私钥正则 0 命中。

## NOT RUN / UNVERIFIED

- 真人脸注册→识别闭环：`--no-camera` 合成场景无人脸，真机层 201 路径仍只证到 409 no-face（与 r1 同一边界，05 集成票承接）。
- 真机层「同名并发」与「宽度守卫」：合成场景两条路径都走不到（无脸/无 `_nearest` 调用），证据为进程内真锁真泵（009/011/012/013）。
- 账本 02-r2-008（多行 `--find` 被 cmd 截断的用法失败，exit 1）与 02-r2-010（我的探针把 `STATE_RUNNING` 字面当成 `running` 的一次失败判词，实为 `mediapipe`）为失败记录，分别由 02-r2-009/011 取代。

## REMEDIATION

none（一条 Important finding 建议 follow-up，不构成重验条件；是否开 r3 由派发方裁量——修法与位置见 FINDINGS-1）。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
| VERIFIED | 3486a02 | .scratch/face-recognition/reports/02-r2-verifier.md | 无整改项（残留 finding 一条 Important 已记） | 三条整改全部亲证：镜像变异杀、守卫变异泵死、同名并发恰一 201 一 409；r1 判据无回退，变异 5/5 被杀 |
