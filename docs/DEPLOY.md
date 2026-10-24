# 部署上线

`navydev.top_book`（应用名仍是 Lector）是一个 Python 进程 + SQLite + 数据目录，
线上挂在 `https://navydev.top/book/`。仓库提供两条部署路径：

- 本地开发：`uv run lector-server`，默认 `127.0.0.1:8000`。
- 线上生产：GitHub Actions 测试后发布到 `/opt/navydev.top_book`，systemd 以
  `127.0.0.1:8010` 运行，中央 nginx 把 `/book/` 原样代理过去。

## 1. 本地环境

```bash
uv sync
uv run lector-server
```

浏览器打开 <http://127.0.0.1:8000/>。生产配置由
`/etc/lector/env` 提供，不写进仓库。

## 2. 数据目录

| 路径 | 内容 | 要不要备份 |
| --- | --- | --- |
| `/var/lib/lector/lector.db` | SQLite：书、进度接口数据、搜索索引、短码 | **要** |
| `/var/lib/lector/books/<id>/` | 原始 EPUB 与解析后的章节 | 可以从 EPUB 重来 |
| `/var/lib/lector/audio/` | 句级音频缓存 | 不用，丢失后会重新合成 |

备份：

```bash
sudo sqlite3 /var/lib/lector/lector.db \
  ".backup '/backup/lector-$(date +%F).db'"
```

## 3. GitHub Actions CI

`.github/workflows/ci.yml` 在每次 push 到 `main` 和 Pull Request 时运行：

1. 固定 Python 3.12；
2. `pip install uv`；
3. 根项目 `uv sync --frozen` 并运行服务端测试；
4. `terminal/` 独立 `uv sync --frozen` 并运行终端测试。

两个项目仍是独立的 `pyproject.toml` / `uv.lock`，CI 不会把终端代码装进服务端
运行时。

## 4. GitHub Actions CD

`.github/workflows/deploy.yml` 在 push 到 `main`、推送 `v*.*.*` tag，或手工触发
时发布。发布前先在同一个 workflow 里重跑两端测试。

仓库需要配置这些 Actions secrets：

| Secret | 用途 |
| --- | --- |
| `REMOTE_IP` | 服务器地址 |
| `SSH_USER` | SSH 用户 |
| `SSH_PRIVATE_KEY` | 对应私钥 |
| `LECTOR_TOKEN` | 服务端访问令牌，建议形如 `<随机值>:admin` |

服务器首次部署前需要满足：

- 已安装 `uv`，且 SSH 用户执行 `command -v uv` 能找到它；
- SSH 用户可以使用 `sudo`；
- 已由 nginx-config 配好 `navydev.top` 的证书和 `/book/` 路由；
- 如果已有 `/var/lib/lector`，保留它，发布不会清空数据。

发布过程：

1. 把 `pyproject.toml`、`uv.lock`、`lector/`、`web/` 与 systemd unit 打包；
2. 上传到 `/tmp/navydev.top_book-<sha>/`；
3. 在服务器解包到 `/opt/navydev.top_book/releases/<sha>/`；
4. 在该 release 内执行 `uv sync --frozen --no-dev`；
5. 原子切换 `/opt/navydev.top_book/current`，重启 `lector.service`；
6. 轮询 `/book/api/v1/health`，失败则切回上一个 release。

systemd 固定配置：

```ini
WorkingDirectory=/opt/navydev.top_book/current
EnvironmentFile=-/etc/lector/env
ExecStart=/opt/navydev.top_book/current/.venv/bin/lector-server
```

`/etc/lector/env` 由 workflow 以 600 权限写入：

```dotenv
LECTOR_TOKEN=<你的令牌>
LECTOR_DATA_DIR=/var/lib/lector
LECTOR_HOST=127.0.0.1
LECTOR_PORT=8010
LECTOR_BASE_PATH=/book
LECTOR_TTS_ENGINE=edge
```

## 5. nginx

站点配置的唯一事实来源是同级仓库 `../nginx-config` 的
`config/nginx/conf.d/navydev-top.conf`。关键配置：

```nginx
upstream lector_app {
    server 127.0.0.1:8010;
    keepalive 32;
}

location /book/ {
    # LECTOR_BASE_PATH=/book，代理时不能剥掉前缀。
    proxy_pass http://lector_app;
    proxy_read_timeout 120s;
}
```

HTTP/2 使用 nginx 1.18 支持的 `listen 443 ssl http2;`。音频与上传接口有单独的
较长超时；静态 CSS/JS 在 nginx 层缓存。

## 6. 终端连接线上服务

终端只读，不提供上传、删除或缓存管理入口：

```bash
cd terminal
uv sync
LECTOR_URL=https://navydev.top/book \
LECTOR_TOKEN=你的令牌 \
uv run lector
```

也可以启动后按 `c` 填地址和令牌，配置保存在
`~/.config/lector/reader.json`（权限 600）。终端自己的阅读位置保存在
`~/.config/lector/progress.json`，与网页端 `localStorage` 完全独立。

## 7. 权限分级

| 服务端配置 | 客户端发送 | 能力 |
| --- | --- | --- |
| `<token>` / `<token>:admin` | `<token>` | 读、上传、删除、预热音频、清缓存 |
| `<token>:reader` | `<token>` | 读；不能上传、删除或管理音频缓存 |

权限后缀只写在服务器 `/etc/lector/env` 中，客户端只发送密钥本身。

## 8. 手动运维

```bash
# 查看状态与日志
sudo systemctl status lector
sudo journalctl -u lector -f

# 查看当前 release 和可用版本
readlink -f /opt/navydev.top_book/current
ls -1dt /opt/navydev.top_book/releases/*

# 健康检查
curl -fsS http://127.0.0.1:8010/book/api/v1/health

# nginx 配置变更后
sudo nginx -t && sudo systemctl reload nginx
```

回滚只需把 `current` 指回上一个 release 并重启服务：

```bash
sudo ln -sfn /opt/navydev.top_book/releases/<旧-sha> \
  /opt/navydev.top_book/current.next
sudo mv -Tf /opt/navydev.top_book/current.next /opt/navydev.top_book/current
sudo systemctl restart lector
```

## 9. 注意事项

- **不要删除 `/var/lib/lector`**，书库、音频缓存和进度数据都在这里。
- `LECTOR_TOKEN` 必须配置；否则反向代理会公开一个无鉴权实例。
- 上传上限 50MB，nginx 的 `client_max_body_size` 要留出余量。
- 音频 URL 的内容由文本、音色、倍速与引擎版本共同决定，可长期缓存。
- 换音色后不必手工删旧文件；缓存键变了，旧缓存只是不再命中。
- 音频第一次可能现场合成；nginx `/book/api/v1/books/.../audio/` 的超时已放宽到
  120 秒，客户端也会提前预热下一小段。
