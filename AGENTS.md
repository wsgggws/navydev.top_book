# navydev.top_ebook

维护 EPUB 有声电子书：`lector/` 服务端、`web/` 网页、`terminal/` 独立只读客户端。
生产入口 `/ebook`，网页标题 `navy's ebook`。两端共享内容，位置与设置分别存于浏览器 localStorage 和终端本地 JSON。

## 按改动读取

- 接口、权限、字段或安全：`docs/API.md`。
- 网页布局、主题、键位、高亮或终端图片：`docs/UI.md`；终端操作与缓存另见 `terminal/README.md`。
- 部署、代理、数据卷或发版：`docs/DEPLOY.md`；终端二进制发布另见 `terminal/README.md` 的发布部分。
- EPUB 解析、构建或产品边界：`PROMPT.md` 对应章节。

改变契约时同步更新文档与实现。Bug 先复现，再修复并添加有意义的回归测试。

## 开发与验证

使用 **uv + Python 3.12**；根目录与 `terminal/` 各自管理依赖，使用 `uv add/remove`，提交受影响的锁文件。
`requirements.txt` 通过 `uv export` 生成。网页为原生 ES Modules + CSS，无构建步骤。

```sh
uv run pytest -q
uv run --directory terminal pytest -q
node --test web/js/util.test.mjs
git diff --check
```

按改动范围执行检查。网页交互另运行 `web/tests/ux.test.mjs`，准备方式见 `web/tests/README.md`。
纯文档改动核对命令、链接与实现即可。交付说明改动、验证及提交/部署状态，明确未验证的限制。

## 内容、播放与进度

- 书籍由 `books/书名(作者).epub` 发布，支持中文括号，文件名优先于内嵌元数据；启动按内容哈希去重导入。
  `make book BOOK="books/路径 带空格.epub"` 构建或导入本地服务；客户端不提供上传、删除入口。
- 唯一位置为 `Cursor = {book_id, chapter_id, sentence_id, word_index}`。
  章节/段落/句子 ID 保持稳定，章节顺序以 spine 为准；解析结果改变时提升 `PARSER_VERSION`。
- EPUB 用标准库解析，保留路径穿越、符号链接、解压膨胀、上传大小限制及 HTML 净化白名单。
- 中文默认中文男声，英文默认美式男声，声音选项由 `/meta` 按语言提供。
  每本书独立保存位置、倍速、性别与音色；缺省从默认值补齐，不继承上一本。
- 改播放设置须验证触屏与鼠标选择、实际速度、换书和重启恢复；换书先停止旧音频并隔离异步结果。
  高亮以句内 timeline/词边界和实际播放时钟为准；图片加载或倍速变化后当前朗读句仍须可见。
- 网页全书百分比只在书架显示，阅读页显示章节时间；未合成时长允许估算并逐步校准。
  打开次数是全局热度，个人进度保留在各客户端本地。
- 音频缓存键含文本、音色、语速与引擎版本；缓存播放不依赖实时音色列表。
  服务端音频缓存默认 10 GiB，淘汰文件时同步清理就绪记录。

## 终端图片与启动

- 图片逐张异步更新，保留文字、图片组件及滚动位置；高亮只刷新相关文字。
- Sixel 在文字合成后按可见区域整图提交，同帧完成清除、遮挡与绘制；滚动只提交一次。
  显式擦除未被遮挡的图片单元格，释放 tmux 保留的旧图层；不能依赖 Textual 输出未变化的空白。
  保留缩放像素与编码缓存上限；适配器依赖 Textual/textual-image 内部接口，升级须重跑图形回归。
- 图片磁盘缓存按服务器、书籍和资源隔离，tmux 内外复用；下载、解码均受大小/像素限制，损坏条目淘汰重试。
- 参数解析后、Textual 接管 stdin 前检测颜色与图形；`--version/--help/--check` 不发送图形探测序列。
  直连 WezTerm/Kitty 按环境识别，避免 Kitty 查询迟到应答；WezTerm + tmux 固定使用彩色半块图片，避免空白或跨页残影。
  其它 tmux 连接校验自身及连接终端的 Sixel 能力，失败用彩色半块图片；能力应答不能替代真实显示验证。
- 焦点恢复或 `Ctrl+l` 重绘缓存位图，不重复下载，不修改用户 tmux 配置。
  图片改动验证首次加载、`jk`/滚轮滚动、窗口切换、裁剪及真实 tmux 的原生/降级路径。
- 自动主题读取终端 RGB，选择状态保持前景/背景对比；终端运行时依赖保持独立，新增依赖须说明用途。

## 安全与发布

- 阅读公开；`X-Lector-Client: terminal` 仅标识客户端，连同 User-Agent/Referer 均不是认证。
- 公网管理操作需要 admin token，未配置时禁用。开发豁免须直接 loopback、本机 Host、loopback 绑定且无代理转发头。
  reader token 无管理权限；浏览器写请求校验完整同源，公开 TTS 参数、并发与媒体读取须受限。
- 客户端地址使用 Uvicorn 的受信代理处理结果，应用不直接信任 X-Forwarded-For。
- GitHub Actions 通过 SSH + Docker Compose 发布；容器绑定 `127.0.0.1:8010`，保留命名卷 `navydev-top-ebook-data`。
  nginx 配置维护在同级 `nginx-config` 仓库；使用 Docker Compose，不使用 systemd。
- 终端发布 PyInstaller 独立二进制；推送 `terminal-v*` 标签，等待 macOS 两种架构发布成功后，
  再更新 `Formula/lector.rb` 的版本和实测 SHA256。Homebrew 不依赖系统 Python。
