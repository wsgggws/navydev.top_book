# Lector Terminal

`navydev.top/ebook` 的只读终端客户端：浏览书架、阅读、听书，不上传、不删除、
不修改服务端内容。

默认连接：

```text
https://navydev.top/ebook
```

书架顶栏：`navy's ebook (有声朗读，逐词高亮，本机续读) 书架`。

## Homebrew 安装

```bash
brew tap wsgggws/ebook https://github.com/wsgggws/navydev.top_ebook
brew install wsgggws/ebook/lector
```

装的是 **PyInstaller 独立二进制**（macOS arm64 / x86_64 自带 Python 运行时），
机器上不需要任何 Python，也不需要 pip / uv。运行时在安装时一次性解压到 Homebrew 的私有目录，启动不再重复解包。

运行：

```bash
lector
```

终端通过请求头 `X-Lector-Client: terminal` 标识自己，默认线上服务不需要
`LECTOR_TOKEN`。只有连接启用令牌的私有服务时才需要 token；如果服务端配置为
`LECTOR_TOKEN=secret:reader`，客户端应填写 `secret`（不要带权限后缀）。

```bash
lector --url https://navydev.top/ebook --token "$LECTOR_TOKEN"
lector --theme dracula
lector --check
lector --version
```

## 主题

默认 `LECTOR_THEME=auto`：

- 启动时通过 OSC 10/11/4 读取终端前景、背景与强调色，以 RGB 绘制
- 背景明暗判断支持 `COLORFGBG` 与显式环境变量覆盖
- 自动配色和选择行保持文字对比，避免 ANSI 默认色混合成黑色
- 因此会跟随 WezTerm 当前使用的 Sheepskin、Dracula、Catppuccin 等配色

无法查询背景时可用：

```bash
LECTOR_THEME_BACKGROUND=light lector
LECTOR_THEME_BACKGROUND=dark lector
```

显式主题：

```bash
LECTOR_THEME=dracula lector
LECTOR_THEME=catppuccin-mocha lector
LECTOR_THEME=catppuccin-latte lector
LECTOR_THEME=solarized-dark lector
```

运行中按 `m` 循环切换主题，选择会写入 `~/.config/lector/reader.json`。

正文在扣除目录的右侧区域居中，最大 96 列、最多 34 行，左右等宽留白。
中英文普通段落首行缩进 4 个终端单元格（中文两字 / 英文四空格），标题、列表和图片不缩进。插图按比例缩放为
完整预览，随窗口调整，最高 28 行，小字形图片保持紧凑。EPUB 内嵌图片
会异步加载为独立的图片组件；支持 Sixel / Kitty 图形协议的终端（WezTerm、
iTerm2、Kitty 等）直接绘制高分辨率图片，其余终端降级为真彩色半块字符。
书架封面使用同样的渲染方式，并带有稳定的 2:3 加载占位图。

听书时当前句使用加粗下划线，当前词使用反色加粗，已读词变暗，不依赖背景色，
因此在浅色和深色终端主题下都能看清。

## 键位

| 按键 | 功能 |
| --- | --- |
| `j` / `k` | 向下 / 向上移动、滚动 |
| `h` / `l` | 上一句 / 下一句；书架中 `l` 打开 |
| `Space` / `p` | 播放 / 暂停 |
| `r` | 重播当前句 |
| `+` / `-` / `0` | 加速 / 减速 / 恢复 1.0× |
| `v` | 听书时切换该书语言的男声 / 女声 |
| `[` / `]` | 上一章 / 下一章 |
| `Ctrl+d` / `Ctrl+u` | 下半页 / 上半页 |
| `Ctrl+f` / `Ctrl+b` | 下一页 / 上一页 |
| `g` / `G` | 章首 / 章末 |
| `/`、`n`、`N` | 搜索、下一处、上一处 |
| `Ctrl+Shift+H` / `Ctrl+Shift+L` | 聚焦目录 / 正文（需要终端传递 CSI-u 修饰键） |
| `t` / `Tab` / `Ctrl+w` | 聚焦目录 / 聚焦目录 / 切换窗格 |
| `f` | 全屏正文 |
| `Ctrl+l` | 重绘当前页面与缓存图片 |
| `m` | 切换主题 |
| `q` | 返回；在书架页退出 |

当前阅读章节在目录中始终带 `●` 和粗体下划线，与键盘选择行独立。
部分终端及 tmux 链路会把 `Ctrl+Shift+H/L` 降为退格 / `Ctrl+l`；此时用 `Ctrl+w`、`Tab`、`t` 切换，`Ctrl+l` 继续重绘。

倍速与男女声只对当前书生效；新书默认 1.0×、男声，切回或重启后恢复。
有 ffmpeg 时用它保留音调变速；没有时使用 afplay / ffplay / mpv 原生倍速。
只有 aplay 的 Linux 环境需要安装 ffmpeg 或改用 mpv 才能变速。

## 本地配置

```text
~/.config/lector/reader.json     URL、token、主题
~/.config/lector/progress.json   每本书的位置、倍速、性别与音色
~/Library/Caches/lector/shelves/ macOS 书架快照
~/Library/Caches/lector/images/  macOS 图片缓存
~/.cache/lector/images/          Linux 图片缓存
```

环境变量 `LECTOR_URL`、`LECTOR_TOKEN`、`LECTOR_THEME` 优先于配置文件。
网页端和终端端的阅读位置完全独立。

书架先显示本地快照，再后台刷新，不阻塞键盘操作；断网保留上次书架，按 `r` 重试。
快照按服务器与令牌隔离，单份最多 2 MiB；相同书单刷新保留已有封面组件。

图片按服务器地址、书籍和资源路径生成缓存键，默认最多占用 512 MiB，超过后自动淘汰
最久未使用的图片。可以用 `LECTOR_CACHE_DIR` 指定其他缓存目录；损坏或超限缓存会
被淘汰并重新下载。单张下载最多 20 MiB，解码前检查单边 16000px、2000 万像素，
原生图片缩放最多 1600 万像素。

图片逐张到达即更新，保留已有文字和图片组件；失败显示提示。Sixel 按可见区域作为
一张完整位图，在文字布局后同帧提交。绘制前显式清理图片区域，释放 tmux 保留的旧图层，
避免占位图或旧图遮住新图；清理避开菜单等遮挡内容。滚动不额外刷新，文字高亮不重发无关图片。
图片裁剪编码缓存最多 8 项 / 8 MiB，返回已有位置可复用。
图形能力在导入渲染器前缓存：WezTerm/Kitty 依环境识别，未知终端只查询 Sixel，
避免 Kitty 探测应答迟到后出现在 shell。`--version`、`--help`、`--check` 不检测图形。

tmux 内外共用上面的磁盘图片缓存。**WezTerm + tmux 已允许透明传输时显示高清 PNG**，
通过 Kitty 图形协议传输完整像素，不压成字符或 256 色图片；缩放使用 Lanczos。
每张图片有独立 ID，滚动替换、离开页面和退出时清理自己的旧图。PNG 在 tmux 的文字
提交后合并绘制；快速滚动取最新位置，隐藏窗口取消待绘图片，分屏和顶部状态栏按实际坐标换算。
所有图形命令使用静默模式，启动不发送 Kitty 能力查询。
图形数据块各自通过透明传输，避免大图超过 tmux 的单条输入缓冲上限。
待绘图片持续保留到实际提交，避免状态栏等后续刷新取消首次图片绘制。
滚动时保留已有 PNG，文字更新跳过图片单元格；位置、裁剪或内容未变化时不重复上传。
此通道使用局部文字更新，避免 tmux 同步文字模式重画整行时擦掉 PNG；菜单遮挡仍正常绘制。
如果 tmux 尚未允许透明传输，使用彩色半块预览。需要启用高清通道可自行配置：

```tmux
set -g allow-passthrough on
set -s focus-events on
```

lector 只读取设置，不替用户修改 tmux 配置；修改设置后重新启动 lector。
其它 tmux 连接会验证它自身及当前连接的 Sixel 能力；支持时显示原生图片，
不支持、没有连接或检测失败时显示彩色半块图片。
高清 PNG 通道仅对已识别的 WezTerm 连接启用。切回窗口会利用焦点事件重绘缓存图片，
也可按 `Ctrl+l` 手动重绘；复用内存位图，不重复下载。
若 tmux 没有启用焦点事件，可在自己的配置中加入 `set -s focus-events on`；lector 只读取
能力信息，不修改 tmux 配置。

## 开发

```bash
cd terminal
uv sync
uv run lector
uv run pytest -q
```

自己构建独立二进制（程序为 `terminal/dist/lector/lector`，同目录 `_internal/` 必须一起保留）：

```bash
cd terminal
bash scripts/build-binary.sh
```

## 发布

推送 `terminal-v*` 标签会触发 `.github/workflows/terminal-release.yml`：
在 macOS arm64 与 x86_64 runner 上各构建一次，压缩成
`lector-macos-<arch>.tar.gz` 并挂到 GitHub Release，Homebrew 公式直接下载
这些二进制。
