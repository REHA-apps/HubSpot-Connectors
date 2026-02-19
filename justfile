# -------------------------
# CRM Connectors Justfile
# Windows PowerShell Compatible
# -------------------------

# Force PowerShell as the execution shell
set shell := ["powershell", "-NoLogo", "-NoProfile", "-Command"]

# -------------------------
# Local Development
# -------------------------

# Run FastAPI with auto-reload
dev:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run linting (Ruff)
lint:
    ruff check .
    ruff format .

# Run type checking (Pyright)
typecheck:
    uv run pyright

# Run tests
test:
    pytest -q

# -------------------------
# Docker Commands
# -------------------------

# Build Docker images
build:
    docker compose build

# Run production docker-compose
up:
    docker compose up --build

# Stop production docker-compose
down:
    docker compose down

# Run development docker-compose (with bind mounts)
dev-up:
    docker compose -f docker-compose.dev.yml up --build

# Stop development docker-compose
dev-down:
    docker compose -f docker-compose.dev.yml down

# -------------------------
# Pre-commit Hooks
# -------------------------

# Install pre-commit hooks
hooks:
    pre-commit install --hook-type pre-commit --hook-type commit-msg

# Run all pre-commit hooks manually
run-hooks:
    pre-commit run --all-files

# -------------------------
# Utility
# -------------------------

# Format + lint + typecheck in one command
check:
    ruff format .
    ruff check .
    uv run pyright

# Remove temporary logs and test artifacts
clean:
    if (Test-Path logs) { Remove-Item -Recurse -Force logs }
    if (Test-Path *.txt) { Remove-Item -Force *.txt }
    if (Test-Path .pytest_cache) { Remove-Item -Recurse -Force .pytest_cache }
    if (Test-Path .ruff_cache) { Remove-Item -Recurse -Force .ruff_cache }
