# Haven Platform — Developer Makefile
# Usage: make <target>

.PHONY: help test lint ci api-test api-lint ui-lint ui-build e2e deploy-check logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Testing
# ============================================================

test: api-test ## Run all backend tests
	@echo "✓ All tests passed"

api-test: ## Run backend pytest
	cd api && python -m pytest tests/ -q --tb=short

api-test-v: ## Run backend pytest (verbose)
	cd api && python -m pytest tests/ -v --tb=short

api-test-cov: ## Run backend pytest with coverage
	cd api && python -m pytest tests/ --cov=app --cov-report=term-missing -q

api-test-count: ## Count backend tests
	@cd api && python -m pytest tests/ --collect-only -q 2>/dev/null | tail -1

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

KC ?= infrastructure/environments/dev/kubeconfig

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

haven-check: ## Run 15/15 Haven compliance checks
	@echo "=== Multi-AZ ==="
	kubectl --kubeconfig=$(KC) get nodes -L topology.kubernetes.io/zone
	@echo "\n=== K8s Version ==="
	kubectl --kubeconfig=$(KC) version --short
	@echo "\n=== Cilium ==="
	kubectl --kubeconfig=$(KC) get pods -n kube-system -l k8s-app=cilium
	@echo "\n=== Longhorn ==="
	kubectl --kubeconfig=$(KC) get storageclass
	@echo "\n=== Certificates ==="
	kubectl --kubeconfig=$(KC) get certificates -A
	@echo "\n=== Kyverno ==="
	kubectl --kubeconfig=$(KC) get clusterpolicy 2>/dev/null || echo "Kyverno not installed"

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

infra-plan: ## Run tofu plan (dry-run)
	cd infrastructure/environments/dev && tofu plan -var-file=terraform.tfvars

infra-validate: ## Validate tofu config
	cd infrastructure/environments/dev && tofu validate

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
