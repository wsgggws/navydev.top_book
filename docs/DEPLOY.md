# 部署上线

`navydev.top_ebook`（应用名仍是 Lector）线上挂在
`https://navydev.top/ebook`。生产环境使用 Docker Compose，不使用 systemd。

- 本地开发：`uv run lector-server`，默认 `127.0.0.1:8000`
- 线上生产：容器只监听宿主机 `127.0.0.1:8010`，由中央 nginx 转发 `/ebook`
- 持久数据：Docker 命名卷 `navydev-top-ebook-data`

## 1. 服务器准备

服务器需要：

- Docker Engine
- Docker Compose v2（`docker compose version` 必须可用）
- SSH 用户可以执行 Docker，不需要 root 登录或 systemd
- 已由 `nginx-config` 配好 `navydev.top` 证书与 `/ebook` 反向代理

服务器**不需要**单独安装 Python、uv，也不需要创建系统用户。

## 2. GitHub Actions Secrets

在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 添加：

| Secret | 内容 |
| --- | --- |
| `REMOTE_IP` | 服务器 IP 或域名 |
| `SSH_USER` | 部署用的 SSH 用户 |
| `SSH_PRIVATE_KEY` | 该用户对应私钥文件的**完整内容** |

线上服务默认不配置 `LECTOR_TOKEN`。阅读、搜索和终端访问公开；上传、删除、
音频预热/清理等管理写接口在公网 Host 下禁用，书籍通过仓库的 `books/` 发布。

`SSH_PRIVATE_KEY` 不是 `.pub` 公钥。要复制私钥文件的完整内容，包括：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

推荐单独创建一把无口令部署密钥：

```bash
ssh-keygen -t ed25519 \
  -C "github-actions@navydev.top_ebook" \
  -f ~/.ssh/navydev_top_ebook_deploy \
  -N ""

ssh-copy-id -i ~/.ssh/navydev_top_ebook_deploy.pub user@server

gh secret set SSH_PRIVATE_KEY < ~/.ssh/navydev_top_ebook_deploy
gh secret set REMOTE_IP --body "server-ip"
gh secret set SSH_USER --body "user"
```

私钥文件权限应为 600：

```bash
chmod 600 ~/.ssh/navydev_top_ebook_deploy
```

## 3. GitHub Actions CI

`.github/workflows/ci.yml` 在 push 到 `main` 和 Pull Request 时运行：

1. 固定 Python 3.12；
2. `pip install uv`；
3. 根项目 `uv sync --frozen` 并运行服务端测试；
4. `terminal/` 独立 `uv sync --frozen` 并运行终端测试。

两个项目仍然各有自己的 `pyproject.toml` 与 `uv.lock`。

## 4. GitHub Actions CD

`.github/workflows/deploy.yml` 在以下情况发布：

- push 到 `main`
- push `v*.*.*` tag
- 手动 `workflow_dispatch`

发布流程：

1. 在 GitHub runner 重跑服务端与终端测试；
2. 打包源码、`books/*.epub`、`Dockerfile`、`docker-compose.yml` 和 `Makefile`；
3. 通过 SCP 上传到 `~/deploy/navydev.top_ebook-staging-<sha>/`；
4. 在服务器解包到 `~/deploy/navydev.top_ebook/releases/<sha>/`；
5. 在 GitHub runner 构建 `linux/amd64` 镜像并推送到 GHCR；
6. 写入权限为 600 的 `.env`；
7. 从国内 GHCR 镜像站拉取并启动镜像（`ghcr.nju.edu.cn`）；
8. 轮询 `http://127.0.0.1:8010/ebook/api/v1/health`；
9. 健康检查通过后切换 `~/deploy/navydev.top_ebook/current`；
10. 失败则用上一个 release 的镜像标签重新启动并回滚。

从 `navydev.top_book` 改名后第一次发布时，工作流会停掉旧容器、把
`navydev-top-book-data` 数据卷复制到 `navydev-top-ebook-data`，确认新容器健康后再
删除旧容器；旧数据卷会保留作备份。迁移失败则自动恢复旧容器。

服务端不需要 uv：依赖在 Docker 构建阶段由镜像内的 uv 按 `uv.lock` 安装。

`.env` 内容只有运行时配置，例如：

```dotenv
LECTOR_TTS_ENGINE=edge
LECTOR_IMAGE=ghcr.nju.edu.cn/wsgggws/navydev.top_ebook:<git-sha>
```

`LECTOR_DATA_DIR=/data`、监听地址和端口由 `docker-compose.yml` 固定。

## 4.1 添加书籍

网页端不提供上传入口。添加书籍只需要把 EPUB 放进仓库：

```bash
cp ~/Downloads/new-book.epub books/
git add books/new-book.epub
git commit -m "book: add new-book"
git push origin main
```

新镜像启动时会把 `books/*.epub` 自动导入命名卷；已导入的内容按 SHA-256 去重，
重复部署不会产生重复书籍。

## 5. Docker Compose

生产服务定义：

```yaml
services:
  lector:
    image: ghcr.nju.edu.cn/wsgggws/navydev.top_ebook:<git-sha>
    container_name: navydev-top-ebook
    restart: unless-stopped
    ports:
      - "127.0.0.1:8010:8010"
    volumes:
      - lector_data:/data
```

固定命名卷：

```text
navydev-top-ebook-data
```

`make docker-stop` 只停止容器，不会删除这个卷。

## 6. 常用运维

```bash
cd ~/deploy/navydev.top_ebook/current

make docker-status
make docker-logs
make docker-release

curl -fsS http://127.0.0.1:8010/ebook/api/v1/health
readlink -f ~/deploy/navydev.top_ebook/current
```

回滚到上一个 release：

```bash
cd ~/deploy/navydev.top_ebook
PREV="$(readlink -f current)"
ls -1dt releases/*

cd releases/<旧-sha>
make docker-release
ln -sfn "$PWD" ../current.next
mv -Tf ../current.next ../current
```

## 7. 数据备份

数据库、EPUB 和音频缓存都在命名卷里。在线备份：

```bash
mkdir -p ~/backups
docker run --rm \
  -v navydev-top-ebook-data:/data:ro \
  -v "$HOME/backups:/backup" \
  alpine \
  tar -czf "/backup/lector-$(date +%F).tgz" -C /data .
```

恢复前先停止容器：

```bash
cd ~/deploy/navydev.top_ebook/current
make docker-stop
```

不要把命名卷当作临时缓存：`lector.db`、书库和音频缓存都在里面。

## 8. nginx

站点配置的唯一事实来源是同级仓库 `../nginx-config` 的
`config/nginx/conf.d/navydev-top.conf`：

```nginx
upstream ebook_app {
    server 127.0.0.1:8010;
    keepalive 32;
}

location = /ebook {
    # LECTOR_BASE_PATH=/ebook，代理时不能剥掉前缀。
    proxy_pass http://ebook_app;
    proxy_read_timeout 120s;
}

location /ebook/ {
    proxy_pass http://ebook_app;
}
```

HTTP/2 使用 nginx 1.18 支持的 `listen 443 ssl http2;`。音频与上传接口有单独的
较长超时；静态 CSS/JS 在 nginx 层缓存。

## 9. 终端连接线上服务

终端只读，不提供上传、删除或缓存管理入口：

```bash
cd terminal
uv sync
LECTOR_URL=https://navydev.top/ebook \
uv run lector
```

终端自己的阅读位置保存在 `~/.config/lector/progress.json`，与网页端
`localStorage` 完全独立。

## 10. 注意事项

- 阅读接口公开；线上未配置 `LECTOR_TOKEN` 时管理写接口禁用，书籍通过仓库发布。
- 上传上限 50MB，nginx 的 `client_max_body_size` 要留出余量。
- 音频 URL 的内容由文本、音色、倍速与引擎版本共同决定，可长期缓存。
- 换音色后不必手工删旧文件；缓存键变了，旧缓存只是不再命中。
- 不要使用 `docker compose down -v`，`-v` 会删除 `navydev-top-ebook-data`。
