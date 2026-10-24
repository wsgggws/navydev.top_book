# Lector —— 常用命令
#
#   make book books/some.epub        造一本书（或把已有的 EPUB 收进书架）
#   make book BOOK="路径 带空格.epub"  路径里有空格时用这种写法
#   make import BOOK=books/x.epub    只把已有的 EPUB 送进服务端
#   make test / server / terminal / dev / clean

UV ?= uv
BOOK ?= books/some.epub
URL ?= http://127.0.0.1:8000

.DEFAULT_GOAL := help
.PHONY: help book import test server terminal dev clean lock reinstall

help:  ## 显示这份清单
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# 位置参数里带空格时，make 会把目标按空格拆开；这里用 wordlist 把它们拼回去。
# 只有一个目标（就是 book/import 自己）时，退回 $(BOOK)。
book:  ## 造一本书：make book books/some.epub
	@target="$(wordlist 2,100,$(MAKECMDGOALS))"; \
	 if [ -z "$$target" ]; then target="$(BOOK)"; fi; \
	 $(UV) run python -m lector.build --url $(URL) "$$target"

import:  ## 把已有的 EPUB 送进服务端：make import books/some.epub
	@target="$(wordlist 2,100,$(MAKECMDGOALS))"; \
	 if [ -z "$$target" ]; then target="$(BOOK)"; fi; \
	 $(UV) run python -m lector.build --url $(URL) --import-only "$$target"

# 只认 books/ 下的书，免得路径里的空格碎片被当成别的目标去建文件。
books/%.epub:
	@$(UV) run python -m lector.build --url $(URL) "$@"

# 兜底：路径被空格拆开的碎片目标在这里安静地过去；
# 单独敲了一个不存在的目标则给出提示。
%:
	@if [ "$(words $(MAKECMDGOALS))" = "1" ]; then \
	   echo "make: 未知目标 '$@'（make help 看可用目标）"; \
	 fi

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
