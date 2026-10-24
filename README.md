# navydev.top_ebook

**有声电子书** —— EPUB 阅读与收听服务，线上地址是
[navydev.top/ebook](https://navydev.top/ebook)。

网页端读、网页端听、终端读、终端听。两端连接同一台内容服务，但各自记录
自己的阅读位置和播放选项：网页存浏览器 `localStorage`，终端存本机缓存文件。

网页支持直接分享的路径：`/ebook/{book_id}` 和
`/ebook/{book_id}/{chapter_id}`。

**读到哪，听到哪。**

## 文档

| 文件 | 用途 |
| --- | --- |
| [PROMPT.md](PROMPT.md) | **主构建提示词** — 粘贴给 coding agent 即可开工 |
| [docs/API.md](docs/API.md) | API 契约：端点、DTO、错误码、幂等语义 |
| [docs/UI.md](docs/UI.md) | 界面规格：token、交互、快捷键、逐词高亮规则 |
| [AGENTS.md](AGENTS.md) | 给在本仓库工作的 agent 的工作方式与不变量 |

## 特色

1. **一个游标** —— 每一端都用 `Cursor = {book_id, chapter_id, sentence_id, word_index}` 表示位置，同时驱动当前句高亮、逐词高亮与本机进度。
2. **句级 TTS** —— 每句独立合成并按内容哈希缓存，点句即听；词边界元数据支撑逐词跟读高亮。
3. **两端独立** —— 网页与终端不共享阅读位置、音色或倍速；切换设备不会覆盖另一端的记录。
4. **零依赖解析** —— 标准库直读 EPUB，自写 XSS 安全净化。
5. **按使用习惯排序** —— 最近打开的书优先，其余按服务端打开次数排序；书架支持书名模糊搜索和每页 12 本分页。
6. **阅读进度可见** —— 阅读区顶部显示本章已读/剩余秒数，书架卡片显示全书百分比；进度保存在浏览器本地。

## 快速上手

环境与依赖用 [uv](https://docs.astral.sh/uv/) 管理：它自己准备 `.venv` 与
Python 版本（`.python-version` 锁定 3.12），不需要手工建虚拟环境。

仓库里有两个互不干扰的项目：

| 项目 | 位置 | 依赖 | 跑起来 |
| --- | --- | --- | --- |
| **服务端 + 网页端** | 仓库根 | fastapi / uvicorn / pydantic / edge-tts | `uv run lector-server` |
| **终端端** | `terminal/` | 只有 textual | `cd terminal && uv run lector` |

终端端只通过 HTTP 与服务端打交道，**不依赖服务端的任何代码**；服务端也不知道
终端端的存在。两边各有自己的 `pyproject.toml` 与 `uv.lock`，可以分别安装、分别发版。

```bash
uv sync                      # 服务端：装依赖（按 uv.lock）
uv run lector-server         # 起服务端，默认 127.0.0.1:8000
uv run pytest -q             # 服务端的测试

cd terminal && uv sync && uv run lector   # 终端端
```

或者用 make（`make help` 看全部）：

```bash
make test                    # 两个项目的测试都跑
make server                  # 起服务端
make terminal                # 起终端端
make book books/my.epub      # 造一本书，并送进服务端
```

打开 http://localhost:8000。`books/` 下的 EPUB 会在服务启动时自动导入，
网页端不提供上传或删除入口。

终端端复用同一套内容 API，默认连 `http://127.0.0.1:8000`；
用 `LECTOR_URL` 改地址；阅读接口不需要令牌，也可在书架屏按 `c` 填写地址。

键位尽量照 vim 来：`hjkl` 移动、`Ctrl+d/u` 半页、`Ctrl+f/b` 整页、`/` 搜索、
`n`/`N` 跳结果、`Ctrl+w` 切窗格。正文默认只占中间一页（最多 26 行）并垂直居中，
按 `f` 才铺满整屏。完整键位见 [docs/UI.md](docs/UI.md) §8。

依赖的唯一事实来源是 `pyproject.toml`，`uv.lock` 是锁定的解析结果；
`requirements.txt` 由 `uv export` 生成，只在需要 pip 环境时用。

### 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LECTOR_DATA_DIR` | `./data` | 数据库、EPUB 副本与音频缓存的落盘位置 |
| `LECTOR_TOKEN` | 空 | 保护管理写操作，并启用网页浏览器访问与同源写请求校验 |
| `LECTOR_BOOKS_DIR` | `./books` | 启动时自动导入此目录的 `*.epub` |
| `LECTOR_HOST` | `127.0.0.1` | 监听地址；配置了令牌时默认 `0.0.0.0` |
| `LECTOR_PORT` | `8000` | 端口 |
| `LECTOR_TTS_ENGINE` | `edge` | `edge` / `espeak` / `auto` |
| `LECTOR_VOICE` | `zh-CN-YunxiNeural` | 默认音色（中文男声） |
| `LECTOR_MAX_UPLOAD` | `52428800` | 上传上限（字节） |
| `LECTOR_BASE_PATH` | 空 | 把应用挂在某个路径下（如 `/ebook`），nginx 那边路径要原样传过去 |

## 线上部署与终端接入

阅读接口对公网公开，不需要令牌。`LECTOR_TOKEN` 只用于管理写操作，防止任何人
上传、删除书籍或清理音频缓存。

配置令牌后，网页、静态资源和公开 API 会拒绝明显的 `curl`、`wget`、
`python-requests` 等命令行 User-Agent；健康检查、官方终端客户端和带 Bearer
token 的管理 CLI 例外。无 Bearer token 的写请求还必须带同源 `Origin` 或
`Referer`。公开只读 API 继续允许终端客户端访问。

```bash
# 服务端
export LECTOR_TOKEN="$(openssl rand -hex 24)"
export LECTOR_HOST=127.0.0.1     # 交给反向代理
uv run lector-server
```

前面放一层 Caddy / nginx 负责 TLS，服务只监听回环地址即可。终端端用同一个
终端只读，不需要令牌：

```bash
# 一次性：环境变量
LECTOR_URL=https://navydev.top/ebook uv run lector

# 或者启动后按 c 交互式填写地址与令牌，记在 ~/.config/lector/reader.json
uv run lector
```

## 添加书籍

网页端不提供上传或删除入口。项目的书籍来源就是仓库里的 `books/` 目录：

```bash
cp ~/Downloads/new-book.epub books/
git add books/new-book.epub
git commit -m "book: add new-book"
git push origin main
```

服务启动时会自动导入 `books/*.epub`，内容哈希保证重复启动不会重复添加。
本地也可以用 `make book books/my.epub` 从 Markdown 生成 EPUB。

推荐文件名格式：

```text
书名(作者).epub
书名（作者）.epub
```

英文和中文括号都支持。书架上的标题、作者**以文件名为准**，会覆盖 EPUB
内嵌元数据，避免出版方广告或额外宣传文字出现在书架上。没有括号时，整个文件名
作为标题，作者显示为空。

源可以是单个 Markdown 文件，也可以是一个目录（每个 `.md` 一章）：

```
books/my/
    meta.json        # {"title": …, "author": …, "language": …, "cover": "images/cover.jpg"}
    01-开始.md
    02-之后.md
    images/
```

Markdown 子集很小（标题、段落、列表、引用、代码块、图片、粗/斜/行内代码/链接），
不引第三方库：`lector/build.py` 自己实现，输出 EPUB2（带 NCX 目录），
生成的文件能被本项目的解析器原样读回来。

**目标文件已经存在又没有源时，它不重建，只把成品收进书架** —— 所以加书和造书
是同一条命令：

```bash
make book "books/某本书 (作者).epub"      # 从 Markdown 生成书
make book BOOK="books/某本书 (作者).epub"  # 路径带空格时用这种写法
```

## 朗读音色

音色跟着书的语言走：中文书默认中文男声（云希），英文书默认**美式男声**（Guy）。
界面只列十个常用音色（中文 4、美式 4、英式 2），在设置里随时换；
换音色会清空该书的音频缓存重新预热。

## 手机上也能用

网页端有专门的窄屏布局：顶栏与听书条按拇指高度设计，目录与设置是全屏抽屉，
触摸目标不小于 44px，听书条留出底部安全区。375px 宽下正文仍是单列满宽，
不横向溢出。

## 部署上线

见 **[docs/DEPLOY.md](docs/DEPLOY.md)**：GitHub Actions 测试后通过 SSH 发布，
服务器用 Docker Compose 运行容器，中央 nginx 管 `/ebook` 路径与 TLS。
数据保存在固定 Docker 命名卷里，不依赖 systemd。

一句话版本：

```bash
cp deploy/env.example .env
# 编辑 .env，把 LECTOR_TOKEN 换成随机令牌
make docker-run
```

阅读永远公开；管理令牌只影响写操作：

| 令牌 | 权限 |
| --- | --- |
| `<token>` / `<token>:admin` | 上传、删除、预热音频、清缓存等管理操作 |
| `<token>:reader` | 不能执行管理写操作 |

终端端只读，不需要配置令牌。

## 两端各自记录

| 端 | 位置 | 每本书的选项 |
| --- | --- | --- |
| 网页 | `localStorage` 的 `lector.books` | 音色、男/女声、倍速、进度 |
| 终端 | `~/.config/lector/progress.json` | 终端自己的游标与百分比 |

终端是只读客户端：可以浏览、搜索、播放和保存本机进度，但不能上传、删除书籍，
也不能修改服务端音频缓存。两端切换书籍时互不影响。

## 结构

```
pyproject.toml    服务端项目：依赖的事实来源
uv.lock           服务端的锁
lector/          服务端：解析器、TTS、HTTP 层、SQLite
web/             网页端：原生 ES Modules + CSS，无打包器
tests/           服务端的 pytest
terminal/         终端端项目：自己的 pyproject.toml / uv.lock / Textual
docs/            契约（API 与界面）
deploy/          部署用的现成配置
Dockerfile       生产镜像
docker-compose.yml 容器、端口、数据卷与健康检查
.github/         CI 与原子发布 workflow
data/            运行时数据（git 忽略）
```

## 开发

```bash
uv run pytest -q                    # 全量测试
uv run pytest -q tests/test_epub.py # 单文件
curl -s localhost:8000/api/v1/health | jq .
```

没有 `package.json`、没有前端构建步骤、没有 lint 配置。改动靠 `pytest` 验证，界面靠肉眼验证。

## 当前状态

阶段 0–8 已实现：解析器、API、TTS、网页阅读与听书、两端独立进度、终端端与打磨。

已知缺口见 [PROMPT.md](PROMPT.md) §7 的验收清单与本次提交的说明。
