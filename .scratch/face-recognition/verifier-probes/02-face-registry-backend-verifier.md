# 02 号票 r1 — 验收探针与原始输出

Verifier 自写探针：`02-face-registry-backend-verifier-probes.py`（子命令
`sample / api / live / persist / churn / stress`），全部针对 gate-kit 副本
`C:\Users\joe\AppData\Local\Temp\verify-02-r1-5adcede`（detach 于 5adcede）
里的代码执行。kill 变异用测试：`02-mirror-sync-verifier-test.py`。

- `sample`：直接调 `FaceRecognizer.sample_faces`——真 landmarker 对空帧与
  噪声帧返 `[]`；桩出两张 478 关键点脸返 2 条各 1434 维互异向量；无模型
  抛 `FaceSamplingError`。7/7（账本 02-r1-004）。
- `api`：进程内起真 aiohttp 服务（TCP、handler、`asyncio.to_thread`、
  `_inference_lock`、FaceStore 全真；仅 landmarker 被桩）。201 契约、
  磁盘向量 == 手算均值 20.0、4 帧只取后 3 帧（取样 3 次）、name-exists /
  no-face / multiple-faces 409 且文件字节不变、8 种 bad-name 400、非 JSON
  / 非 dict 体 400、GET 有序、DELETE 立即落盘、404、503 三态、写零次。
  34/34（账本 02-r1-008）。
- `live`：`run_server.py --no-camera` 真进程。暖机窗口内 POST →
  503 `models-loading`（实测抓到，非桩）；合成场景 → 409 `no-face`；
  预置名单 → 重名 409 文件不变；DELETE → 文件立刻 `faces={}`，再删 →
  404；`--no-analysis` → 503 `analysis-disabled`；把副本里
  `models/face_landmarker.task` 改名 → 503 `unavailable`（已还原）。
  13/13（账本 02-r1-009）。
- `persist`：`--known-faces` 自定义路径生效；重启名单仍在；删除落盘；
  默认 `<cwd>/data/known_faces.json`；坏 JSON 与坏结构均降级空名单 +
  log warning，服务不崩。8/8（账本 02-r1-010）。
- `churn`：2000 条名单 + 3000 次 add/remove × 4 个迭代读线程 → 无
  `dictionary changed size during iteration`；120 次 register+remove
  周期 × 4 读线程同样干净，最终文件 `faces={}`。3/3（账本 02-r1-006）。
- `stress`：24 次 POST 爆发（每次真跑 3 次 landmarker 推理、真抢
  `_inference_lock`）期间 `/api/status` p50=2.1ms / p95=27.4ms
  （基线 p50=12.8 / p95=21.3），MJPEG 6 秒收 68 帧（≈11 fps，基线
  31/3s≈10 fps）；爆发请求零错误零悬挂。3/3（账本 02-r1-011）。

## 变异记录（gate-kit mutate，副本内，sha1 已还原 BBB21F24…）

| # | 变异 | 测试态 | 结果 |
|---|---|---|---|
| M1 | `frames[-REGISTRATION_FRAMES:]` → `frames[-1:]` | test_face_api 3 红（均值/重启/事件循环） | 被杀 |
| M2 | `_sample_faces` 的 `self._inference_lock` → `self._audio_lock` | `test_registration_and_analysis_take_the_same_lock` 红 | 被杀 |
| M3 | `if name in self.face_store.faces:` → `if False:` | `test_a_duplicate_name_is_refused...` 红（201 vs 409） | 被杀 |
| M4 | `_publish_faces` 删 `self.face_recognizer.replace_known_faces(faces)` | 定向 64 绿 + **全套 541 全绿** | **存活（非等价）** |

M4 非等价：名单文件与 FaceStore 更新、识别器镜像不更新——注册后
`recognize()` 本会话认不出新脸（restart 才生效），删除后仍能认出。
「当场见效」静默失效而全套测试无一变红。

## 杀手测试验证

`02-mirror-sync-verifier-test.py` 复制进副本 `tests/` 后：
真码 3 绿；手工施加 M4 变异 → 3 全红（`set() == {'Ada'}` 型断言失败）；
还原 sha1 一致、复绿。（M4 手工变异由 python 脚本施加；首次用 LF 写出
导致 sha1 不符，改用 `git checkout` 还原到提交态后 sha1 复核一致。）

## 补充点检

- `samples-missing`：<3 帧 `register_face` 直调 → 409 `samples-missing`。
- 名字含 `/`：`POST "a/b"` 201 → `DELETE a%2Fb` 200 removed（可删，无
  路由死角）；`DELETE a/b` 裸斜杠 404（两分段，符合路由形态）。
- 混维向量：`known_faces` 塞入 1434 维 + 8 维两条目 → `_match` 内
  `np.linalg.norm` 抛 `ValueError`；`_analyse`→`run_once`→`run_forever`
  无兜底 → pump 任务死亡、画面流永久停摆（`faces={"Bob":[0.75]*8}` 这种
  合法形状即可触发，只要有一帧检出人脸）。
- 安全扫描 `git diff 3eae186~1..5adcede` 密钥/私钥正则：0 命中。
