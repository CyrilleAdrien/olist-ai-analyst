# Olist AI Analyst: entry points. The Olist warehouse must be running (make up in Olist-Analytics).

-include .env
export

.DEFAULT_GOAL := help
.PHONY: help install role doctor test lint format

help: ## List the available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(firstword $(MAKEFILE_LIST)) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example"

install: .env ## Install the dependencies with uv
	uv sync

role: .env ## Create the read-only role of the agent in the warehouse
	uv run python scripts/create_readonly_role.py

doctor: .env ## Check the warehouse connection and the LLM
	uv run olist-ai-analyst doctor

test: ## Run the tests (integration tests are skipped without a warehouse)
	uv run pytest

lint: ## Check the code style
	uv run ruff check . && uv run ruff format --check .

format: ## Format the code
	uv run ruff check --fix . && uv run ruff format .
