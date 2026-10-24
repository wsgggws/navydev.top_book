# Lector

EPUB 阅读器 + 有声书播放器。网页端读、网页端听、终端读、终端听——四个场景共用一份内容、一个阅读位置。

**读到哪，听到哪。**

## 文档

| 文件 | 用途 |
| --- | --- |
| [PROMPT.md](PROMPT.md) | **主构建提示词** — 粘贴给 coding agent 即可开工 |
| [docs/API.md](docs/API.md) | API 契约：端点、DTO、错误码、幂等语义 |
| [docs/UI.md](docs/UI.md) | 界面规格：token、交互、快捷键、逐词高亮规则 |
| [AGENTS.md](AGENTS.md) | 给在本仓库工作的 agent 的工作方式与不变量 |

## 特色

1. **一个游标** —— `Cursor = {book_id, chapter_id, sentence_id, word_index}` 同时驱动阅读游标线、卡拉OK逐词高亮、终端跟随与进度存储。
2. **句级 TTS** —— 每句独立合成并按内容哈希缓存，点句即听；词边界元数据支撑逐词跟读高亮。
3. **跨端接力** —— 网页与终端读写同一份进度；终端 `s` 推送，网页刷新接着读。
4. **零依赖解析** —— 标准库直读 EPUB，自写 XSS 安全净化。

## 快速上手

环境与依赖用 [uv](https://docs.astral.sh/uv/) 管理：它自己准备 `.venv` 与
Python 版本（`.python-version` 锁定 3.12），不需要手工建虚拟环境。

```bash
uv sync                      # 装依赖（按 uv.lock）
uv run lector-server         # 起服务端，默认 127.0.0.1:8000
uv run lector                # 起终端端
uv run pytest -q             # 跑测试
```

或者用 make（`make help` 看全部）：

```bash
make test                    # 跑测试
make server                  # 起服务端
make terminal                # 起终端端
make book books/some.epub    # 造一本书，并送进服务端
```

打开 http://localhost:8000，把 `books/` 里的 EPUB 拖进去。

终端端复用同一套 API 与同一份进度，默认连 `http://127.0.0.1:8000`；
用 `LECTOR_URL` 与 `LECTOR_TOKEN` 改地址与令牌，或在书架屏按 `c` 填写。

键位尽量照 vim 来：`hjkl` 移动、`Ctrl+d/u` 半页、`Ctrl+f/b` 整页、`/` 搜索、
`n`/`N` 跳结果、`Ctrl+w` 切窗格。正文默认只占中间一页（最多 26 行）并垂直居中，
按 `f` 才铺满整屏。完整键位见 [docs/UI.md](docs/UI.md) §8。

依赖的唯一事实来源是 `pyproject.toml`，`uv.lock` 是锁定的解析结果；
`requirements.txt` 由 `uv export` 生成，只在需要 pip 环境时用。

### 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LECTOR_DATA_DIR` | `./data` | 数据库、EPUB 副本与音频缓存的落盘位置 |
| `LECTOR_TOKEN` | 空 | 非空时所有 `/api/v1/*`（`/health` 除外）要求 Bearer 令牌 |
| `LECTOR_HOST` | `127.0.0.1` | 监听地址；配置了令牌时默认 `0.0.0.0` |
| `LECTOR_PORT` | `8000` | 端口 |
| `LECTOR_TTS_ENGINE` | `edge` | `edge` / `espeak` / `auto` |
| `LECTOR_VOICE` | `zh-CN-XiaoxiaoNeural` | 默认音色 |
| `LECTOR_MAX_UPLOAD` | `52428800` | 上传上限（字节） |

## 线上部署与终端接入

服务要放到公网上，**必须设置 `LECTOR_TOKEN`** —— 未设置令牌时服务端只监听
`127.0.0.1`，不会对外暴露；令牌同时也是终端端的接入凭证。

```bash
# 服务端
export LECTOR_TOKEN="$(openssl rand -hex 24)"
export LECTOR_HOST=127.0.0.1     # 交给反向代理
uv run lector-server
```

前面放一层 Caddy / nginx 负责 TLS，服务只监听回环地址即可。终端端用同一个
令牌接入：

```bash
# 一次性：环境变量
LECTOR_URL=https://reader.example.com LECTOR_TOKEN=xxx uv run lector

# 或者启动后按 c 交互式填写地址与令牌，记在 ~/.config/lector/reader.json
uv run lector
```

## 在项目里造一本书

`make book books/some.epub` 把 Markdown 变成 EPUB，并送进正在跑的服务端 ——
网页端立刻能看能听，不用手动上传。

源可以是单个 Markdown 文件，也可以是一个目录（每个 `.md` 一章）：

```
books/some/
    meta.json        # {"title": …, "author": …, "language": …, "cover": "images/cover.jpg"}
    01-开始.md
    02-之后.md
    images/
```

Markdown 子集很小（标题、段落、列表、引用、代码块、图片、粗/斜/行内代码/链接），
不引第三方库：`lector/build.py` 自己实现，输出 EPUB2（带 NCX 目录），
生成的文件能被本项目的解析器原样读回来。

## 朗读音色

音色跟着书的语言走：中文书默认中文（晓晓），英文书默认**美式男声**（Guy）。
界面只列十个常用音色（中文 4、美式 4、英式 2），在设置里随时换；
换音色会清空该书的音频缓存重新预热。

## 手机上也能用

网页端有专门的窄屏布局：顶栏与听书条按拇指高度设计，目录与设置是全屏抽屉，
触摸目标不小于 44px，听书条留出底部安全区。375px 宽下正文仍是单列满宽，
不横向溢出。

## 跨端接力

网页与终端读写**同一份进度**（SQLite 里的一行），所以两端始终在同一处接着读。

| 端 | 自动 | 手动 |
| --- | --- | --- |
| 终端 | 游标停下 1.2 秒后自动推送 | `s` 立即推送，`S` 立即拉取 |
| 网页 | 游标停下 600ms 后自动推送；阅读时每 5 秒拉取一次 | 刷新页面即取到最新位置 |

规则是**最后写入者胜**：两端同时在读时，以最后一次写入为准，界面上的
`updated_by` 会告诉你刚才是哪一端动的。

想从终端把书送进网页：终端按 `u`，输入本地 `.epub` 的路径；
上传后两端看到的是同一本书、同一个位置。

## 结构

```
pyproject.toml    uv 项目定义（依赖的唯一事实来源）
uv.lock           锁定的依赖解析结果
lector/          服务端：解析器、TTS、HTTP 层、SQLite
web/             网页端：原生 ES Modules + CSS，无打包器
terminal/        终端端：Textual
tests/           pytest
docs/            契约（API 与界面）
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

阶段 0–8 已实现：解析器、API、TTS、网页阅读与听书、进度接力、终端端与打磨。

已知缺口见 [PROMPT.md](PROMPT.md) §7 的验收清单与本次提交的说明。
