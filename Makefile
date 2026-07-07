.PHONY: install dev backend frontend test migrate seed clean clean-db

# Detect whether the frontend has been scaffolded yet (Phase 8).
HAS_FRONTEND := $(shell test -f frontend/package.json && echo yes)

install:
	uv sync
ifeq ($(HAS_FRONTEND),yes)
	cd frontend && npm ci
else
	@echo "[install] frontend/ not initialized yet; skipping npm ci."
endif

dev:
ifeq ($(HAS_FRONTEND),yes)
	$(MAKE) -j 2 backend frontend
else
	@echo "[dev] frontend/ not initialized yet; running backend only."
	$(MAKE) backend
endif

backend:
	uv run uvicorn backend.app.main:app --reload --port 8000

frontend:
ifeq ($(HAS_FRONTEND),yes)
	cd frontend && npm run dev
else
	@echo "[frontend] frontend/ not initialized yet; nothing to run."
endif

test:
	uv run pytest
ifeq ($(HAS_FRONTEND),yes)
	cd frontend && npm test
endif

migrate:
	uv run alembic upgrade head

seed:
	uv run python scripts/seed.py

# Rebuildable artifacts only. The database — which holds hand-entered
# classifications that can't be regenerated — has its own explicit target.
clean:
	rm -rf .venv frontend/node_modules frontend/dist

clean-db:
	@echo "This deletes data/*.db including all your classifications."
	@read -p "Type 'yes' to confirm: " ans && [ "$$ans" = "yes" ] && rm -f data/*.db || echo "Aborted."
