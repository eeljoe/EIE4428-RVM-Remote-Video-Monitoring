# Review leads — face-recognition

> 本文件是给实现后整体验收门的**未证实预测**，不是证据。门必须亲手复验，禁止照抄。

## 本轮路由

- 命令：`node "C:/Users/joe/Desktop/工作学习/软件开发/dsh plugin/tools/verification-plan.mjs" --spec .scratch/face-recognition/spec.md --issues .scratch/face-recognition/issues --json`
- 结果：`seamCount=1`、`reviewTickets=3`、`scopeTicketCount=5`、`overallCodeReview=2`、`perTicketDynamic=5`、`overallDynamic=1`
- 期望成员集：`review-tickets:SEAM-1:Fidelity`、`review-tickets:SEAM-1:Repo-fit`、`review-tickets:SEAM-1:Soundness`（三个全部已结算）

## SEAM-1

浏览器注册一张脸到名字出现、重启后仍在、四类失败都走通，且两档视口的字号与对比度达标。涉及票 01–05。

**Soundness 红队预测（未证实）**：最危险的是 02 与 04 之间的错误契约缝——02 的门只看状态码，04 要按 409 区分无脸、多脸、重名三类，若 `reason` 枚举与文案映射没有逐字对齐，两个门各自全绿而整条 seam 断。已在 spec「接口契约」钉死枚举与响应体，验收时须实测三种 409 的 `reason` 与页面文案一一对应。

**Repo-fit 风险（未证实）**：注册与删除若原地改 `known_faces`，encode 线程正在迭代会直接断流；票面已要求整体替换或加锁，验收时须在注册瞬间持续拉取状态与 MJPEG 验证。

**Fidelity 风险（未证实）**：AS-2 的「低于阈值不显示名字」在现有 `analysisText()` 里没有专门分支，容易被写成「有名单就显示」；验收时须用低相似度样本实测。

## Dispatch failures

none (route plan exit 0, S=1)
