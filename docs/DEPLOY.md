# 部署上线

Lector 是个自托管的服务：一个 Python 进程 + 一个 SQLite + 一个数据目录。
下面是最省事也最稳的一套：uv 管依赖，systemd 管进程，Caddy 管 TLS。

## 0. 一分钟版本

```bash
# 服务器上
git clone <你的仓库> /opt/lector && cd /opt/lector
uv sync --frozen

export LECTOR_TOKEN="$(openssl rand -hex 24)"   # 记下来，两端都要用
export LECTOR_DATA_DIR=/var/lib/lector
export LECTOR_HOST=127.0.0.1                     # 只给反向代理看
export LECTOR_PORT=8000
uv run lector-server
```

浏览器打开 `http://127.0.0.1:8000` 就能用了。

> **令牌是必须的。** 没有 `LECTOR_TOKEN` 时服务端只监听 `127.0.0.1`，
> 外面访问不到；设了令牌以后 `/api/v1/*`（`/health` 除外）都要带
> `Authorization: Bearer <token>`。

## 1. 目录与数据

| 路径 | 内容 | 要不要备份 |
| --- | --- | --- |
| `$LECTOR_DATA_DIR/lector.db` | SQLite：书、进度、搜索索引、短码 | **要** |
| `$LECTOR_DATA_DIR/books/<id>/` | 原始 EPUB 与解析后的章节 | 可以从 EPUB 重来 |
| `$LECTOR_DATA_DIR/audio/` | 句砖音频缓存 | 不用（丢了会重新合成） |

真正不能丢的是 `lector.db` 里的**进度**。备份就一件事：

```bash
sqlite3 "$LECTOR_DATA_DIR/lector.db" ".backup '/backup/lector-$(date +%F).db'"
```

## 2. systemd

`deploy/lector.service`：

```ini
[Unit]
Description=Lector
After=network.target

[Service]
Type=simple
User=lector
Group=lector
WorkingDirectory=/opt/lector
Environment=LECTOR_DATA_DIR=/var/lib/lector
Environment=LECTOR_HOST=127.0.0.1
Environment=LECTOR_PORT=8000
Environment=LECTOR_TOKEN=换成你的令牌
ExecStart=/opt/lector/.venv/bin/lector-server
Restart=always
RestartSec=3

# 只需要读代码目录，数据目录可写
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/lector

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --home /opt/lector --shell /usr/sbin/nologin lector
sudo mkdir -p /var/lib/lector && sudo chown lector:lector /var/lib/lector
sudo cp deploy/lector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lector
sudo systemctl status lector
```

## 3. 反向代理与 TLS

### Caddy（最省事，自动续证书）

`deploy/Caddyfile`：

```
reader.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

### nginx

`deploy/nginx.conf`：

```nginx
server {
    listen 443 ssl http2;
    server_name reader.example.com;

    ssl_certificate     /etc/letsencrypt/live/reader.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/reader.example.com/privkey.pem;

    client_max_body_size 60m;   # 上传上限 50MB，留点余量

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # 合成音频可能慢一点
    }
}
```

## 4. 权限分级

令牌可以带权限后缀：

| 令牌 | 能做什么 |
| --- | --- |
| `<token>` 或 `<token>:admin` | 全部：读、上传、删除、预热音频、清缓存、写进度 |
| `<token>:reader` | 读 + 写自己的阅读进度（跨端接力要用），**不能**上传/删除书、不能动音频缓存 |

**终端端用 `reader` 就够了** —— 它只是读书和记下自己读到哪。

```bash
# 终端（它在自己的项目目录里，只需要 textual 一个依赖）
cd terminal && uv sync
LECTOR_URL=https://reader.example.com LECTOR_TOKEN=你的令牌:reader uv run lector
```

在终端的书架屏按 `c` 也能交互式填地址与令牌，存在 `~/.config/lector/reader.json`（权限 600）。

被拒绝的写操作会得到 `403 FORBIDDEN`；令牌不对是 `401 UNAUTHORIZED`。

## 5. 终端接线上服务

```bash
uv run lector
# 书架屏按 c → 填 https://reader.example.com 与令牌
```

终端只读，不上传也不删书；它只把自己的阅读位置推给服务器，网页端每 5 秒拉一次，
两端因此始终在同一处接着读。

## 6. 升级

```bash
cd /opt/lector
git pull
uv sync --frozen
sudo systemctl restart lector
```

数据目录不动，升级不影响书与进度。

## 7. 看着它

```bash
curl -s https://reader.example.com/api/v1/health | jq .
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "parser_version": 1,
  "tts": { "engine": "edge", "available": true, "voice_count": 322 },
  "books": 12
}
```

`status` 为 `degraded` 说明 TTS 不可用（读没问题，听不了）；为 `error` 说明
服务本身有问题。`/health` 不需要令牌，可以直接拿来做探活。

## 8. 几个要注意的地方

- **别把 `LECTOR_DATA_DIR` 放在临时盘上**，进度会丢。
- **令牌别写进仓库**，用 systemd 的 `EnvironmentFile=` 读一个 600 权限的文件更稳。
- **上传上限 50MB**（`LECTOR_MAX_UPLOAD` 可调），反向代理的 body 限制要跟着放大。
- **限流**按客户端 IP：上传 10 次/分钟，其余读接口 600 次/分钟。终端一次拖动
  不会触发限流（它只写进度）。
- **音频缓存**按内容哈希存，换音色后旧的缓存还在，只是不会被命中；要清就调
  `DELETE /api/v1/books/{id}/audio`（需要 admin 令牌）。
