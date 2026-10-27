# navy's ebook

**有声电子书：戴上耳朵读，声音读到哪里，文字就亮到哪里。**

访问 <https://navydev.top/ebook>，无需登录。支持 PC、移动浏览器和独立终端客户端 `lector`。
仓库名为 `navydev.top_ebook`。

## 阅读与听书

- 书架支持书名模糊搜索，每页 12 本；最近阅读优先，其余按打开次数排序。
- 阅读支持章节目录、全书搜索、字号调整和主题切换，默认羊皮色、20px 正文。
- 听书支持中英文、男女声、0.75–2.0× 倍速和音频预取；当前朗读文字高亮，离开可视区时自动滚动。
- 中文书默认中文男声，英文书默认美式男声；新书默认 1.0×，声音选项限定为该书语言。
- 每本书分别保存位置、倍速、性别和音色，切回或重开后恢复。全书百分比显示在书架，章节时间显示在播放条。

网页使用浏览器 `localStorage`，终端使用本机 JSON。两端共享书籍内容，**进度与设置各自独立，不跨浏览器或设备同步**。
章节时间显示为 `mm:ss / mm:ss`，有小时时两侧均用 `hh:mm:ss`；尚未合成的音频时长为估算值，生成后校准。

## 使用终端 lector

```sh
brew tap wsgggws/ebook https://github.com/wsgggws/navydev.top_ebook
brew install wsgggws/ebook/lector
lector
```

Homebrew 提供 macOS arm64 / x86_64 的 **PyInstaller 独立二进制**，无需安装 Python、pip 或 uv。
升级：`brew update && brew upgrade wsgggws/ebook/lector`。默认连接线上服务，无需 token。

- `j/k` 移动或滚动，书架按 `l` 打开；阅读时 `h/l` 切换句子。
- 空格播放/暂停，听书时 `+/-` 调速、`0` 恢复 1.0×、`v` 切换男女声。
- `Ctrl+Shift+H/L` 聚焦目录/正文（终端需保留 Shift），`Ctrl+w` 切换窗格，`t` 聚焦目录。
- `f` 全屏正文，`q` 返回、书架退出，`Ctrl+l` 重绘页面与图片。

启动免重复解包；书架先读本地快照，再后台刷新。自动主题读取终端配色；正文在目录右侧居中，最大 96 列，普通段落首行缩进两字宽。书架封面与插图异步加载并缓存到磁盘，默认上限 512 MiB。
tmux 内外共用缓存；WezTerm + tmux 已开启透明传输时显示高清 PNG，直连保留高清位图。其它连接按图形能力选择原生图片或彩色半块预览。
macOS 缓存位于 `~/Library/Caches/lector/images/`，Linux 位于 `~/.cache/lector/images/`。
完整键位、缓存配置、播放器要求与 tmux 说明见 [terminal/README.md](terminal/README.md)。

## 本地开发

使用 **uv + Python 3.12**。服务端与 `terminal/` 各有独立的依赖和锁文件。

```sh
uv sync
uv run lector-server
# 浏览器打开 http://127.0.0.1:8000
```

```sh
make dev        # 热重载服务端
make terminal   # 启动独立终端项目，默认连接线上
make test       # JavaScript、服务端与终端测试
```

技术栈：`lector/` 使用 FastAPI、SQLite、标准库 EPUB 解析和 Edge TTS；`web/` 使用原生
JavaScript ES Modules 与 CSS，无前端构建步骤；`terminal/` 使用 Textual、textual-image、Pillow 和系统音频播放器。

## 添加书籍

维护者将 EPUB 放入 `books/`，命名为 `书名(作者).epub` 或 `书名（作者）.epub`。
书架以文件名显示书名与作者；网页和终端均无上传、删除入口。

```sh
cp ~/Downloads/new-book.epub books/
git add books/new-book.epub
git commit -m "book: add new-book"
git push origin main
```

部署后服务启动时自动导入，按内容哈希去重。本地可将已有 EPUB 导入运行中的服务，或从 Markdown 构建：

```sh
make book BOOK="books/书名（作者）.epub"
```

已有 EPUB 且无 Markdown 源时直接导入。构建规则见 [PROMPT.md](PROMPT.md)，默认目标服务为 `http://127.0.0.1:8000`。

## 部署与安全

GitHub Actions 测试、构建镜像后，通过 **SSH + Docker Compose** 发布。容器绑定
`127.0.0.1:8010`，由同级 `nginx-config` 仓库代理 `/ebook`；数据卷
`navydev-top-ebook-data` 保存书籍、数据库与音频。健康检查失败会回滚。

阅读公开。公网管理接口需要管理员 token，未配置 `LECTOR_TOKEN` 时禁用；直接 loopback 开发连接有受限管理豁免。
浏览器写请求校验同源，EPUB、图片和 TTS 有资源限制。终端标识头与 User-Agent/Referer 过滤不构成身份认证。
服务端音频缓存默认 10 GiB，可用 `LECTOR_AUDIO_CACHE_BYTES` 调整。

部署配置、Secrets、备份和运维见 [docs/DEPLOY.md](docs/DEPLOY.md)；
接口与安全规则见 [docs/API.md](docs/API.md)，交互规则见 [docs/UI.md](docs/UI.md)，
开发约束见 [AGENTS.md](AGENTS.md)。

## 验证

```sh
uv run pytest -q
uv run --directory terminal pytest -q
node --test web/js/util.test.mjs
git diff --check
```

网页交互测试的准备与执行见 [web/tests/README.md](web/tests/README.md)。
