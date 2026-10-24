# Lector 终端端

独立项目，只通过 HTTP 与服务端打交道 —— 不依赖服务端的任何代码。

```bash
cd terminal
uv sync          # 只装 textual 这一个依赖
uv run lector    # 起客户端
```

连哪台服务器：书架屏按 `c` 填地址与令牌（记在 `~/.config/lector/reader.json`），
或者用环境变量 `LECTOR_URL` 与 `LECTOR_TOKEN`。

令牌只需要 `reader` 权限（能读、能写自己的阅读位置，不能上传或删除书）。

服务端不在本机时：

```bash
LECTOR_URL=https://reader.example.com LECTOR_TOKEN=xxx:reader uv run lector
```

键位见 [../docs/UI.md](../docs/UI.md) §8。
