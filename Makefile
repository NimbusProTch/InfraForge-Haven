# Haven Platform — Developer Makefile
# Usage: make <target>

SHELL := /bin/bash

.PHONY: help test lint ci api-test api-lint ui-lint ui-build e2e deploy-check logs clean \
        haven haven-json haven-cis haven-all haven-rationale haven-install haven-version haven-check \
        infra-init infra-validate infra-plan infra-apply infra-destroy kubeconfig

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Testing
# ============================================================
#  api/.venv is the canonical local virtualenv. All python targets run
#  through it so they do not depend on a system `python` symlink (some
#  Homebrew setups only ship `python3`). CI (self-hosted runner) already
#  activates the venv before invoking make.

PYTHON ?= api/.venv/bin/python

test: api-test ## Run all backend tests
	@echo "✓ All tests passed"

api-test: ## Run backend pytest
	cd api && $(abspath $(PYTHON)) -m pytest tests/ -q --tb=short

api-test-v: ## Run backend pytest (verbose)
	cd api && $(abspath $(PYTHON)) -m pytest tests/ -v --tb=short

api-test-cov: ## Run backend pytest with coverage
	cd api && $(abspath $(PYTHON)) -m pytest tests/ --cov=app --cov-report=term-missing -q

api-test-count: ## Count backend tests
	@cd api && $(abspath $(PYTHON)) -m pytest tests/ --collect-only -q 2>/dev/null | tail -1

# ============================================================
# Linting
# ============================================================

lint: api-lint ## Run all linters
	@echo "✓ All linters passed"

api-lint: ## Run Python linters (ruff)
	cd api && ruff check . && ruff format --check .

api-lint-fix: ## Auto-fix Python lint issues
	cd api && ruff check --fix . && ruff format .

ui-lint: ## Run TypeScript linter
	cd ui && npm run lint

ui-build: ## Build UI (type check + bundle)
	cd ui && npm run build

# ============================================================
# Full CI (local)
# ============================================================

ci: api-lint api-test ## Run full CI locally (lint + test)
	@echo "✓ CI passed locally"

ci-full: api-lint api-test ui-lint ui-build ## Run full CI including UI
	@echo "✓ Full CI passed locally"

# ============================================================
# E2E Tests
# ============================================================

e2e: ## Run Playwright E2E tests
	npx playwright test

e2e-ui: ## Run Playwright with browser UI
	npx playwright test --ui

# ============================================================
# Deploy Verification
# ============================================================

KC ?= infrastructure/environments/prod/kubeconfig

deploy-check: ## Verify cluster deployment status
	@echo "=== Nodes ==="
	kubectl --kubeconfig=$(KC) get nodes -o wide
	@echo "\n=== Haven Pods ==="
	kubectl --kubeconfig=$(KC) get pods -n haven-system
	@echo "\n=== ArgoCD Apps ==="
	kubectl --kubeconfig=$(KC) get applications -n argocd
	@echo "\n=== API Image ==="
	kubectl --kubeconfig=$(KC) get pods -n haven-system -l app=haven-api -o jsonpath='{.items[0].spec.containers[0].image}'
	@echo ""

api-check: ## Verify API is accessible
	@curl -sf https://api.46.225.42.2.sslip.io/api/docs > /dev/null && echo "✓ API OK" || echo "✗ API UNREACHABLE"

pod-wait: ## Wait for haven-api pod rollout
	kubectl --kubeconfig=$(KC) rollout status deploy/haven-api -n haven-system --timeout=120s

# ============================================================
# Haven Compliance Gate (iyziops fork of VNG Haven CLI)
# ============================================================
#  Source of truth: haven/ folder + haven/VERSION (pinned CLI version)
#  Upstream:        https://gitlab.com/commonground/haven/haven
#  Fork binaries:   https://github.com/NimbusProTch/InfraForge-Haven/releases
#  Rationale:       zero custom check code. The fork is a 5-line patch
#                   (see haven/PATCH.md) that adds HAVEN_RELEASES_URL env
#                   var support so the bootstrap manifest can be mirrored
#                   on github.com, bypassing Cloudflare's bot challenge
#                   against Go's default http.Client User-Agent (hit
#                   upstream gitlab.com in Aug 2025).
# ============================================================

HAVEN_BIN     := haven/bin/haven
HAVEN_VERSION := $(shell tr -d '[:space:]' < haven/VERSION)
HAVEN_KC      := $(if $(wildcard /tmp/iyziops-kubeconfig),/tmp/iyziops-kubeconfig,$(KC))
# Pull the release manifest straight from the matching GitHub release
# asset. This URL is stable across `main` / feature branches and never
# touches gitlab.com, so Cloudflare's bot challenge is out of the path.
HAVEN_RELEASES_URL ?= https://github.com/NimbusProTch/InfraForge-Haven/releases/download/$(HAVEN_VERSION)/releases.json
HAVEN_ENV := HAVEN_RELEASES_URL=$(HAVEN_RELEASES_URL) KUBECONFIG=$(HAVEN_KC)

$(HAVEN_BIN): haven/install.sh haven/VERSION haven/releases.json
	@bash haven/install.sh

haven: $(HAVEN_BIN) ## Run Haven 15/15 compliance check (human output)
	@$(HAVEN_ENV) $(HAVEN_BIN) check

haven-json: $(HAVEN_BIN) ## Haven check with JSON output (pipeable to jq)
	@$(HAVEN_ENV) $(HAVEN_BIN) check --output=json

haven-cis: $(HAVEN_BIN) ## Haven check + external CIS Kubernetes Benchmark
	@$(HAVEN_ENV) $(HAVEN_BIN) check --cis

haven-all: $(HAVEN_BIN) ## Haven check + CIS + Kubescape (full external checks)
	@$(HAVEN_ENV) $(HAVEN_BIN) check --cis --kubescape

haven-rationale: $(HAVEN_BIN) ## Show rationale for each Haven check (does not run)
	@$(HAVEN_BIN) check --rationale

haven-install: ## Force re-install / upgrade Haven CLI binary (edit haven/VERSION first)
	@rm -f $(HAVEN_BIN)
	@bash haven/install.sh

haven-version: $(HAVEN_BIN) ## Show installed Haven CLI version
	@$(HAVEN_BIN) version

haven-check: haven ## Legacy alias (deprecated, use 'make haven')
	@echo "(haven-check is deprecated, prefer 'make haven')"

# ============================================================
# Git & PR
# ============================================================

pr-status: ## Check CI status for current branch
	gh run list --branch $$(git branch --show-current) --limit 5

pr-create: ## Create PR from current branch
	gh pr create --fill

pr-merge: ## Merge current PR (after approval)
	gh pr merge --merge --delete-branch

# ============================================================
# Infrastructure
# ============================================================
#  Targets run against environments/prod (single-env model — there is
#  no dev). tofu picks up prod.auto.tfvars automatically so no -var-file
#  flag is needed; sensitive values come from the iyziops-env function.

INFRA_DIR := infrastructure/environments/prod
TS := $(shell date -u +%Y%m%d-%H%M%S)

infra-init: ## tofu init (remote state)
	cd $(INFRA_DIR) && tofu init

infra-validate: ## Validate tofu config
	cd $(INFRA_DIR) && tofu validate

infra-plan: ## tofu plan → logs/tofu-plan-prod-<ts>.log
	@mkdir -p logs
	set -o pipefail; cd $(INFRA_DIR) && tofu plan 2>&1 | tee ../../../logs/tofu-plan-prod-$(TS).log

infra-apply: ## tofu apply -auto-approve (Haven 15/15 sprint uses this)
	@mkdir -p logs
	set -o pipefail; cd $(INFRA_DIR) && tofu apply -auto-approve 2>&1 | tee ../../../logs/tofu-apply-prod-$(TS).log

infra-destroy: ## tofu destroy -auto-approve
	@mkdir -p logs
	set -o pipefail; cd $(INFRA_DIR) && tofu destroy -auto-approve 2>&1 | tee ../../../logs/tofu-destroy-prod-$(TS).log

kubeconfig: ## SCP kubeconfig from first master and pin to /tmp/iyziops-kubeconfig
	@bash scripts/fetch-kubeconfig.sh 2>/dev/null || \
	  (echo "fetch-kubeconfig.sh missing; copy manually via: scp -i logs/iyziops-prod-ssh.pem root@<master0>:/etc/rancher/rke2/rke2.yaml /tmp/iyziops-kubeconfig" && false)

# ============================================================
# Logs
# ============================================================

logs: ## Tail haven-api logs
	kubectl --kubeconfig=$(KC) logs -n haven-system -l app=haven-api -f --tail=50

logs-build: ## Tail latest build job logs
	kubectl --kubeconfig=$(KC) logs -n haven-builds -l app=haven-build --tail=100

# ============================================================
# Cleanup
# ============================================================

clean: ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
