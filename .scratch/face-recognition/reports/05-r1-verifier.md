VERDICT: VERIFIED — 四步链与失败路径经独立探针与全套件在干净副本重跑皆绿，四个变异全被杀死，收编清单逐项复验属实
HEAD: 767138845b3adbfb1df1b86c83e73ffeeb55cf93
LEDGER: 05-r1-001,05-r1-002,05-r1-003,05-r1-005

# 05 — 集成测试与探针收编（r1 独立验收）

## 定靶

- HEAD `767138845b3adbfb1df1b86c83e73ffeeb55cf93`（票面提交 `7671388`，一致）；基线取 05 认领 `fdf03c9` 之前——本提交 `git show --stat` 仅 2 文件：`tests/test_integration_faces.py` +300、票据 +53；写域合规，`src/` 零改动，尺寸 300 行 = 票面上限。
- 取证环境：gate-kit 干净副本 `Temp\verify-05-7671388`（已 cleanup），变异与套件均在副本内跑；真机自检以主仓 HEAD 跑（同一提交、src 无脏改）。
- 偷懒自查（我若省事会在哪 5 处放水）：①只重跑 worker 的测试不另写驱动；②相信「端口>1024」断言而不直连 socket；③变异只做派发方给的两个不加自选；④收编清单只抽查一行；⑤真机自检不跑直接引用 worker 读数。以上逐条做了反向动作。

## 判据重建（AC → 本轮证据）

| 判据 | 证据 | 结果 |
|---|---|---|
| AC-1 四步链+自起停真服务端 | 独立探针 05-r1-003（socket 直连证明监听 + 全链 HTTP/文件证据）；套件定向 05-r1-001（3 passed）；变异 Ma/Mb 各杀链上不同接缝 | 成立 |
| AC-2 失败路径+仍可响应 | 05-r1-003 FAILPATH 段（重名/无脸 409、文件字节不变、status 200、retry 201）；变异 Mc 杀死 | 成立 |
| AC-3 探针收编 | `02-r2-verifier-persist.py` 重写为 `:258`（非照抄：改 pytest 结构、加第三进程回读）；其余探针归类逐项复验见证据文件 §5 | 成立 |
| AC-4 全套绿+无新依赖 | 05-r1-002 `573 passed in 47.87s`（与自报 573 一致）；import 仅既有依赖 | 成立 |
| 票外要求：真机自检必须 | 05-r1-005 复跑 `11 passed, 0 failed`，真进程+真 MediaPipe（日志含 `landmark_projection_calculator.cc:81`） | 成立 |

## 攻击面（逐族）

- **变异族 ×4**：Ma 重启不读名单→15s 超时红；Mb 不落盘→FileNotFoundError 红；Mc 无脸拒绝失效→IndexError/500 红；Md（自选，CLI 接线）`--known-faces`→`None`→`{'known': []}` 红。全部还原 sha1 一致、复绿。每条测试都有杀伤变异，无没牙断言。
- **独立重推导**：自写驱动（非复用 worker 测试）重跑四步链+失败路径，期望值取自 spec 契约（`samples:3`、`{"removed":true,"known":[]}`、reason 枚举）。
- **证据-vs-自陈**：worker 报的红签名（timeout/FileNotFoundError/`known==[]`）本轮逐字复现；573/3/11 三个读数独立重算吻合。
- **覆盖核查**：收编清单 12 行逐条对到 `test_face_api.py`/`test_face_store.py` 具体行号，全部属实；原探针漏收的 uniform-错宽度腿已由 `test_face_store.py:105` 等价覆盖。
- **不适用的族**：UI 视觉（票面 `UI:` 未标 yes，本票无排布面判据）；并发端点级交错——worker 与 06 报告均披露为已知未覆盖族，属已声明缺口而非隐瞒缺陷。

## FINDINGS

1. [FYI] tests/test_integration_faces.py:82 — `wait_for_identity` 对「镜像不更新」是 15s 慢红而非快速断言失败；本轮 Ma 变异实跑确认仍稳定变红可分辨，worker 已披露；confidence: HIGH
2. [FYI] tests/test_integration_faces.py:300 — 损坏名单断言咬日志子串 `corrupt`，措辞变更会红；属有意格式耦合，worker 已披露；confidence: HIGH

## NOT RUN

无。套件、变异、独立探针、真机自检均本轮实跑。

## 收编清单

本轮无存活变异需收编（四个变异均被既有测试杀死，变异本身是攻击手段非新增覆盖）。worker 侧收编已核对属实，无需 adopt-test 动作。

## 回执

| 裁决 | HEAD | 报告路径 | 整改项按标签计数 | 一句理由 |
|---|---|---|---|---|
| VERIFIED | 7671388 | reports/05-r1-verifier.md | 无 | 四步链与失败路径在干净副本独立重跑全绿，四个变异全被杀、还原复绿，收编清单逐项属实，全套 573 passed |
