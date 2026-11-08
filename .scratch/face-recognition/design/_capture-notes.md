# 人脸注册参照图 - 内部记录

产物(design/):`mock.html`(自包含,双击可看)、`mock-desktop.png` 1440x1000、`mock-mobile.png` 390x844。

## 怎么截的

本机 Chrome 149 headless。`--window-size` 在截图模式下就是 CSS 视口尺寸,PNG 也同尺寸:

```
chrome --headless=new --force-device-scale-factor=1 --window-size=1440,1000 \
       --virtual-time-budget=5000 --user-data-dir=%TEMP%\rvm-mock \
       --screenshot=mock-desktop.png "file:///.../mock.html#faces"
```

- `#faces`:面板 rail 滚到底(模拟面板已滚到 Face registry 的状态),mock 内 JS 反复 clamp 到 max。
- 手机:Chrome 窗口最小约 500px 宽,拿不到 390 视口,所以用 390x844 的 iframe 包一层,
  再截 416x2100 从 y=1113 裁 390x844(1113 = 页面里 `#analysis` 的文档坐标 - 10,由同一构建的调试叠层量得)。
  390 宽下没有任何 vh/dvh 规则,所以整页渲染再裁 = 真机视口截图。
- 直接对滚动的顶层页面截图会得到空白图(headless 的已知限制),所以手机用的是整页渲染再裁。

## 与现状的偏差(worker 需要知道的)

1. `.panel` 在 >=901px 时 `max-height: calc(100vh - 102px); overflow-y: auto`。原来是页面整体变高,
   加了新块后页面 1207px,1000 高视口里注册块被切。现在画面高度不动,面板自己滚。
2. `:root { color-scheme: dark }` + `html { scrollbar-width: thin; scrollbar-color: #3a5158 transparent }`。
   原来只有控件声明了 color-scheme,窗口滚动条是浅灰的,在近黑底上很跳。
3. `app.js` 的 sparkline 用 `#4f9cf9`(蓝),图里画成 `--accent`。
4. 原文 hint 里有个 em-dash(`Watch only that area — movement...`),图里改成句号。
5. 页面仍比 1000 高约 48px,截图底部会切掉 1px 的 hint 框顶边;这是现状(画面 4:3 撑高)不是新问题。

## 文案与状态(给实现)

- 按钮 `REMEMBER FACE`(全页英文大写 mono;要中文「记住这张脸」只换这一个字符串)
- 占位 `e.g. Alice Ng`
- 日志:ok `saved as <name>`;err `no face in frame, hold still`;busy `working`(按钮 `.commit:disabled`)
- 空名单:`<li class="reg-empty">no names saved yet</li>`
- Face IDs 读数:`name + 0.82` 这种「名字 空格 相似度」。**现在 `analysisText()` 只输出 `item.name`,
  不带分数**,要改这一处(见 `src/rvm/web/app.js:44`)。
- 画面用的是仓库里 `_verify/snapshot.jpg` 真帧(320x240,data URI 内嵌),不是找来的图。

## 没覆盖

- 删除的二次确认(图里是直接删)
- 多人同框时「给哪张脸命名」的选择(图里假设画面里只有一张已知脸)
