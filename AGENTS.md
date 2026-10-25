# navydev.top_ebook

维护 EPUB 有声电子书：`lector/` 服务端、`web/` 网页，以及 `terminal/` 独立只读客户端。
两端共享内容；网页用 localStorage、终端用本地 JSON 保存个人位置和选项，互不覆盖。

## 开工时

- 改接口、认证或字段：先读 `docs/API.md`。
- 改界面、主题、键位或图片渲染：先读 `docs/UI.md`。
- 改部署或发版：先读 `docs/DEPLOY.md`、`terminal/README.md` 的发布部分。
- 改解析、构建或产品边界：读 `PROMPT.md` 对应章节。
- 契约改变时，同一提交更新契约和实现。Bug 先复现，再修复并加回归测试。

## 环境与验证

使用 **uv + Python 3.12**。根目录与 `terminal/` 各有依赖和锁文件；依赖用
`uv add/remove`，提交两份受影响的锁文件。`requirements.txt` 由 `uv export` 生成。

```sh
uv run pytest -q
(cd terminal && uv run pytest -q)
node --test web/js/util.test.mjs
git diff --check
```

网页是原生 ES Modules + CSS，没有前端构建步骤。改网页交互时运行
`web/tests/ux.test.mjs`，环境准备见 `web/tests/README.md`。
改终端图片时，检查 Sixel 局部重绘、滚动裁剪、异步加载前后组件身份及真实终端效果；
改启动流程时，验证 `--version/--help/--check` 不发送图形探测序列。

## 内容与位置

- 唯一位置：`Cursor = {book_id, chapter_id, sentence_id, word_index}`。
- ID 稳定：章节 `c{n}`、段落 `c{n}.b{m}`、句子 `c{n}.b{m}.s{k}`。
  改解析结果时提升 `PARSER_VERSION`；章节顺序由 spine 决定，TOC 不能代替章节 ID。
- EPUB 用标准库解析；保持路径穿越、符号链接、解压膨胀及上传大小限制。
  HTML 净化白名单和中英分句规则见 API/PROMPT 与对应测试。
- 书籍放 `books/书名(作者).epub`，中文括号也支持；文件名优先于内嵌元数据。
  启动自动导入。`make book BOOK="books/路径 带空格.epub"` 可构建或导入成品。
- 中文默认中文男声，英文默认美式男声；音色映射由 `/meta` 提供。
- 倍速、性别、音色与位置按书在各客户端本地保存；缺省配置从产品默认值补齐，
  不继承上一本。改朗读设置时验证触屏点选、实际音频速度、换书及重启恢复。
- 音频缓存键是文本、音色、语速、引擎版本的哈希；复用同键音频。
  定位和高亮以句内 timeline/词边界为准，缓存播放不应依赖实时音色列表可用性。
  音频缓存默认 10 GiB，可用 `LECTOR_AUDIO_CACHE_BYTES` 调整；淘汰时同步清理就绪记录。
- 网页全书百分比只放在书架；阅读页显示章节时间。打开次数是全局热度，不是个人进度。

## 终端图片与配色

- 图片逐张异步更新，保留正文和图片组件；高亮只刷新相关文字。
- Sixel 由 ImageApp 在文字合成后按可见区域整图提交，同一帧处理清除、遮挡与绘制；
  局部刷新重绘受影响整图，滚动只提交一次。缩放像素和编码缓存均有上限。
  适配器使用 Textual 8.2/textual-image 0.14 内部接口，升级须重跑图形回归测试。
- 磁盘图片缓存键包含服务器、书籍和资源；损坏条目淘汰后重试。
  所有下载和解码均通过共享大小/像素限制，失败不影响其余正文。
- 图形、颜色检测在参数解析后、Textual 接管 stdin 前执行；单次命令直接退出。
  原生图形能力先缓存再导入渲染器；WezTerm/Kitty 按环境识别，避免 Kitty 查询迟到应答。
  自动主题读取终端 RGB，选择状态须保持前景和背景对比。
- 终端依赖含 Textual、textual-image、Pillow、certifi；服务端保持独立。
  新运行时依赖要说明用途及标准库无法满足的原因。

## 安全与发布

- 阅读公开；终端以 `X-Lector-Client: terminal` 标识，只调用读取接口。
  这个字段和 User-Agent/Referer 过滤均不是身份认证。
- 公网管理操作需要 admin token；未配置时禁用。开发豁免要求直接 loopback 连接、
  本机 Host、loopback 绑定，且没有代理转发头。reader token 不能管理或上传。
- 客户端地址由 Uvicorn 的受信代理处理结果提供，应用不直接信任 X-Forwarded-For。
  浏览器写请求校验完整同源；公开 TTS 参数、并发和媒体读取必须受限。
- 生产路径 `/ebook`；GitHub Actions 通过 SSH + Docker Compose 发布，不使用 systemd。
  容器绑定 `127.0.0.1:8010`；保留数据卷 `navydev-top-ebook-data`。
- 终端发布 PyInstaller 独立二进制；推送 `terminal-v*` 标签后等待两种架构发布成功，
  再更新 `Formula/lector.rb` 的版本和真实 SHA256。Homebrew 不依赖系统 Python。
- 交付时报告具体改动、验证结果、提交/部署/终端发版状态及尚未验证的限制。
