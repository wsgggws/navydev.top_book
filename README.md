# navy's ebook

**有声电子书**：阅读 EPUB、逐句听书、文字随声音高亮。
线上入口：<https://navydev.top/ebook>。仓库名为 `navydev.top_ebook`。

## 功能与结构

- 书架：书名模糊搜索、每页 12 本、最近阅读优先、其余按打开次数排序。
- 阅读：目录、全书搜索、羊皮色默认主题、PC 与手机布局、键盘与触屏操作。
- 听书：句级 TTS、词级高亮、音频预取、0.75–2.0× 倍速；中英文默认男声。
- 进度：书架显示全书百分比，播放条显示本章 `mm:ss / mm:ss`，有小时用 `hh:mm:ss`。
- 独立客户端：网页用 localStorage；终端用本机 JSON，阅读位置与选项互不覆盖。

| 目录 | 用途 |
| --- | --- |
| `lector/` | FastAPI、SQLite、标准库 EPUB 解析、Edge TTS 与音频缓存 |
| `web/` | 原生 JavaScript ES Modules + CSS，无前端构建步骤 |
| `terminal/` | 独立 Textual 客户端；系统音频播放器；原生终端图片与磁盘缓存 |
| `books/` | 随仓库发布的 EPUB |
| `docs/`、`deploy/` | API/UI 契约与部署说明 |

## 本地运行

开发统一使用 **uv + Python 3.12**。服务端与终端各自有 `pyproject.toml` 和 `uv.lock`。

```sh
uv sync
uv run lector-server
# 浏览器打开 http://127.0.0.1:8000
```

```sh
make dev        # 热重载服务端
make terminal   # 启动终端，默认连接线上
make test       # 服务端与终端测试
```

## 安装终端

```sh
brew tap wsgggws/ebook https://github.com/wsgggws/navydev.top_ebook
brew install wsgggws/ebook/lector
lector
```

Homebrew 安装自带 Python 运行时的 **PyInstaller 独立二进制**，支持 macOS arm64/x86_64，
不依赖系统 Python。已有安装可执行 `brew update && brew upgrade lector`。

默认连接线上 `/ebook`，公开阅读无需 token。支持 `hjkl`、空格播放/暂停、`q` 返回/退出。
自动主题读取终端配色；书架封面与正文图片逐张异步显示。Sixel 在同一帧内整图绘制，
支持局部刷新和滚动裁剪；不支持原生图片的终端使用彩色半块字符。

图片默认缓存 512 MiB，按服务器隔离；损坏缓存重新获取。macOS 缓存在
`~/Library/Caches/lector/images/`，Linux 在 `~/.cache/lector/images/`，
可用 `LECTOR_CACHE_DIR` 更改。完整键位、配置与发版见 [terminal/README.md](terminal/README.md)。

## 发布书籍

书籍由维护者放进 `books/`，网页和终端均不提供上传、删除入口。
启动时按内容哈希去重导入。文件名支持 `书名(作者).epub` 和 `书名（作者）.epub`，
显示书名、作者以文件名为准。

```sh
cp ~/Downloads/new-book.epub books/
git add books/new-book.epub
git commit -m "book: add new-book"
git push origin main
```

也可以从 Markdown 生成 EPUB 并导入本地运行的服务：

```sh
make book books/my.epub
make book BOOK="books/路径 带空格.epub"
```

目标 EPUB 已存在且没有 Markdown 源时只导入成品。源目录格式与支持的 Markdown
子集见 [PROMPT.md](PROMPT.md) 和 `lector/build.py`。

## 配置与安全

| 环境变量 | 默认 | 用途 |
| --- | --- | --- |
| `LECTOR_DATA_DIR` | `./data` | SQLite、导入书籍、音频缓存 |
| `LECTOR_BOOKS_DIR` | `./books` | 启动导入目录 |
| `LECTOR_HOST` / `LECTOR_PORT` | `127.0.0.1` / `8000` | 监听地址与端口 |
| `LECTOR_BASE_PATH` | 空 | 生产为 `/ebook` |
| `LECTOR_TOKEN` | 空 | 公网管理令牌；不配置则禁用管理写接口 |
| `LECTOR_TTS_ENGINE` | `edge` | `edge` / `espeak` / `auto` |
| `LECTOR_MAX_UPLOAD` | `52428800` | 上传字节上限 |
| `LECTOR_AUDIO_CACHE_BYTES` | `10737418240` | 服务端音频缓存上限，默认 10 GiB，按最近使用淘汰 |

阅读公开。管理接口使用 Bearer token：`secret` 或 `secret:admin` 具有管理权限，
`secret:reader` 只读；客户端只发送 `secret`。本地管理豁免仅适用于直接 loopback
开发连接；伪造 Host 或转发头不能取得管理权限。

浏览器写请求校验完整同源，媒体读取和 TTS 参数/并发有上限；返回 CSP 等安全头。
终端的 `X-Lector-Client: terminal` 和 User-Agent/Referer 检查是客户端识别及基础过滤，
不构成身份认证。终端图片下载与解码也有大小、尺寸、像素限制。

## 部署与验证

GitHub Actions 在 main 提交后测试、构建镜像，再通过 **SSH + Docker Compose** 发布。
容器绑定 `127.0.0.1:8010`，中央 Nginx 代理 `/ebook`；数据卷
`navydev-top-ebook-data` 持久保存书籍和音频。健康检查失败会回滚。
设置 GitHub Secrets 和手动运维见 [docs/DEPLOY.md](docs/DEPLOY.md)。

```sh
uv run pytest -q
(cd terminal && uv run pytest -q)
node --test web/js/util.test.mjs
```

浏览器回归覆盖窄屏布局、倍速菜单、抽屉与焦点，准备方法见
[web/tests/README.md](web/tests/README.md)。依赖导出文件 `requirements.txt` 由 uv 生成。
开发约束见 [AGENTS.md](AGENTS.md)，接口与交互见 [docs/API.md](docs/API.md) 和
[docs/UI.md](docs/UI.md)。
