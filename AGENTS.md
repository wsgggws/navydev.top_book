# AGENTS.md

你在维护 **navydev.top_ebook**：一个 EPUB 有声电子书服务，包含网页端和独立的终端端。
两端共享内容和全局打开次数，但阅读位置、音色、倍速等个人状态各自保存在本地。

## 核心模型

**位置只有一种表示**：

```text
Cursor = {book_id, chapter_id, sentence_id, word_index}
```

高亮、逐词朗读、本地进度、短码分享都是这个游标的投影。不要引入页码、段落序号等
第二套位置。

## 先读契约

- 改 HTTP 端点、字段、错误码、状态码：先读 `docs/API.md`
- 改界面、主题、快捷键、布局：先读 `docs/UI.md`
- 不确定范围：读 `PROMPT.md` 的「边界」与「完成定义」
- 改 EPUB 解析异常行为：读 `PROMPT.md` §4 与 §7 阶段 1

契约与实现冲突时以契约为准。确需修改契约时，先改契约，再改实现，并在同一个提交完成。

## 两个独立项目

环境统一使用 **uv + Python 3.12**。不要手工建 venv，也不要手工 `pip install`。

| 项目 | 位置 | 启动 | 测试 |
| --- | --- | --- | --- |
| 服务端 + 网页端 | 仓库根 | `uv run lector-server` | `uv run pytest -q` |
| 终端端 | `terminal/` | `cd terminal && uv run lector` | `cd terminal && uv run pytest -q` |

```bash
uv sync
make test
make dev
make book books/my.epub
```

- 两个项目各有自己的 `pyproject.toml` 和 `uv.lock`，都要提交。
- 改依赖用 `uv add` / `uv remove`。
- `requirements.txt` 只由 `uv export` 生成，不要手改。
- 前端是原生 ES Modules + CSS，没有 `package.json`、打包器或前端 lint。

## 开发工作流

### 新功能

1. 确认需求在 `PROMPT.md` 范围内。
2. 阅读对应 API/UI 契约。
3. 列出要改的具体文件。
4. 实现并同步契约。
5. 添加测试，运行两端 `pytest -q`。
6. 汇报文件、契约变更、测试结果和已知缺口。

### 修 Bug

1. 先写可稳定复现的失败测试并确认失败。
2. 修实现直到测试通过。
3. 跑全量测试，确认没有回归。

### 新阶段

按 `PROMPT.md` §7 的顺序推进，逐条对照验收项，不要笼统汇报“已完成”。

## 不变量

- **ID 稳定**：`chapter = c{index}`、`block = c{chapter}.b{n}`、
  `sentence = c{chapter}.b{block}.s{n}`。同一 EPUB 重复解析必须产生相同 ID；
  解析行为改变时提升 `PARSER_VERSION`。
- **目录与正文分离**：章节顺序由 spine 决定；TOC 节点只携带 `chapter_id`
  和可选 `anchor`，不得拿 TOC 节点 id 请求章节。TOC 同时支持 EPUB3 `nav`
  （优先）与 EPUB2 `NCX`。
- **句子切分**：支持中英混排；中文句号/问号/叹号/分号/省略号及闭引号成句，
  英文 `.!?` 后接空格或行尾成句；小数和 `Mr.`、`e.g.` 等缩写不切。
  规则由 `tests/test_sentence_split.py` 锁定。
- **净化白名单**：只允许 `href/src/alt/title/lang/dir/class`，`class` 仅
  `epub-*`；拒绝 `javascript:`、`data:`；丢弃
  `script/style/iframe/object/embed/form`。
- **上传安全**：拒绝路径穿越和符号链接，限制解压膨胀比，上传上限 50MB。
- **EPUB 解析**：只用标准库 `zipfile`、`ElementTree`、`html.parser`，不引入
  第三方解析器；生成的文件必须让 `mimetype` 是首个且不压缩的条目，但解析时
  不要依赖它的位置。
- **音频缓存**：键为 `sha256(text | voice | rate | engine_version)`；同键必须复用。
- **TTS 词边界**：引擎返回字素偏移，需要归一化为词级并换算成句内相对秒数；
  espeak 回退没有词边界，`granularity` 降为 `"sentence"`。
- **音色跟随语言**：中文默认 `zh-CN-YunxiNeural`，英文默认
  `en-US-GuyNeural`；客户端通过 `GET /api/v1/meta` 读取映射，不各自硬编码。
- **进度隔离**：网页和终端各存各的。网页以 `localStorage` 为准，终端以本地
  JSON 为准；内置客户端不通过服务端同步位置。服务端 `/progress` 仅为兼容保留。
- **网页进度计算**：游标变化时立即写本地位置；全书百分比通过
  `/percent` 计算，并用约 400ms 防抖避免连续请求。
- **打开次数**：`open_count` 是全局热度数据；网页只在用户主动打开书时调用
  `POST /api/v1/books/{id}/open`。书架先按本地最近阅读，再按 `open_count` 排序。
- **依赖白名单**：`fastapi`、`uvicorn`、`pydantic`、`edge-tts`、`textual`、
  `pytest`、`httpx`、`python-multipart`。新增依赖必须说明标准库为何不够，
  并更新契约或提交说明。`python-multipart` 是 FastAPI 解析上传表单所必需。
- **权限**：阅读 API 公开；公网 Host 下上传/删除/预热/清缓存需要 admin token，
  未配置时返回 `ADMIN_DISABLED`；本机开发 Host 例外。终端只读，通过
  `X-Lector-Client: terminal` 标识且不需要 token。令牌支持
  `<token>:admin` 和 `<token>:reader`。
- **浏览器防护**：生产 Nginx 和应用层拦截明显的 CLI User-Agent；健康检查、
  带 `X-Lector-Client: terminal` 的终端、带 Bearer token 的管理请求例外。
  无 token 的写请求必须同源。防护不能替代 token。
- **部署**：GitHub Actions 构建镜像并通过 SSH + Docker Compose 发布；生产容器
  只监听 `127.0.0.1:8010`，数据卷为 `navydev-top-ebook-data`。不要改回 systemd。

## 书籍构建

- `make book books/my.epub` 可从 Markdown 生成并导入；目标 EPUB 已存在且没有源时
  只导入成品。
- 路径含空格用 `make book BOOK="books/路径 带空格.epub"`。
- 目录源支持 `meta.json`、按文件名排序的 `.md` 章节和 `images/`。
- 仓库书籍元数据以文件名 `书名(作者).epub` / `书名（作者）.epub` 为准；
  中英文括号都支持，文件名优先于 EPUB 内嵌标题和作者。
- Markdown 子集：标题、段落、列表、引用、代码块、分隔线、图片、行内粗体/斜体/
  代码/链接；`lector/build.py` 自己实现，输出可回读的 EPUB2 + NCX。

## 约定

- Python 3.12，全程类型注解；DTO 集中在 `lector/models.py`，与 `docs/API.md`
  字段一一对应，不设别名。
- API 字段和 Python 用 `snake_case`，JS 用 `camelCase`。
- 网页一个文件一个职责，纯函数放 `web/js/util.js`；终端屏幕放
  `terminal/lector_tui/screens/`。
- 注释解释“为什么”，不解释“做什么”。
- 不重复合成同键音频；音频 URL 不可变，换音色/语速后由缓存键自然失效。
- 音频播放以 timeline 的 `start/end` 为准，不用章节元数据里的
  `audio_duration` 做定位。

## 完成判据

工作完成必须同时满足：

1. 需求逐条实现，没有遗漏。
2. 新行为有测试；Bug 有可复现的回归测试。
3. `docs/API.md` / `docs/UI.md` 与实现一致。
4. 服务端与终端端测试全绿。
5. 没有新增白名单外依赖。
6. 汇报改动文件、契约变化、测试输出、未完成项和已知问题。

没做完就明确说没做完，不要用“看起来没问题”代替验证。
