# Lector API 契约 v1

> 规范性文档。实现与本文件不一致时，以本文件为准并同步修改实现。
> 配套：[界面规格](UI.md)、[主构建提示词](../PROMPT.md)、[仓库指令](../AGENTS.md)

## 0. 约定

| 项 | 值 |
| --- | --- |
| Base URL | `/api/v1` |
| 内容类型 | 请求与响应均为 `application/json; charset=utf-8`，**除**文件上传与二进制下载 |
| 字段命名 | `snake_case` |
| 时间 | ISO-8601 UTC，字符串形式 `2026-10-24T08:00:00Z` |
| 时长 | 数值，**秒**（float）。`duration_ms` 除外，仅在需要毫秒精度时使用 |
| ID | 字符串。`book_id` 形如 `b_9f3a2c1d`；章节 `c{index}`；块 `c12.b3`；句 `c12.b3.s0` |
| 鉴权 | 阅读接口公开。上传、删除、预热/清理音频等管理写操作在配置 `LECTOR_TOKEN` 后要求 `Authorization: Bearer <token>` |
| 分页 | 列表接口用 `?limit=&offset=`，`limit` 默认 50、上限 200 |
| 排序 | 列表默认按 `updated_at DESC`；不接受客户端自定义排序参数 |

### 0.1 成功响应

统一返回资源对象本身，不套 `{data: ...}` 外壳。列表接口直接返回**裸数组**。

### 0.2 错误响应

所有非 2xx 响应使用同一信封：

```json
{
  "error": {
    "code": "EPUB_INVALID",
    "message": "EPUB 结构不完整：缺少 OPF 文件",
    "detail": { "missing": "META-INF/container.xml" }
  }
}
```

- `code`：**稳定标识**，机器可判分支。客户端逻辑只依赖 `code`，不解析 `message`。
- `message`：人类可读的简短说明（中文），可直接展示。
- `detail`：可选对象，承载参数级上下文。

### 0.3 错误码表

| HTTP | `code` | 含义 | 客户端应对 |
| --- | --- | --- | --- |
| 400 | `BAD_REQUEST` | 请求体无法解析或参数非法 | 展示 `message`，不重试 |
| 401 | `UNAUTHORIZED` | 管理写操作缺少或错误的 Bearer token | 只在管理操作时提示 token |
| 403 | `FORBIDDEN` | 令牌有效但权限不够（如 reader 令牌想上传） | 换个权限更高的令牌 |
| 404 | `NOT_FOUND` | 资源不存在 | 返回书架 |
| 409 | `ALREADY_EXISTS` | 冲突（如书名重复上传且策略为拒绝） | 提示并引导到既有条目 |
| 413 | `PAYLOAD_TOO_LARGE` | 上传超过 50MB | 提示改用小文件 |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 不是 epub / zip | 提示格式 |
| 422 | `EPUB_INVALID` | epub 结构损坏或不受支持 | 展示 `message`，可查看 `detail` |
| 422 | `VALIDATION_ERROR` | 字段校验失败 | 逐字段展示 `detail` |
| 429 | `RATE_LIMITED` | 请求过频 | 按 `Retry-After` 退避 |
| 500 | `INTERNAL_ERROR` | 服务端异常 | 展示通用文案，附 `request_id` |
| 503 | `TTS_UNAVAILABLE` | TTS 引擎不可用或正在冷启动 | 降级为纯阅读模式，提示重试 |
| 504 | `TTS_TIMEOUT` | 单句合成超时 | 该句标记失败，其余可读 |

### 0.4 线上部署与终端接入

书籍、章节、搜索、封面、音频等阅读接口**不需要令牌**，任何人都可以访问。
`LECTOR_TOKEN` 只用于管理写操作；生产环境仍建议配置，防止上传、删除或清缓存。

```bash
# 服务端
export LECTOR_TOKEN="$(openssl rand -hex 24)"
export LECTOR_HOST=127.0.0.1        # 交给反向代理，不直接暴露
export LECTOR_PORT=8000
uv run lector-server
```

推荐在前面放一层反向代理（Caddy / nginx）负责 TLS，服务只监听回环地址：

```
终端 ──https──▶ 反向代理 ──http──▶ lector.web:app (127.0.0.1:8000)
```

终端端只读书，不需要令牌：

```bash
# 一次性：环境变量
LECTOR_URL=https://navydev.top/book uv run lector

# 或者在书架屏按 c 交互式填写，之后记在 ~/.config/lector/reader.json
uv run lector
```

`GET /api/v1/health` 不需要令牌，可用来探测服务是否活着。

### 0.6 限流

按客户端 IP：上传接口 10 次/分钟，其余读接口 600 次/分钟。超限返回 429 与 `Retry-After`（秒）。写接口命中限流时**不做**自动重试。

---

## 1. 核心模型

### 1.1 Book

```json
{
  "book_id": "b_9f3a2c1d",
  "title": "小王子",
  "author": "安托万·德·圣埃克苏佩里",
  "language": "zh-CN",
  "sha256": "3f2a...（64 位十六进制，全书内容指纹）",
  "size_bytes": 412233,
  "cover_url": "/api/v1/books/b_9f3a2c1d/cover",
  "chapter_count": 27,
  "sentence_count": 8421,
  "progress": 0.423,
  "tts_state": "ready",
  "created_at": "2026-10-24T08:00:00Z",
  "updated_at": "2026-10-24T08:12:33Z"
}
```

`tts_state` 取值：

| 值 | 含义 |
| --- | --- |
| `pending` | 尚未生成任何音频 |
| `partial` | 已生成部分章节（比例见 `tts_ratio`） |
| `ready` | 全书音频就绪 |
| `failed` | 引擎持续失败，可重试 |

`cover_url` 在无封面时为 `null`。

- `progress` 是这本书自己的阅读进度（`[0, 1]`），按字数加权。**每本书各记各的**，
  进度存在服务端，与浏览器无关；换设备打开同一本书会接着上次的位置读。

### 1.2 Chapter

```json
{
  "chapter_id": "c12",
  "index": 12,
  "title": "第三章 星辰",
  "blocks": [ /* Block[]，见 1.3 */ ],
  "sentence_count": 312,
  "word_count": 4820,
  "audio_duration": 1912.4,
  "tts_state": "ready"
}
```

### 1.3 Block 与 Sentence

```json
{
  "type": "p",
  "id": "c12.b3",
  "sentences": [
    { "id": "c12.b3.s0", "text": "他把玫瑰留在原处。", "char_start": 0, "char_end": 9 }
  ]
}
```

- `type` ∈ `p` `h1`…`h6` `li` `blockquote` `img` `hr` `pre`。
- `char_start` / `char_end` 是**该句在所属 block 纯文本中的字符区间**（半开区间 `[start, end)`），用于在块内定位。
- `img` 块的 `sentences` 为空数组，额外带 `alt` 与 `src`。`src` 是该图片在 EPUB 压缩包内的路径（相对 zip 根，如 `OEBPS/html/images/f1.jpg`），取值时拼在 `/api/v1/books/{book_id}/media/` 之后。
- 块可带 `anchor`（字符串或 `null`）：EPUB 内部 `<a name>`/`<a id>` 的锚点，供目录节点定位到章内小节。
- 块可带 `anchors`（字符串数组，默认 `[]`）：该块内**全部**锚点。一个段落里可能落着多个 `<a id>`，只给一个 `anchor` 时客户端将无法定位到后面的那些，因此 `anchor` 始终等于 `anchors[0]`，其余锚点在 `anchors` 里。
- `id` 全书唯一且稳定；同一 EPUB 重复解析必须得到相同 id。

### 1.4 Cursor（位置游标）

全书唯一的位置表示，跨端、跨模式通用：

```json
{ "book_id": "b_9f3a2c1d", "chapter_id": "c12", "sentence_id": "c12.b3.s0", "word_index": 4 }
```

- `word_index` 为句子内的词下标；`null` 表示句级粒度（未开启逐词同步时）。
- `sentence_id` 隐含 `chapter_id` 与块位置，冗余携带是为便于日志排查。

---

## 2. 系统

### `GET /api/v1/health`

无需鉴权。

```json
{
  "status": "ok",
  "version": "1.0.0",
  "parser_version": 1,
  "tts": { "engine": "edge", "available": true, "voice_count": 218 },
  "books": 12
}
```

`status` ∈ `ok` | `degraded`（TTS 不可用但读功能正常） | `error`。

### `GET /api/v1/meta`

构建信息与默认音色，给客户端做初始化用。公开接口，不需要令牌。

```json
{
  "version": "1.0.0",
  "parser_version": 1,
  "default_voice": "zh-CN-YunxiNeural",
  "featured_voices": ["zh-CN-YunxiNeural", "en-US-GuyNeural"],
  "default_voices": { "zh": "zh-CN-YunxiNeural", "en": "en-US-GuyNeural" },
  "default_rates": { "zh": "+0%", "en": "-8%" },
  "scope": "admin"
}
```

- `scope` 是这个令牌拿到的权限：`admin` 或 `reader`。

- `featured_voices` 是**界面上应当提供的常用音色**：中文（zh-CN）、美式（en-US）、英式（en-GB）各若干。引擎本身还有三百多个音色，`/tts/voices` 全部返回，客户端按需自选。
- `default_voices` 是**按语言分的默认音色**：中文书用中文男声，英文书用美式男声。客户端不要自己猜，按这份表来。
- `default_rates` 是 TTS 基础语速：中文 `+0%`，英文 `-8%`。界面上的 1.0×
  指各自的基础语速；0.75×–2.0× 再叠加在基础语速之上。

### `GET /api/v1/tts/voices`

```json
{
  "engine": "edge",
  "voices": [
    { "voice_id": "zh-CN-YunxiNeural", "name": "云希", "locale": "zh-CN", "gender": "male", "engine": "edge" }
  ]
}
```

按 `locale` 与 `name` 升序。客户端应把 `voice_id` 原样回传。

---

## 3. 书籍

### `POST /api/v1/books`

上传 EPUB，仅用于管理。`multipart/form-data`，需要 admin 令牌。普通书架内容通过
仓库的 `books/*.epub` 在服务启动时自动导入，网页不提供上传入口。字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | `.epub` 文件 |
| `title` | string | 否 | 覆盖 EPUB 内元数据标题 |
| `author` | string | 否 | 覆盖 EPUB 内作者 |
| `voice_id` | string | 否 | 该书默认音色 |

**响应 `201`**（新建）或 `200`（同内容已存在，见幂等）：

```json
{ "book": { /* Book */ }, "duplicate": false }
```

- **幂等**：以 `sha256` 去重。同文件再次上传返回 `200` + 既有记录 + `"duplicate": true`，**不重复解析**，不产生新 `book_id`。
- **大小限制**：50MB。超限 `413`。
- **格式校验**：文件须为 ZIP 容器且含 `META-INF/container.xml`。不满足 → `415`（非 zip）或 `422`（结构损坏）。
- **安全**：解压时拒绝 `..` 路径穿越条目、拒绝符号链接条目、限制解压膨胀比（压缩炸弹防护）。任一命中 → `422`。
- **解析耗时**：目标 < 2s（万字级）。超过 10s 视为失败 → `422`。

### `GET /api/v1/books`

裸数组，`Book[]`。支持 `?limit=&offset=`。

### `GET /api/v1/books/{book_id}`

```json
{ "book": { /* Book */ }, "progress": { /* Progress，见 5.1 */ } }
```

### `DELETE /api/v1/books/{book_id}`

删除书籍、其解析产物与音频缓存。需要 admin 令牌。返回 `204`。不存在时 `404`。

### `GET /api/v1/books/{book_id}/cover`

二进制图片（`image/jpeg` 或 `image/png`），`Cache-Control: public, max-age=31536000, immutable`。无封面 `404`。

### `GET /api/v1/books/{book_id}/media/{path}`

取书内图片。`{path}` 是章节内容里 `img` 块的 `src`（去掉前导 `/`）。

- 返回二进制图片，类型与 EPUB 内一致。
- `Cache-Control: public, max-age=31536000, immutable`。
- 路径被规范化后若越出压缩包，返回 `404`。
- 资源不存在返回 `404`。

### `GET /api/v1/books/{book_id}/toc`

```json
{
  "toc": [
    {
      "id": "c12",
      "title": "第三章 星辰",
      "chapter_id": "c12",
      "anchor": null,
      "children": [
        { "id": "c12.1", "title": "一", "chapter_id": "c12", "anchor": "s3", "children": [] }
      ]
    }
  ]
}
```

- `id` 是**目录节点**的 id，唯一即可，不承担定位职责。
- `chapter_id` 是该节点**实际所在的章节**，必定是一个可被 `GET /books/{id}/chapters/{chapter_id}` 取到的章节。
- `anchor` 是章节内的锚点（EPUB 里的 `#id`），可空。定位时：取该章节 → 找到带此 anchor 的块 → 把游标移到该块第一句。
- `children` 递归，最多 3 层；更深层级被压平到第 3 层。

**定位一个目录节点的完整动作**：`chapter_id` → 取章节 → 按 `anchor` 找到块 → 游标落到 `块的第一句`。客户端不应直接用 `id` 去请求章节端点。

### `GET /api/v1/books/{book_id}/chapters/{chapter_id}`

返回完整章节内容：

```json
{
  "chapter": { "chapter_id": "c12", "index": 12, "title": "第三章 星辰", "blocks": [ /* Block[] */ ], "sentence_count": 312, "word_count": 4820, "audio_duration": 1912.4, "tts_state": "ready" },
  "prev_chapter_id": "c11",
  "next_chapter_id": "c13"
}
```

`prev_chapter_id` / `next_chapter_id` 在首尾为 `null`。

### `GET /api/v1/books/{book_id}/chapters/{chapter_id}/timeline`

该章的**音频时间线**，听书模式的唯一数据源：

```json
{
  "chapter_id": "c12",
  "duration": 1912.4,
  "sentences": [
    { "sentence_id": "c12.b3.s0", "start": 0.0, "end": 2.8, "audio_url": "/api/v1/books/b_9f3a2c1d/audio/c12.b3.s0.mp3", "word_count": 7 }
  ]
}
```

- `start` / `end` 为**章内相对秒数**，已包含句间停顿。
- 句子未合成时该条目**被省略**（不是 null），保证数组可直接顺序播放。
- 全部未合成时返回 `200` + 空数组 + `tts_state` 字段为 `pending`。

---

## 4. 音频

### `GET /api/v1/books/{book_id}/audio/{sentence_id}.mp3`

返回该句的 MP3 二进制。

可选查询参数：

| 参数 | 说明 |
| --- | --- |
| `voice_id` | 用哪个音色合成。缺省按该书的语言定（见 `default_voices`） |
| `rate` | 合成语速，如 `+10%`。缺省 `+0%` |

- `Content-Type: audio/mpeg`
- `Content-Length` 必填（客户端据此预载下一句）
- `Cache-Control: public, max-age=31536000, immutable`（URL 含内容哈希，天然不可变）
- **首次请求触发合成**，可能耗时 0.3–3s；服务端须在 8s 内返回，否则 `504`
- 该句合成失败时返回 `503`，`error.code = "TTS_UNAVAILABLE"`
- 音频不存在时 `404`

### `GET /api/v1/books/{book_id}/audio/{sentence_id}.words`

该句的**词边界**，逐词高亮的数据源。查询参数与上面的 MP3 端点相同
（`voice_id`、`rate`），两者必须一致，否则拿到的词边界对不上音频。

```json
{
  "sentence_id": "c12.b3.s0",
  "duration": 2.8,
  "words": [
    { "text": "他", "start": 0.0, "end": 0.32 },
    { "text": "把", "start": 0.32, "end": 0.58 }
  ],
  "granularity": "word"
}
```

- `granularity` ∈ `word`（引擎提供词边界） | `sentence`（回退引擎，只定位到句）。
- 词边界为句内相对秒数，浮点，保留 3 位小数。

### `POST /api/v1/books/{book_id}/audio/warm`

批量预合成，请求：

```json
{ "chapter_id": "c12", "voice_id": "zh-CN-YunxiNeural", "rate": "+0%", "limit": 12 }
```

- `chapter_id` 为 `null` 表示全书。
- `limit` 可选：一次最多预热多少句。客户端用它把预热拆成小段，
  免得一个请求挂上好几分钟。
- 同步执行，返回：

```json
{ "queued": 312, "ready": 298, "failed": 14, "state": "partial" }
```

- 建议客户端在后台调用，不阻塞阅读。**这个调用会一直占用连接**：每句合成约 1–3 秒，一章几十句就是几分钟；整书预热可能以小时计。客户端应当在后台发起，不要等待它返回。
- 引擎偶发卡顿时服务端会对该句重试一次；仍失败则计入 `failed`，不影响其余句子。

### `DELETE /api/v1/books/{book_id}/audio`

清空该书全部音频缓存。返回 `204`。用于换音色后重来。

---

## 5. 进度（可选）

> **内置客户端不用这一节。** 网页端与终端端各自在本地记阅读位置
> （网页 localStorage，终端本地缓存文件），互不干扰。这里的接口留给需要
> 跨端同步的第三方客户端，或者只是想拿到"按字数加权的百分比"的场景。

### 5.1 Progress

```json
{
  "book_id": "b_9f3a2c1d",
  "cursor": { "chapter_id": "c12", "sentence_id": "c12.b3.s0", "word_index": 4 },
  "percent": 0.423,
  "updated_at": "2026-10-24T08:12:33Z",
  "updated_by": "web",
  "device_label": "MacBook Pro"
}
```

- `percent` ∈ `[0, 1]`，全书进度（按字数加权）。
- `updated_by` ∈ `web` | `terminal` | `api`。客户端通过请求头 `X-Lector-Client: web|terminal|api` 声明身份，缺省为 `api`。
- `device_label` 供"另一台设备正在读第 X 页"提示，可为空。

### `GET /api/v1/books/{book_id}/progress`

返回 `Progress`。无记录时返回 `200` + `{"cursor": null, "percent": 0.0}`，**不是 404**（读取空进度是正常状态）。

### `PUT /api/v1/books/{book_id}/progress`

请求：

```json
{ "chapter_id": "c12", "sentence_id": "c12.b3.s0", "word_index": 4, "device_label": "MacBook Pro" }
```

- `sentence_id` 必须属于 `chapter_id`，否则 `422 VALIDATION_ERROR`。
- **写入策略**：`updated_at` 较新者胜；服务端返回写入后的 `Progress`。
- 写入应**防抖**：客户端在同一位置反复写入时，服务端接受但不打乱 `updated_at` 序（同一秒内的重复写视为同一次）。
- 响应 `200` + `Progress`。

### `GET /api/v1/books/{book_id}/percent`

**无状态**：给一个游标，算出全书百分比。内置客户端用它来给自己的本地进度
算百分比，服务端不记任何东西。

```
GET /api/v1/books/{book_id}/percent?chapter_id=c12&sentence_id=c12.b3.s0
```

```json
{ "percent": 0.423 }
```

- `percent` ∈ `[0, 1]`，按字数加权。
- `sentence_id` 不属于 `chapter_id` 时 `422 VALIDATION_ERROR`。

### 各端各自记位置

位置由客户端自己保存，服务端不参与：

| 端 | 存在哪 | 内容 |
| --- | --- | --- |
| 网页 | 浏览器 `localStorage`（按书分开） | 游标、百分比、音色、性别、倍速 |
| 终端 | `~/.config/lector/` 下的本地文件 | 游标、百分比、服务器地址与令牌 |

所以在终端读到哪不会把网页顶走，网页读到哪也不会影响终端。
**不做**跨端接力；需要跨端同步的话，自己用上面的 `GET`/`PUT /progress` 接。

---

## 6. 短码分享

### `POST /api/v1/s`

```json
{ "book_id": "b_9f3a2c1d", "chapter_id": "c12", "sentence_id": "c12.b3.s0", "word_index": null }
```

响应：

```json
{ "code": "K7QW2M3X", "url": "/s/K7QW2M3X" }
```

- 短码为 8 位 Crockford Base32（字符集 `0123456789ABCDEFGHJKMNPQRSTVWXYZ`，剔除易混字符 I/L/O/U）。
- 服务端存储，短码可被反查为游标。
- 同一游标重复请求返回**同一短码**（幂等），便于"分享同一处"。

### `GET /api/v1/s/{code}`

```json
{ "book_id": "b_9f3a2c1d", "chapter_id": "c12", "sentence_id": "c12.b3.s0", "word_index": null }
```

未知或过期短码 → `404`。

---

## 7. 搜索

### `GET /api/v1/books/{book_id}/search?q={query}&limit=50`

```json
{
  "query": "玫瑰",
  "total": 12,
  "results": [
    {
      "sentence_id": "c12.b3.s0",
      "chapter_id": "c12",
      "chapter_title": "第三章 星辰",
      "snippet": "…他把<em>玫瑰</em>留在原处…",
      "before": "…",
      "after": "…"
    }
  ]
}
```

- `snippet` 含 `<em>` 高亮标记；`before` / `after` 为纯文本上下文，各不超过 40 字。
- 结果按出现顺序（章节序、句序）排列。
- `q` 为空 → `400`。

---

## 8. 终端端用到的接口

终端端复用同一套 API，仅额外依赖：

| 用途 | 接口 |
| --- | --- |
| 拉书架 | `GET /api/v1/books` |
| 拉章节 | `GET /api/v1/books/{id}/chapters/{cid}` |
| 拉时间线 | `GET /api/v1/books/{id}/chapters/{cid}/timeline` |
| 拉音频 | `GET /api/v1/books/{id}/audio/{sid}.mp3` |
| 拉词边界 | `GET /api/v1/books/{id}/audio/{sid}.words` |

终端端不写服务端书库，也不需要令牌。它**不做**流式播放：下载整句 MP3 到临时文件
再交给系统播放器（`afplay`/`ffplay`/`aplay`），换取逐词高亮的精确控制。

---

## 9. 变更规则

- 本文件是 API 的**单一事实来源**。新增端点、改字段、改错误码，先改本文件再改实现。
- **向后兼容**：删除字段、改变字段类型、改变语义 → 必须升 `v2` 或提供迁移。
- 新增可选字段、新增端点 → 可在 `v1` 内完成。
- DTO 的 Pydantic 模型（`lector/models.py`）必须与本文件逐字段对应，字段名不设别名。
