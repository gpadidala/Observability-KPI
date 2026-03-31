.PHONY: up down build logs restart status clean

# ---- One-click commands ----

up: ## Start the entire application
	docker-compose up -d --build
	@echo ""
	@echo "============================================"
	@echo "  Observability KPI App is UP"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  Backend:   http://localhost:8000"
	@echo "  API Docs:  http://localhost:8000/docs"
	@echo "============================================"

down: ## Stop the entire application
	docker-compose down
	@echo "Observability KPI App is DOWN"

build: ## Build containers without starting
	docker-compose build

logs: ## Tail logs from all services
	docker-compose logs -f

logs-backend: ## Tail backend logs only
	docker-compose logs -f backend

logs-frontend: ## Tail frontend logs only
	docker-compose logs -f frontend

restart: ## Restart all services
	docker-compose restart

status: ## Show running containers
	docker-compose ps

clean: ## Stop and remove containers, images, volumes
	docker-compose down --rmi local --volumes --remove-orphans
	@echo "Cleaned up all containers, images, and volumes"

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
