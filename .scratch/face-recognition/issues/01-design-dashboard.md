# 01 — 监控页设计规范（可读性与简化）

Status: ready-for-agent
Blocked by:
**UI:** yes

## 交付什么

把已签字的参照图 v2 落成一份可执行的设计规范 `docs/DESIGN-dashboard.md`：字号阶梯、颜色与对比度、间距、组件规则、分区清单、码率折线的峰值标注。只写规范，不写实现代码，不改 `src/` 与 `tests/`。

## Acceptance criteria

- [ ] 文档含字号、颜色、间距、组件、分区五节，每节给出可直接照抄的具体值 [AS-6, AS-7]
- [ ] 峰值标注写明形式、颜色、字号与位置，能按文档直接实现 [AS-6]
- [ ] 规范与参照图 v2 一致，路径与两张截图均可打开 [AS-7, AS-6]
- [ ] 不修改任何 `src/`、`tests/` 或 `README.md` 文件 [AS-5]

## 测试命令

- 人工核对：文档存在、路径有效、每个数值都能在参照图上指到对应位置。
- 无自动化测试；本票不改代码，不跑 pytest。

## 写域

- `docs/DESIGN-dashboard.md`

## 开工包

- 读 `.scratch/face-recognition/design/v2/NOTES.md` 与两张截图，作为唯一视觉来源。
- 读 `src/rvm/web/style.css` 的现有变量与字号，写清旧值到新值的对照。
- 文档上限 250 行；不新增依赖、不生成 HTML mock。

## 验收包

- 判据：AS-6 可读性、AS-7 简洁与观感。
- 首攻靶：字号是否全部达标、对比度数值是否给出、分区是否不超过 6 个、峰值标注是否可落地、是否偷偷改了实现文件。
- 相关 AS：AS-5 只读边界，AS-6 数值，AS-7 结构。

## 完成条件

文档提交后由独立门对照截图逐条核对；判 `VERIFIED` 前不得标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
