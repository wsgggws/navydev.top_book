# navydev.top_book（Lector）— 主构建提示词（Master Prompt）

> **用途**：把本文件整段粘贴给一个 coding agent，或直接作为项目的立项契约。
> **配套契约**（构建时必须遵循，冲突时以契约文件为准）：
> - [API 契约](docs/API.md) — 端点、DTO、错误码、缓存语义
> - [界面规格](docs/UI.md) — 网页端与终端端的视觉/交互/键盘契约
> - [仓库指令](AGENTS.md) — 给在本仓库工作的 agent 的工作方式

---

## 0. 一句话

做一个 **EPUB 阅读器 + 有声书播放器**：上传 EPUB，在网页上读、在网页上听、在终端里读、在终端里听。四个场景共享同一份内容；**位置各端各记各的**，互不干扰。

## 1. 产品主张

**读到哪，听到哪。**

大多数阅读器把"阅读"和"听书"做成两个互不相干的模式：位置模型不同、进度不同、书签不同、跨端不互通。本项目只保留**一个**位置模型：

```
Cursor = { book_id, chapter_id, sentence_id, word_index }
```

这一个游标同时驱动三处表现：

| 表现层 | 游标的作用 |
| --- | --- |
| 网页阅读态 | 当前句的琥珀色游标线与背景 |
| 网页听书态 | 逐词卡拉OK高亮落到哪个词 |
| 终端阅读态 | 当前句加粗高亮 + 自动滚动对齐 |
| 终端听书态 | 终端里逐词高亮 + 状态栏时间 |

由此得到四个特征，**全部由这个模型自然导出，不额外造功能**：

1. **句级 TTS 粒度** — 每句话独立合成并缓存，点句即听、听即定位。
2. **逐词时间戳** — 引擎给出词边界，网页端做跟读式卡拉OK高亮，终端端同样逐词点亮。
3. **各端自记位置** — 网页把位置存在浏览器本地（localStorage），终端存在自己的缓存文件里。两端独立：在终端读到哪，不会把网页顶走；同一端关掉再打开，接着上次那一处。
4. **零依赖 EPUB 解析** — 标准库直读 zip/OPF/NCX，自写 XSS 安全净化。

## 2. 技术栈（已定，不要替换）

| 层 | 选择 | 理由 |
| --- | --- | --- |
| 后端 | Python 3.12 / FastAPI / Uvicorn | TTS 与 EPUB 处理生态在 Python 侧最成熟 |
| 依赖策略 | **运行时零第三方依赖**（仅 FastAPI + uvicorn + pydantic） | EPUB 解析走标准库 `zipfile`+`ElementTree`，避免被第三方解析器的行为差异绑住 |
| TTS | `edge-tts`（必需）+ `espeak-ng`（可选离线回退） | edge-tts 免费无需密钥、支持词边界元数据；espeak 降级为句级高亮 |
| 存储 | SQLite（进度/元数据/搜索索引） + 文件系统（原始 EPUB、解析结果、音频缓存） | 二进制与大对象走文件系统，结构化数据走 SQLite |
| 前端 | 原生 ES Modules + CSS，**无打包器、无框架** | `uv sync && uv run lector-server` 即可跑；阅读器交互自定义程度高，框架收益低 |
| 终端端 | Textual | Python 原生 TUI，跨平台，滚动/焦点/快捷键成熟 |
| 测试 | pytest | — |

**依赖白名单**：Python 侧 `fastapi`、`uvicorn`、`pydantic`、`edge-tts`、`textual`、`pytest`、`httpx`、`python-multipart`（上传端点的 `multipart/form-data` 解析，FastAPI 强制依赖）。新增任何依赖前先在 `AGENTS.md` 的约束里确认；确实需要时在 PR 说明里写清"为什么标准库做不到"。

## 3. 目录结构（按此落地）

```
pyproject.toml       # 服务端项目：依赖的事实来源
uv.lock              # 服务端的锁
lector/
  __init__.py
  config.py          # 配置：路径、端口、TTS 引擎、访问令牌
  db.py              # SQLite 连接、schema、迁移
  models.py          # Pydantic DTO（API 出入参唯一来源）
  positions.py       # 游标编解码、短码、进度合并
  epub/
    __init__.py
    container.py     # 读取 META-INF/container.xml → OPF 路径
    opf.py           # manifest / spine / metadata
    toc.py           # EPUB3 nav 与 EPUB2 NCX 双通道解析
    html.py          # XHTML → 块结构（自写 html.parser）
    sanitize.py      # 标签/属性白名单
    parse.py         # 编排：产出 Book / Chapter / Block / Sentence
  tts/
    __init__.py
    base.py          # TTSEngine 协议 + TTSResult + Voice
    edge.py          # edge-tts 实现（含 WordBoundary 采集）
    espeak.py        # espeak-ng 回退实现（句级时间戳）
    cache.py         # 内容寻址缓存
  api/
    __init__.py
    books.py  chapters.py  audio.py  progress.py  search.py  system.py
web/
  index.html
  styles/{tokens,base,library,reader,player}.css
  js/{api,state,player,util}.js
  js/views/{library,reader,toc}.js
terminal/lector_tui/
  __init__.py  app.py  screens/{library,reader,listen}.py  audio.py
tests/
data/            # 运行时数据（git 忽略）
```

## 4. 内容模型（解析器与 TTS 的共同基础）

EPUB → 书籍 → 章节 → 块 → 句子：

```
Book
├── id, title, author, language, sha256, cover_path
├── toc: TreeNode[]            # nav/NCX 归一化后的目录树
└── chapters: Chapter[]        # 按 spine 顺序
    └── id="c{index}", title, index, blocks[]
        └── id="c12.b3", type ∈ {p,h1..h6,li,blockquote,img,hr}, anchor?
            └── id="c12.b3.s0", text, words[]
```

- **ID 规则**：`chapter = c{spine下标}`，`block = c{chapter}.b{块下标}`，`sentence = c{chapter}.b{block}.s{句下标}`。ID 必须稳定、可预测、可在日志里肉眼定位。解析器行为变更时同步提升 `PARSER_VERSION`。
- **句子切分**：中英混排切分。中文标点 `。！？；…` 及其闭引号/后缀成句；英文 `.!?` 后接空格或行尾成句；数字中的小数点、缩写（`Mr.`、`e.g.`）不切；空白与标点归入前句。**切分必须由单元测试锁定**（见验收）。
- **图片**：`img` 块保留 `src`（相对 EPUB 内路径）与 `alt`；解析期不外联，只在有本地封面时提供封面接口。
- **锚点**：块可携带 `anchor`（EPUB 内部 `<a name>`/`<a id>`），供目录节点定位到章内小节。目录树节点与章节是两个层级：目录节点带 `chapter_id` + 可选 `anchor`，定位动作为「取章节 → 按 anchor 找块 → 游标落到块首句」。
- **净化**：`script`/`style`/`iframe`/`object`/`embed`/`form` 一律丢弃；属性白名单只放 `href`/`src`/`alt`/`title`/`lang`/`dir`/`class`（class 限定 `epub-*` 前缀）；`javascript:`/`data:` URL 拒绝。

## 5. TTS 契约

```python
class TTSEngine(Protocol):
    name: str
    def voices(self) -> list[Voice]: ...
    def synth(self, text: str, voice: str, rate: str) -> TTSResult: ...
    # TTSResult: audio: bytes, duration: float(秒),
    #            words: list[WordBoundary(w, start, end)]  # 秒
```

- **句砖（tile）**：一个 sentence 的音频 + 词边界。缓存键 = `sha256(text | voice | rate | engine_version)`，落盘 `data/audio/<key[:2]>/<key>.mp3`，同键复用。
- 词边界从引擎给出的**字��偏移**归一化到句子内的**词偏移**；引擎不提供词边界时（espeak 回退），退化为句级时间戳，前端只做整句高亮。
- 章节时间线 = 该章所有句砖按时序拼接，`sentence_id → (start, end)` 秒。

## 6. 界面契约

- 网页端三个区：**顶栏**（书名/章节/主题/字号/设置）、**左侧目录抽屉**（TOC + 搜索）、**中间阅读列**（最大 680px 宽）。底部**听书条**可折叠。
- 网页端听书时，**逐词高亮**是视觉签名；朗读中的句子带琥珀色游标线。
  播放期间不自动滚动正文，只保证当前句高亮准确。
- 终端端三个屏：**书架** / **阅读** / **听书**。听书屏与阅读屏共用同一份块/句结构，逐词高亮方式一致。
- 主题三套：纸白 / 羊皮 / 夜间。字体走系统衬线栈（含中文衬线）。
- 完整视觉 token、间距、动效、键盘映射、无障碍要求见 [界面规格](docs/UI.md)，**实现时逐条对照**。

## 7. 实施阶段（每阶段结束必须满足该阶段的验收项）

### 阶段 0 · 骨架
- 仓库结构、`pyproject.toml` + `uv.lock`、`config.py`、SQLite schema、FastAPI 应用装配、`GET /api/v1/health` 返回 200 与 `{status, version, tts, parser_version}`。
- **验收**：`uvicorn lector.web:app` 起得来；`pytest` 有骨架用例通过；`curl /api/v1/health` 返回预期 JSON。

### 阶段 1 · EPUB 解析器
- container → OPF → spine → manifest → nav/NCX → XHTML → 块 → 句。
- 安全净化与 zip-slip 防护到位。
- **验收**：
  - 用 2 个真实 EPUB（含 EPUB3 nav 与 EPUB2 NCX 各一）解析出正确的标题/作者/章节目录/句子数；
  - 句子切分单测覆盖：中英混排、小数点、缩写、引号收尾、省略号；
  - 恶意 EPUB（`../../etc/passwd` 条目、`<script>`、`<a href="javascript:...">`）被拒或净化，测试断言通过。

### 阶段 2 · 书籍 API 与数据层
- `books` / `chapters` / `toc` / `cover` 端点与 Pydantic DTO 落地。
- 上传按 sha256 去重（同文件二次上传返回既有记录，状态 200 而非 201）。
- **验收**：上传→列表→取章节的端到端用例通过；契约文档里的每个端点都有对应测试。

### 阶段 3 · TTS 与音频缓存
- `edge-tts` 引擎、句砖缓存、`voices` 列表、按需合成、章节时间线。
- **验收**：同一句砖二次请求命中缓存（不重复合成）；合成结果带词边界；引擎不可用时返回 503 且错误信息可读。

### 阶段 4 · 网页阅读端
- 书架、目录抽屉、阅读列、设置（字号/主题/行距）、搜索。
- **验收**：上传一本 EPUB 后可在网页读完任意一章；刷新后位置不丢；键盘映射与界面规格一致。

### 阶段 5 · 网页听书端
- 听书条、句砖播放器（预载下一砖）、逐词高亮、可点句定位。
- **验收**：点句→该句播放且高亮落到该句词上；播放中逐词点亮；手风琴式无明显断音；跳句/跳章不崩。

### 阶段 6 · 进度与短码
- 各端在自己这边记位置与阅读选项（网页 localStorage，终端本地缓存文件）、
  `GET /api/v1/s/{code}` 短码解析。
- **验收**：网页读到 A 处，刷新后仍在 A；终端读到 B 处，重启后仍在 B；
  两端的 A 与 B 互不影响；短码可解析回 (book, chapter, sentence)。

### 阶段 7 · 终端端
- 书架/阅读/听书三屏，键盘全覆盖，音频后端多平台回退（`afplay`/`ffplay`/`aplay`/`mpv`）。
- **验收**：终端可读、可听、逐词高亮；本机进度重启后可恢复，且不影响网页端。

### 阶段 8 · 打磨
- 三套主题、暗色下的对比度、窄屏适配、空态/加载态/错误态、README。
- **验收**：`pytest` 全绿；网页端在 375px 宽可读；键盘可完成"打开书→跳章→听→定位"的完整闭环。

## 8. 完成定义（DoD）

一个阶段算完成，当且仅当：

1. 该阶段验收项全部通过；
2. 新增行为有对应测试（解析、切分、游标编解码、API 契约各一层）；
3. 契约文档与实现一致（端点/字段/错误码改动同步更新 `docs/API.md`）；
4. 无新增未列入白名单的依赖；
5. `pytest -q` 全绿。

## 9. 边界（本期不做）

- 多用户账号体系、社交、书评、书城、推荐、支付、云端同步（本地 SQLite 已是单一事实来源）；
- 除 EPUB 外的格式（PDF/MOBI/AZW3/FB2）；
- PDF、DOCX、网页链接转 EPUB；
- 移动端原生 App；
- 商业 TTS（微软 Azure / Google / OpenAI）——引擎接口已留好扩展点，本期不接；
- 音频变速以外的 DSP（响度归一化、降噪）。

## 10. 开工第一条指令（给 agent）

```
读 /Users/thj/github/navydev.top_book/AGENTS.md 与 PROMPT.md，然后从「阶段 0 · 骨架」开始执行。
每完成一个阶段，先跑该阶段验收项，再在回复里给出：改了哪些文件、验收项逐条结论、命令输出。
遇到 PROMPT.md 与 docs/API.md、docs/UI.md 冲突时，以 docs/ 下的契约为准，并同步修正 PROMPT.md。
```
