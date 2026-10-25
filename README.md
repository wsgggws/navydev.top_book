# navydev.top_ebook

**有声电子书**：EPUB 阅读 + 句级语音朗读服务。

- 线上：<https://navydev.top/ebook>
- 网页端与终端端连接同一份内容，但各自保存阅读位置和播放选项
- Python 3.12，依赖和环境统一由 [uv](https://docs.astral.sh/uv/) 管理

## 功能

- **书架**：书名模糊搜索、每页 12 本、最近阅读优先、其余按打开次数排序
- **阅读**：本书独立进度、章节播放时长、目录、全书搜索、主题与排版设置
- **听书**：句级 TTS、逐词高亮、音频预取与本地缓存、0.75–2.0× 倍速
- **语言音色**：中文默认中文男声，英文默认美式男声；只展示常用中英音色
- **两端独立**：网页使用 `localStorage`，终端使用本地 JSON，不互相覆盖
- **安全**：管理写操作使用 Bearer token；Nginx 与应用层拒绝明显的命令行客户端，
  写请求校验同源来源，并返回 CSP、HSTS、Referrer Policy 等安全头

## 项目结构

| 项目 | 位置 | 依赖文件 | 启动 |
| --- | --- | --- | --- |
| 服务端 + 网页端 | 仓库根 | `pyproject.toml` / `uv.lock` | `uv run lector-server` |
| 终端端 | `terminal/` | 独立的 `pyproject.toml` / `uv.lock` | `cd terminal && uv run lector` |

终端端只通过 HTTP 访问服务端，不依赖服务端代码。

```text
lector/       EPUB 解析、TTS、SQLite、HTTP API
web/          原生 ES Modules + CSS，无前端构建步骤
terminal/     Textual 终端客户端
books/        随仓库发布的 EPUB
docs/         API 与 UI 契约
deploy/       部署配置
data/         本地运行时数据（git 忽略）
```

## 快速开始

```bash
uv sync
uv run lector-server
# 打开 http://127.0.0.1:8000
```

常用命令：

```bash
make test       # 服务端 + 终端端测试
make dev        # 热重载服务端
make terminal   # 启动终端端
make book books/my.epub
```

通过 Homebrew 安装终端（PyInstaller 独立二进制，自带 Python 运行时，
机器上不需要 Python）：

```bash
brew tap wsgggws/ebook https://github.com/wsgggws/navydev.top_ebook
brew install wsgggws/ebook/lector
lector
```

终端默认连接 `https://navydev.top/ebook`，自动跟随终端 ANSI 配色，也支持
`dracula`、`catppuccin-*` 等主题；正文采用窄长布局并支持 EPUB 内嵌图片。
开发时可在 `terminal/` 内执行 `uv sync`，键位与主题设置见
[terminal/README.md](terminal/README.md)。

## 添加书籍

网页不提供导入、上传或删除入口。书籍放在仓库的 `books/`，服务启动时自动导入。

推荐文件名：

```text
书名(作者).epub
书名（作者）.epub
```

中英文括号都支持，书名和作者以文件名为准，不用 EPUB 内的广告元数据。

```bash
cp ~/Downloads/new-book.epub books/
git add books/new-book.epub
git commit -m "book: add new-book"
git push origin main
```

也可以从 Markdown 目录生成 EPUB，并发送到正在运行的服务端：

```bash
make book books/my.epub
make book BOOK="books/路径 带空格.epub"
```

`make book` 在目标 EPUB 已存在且没有 Markdown 源时只导入成品，不重新构建。
Markdown 源格式见 [AGENTS.md](AGENTS.md)。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LECTOR_DATA_DIR` | `./data` | SQLite、书籍副本和音频缓存 |
| `LECTOR_BOOKS_DIR` | `./books` | 启动时导入的 EPUB 目录 |
| `LECTOR_TOKEN` | 空 | 可选管理令牌；未配置时公网管理写接口禁用 |
| `LECTOR_HOST` | `127.0.0.1` | 监听地址；设置 token 后默认 `0.0.0.0` |
| `LECTOR_PORT` | `8000` | 监听端口 |
| `LECTOR_BASE_PATH` | 空 | HTTP 前缀；生产环境为 `/ebook` |
| `LECTOR_TTS_ENGINE` | `edge` | `edge` / `espeak` / `auto` |
| `LECTOR_VOICE` | `zh-CN-YunxiNeural` | 全局默认音色 |
| `LECTOR_MAX_UPLOAD` | `52428800` | 上传上限，单位字节 |

令牌权限：

| 令牌 | 权限 |
| --- | --- |
| `<token>` / `<token>:admin` | 上传、删除、预热音频、清理缓存 |
| `<token>:reader` | 只读，不能执行管理写入 |

终端端只读，不需要令牌。

## 进度与状态

- 网页：`localStorage` 的 `lector.settings`、`lector.book`、`lector.books`
- 终端：`~/.config/lector/progress.json` 及同目录配置
- `open_count` 是服务端全局打开次数，只影响书架热度排序，不是阅读进度
- 网页听书条显示本章累计已播时间/章节总时长（`mm:ss`；有小时用 `hh:mm:ss`）；
  全书百分比显示在书架卡片

两端互不覆盖。服务端 `/progress` 接口仅作为可选兼容能力保留。

## 安全与部署

- 阅读 API 公开；未配置 token 时，上传、删除、音频预热/清理等管理写接口禁用
- Nginx 拦截明显的 `curl`、`wget`、`python-requests`、`httpx` 等客户端
- 健康检查、带 `X-Lector-Client: terminal` 的官方终端不需要 token
- 本地 `127.0.0.1` 开发环境允许管理写入；线上域名未配置 token 时禁用管理写接口
- 无 token 的写请求必须带同源 `Origin` 或 `Referer`
- 这些是基础防护，不能替代 token 和 HTTPS

生产环境使用 Docker Compose，由中央 Nginx 提供 TLS 和 `/ebook` 反向代理；
数据在命名卷 `navydev-top-ebook-data`，不使用 systemd。完整流程见
[docs/DEPLOY.md](docs/DEPLOY.md)。

```bash
cp deploy/env.example .env
# 按需编辑 .env；线上默认不配置 LECTOR_TOKEN
make docker-run
```

## 测试

```bash
uv run pytest -q
cd terminal && uv run pytest -q
```

`requirements.txt` 由 `uv export` 生成，不要手工编辑。前端没有 `package.json`
或构建步骤，界面变更通过浏览器验证。

## 文档

- [docs/API.md](docs/API.md)：HTTP API 契约
- [docs/UI.md](docs/UI.md)：网页与终端界面契约
- [docs/DEPLOY.md](docs/DEPLOY.md)：GitHub Actions、Docker、Nginx 与运维
- [AGENTS.md](AGENTS.md)：开发约束、工作流与不变量
- [PROMPT.md](PROMPT.md)：产品范围与阶段目标
