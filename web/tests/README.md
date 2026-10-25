# 网页体验回归测试

现有纯函数测试不需要额外依赖：

```sh
node --test web/js/util.test.mjs
```

`ux.test.mjs` 使用 Node 内置测试运行器、Playwright 和本机 Chrome。
通过 `NODE_PATH` 提供已有的 Playwright 安装，不需要修改项目依赖或创建 `package.json`：

```sh
NODE_PATH=/path/to/node_modules node --test web/tests/ux.test.mjs
```

默认使用 `channel: 'chrome'`；可用 `BROWSER_CHANNEL` 指定其他已安装的 Chromium 通道。
如果没有 Playwright，可将它安装在仓库外的临时目录，再把该目录的 `node_modules`
作为 `NODE_PATH`。

测试自行启动临时 HTTP 服务并使用固定 API 数据，不会访问生产服务、修改真实阅读进度
或触发语音合成。覆盖浏览器标题、章节刷新、长标题布局、320/375/768/1920px 控件
可见性与点击命中、44px 手机触控区域、倍速菜单键盘操作、播放面板折叠、抽屉焦点
循环与恢复、快速切换、沉浸模式和横屏低高度布局。API 与音频是模拟数据，实际音频
播放、移动 Safari 和设备安全区域仍需真机验证。
