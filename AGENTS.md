# AGENTS.md

你在维护 **Lector** —— 一个 EPUB 阅读器 + 有声书播放器，网页端与终端端共享同一份内容与同一个阅读位置。

## 首要原则

**位置只有一种表示。** 全书的阅读位置永远是 `Cursor = {book_id, chapter_id, sentence_id, word_index}`。阅读高亮、逐词高亮、终端跟随、进度存储、短码分享，全部是这一个游标的不同投影。任何新增的"位置"概念都是 bug，不是特性。

## 必读指针

按需触发，不要预先全读：

- **改动任何 HTTP 端点、字段名、错误码、状态码之前** → 读 `docs/API.md`。它是 API 的**契约**，唯一事实来源。
- **改动界面、主题、快捷键、布局之前** → 读 `docs/UI.md`。它是界面的**契约**，唯一事实来源。
- **不确定某个功能该不该做、该做到什么程度** → 读 `PROMPT.md` 的「边界」与「完成定义」。它定义了产品范围。
- **解析 EPUB 的异常行为** → 读 `PROMPT.md` §4「内容模型」与 §7 阶段 1 的验收项。

契约与实现冲突时：以契约为准，改实现。若确信契约本身该改，**先改契约文件，再改实现**，两者同一个提交里完成。

## 常用命令

环境与依赖一律用 **uv** 管理，不要手工建 venv、也不要手工 pip install。

```bash
# 安装：uv 自己准备 .venv 与 Python 版本（见 .python-version）
uv sync

# 开发服务器
uv run lector-server                              # 默认 127.0.0.1:8000
uv run uvicorn lector.web:app --reload --port 8000

# 终端端
uv run lector

# 测试
uv run pytest -q                    # 全量
uv run pytest -q tests/test_epub.py # 单文件
uv run pytest -q -k sentence        # 按名字过滤

# 端到端冒烟
curl -s localhost:8000/api/v1/health | jq .
```

以上都有对应的 make 目标（`make help` 看全部）：

```bash
make test            # uv run pytest -q
make server          # uv run lector-server
make dev             # 带热重载的服务端
make terminal        # uv run lector
make book books/some.epub   # 生成一本书，并送进服务端
make import books/some.epub # 把已有的 EPUB 送进服务端
```

- `pyproject.toml` 是依赖的**唯一事实来源**；`uv.lock` 是锁定的解析结果，两者都要提交。
- `requirements.txt` 是由 `uv export --format requirements-txt --no-hashes --no-emit-project --output-file requirements.txt` 生成的产物，**不要手工编辑**。只在需要 pip 环境时用它。
- 改依赖用 `uv add <包>` / `uv remove <包>`，不要手写 `pyproject.toml` 里的版本号。
- 新增运行时依赖仍要遵守下面的依赖白名单。
- 构建期依赖（`hatchling`）不进运行时环境，不受白名单约束。

没有 `package.json`、没有前端构建步骤、没有 lint 配置。改动靠 `pytest` 验证，靠肉眼验证界面。

## 在项目里造一本书

`make book books/some.epub` 把 Markdown 源变成 EPUB，并顺手送进正在跑的服务端，
网页端立刻能看能听。

源可以是单个 Markdown 文件，也可以是一个目录：

```
books/some/
    meta.json        # {"title": …, "author": …, "language": …, "cover": "images/cover.jpg"}
    01-开始.md       # 每个 .md 一个章节，按文件名排序
    02-之后.md
    images/          # 章节里引用的图片
```

- Markdown 子集很小：标题、段落、列表、引用、代码块、分隔线、图片、行内的粗/斜/代码/链接。
- 不引第三方 Markdown 库：`lector/build.py` 自己实现，输出 EPUB2（NCX 目录），
  生成的文件能被本项目的解析器读回来。
- 目录节点与章节是两回事：目录节点带 `chapter_id` 与可选 `anchor`；客户端按
  「取章节 → 按 anchor 找块 → 游标落到块首句」定位，不得拿节点 id 去请求章节端点。

## 工作流

### 开始一个新功能

1. 在 `PROMPT.md` §9「边界」里确认它在范围内。范围外 → 停下并说明，不要自行扩大范围。
2. 读对应的契约文件（`docs/API.md` 或 `docs/UI.md`）里相关的小节。
3. 找出要改的落点，列出**具体文件路径**再动手。
4. 实现时同步更新契约文件。
5. 写测试，跑 `pytest -q`，确认全绿。
6. 汇报：改了哪些文件、契约改了哪几节、测试结果。

### 修一个 bug

1. 先写一个**能复现该 bug 的失败测试**。跑一次，确认它确实失败。
2. 改实现，让测试通过。
3. 跑 `pytest -q` 确认没有连带破坏。

复现测试是修复的**完成判据**：没有它，修复只是"看起来好了"。

### 实现一个新阶段

按 `PROMPT.md` §7 的阶段顺序推进。每个阶段的验收项是**逐条可检查**的清单，做完逐条对照汇报，不要笼统说"已完成"。

## 不变量

这些是硬约束，改动时必须保持：

- **ID 稳定性**：`chapter = c{index}`，`block = c{chapter}.b{n}`，`sentence = c{chapter}.b{block}.s{n}`。同一 EPUB 重复解析必须得到完全相同的 ID。解析器行为变更时，同步提升 `PARSER_VERSION`。
- **目录与章节分层**：目录节点的 id 与章节 id 是两套命名。目录节点带 `chapter_id` 与可选 `anchor`；定位动作是「取章节 → 按 anchor 找块 → 游标落到块首句」。客户端不得拿目录节点 id 去请求章节端点。
- **句子切分**：中英混排。中文标点 `。！？；…` 及闭引号成句；英文 `.!?` 后接空格或行尾成句；小数点、缩写（`Mr.`、`e.g.`）不成句。切分规则由 `tests/test_sentence_split.py` 锁定。
- **净化白名单**：只放行 `href`/`src`/`alt`/`title`/`lang`/`dir`/`class`（`class` 仅 `epub-*` 前缀）。`javascript:` 与 `data:` URL 一律拒绝。`script`/`style`/`iframe`/`object`/`embed`/`form` 一律丢弃。
- **上传安全**：拒绝 `..` 路径穿越条目、拒绝符号链接、限制解压膨胀比。上传上限 50MB。
- **音频缓存**：缓存键 = `sha256(text | voice | rate | engine_version)`。同键必须复用，不重复合成。
- **无第三方案例**：EPUB 解析走标准库 `zipfile` + `ElementTree` + `html.parser`，不引入第三方解析器。
- **依赖白名单**：`fastapi` `uvicorn` `pydantic` `edge-tts` `textual` `pytest` `httpx` `python-multipart`。新增依赖需要能回答"标准库为什么做不到"，并在提交说明里写清。
  - `python-multipart`：`docs/API.md` §3 规定上传端点是 `multipart/form-data`，FastAPI 解析 multipart 表单强制依赖它；标准库的 `email`/`cgi` 无法被 FastAPI 直接使用（`cgi` 已在 Python 3.13 移除）。
- **进度写入**：客户端防抖 600ms。服务端按 `updated_at` 后写入者胜。
- **音色跟着书的语言走**：中文书默认中文（`zh-CN-XiaoxiaoNeural`），英文书默认美式男声
  （`en-US-GuyNeural`）。映射写在 `lector/config.py` 的 `DEFAULT_VOICE_BY_LOCALE`，
  客户端经 `GET /api/v1/meta` 的 `default_voices` 拿到同一份，不要各写一套。

## 约定

- Python 3.11+，全程类型注解。DTO 用 Pydantic，定义集中在 `lector/models.py`，与 `docs/API.md` 逐字段对应，不设字段别名。
- 网页端是原生 ES Modules + CSS：每个文件一个职责，`views/` 放页面级模块，`util.js` 放纯函数。不引入框架或 UI 库。
- 终端端用 Textual：屏幕放 `screens/`，与 `web/js/views/` 一一对应。
- 命名：API 字段 `snake_case`；Python `snake_case`；JS `camelCase`。
- 注释解释**为什么**，不解释**做了什么**。能自解释的代码不写注释。
- 提交前跑 `pytest -q`，必须全绿。绿的截图/日志贴进汇报。

## 常见坑

- **EPUB 的 TOC 有两套**：EPUB3 用 `nav` 文档，EPUB2 用 `NCX`。两者都要支持，且 EPUB3 优先。`toc.py` 里两套解析器共用同一个归一化输出。
- **章节顺序由 spine 决定**，不由 TOC 决定。TOC 是目录，spine 是正文顺序，两者不一致的 EPUB 真实存在。
- **`mimetype` 必须是 zip 的第一个条目且不压缩**。部分 EPUB 不满足，解压时不要强制校验，但解析时不要依赖它的位置。
- **TTS 的词边界是字素偏移**，需要归一化到词级，再换算成句内相对秒数。回退引擎（espeak）没有词边界，`granularity` 降为 `"sentence"`，前端相应不做词级拆分。
- **音频 URL 不可变**：`audio/{sentence_id}.mp3` 的内容随内容哈希固定，可长期 `immutable` 缓存。换音色后要清缓存（`DELETE /books/{id}/audio`）。
- **`audio_duration` 与实际时长可能不等**：合成器对同一段文本两次生成的时长略有差异。以 `timeline` 接口返回的 `start`/`end` 为准，不要用章节元数据里的 `audio_duration` 做播放定位。
- **进度写入风暴**：拖动滚动条会连续触发 PUT。前端必须防抖，服务端也不要在同秒内反复改写 `updated_at`。

## 完成判据

一次工作算完成，当且仅当：

1. 需求项逐条实现，无遗漏、无部分完成。
2. 新增行为有对应测试。
3. 契约文件（`docs/API.md` / `docs/UI.md`）与实现一致。
4. `pytest -q` 全绿。
5. 无新增未列入白名单的依赖。
6. 汇报里给出了：改了哪些文件、契约改了哪几节、测试输出、尚未完成或已知问题。

第 6 条不可省。**没做完就说没做完** —— 半成品加沉默，比明确报出缺口更贵。
