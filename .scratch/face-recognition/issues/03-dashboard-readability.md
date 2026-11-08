# 03 — 整页可读性与结构重做

Status: ready-for-agent
Blocked by: 01
**UI:** yes

## 交付什么

按 01 号票的设计规范重做监控页的可读性与结构：字号阶梯、对比度、行距与分组、去掉冗余框线与重复标签、码率折线加峰值标注。保留全部既有元素 ID、控件与八项操作。

## Acceptance criteria

- [ ] 标签 ≥12px、读数 ≥15px、正文 ≥15px、手机正文 ≥14px，行高 ≥1.5 [AS-6]
- [ ] 灰字对比度 ≥4.5:1、正文 ≥7:1，并在实现说明里给出实测读数 [AS-6]
- [ ] 分组间距 ≥20px；分区不超过 6 个；去冗余框线与重复标签；画面为第一焦点 [AS-7]
- [ ] 码率折线有峰值虚线与 `peak x.xx Mbps` 角标，字号 12px、灰字、不新增分区 [AS-6, AS-7]
- [ ] 既有 DOM ID 与八项操作保持；390×844 无横向溢出；1440×1000 无被截断的操作 [AS-5, AS-7]
- [ ] 无远程资源、无新增依赖；全套测试通过 [AS-5]

## 测试命令

- 定向：`.venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_delivery.py -q`
- 全套：`.venv\Scripts\python.exe -m pytest`
- 目视：`run_server.py --no-camera --port 8099`，桌面与手机视口各截一张图。

## 写域

- `src/rvm/web/index.html`
- `src/rvm/web/style.css`
- `src/rvm/web/app.js`
- `tests/test_app.py`

## 开工包

- 先读 `docs/DESIGN-dashboard.md`（01 号票产出）与 `.scratch/face-recognition/design/v2/mock.html`。
- `#stream` 必须仍是内联 `src=` 且包含 `stream.mjpg`（`tests/test_delivery.py` 钉住）。
- 保留 `.layout` 类与 `view-source`、`view-decoded`、`roi`、`sensitivity`、`clear-roi`、`clips`、`spark` 等字面 ID。
- 折线数据来自 `history.bitrate`（最多 60 点），峰值标注用同一数组的最大值，别另算。
- 不改后端、API、WebSocket、编解码与录像；不加框架、不加构建步骤。

## 验收包

- 判据：AS-6、AS-7、AS-5。
- 首攻靶：字号是否真的达标、对比度是否实测、1440 是否截断、390 是否横向溢出、旧 ID 与八项操作是否还在、峰值标注是否与数组同源。
- 相关 AS：AS-5 不回归；AS-6 可读性；AS-7 简洁与观感。

## 完成条件

测试先红后绿；独立动态门用真实浏览器在两档视口取证并判 `VERIFIED` 后才可标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
