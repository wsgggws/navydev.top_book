# Lector —— 常用命令
#
#   make book books/some.epub   生成一本书，并送进服务端
#   make import books/some.epub  把已有的 EPUB 送进服务端
#   make test                    跑测试
#   make server                  起服务端
#   make terminal                起终端端

UV ?= uv
BOOK ?= books/some.epub
URL ?= http://127.0.0.1:8000

.DEFAULT_GOAL := help
.PHONY: help book import test server terminal dev clean lock reinstall

help:  ## 显示这份清单
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

book:  ## 生成一本书：make book books/some.epub
	@target="$(lastword $(MAKECMDGOALS))"; \
	 if [ "$$target" = "book" ]; then target="$(BOOK)"; fi; \
	 $(UV) run python -m lector.build --url $(URL) "$$target"

import:  ## 把已有的 EPUB 送进服务端：make import books/some.epub
	@target="$(lastword $(MAKECMDGOALS))"; \
	 if [ "$$target" = "import" ]; then target="$(BOOK)"; fi; \
	 $(UV) run python -m lector.build --url $(URL) --import-only "$$target"

# 任何 *.epub 目标都能直接生成：make books/some.epub
%.epub:
	@$(UV) run python -m lector.build $@

test:  ## 跑测试
	@$(UV) run pytest -q

server:  ## 起服务端
	@$(UV) run lector-server

terminal:  ## 起终端端
	@$(UV) run lector

dev:  ## 起带热重载的服务端
	@$(UV) run uvicorn lector.web:app --reload --port 8000

lock:  ## 更新依赖锁
	@$(UV) lock

reinstall:  ## 重新装一遍环境
	@$(UV) sync --reinstall

clean:  ## 清掉运行数据（书与音频缓存都在 data/ 里）
	@find data -mindepth 1 -delete 2>/dev/null || true
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "已清理 data/ 与 __pycache__"
