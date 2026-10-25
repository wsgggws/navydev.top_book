# Lector Terminal

`navydev.top/ebook` 的只读终端客户端：浏览书架、阅读、听书，不上传、不删除、
不修改服务端内容。

默认连接：

```text
https://navydev.top/ebook
```

## Homebrew 安装

```bash
brew tap wsgggws/ebook https://github.com/wsgggws/navydev.top_ebook
brew install wsgggws/ebook/lector
```

运行：

```bash
LECTOR_TOKEN="你的 reader token" lector
```

不配置 token 也可读取公开内容；token 会以 Bearer 方式发送。

```bash
lector --url https://navydev.top/ebook --token "$LECTOR_TOKEN"
lector --theme dracula
lector --version
```

## 主题

默认 `LECTOR_THEME=auto`：

- 优先通过 OSC 11 查询终端实际背景色
- 支持 `COLORFGBG`
- 使用 Textual `ansi-light` / `ansi-dark`，保留终端自身的 ANSI 调色板
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

## 键位

| 按键 | 功能 |
| --- | --- |
| `j` / `k` | 向下 / 向上移动、滚动 |
| `h` / `l` | 上一句 / 下一句；书架中 `l` 打开 |
| `Space` / `p` | 播放 / 暂停 |
| `r` | 重播当前句 |
| `+` / `-` / `0` | 加速 / 减速 / 恢复 1.0× |
| `[` / `]` | 上一章 / 下一章 |
| `Ctrl+d` / `Ctrl+u` | 下半页 / 上半页 |
| `Ctrl+f` / `Ctrl+b` | 下一页 / 上一页 |
| `g` / `G` | 章首 / 章末 |
| `/`、`n`、`N` | 搜索、下一处、上一处 |
| `t` | 聚焦目录 |
| `f` | 全屏正文 |
| `m` | 切换主题 |
| `q` | 返回 / 退出 |

## 本地配置

```text
~/.config/lector/reader.json     URL、token、主题
~/.config/lector/progress.json   终端自己的阅读位置
```

环境变量 `LECTOR_URL`、`LECTOR_TOKEN`、`LECTOR_THEME` 优先于配置文件。
网页端和终端端的阅读位置完全独立。

## 开发

```bash
cd terminal
uv sync
uv run lector
uv run pytest -q
```
