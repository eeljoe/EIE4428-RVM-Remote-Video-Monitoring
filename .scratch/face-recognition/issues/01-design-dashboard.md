# 01 — 监控页设计规范（可读性与简化）

Status: claimed
Blocked by:
真机自检：不需要
**UI:** yes

## What to build

把已签字的参照图 v2 落成一份可执行的设计规范 `docs/DESIGN-dashboard.md`：字号阶梯、颜色与对比度、间距、组件规则、分区清单、响应式顺序、码率折线峰值标注、注册成功与失败态的精确文案。只写规范，不写实现代码，不改 `src/` 与 `tests/`。

## Acceptance criteria

- [ ] 文档含字号、颜色、间距、组件、分区五节，每节给出可直接照抄的具体值，字号下限取签字版 13px / 15px [AS-6, AS-7]
- [ ] 峰值标注写明形式、颜色、字号与位置，能按文档直接实现 [AS-6]
- [ ] 写明 390px 宽下面板顺序：画面 → 控件 → FACE REGISTRY → 遥测 [AS-7, AS-5]
- [ ] 写明注册成功、无脸、多脸、重名、分析关闭五态的精确文案与配色 [AS-1, AS-4]
- [ ] 规范与参照图 v2 一致，路径、mock.html 与两张截图均可打开 [AS-7, AS-6]
- [ ] 不修改任何 `src/`、`tests/` 或 `README.md` 文件 [AS-5]

## 测试命令

- 人工核对：文档存在、路径有效、每个数值都能在参照图上指到对应位置。
- 无自动化测试；本票不改代码，不跑 pytest。

## 写域

- `docs/DESIGN-dashboard.md`

## 开工包

- **写域**：`docs/DESIGN-dashboard.md`

- **视觉来源**：`.scratch/face-recognition/design/v2/mock.html`（含状态文案注释）与两张截图、`NOTES.md`；mock.html 与截图同为唯一来源，不只用截图。
- **锚点**：`grep -n "font-size" src/rvm/web/style.css` 与 `grep -n "color:" src/rvm/web/style.css` 取旧值对照。
- **尺寸上限**：文档 ≤250 行；不新增依赖、不生成 HTML mock。
- **估算**：预计 25 分钟 / 120 步（设计规范票，固定角色，不受甜点区间下限约束）。

## 验收包

- **判据**：AS-6、AS-7、AS-5；文档五节齐全且数值可指到截图。
- **首攻靶**：字号下限是否写成 13px、对比度是否给数值、390 顺序是否写明、五态文案是否可落地、是否偷偷改了实现文件。
- **相关 AS 摘录**：AS-6 可读性（最小标签 12px、值 15px、对比 4.5:1、行高 1.5、间距 20px）；AS-7 简洁（分区 ≤6、画面第一焦点）。

## 完成条件

文档提交后由独立门对照截图逐条核对；判 `VERIFIED` 前不得标 `resolved`。

## 实现说明

（由 worker 在交票前补写）

## Verdicts
