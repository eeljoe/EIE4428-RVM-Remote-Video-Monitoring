# Review leads — RVM 前端优化

> 以下是实现前静态审票给出的未证实风险，不是动态验收结论。最终门必须亲自复验，禁止照抄。

## 红队首要风险

`tests/test_delivery.py:48-52` 钉住 `<img id="stream" ... src="/api/stream.mjpg">` 的标签形状与内联源。视觉改造若换标签、懒加载或把 src 挪进 JavaScript，会碰到写域外回归测试。实现必须保留该内联锚点，动态门首先检查它。

## 其他 leads

- 保留 `view-source`、`view-decoded`、`roi`、`sensitivity`、`clear-roi`、`clips`、`spark` 的 HTML 字面 ID，以及 CSS 的 `.layout`；这些被写域外测试或 `verify_system.py` 钉住。
- 300 行预算不支持无条件整文件重刷；应按既有 CSS 块做定向改造，并在实现提交前实测 numstat。
- 审票发现 README 的 HTTP API 表可能缺 `POST /api/motion`，但本票明确禁改 README；不作为本票验收缺陷，留待后续文档维护核对。

## 实现前审票汇总

Fidelity 3 条 non-blocking；Repo-fit 2 条 non-blocking；Soundness 2 条 non-blocking；三轴 blocking = 0。票已机械补全 AS 引用、尺寸上限、既有锚点与验收包。
