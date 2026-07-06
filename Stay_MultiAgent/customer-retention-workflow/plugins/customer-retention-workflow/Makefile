# ============================================================
# customer-retention-workflow — Task runner
# ============================================================
# Usage:
#   make install      → install core + UI dependencies
#   make install-dev  → install all dev dependencies
#   make ui           → launch the Streamlit app
#   make run          → run the CLI on the synthetic dataset
#   make data         → generate the synthetic dataset
#   make test         → run pytest with coverage
#   make lint         → run all linters (black, isort, flake8, pylint, mypy)
#   make format       → auto-format with black + isort
#   make clean        → remove caches and build artifacts

PYTHON     := python3
PIP        := $(PYTHON) -m pip
PYTHONPATH := src
SRC        := src
APP        := app/streamlit_app.py
SCRIPTS    := scripts
TESTS      := tests
DATA_DIR   := data
POLICY     := $(SRC)/customer_retention/resources/politica_retencion.md
DATASET    := $(DATA_DIR)/customers.csv

# ── installation ──────────────────────────────────────────────
.PHONY: install
install:
	$(PIP) install -e ".[ui]"

.PHONY: install-dev
install-dev:
	$(PIP) install -e ".[dev]"

# ── dataset generation ────────────────────────────────────────
.PHONY: data
data:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(SCRIPTS)/generate_synthetic_dataset.py \
		--rows 1000 --seed 42 --out-dir $(DATA_DIR) --formats csv xlsx
	@echo "Dataset ready in $(DATA_DIR)/"

# ── UI ────────────────────────────────────────────────────────
.PHONY: ui
ui:
	PYTHONPATH=$(PYTHONPATH) streamlit run $(APP) \
		--server.address localhost \
		--server.port 8501

# ── CLI ───────────────────────────────────────────────────────
.PHONY: run
run: data
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(SCRIPTS)/run_workflow.py \
		--csv $(DATASET) \
		--policy $(POLICY) \
		--out report.json
	@echo "Report → report.json"

# ── tests ─────────────────────────────────────────────────────
.PHONY: test
test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest $(TESTS) \
		--cov=customer_retention \
		--cov-report=term-missing \
		-q

# ── linting ───────────────────────────────────────────────────
.PHONY: lint
lint:
	@echo "── black ──"; black --check --line-length 100 $(SRC) app $(SCRIPTS) $(TESTS)
	@echo "── isort ──"; isort --profile black --line-length 100 --check-only $(SRC) app $(SCRIPTS) $(TESTS)
	@echo "── flake8 ──"; flake8 $(SRC) app $(SCRIPTS) $(TESTS)
	@echo "── pylint ──"; pylint $(SRC)/customer_retention app/streamlit_app.py $(SCRIPTS)/*.py --rcfile=.pylintrc
	@echo "── mypy ──"; mypy $(SRC)/customer_retention app/streamlit_app.py $(SCRIPTS)/run_workflow.py $(SCRIPTS)/generate_synthetic_dataset.py
	@echo "── bandit ──"; bandit -r $(SRC) app $(SCRIPTS) -q

.PHONY: format
format:
	black --line-length 100 $(SRC) app $(SCRIPTS) $(TESTS)
	isort --profile black --line-length 100 $(SRC) app $(SCRIPTS) $(TESTS)

# ── docker ────────────────────────────────────────────────────
.PHONY: docker-build
docker-build:
	docker compose build

.PHONY: docker-ui
docker-ui:
	docker compose up ui

.PHONY: docker-run
docker-run:
	docker compose run --rm retention-workflow

.PHONY: docker-test
docker-test:
	docker compose --profile ci run --rm tests

# ── clean ─────────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"   -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage report.json
	@echo "Clean!"
