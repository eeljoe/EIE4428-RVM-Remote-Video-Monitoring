# 04 号票 真机自检 — FACE REGISTRY 面板

日期：本轮 worker 会话。机器：本机（Windows），无摄像头。
浏览器：Microsoft Edge（pid 42184），窗口 1400×828（`get_window_state` 截图，非代码渲染数字）。

## 环境与命令（原文）

```powershell
# 主服务器：分析开启，名单指向仓库外的临时文件
.\.venv\Scripts\python.exe run_server.py --no-camera --port 8099 `
    --known-faces $env:TEMP\rvm04\known_faces.json --recordings $env:TEMP\rvm04\clips
# 输出：RVM serving on http://0.0.0.0:8099/  (320x240 @ 15 fps, source: synthetic)

# 第二台：分析关闭，用来触发真实的 503
.\.venv\Scripts\python.exe run_server.py --no-camera --no-analysis --port 8098 `
    --known-faces $env:TEMP\rvm04\off.json --recordings $env:TEMP\rvm04\clips
```

名单文件不在仓库内：`data/known_faces.json` 始终未被创建（`git status` 无 `data/`），
`--recordings` 也指向临时目录。

## 怎么点的（哪一段是桩）

合成场景里没有真人脸，所以「成功」这一态无法用真后端造出来。为此写了一个
**同源 iframe 驱动页**（`04-selfcheck-harness.html`），临时放进 `src/rvm/web/`
以便由同一台服务器以 `/static/__selfcheck04.html` 提供（截图完成后已删除，
`git status` 里没有它）。它做的事就是人手动能做的两件：往 `#face-name` 里填名字、
点 `#face-remember` 或 `#face-list .x`。产品文件没有被它改动过。

分界：

- **真后端**：0 号到 5 号图（空态、no-face、name-exists、删除、analysis-off）。
  请求真的发到 8099/8098，状态行文字来自真实的 409/503 响应体，名单与
  `known_faces.json` 由服务端真实改写。
- **桩**：6 号（成功 201）与 7 号（multiple-faces 409）只把 `fetch` 对
  `/api/faces/known` 的响应换成预置 JSON，其余（DOM、CSS、状态行逻辑、名单渲染、
  删除按钮绑定）都是产品代码。
- **models-loading**：没有截到图（见下），用真实 HTTP 探针证明后端在预热窗口内
  真的回 `models-loading`。

## 截图与读数

| 图 | 场景 | 真/桩 | 读数 |
|---|---|---|---|
| `04-selfcheck-1-empty.png` | 空名单、无人脸 | 真 | `GET /api/faces/known` → `{"known": []}`；Face IDs 行 `0 faces, none known`；名单 `No names saved yet` |
| `04-selfcheck-2-noface.png` | 输入 Alice Ng 后点 REMEMBER FACE | 真 409 | 状态行红点 + `no face in frame, hold still`；输入框保留原文字；名单不变 |
| `04-selfcheck-3-exists.png` | 名单预置 Alice Ng / Marcus Foo 后重启，输入 Marcus Foo | 真 409 | 状态行琥珀 `Marcus Foo is already saved`；Face IDs `no face`（名单非空，不谎报 none known） |
| `04-selfcheck-3b-list.png` | 同上，滚动到名单 | 真 | 两行 `Alice Ng` / `Marcus Foo`，每行右侧 `×`（`aria-label="Delete <name>"`） |
| `04-selfcheck-4-deleted.png` | 点第一行 `×` | 真 DELETE | 只剩 `Marcus Foo`；`GET /api/faces/known` → `{"known": ["Marcus Foo"]}`；临时 JSON 同步只剩 Marcus Foo；状态行清空 |
| `04-selfcheck-5-analysis-off.png` | `--no-analysis` 服务器（8098）上点 REMEMBER FACE | 真 503 | 状态行灰 `analysis is off`；Face IDs / Expressions / Gestures 均 `off`；名单空态 |
| `04-selfcheck-6-saved-stub.png` | 成功 201（响应体为桩） | 桩 | 状态行绿 `Saved as Ada Lovelace, 3 frames averaged`；输入框清空；名单立刻出现 `Ada Lovelace`（按响应里的 `known` 重绘） |
| `04-selfcheck-7-multiple-stub.png` | 多脸 409（响应体为桩） | 桩 | 状态行红 `more than one face in frame`；名单未被改动 |

## models-loading（未截到图，但有真后端读数）

多次开新窗口后 Edge 只给出空白页（地址栏有 URL、标签题 `无标题`），没有再截到图。
改用直接打后端：`04-warmup-probe.py` 在服务器启动瞬间开始轮询 `POST /api/faces/known`，
第一次成功连上的响应就是预热态：

```
2.61s status=503 body={"error": "the face models are still loading", "reason": "models-loading"}
```

这一条 reason 到文案的映射由
`tests/test_app.py::test_the_registry_status_line_carries_the_five_outcomes` 钉住
（`"models-loading": ["", "models still loading"]`），与 `analysis-disabled` 走同一张表、
同一条状态行路径（后者已用真 503 截图）。

## 一眼看出来的三点（自评）

- **层级**：画面 > 读数 > 标签，注册分区标题 13px/600 `--text-2`、名字 15px、状态行 13px，
  与 DESIGN §5 一致；注册区在 Analysis 之下、Clips 之上，是第 4 个分区。
- **对齐**：输入框与 `REMEMBER FACE` 同一行（gap 10），状态行紧贴输入行下方（margin-top 8），
  名单行名字左、`×` 右，行间 1px `--line`；截图里三者左边线与分区左边界齐。
- **重复项**：一屏只有一个「保存这张脸」的动作；Face IDs 行只在有匹配时出现名字，
  名单里不再重复相似度。
