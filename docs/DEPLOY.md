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

## 5.1 音频缓存容量

`LECTOR_AUDIO_CACHE_BYTES` 设置共享音频文件和词边界元数据的容量上限，单位为字节，
默认 **10 GiB（10737418240 字节）**，用于保留听书预缓存。未设置、非法或非正数使用默认值。
容量适用于内置单进程部署；启动时按文件时间裁剪，运行中按最近使用顺序淘汰缓存对，
同时移除相应音频就绪记录；后续播放被淘汰的句子时会重新合成。调低上限并重启会淘汰
超出容量的旧音频，书籍和阅读位置不受影响。

本地运行可直接传入环境变量：

```bash
LECTOR_AUDIO_CACHE_BYTES=10737418240 uv run lector-server
```

Docker 部署需将变量传入容器；仅在 Compose 的 `.env` 写入变量不会自动注入应用。
需要覆盖默认值时，在部署使用的 Compose `lector.environment` 中转发：

```yaml
services:
  lector:
    environment:
      LECTOR_AUDIO_CACHE_BYTES: ${LECTOR_AUDIO_CACHE_BYTES:-10737418240}
```

然后在部署 `.env` 中设置 `LECTOR_AUDIO_CACHE_BYTES=<正整数字节数>`，并重建容器。

## 5.2 nginx 到容器的受信代理链

宿主机 nginx 的 HTTPS 请求通过 `127.0.0.1:8010` 转发到容器。容器看到的 TCP
对端通常是 Docker bridge 网关，而不是 `127.0.0.1`。如果沿用 Uvicorn 仅信任
`127.0.0.1` 的默认值，`X-Forwarded-Proto: https` 不会生效，同源校验会把正常的
HTTPS `POST /open` 拒绝为 403，限流也会把所有用户合并到网关 IP。

本仓库的 Compose 将 `lector` 单独连接到项目专属的 `lector_proxy` bridge：

| 项目 | 默认值 |
| --- | --- |
| `LECTOR_PROXY_SUBNET`（专属网段） | `172.30.81.0/24` |
| `LECTOR_PROXY_GATEWAY`（网关） | `172.30.81.1` |
| 发布地址 | `127.0.0.1:8010:8010`，仅宿主机回环 |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1,172.30.81.1/32` |

Uvicorn 从环境变量读取受信列表。只有连接对端匹配该列表时，才接受代理给出的
`X-Forwarded-Proto` 和 `X-Forwarded-For`；应用的同源检查和限流使用处理后的
scheme 与客户端地址，不直接解释转发头。默认只信任固定网关 `/32`，不信任整个
Docker 子网或全部 RFC1918 私网；同网段的其他容器也不自动获得代理信任。
该网络不设为 external，不应接入其他服务；保留当前仅回环发布端口的限制。

上线前确认默认网段不与宿主机路由或已有 Docker 网络冲突。如有冲突，只需在
Compose 的 `.env` 中覆盖以下两个值，无需修改 YAML；网关必须位于所选子网内：

```dotenv
LECTOR_PROXY_SUBNET=172.24.8.0/24
LECTOR_PROXY_GATEWAY=172.24.8.1
```

未显式设置 `FORWARDED_ALLOW_IPS` 时，默认受信列表会自动引用同一个
`LECTOR_PROXY_GATEWAY`，上例得到 `127.0.0.1,::1,172.24.8.1/32`。
如确需单独指定受信代理，仍可显式覆盖：

```dotenv
FORWARDED_ALLOW_IPS=127.0.0.1,::1,172.24.8.1/32
```

显式覆盖值会替换默认列表，不再自动跟随网关；必须填写容器实际看到的受信代理
地址，不能使用 `*`。更改已有网络的 subnet/gateway 时，需要重建 Compose 网络和容器，
可执行 `docker compose down`（不带 `-v`）后重新启动。
命名数据卷保持不变，无需删除数据卷，也无需修改兄弟 nginx 项目。

现有 nginx 必须覆盖 `X-Forwarded-Proto` 为实际 `$scheme`，并通过
`$proxy_add_x_forwarded_for` 把实际连接客户端追加到 XFF 右侧。Uvicorn 从右向左跳过
已知代理，选取第一个不受信地址作为客户端；例如攻击者伪造前缀后得到
`198.51.100.8, 203.0.113.9`，限流仍归于实际客户端 `203.0.113.9`。不受信的直接
连接即使提供 XFP/XFF，也不能改变 scheme 或客户端身份。

部署后检查：

```bash
docker compose config
docker inspect navydev-top-ebook --format '{{json .NetworkSettings.Networks}}'
docker compose exec -T lector printenv FORWARDED_ALLOW_IPS
```

最终通过 HTTPS 网页打开书籍，确认 `POST /ebook/api/v1/books/{id}/open` 返回 200。
仓库的 `tests/test_proxy_deployment.py` 通过实际 Uvicorn 配置及代理中间件覆盖该链路、
不受信连接、伪造 XFF 前缀与不同客户端的独立限流。

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
