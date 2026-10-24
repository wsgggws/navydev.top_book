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
Python 版本（`.python-version` 锁定 3.11），不需要手工建虚拟环境。

```bash
uv sync                      # 装依赖（按 uv.lock）
uv run lector-server         # 起服务端，默认 127.0.0.1:8000
uv run lector                # 起终端端
uv run pytest -q             # 跑测试
```

打开 http://localhost:8000，把 `books/` 里的 EPUB 拖进去。

终端端复用同一套 API 与同一份进度，默认连 `http://127.0.0.1:8000`；
用 `LECTOR_URL` 与 `LECTOR_TOKEN` 改地址与令牌。

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
