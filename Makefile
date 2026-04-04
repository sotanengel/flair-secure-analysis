.DEFAULT_GOAL := help

PROJECT_DIR := $(shell pwd)
IMAGE_NAME   := flair-secure-analysis
IMAGE_TAG    := latest

.PHONY: help install build run test lint smoke ui clean

help: ## このヘルプを表示する
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Python 依存パッケージをインストールする (uv sync)
	uv sync

build: ## コンテナイメージをビルドする
	./scripts/build-image.sh

run: ## ワーカーをローカル実行する (例: make run INPUT=work/input/data.csv)
	@if [ -z "$(INPUT)" ]; then \
	  echo "使い方: make run INPUT=work/input/data.csv [DATETIME_COL=timestamp] [VALUE_COL=value]"; \
	else \
	  ./scripts/run-worker.sh \
	    --input "$(INPUT)" \
	    --datetime-col "$${DATETIME_COL:-timestamp}" \
	    --value-col "$${VALUE_COL:-value}" \
	    --horizon "$${HORIZON:-24}" \
	    --seed "$${SEED:-42}"; \
	fi

test: ## pytest でテストを実行する
	uv run pytest tests/ -v

lint: ## ruff でコードチェックする
	uv run ruff check worker/ tests/
	uv run ruff format --check worker/ tests/

ui: ## Web UI を起動する (http://127.0.0.1:5000)
	./scripts/run-ui.sh

smoke: ## smoke-test を実行する（サンプルデータで動作確認）
	./scripts/smoke-test.sh

clean: ## 出力・ログ・一時ファイルを削除する（入力は保持）
	rm -rf work/output/* work/logs/* work/tmp/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
