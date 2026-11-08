# 05 — 集成测试与探针收编

Status: ready-for-agent
Blocked by: 02, 03, 04
真机自检：必须（探针路径占位：`.scratch/face-recognition/verifier-probes/05-integration-selfcheck.md`）

## What to build

写一张把多张票能力串起来压一遍的集成测试：注册一张脸 → 身份行出现名字 → 重启服务后仍能识别 → 删除后消失。并把实现期各票验收门留在 `.scratch/face-recognition/verifier-probes/` 的持久探针按红绿纪律收编进正式套件。

## Acceptance criteria

- [ ] 新增跨票集成测试：注册、识别、重启、删除四步走通，测试自己起停真实服务端 [AS-1, AS-2, AS-3]
- [ ] 集成测试覆盖一条失败路径（无脸或重名），断言服务仍可响应 [AS-4]
- [ ] 探针目录有持久探针时收编为正式测试（重写到套件标准），目录为空则在报告里声明 none [AS-5]
- [ ] 全套测试通过，无新增依赖 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_integration_faces.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`

## 写域

- `tests/test_integration_faces.py`（新增）
- `.scratch/face-recognition/verifier-probes/`（只读收编，不改历史探针原文）

## 开工包

- **写域**：`tests/test_integration_faces.py`, `.scratch/face-recognition/verifier-probes/`

- 复用 `tests/test_face_api.py` 的启动方式；端口用高位随机端口，避免与演示实例冲突。
- 名单路径用 `tmp_path` 注入，不碰仓库里的 `data/known_faces.json`。
- 重启用同一临时目录起第二个进程或第二个 app 实例，断言名单仍在。
- 收编探针时保留原始探针文件，新增套件测试另行命名。
- **尺寸上限**：≤300 行 / 2 文件。
- **估算**：预计 40 分钟 / 180 步。

## 验收包

- **判据**：AS-1、AS-2、AS-3、AS-4、AS-5；集成测试必须真实起服务端，不允许只 mock。
- **首攻靶**：重启是否真的重读文件、删除是否真的落盘、失败路径后服务是否还能响应、探针收编是否只是抄一遍。
- **相关 AS 摘录**：AS-1 注册闭环；AS-2 展示；AS-3 持久化；AS-4 失败；AS-5 不回归。

## 完成条件

集成测试绿、全套绿；独立动态门在干净副本里重跑同一命令并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
