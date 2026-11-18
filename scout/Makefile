# Confluo Scout. Run from this directory: make <target>
.PHONY: up down restart logs ps check test lint web dev-qdrant dev-api dev-web embed-host crawl search snapshot

COMPOSE = docker compose
DEV = docker compose -f compose.yaml -f compose.dev.yaml

up:            ## build and start the service (http://127.0.0.1:8770)
	$(COMPOSE) up -d --build

down:          ## stop and remove the containers (data and the qdrant volume stay)
	$(COMPOSE) down

restart:
	$(COMPOSE) restart scout

logs:
	$(COMPOSE) logs -f --tail=200 scout

ps:
	$(COMPOSE) ps

check: lint test web   ## everything the repository checks locally

lint:
	cd server && uv run ruff check src tests

test:
	cd server && uv run pytest -q -p no:warnings

web:
	cd web && pnpm install --frozen-lockfile && pnpm build

dev-qdrant:    ## qdrant with its port on 127.0.0.1:6333 for host-side development
	$(DEV) up -d qdrant

dev-api:       ## API on the host (MPS), no background jobs; web dev server proxies to it
	cd server && SCOUT_SCHEDULER=0 uv run scout serve --port 8771

dev-web:
	cd web && pnpm dev

embed-host:    ## bulk embedding on the host GPU (MPS) while the container is stopped
	$(COMPOSE) stop scout
	$(DEV) up -d qdrant
	cd server && uv run scout embed
	$(COMPOSE) up -d scout

crawl:         ## make crawl EDITION=iclr-2027
	$(COMPOSE) exec scout scout crawl $(EDITION)

search:        ## make search Q="sparse autoencoders"
	$(COMPOSE) exec scout scout search "$(Q)"

snapshot:      ## qdrant snapshots into ../.confluo/scout/qdrant/snapshots
	$(COMPOSE) exec scout python -c "from confluo_scout.services import Services; print(Services().vectors.snapshot())"
