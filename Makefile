.DEFAULT_GOAL := help
COMPOSE := docker compose
STACK_DIR := stack

.PHONY: help up down restart logs ps validate clean seed

help: ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## スタックを起動 (Grafana/Prometheus/InfluxDB/TimescaleDB/simulator)
	cd $(STACK_DIR) && [ -f .env ] || cp .env.example .env
	cd $(STACK_DIR) && $(COMPOSE) up -d
	@echo "Grafana:    http://localhost:3000  (admin/admin)"
	@echo "Prometheus: http://localhost:9090"
	@echo "InfluxDB:   http://localhost:8086"

down: ## スタックを停止・削除
	cd $(STACK_DIR) && $(COMPOSE) down

clean: ## スタックを停止し、ボリュームも削除
	cd $(STACK_DIR) && $(COMPOSE) down -v

restart: ## スタックを再起動
	cd $(STACK_DIR) && $(COMPOSE) restart

logs: ## simulator のログを追従 (svc=<name> で対象変更可)
	cd $(STACK_DIR) && $(COMPOSE) logs -f $(or $(svc),simulator)

ps: ## コンテナ状態を表示
	cd $(STACK_DIR) && $(COMPOSE) ps

validate: ## compose 定義の静的検証
	cd $(STACK_DIR) && $(COMPOSE) config -q && echo "compose OK"
	python3 scripts/validate.py
