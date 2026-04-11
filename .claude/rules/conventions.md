# Code Conventions

## Python / FastAPI
- Python 3.12+, type hints mandatory
- Pydantic v2 (model_validator, field_validator)
- SQLAlchemy 2.0 async (mapped_column, DeclarativeBase)
- Ruff linter + formatter (line-length = 120)
- Import order: stdlib → third-party → local
- Router files: `api/app/routers/{resource}.py`
- Service files: `api/app/services/{domain}.py`
- Test files: `api/tests/test_{module}.py`

## TypeScript / Next.js
- Next.js 14 App Router (no Pages Router)
- shadcn/ui components
- `export const dynamic = "force-dynamic"` on pages with useSearchParams
- Suspense boundary required for useSearchParams()

## OpenTofu / HCL
- Module: `infrastructure/modules/{provider}-{resource}/`
- Environment: `infrastructure/environments/{env}/`
- Helm templates: inside module `templates/*.yaml.tpl`
- Secrets: tfvars (gitignored), NEVER hardcode
- Every model change requires Alembic migration

## Git
- Conventional commits: feat:, fix:, infra:, docs:
- Code comments in English
- CLAUDE.md and docs in Turkish
- Feature branch → PR → review → merge

## CI/CD
- Self-hosted runner: `runs-on: [self-hosted, haven]`
- PostgreSQL in tests: docker run step (NOT service container)
- NEVER use `runs-on: ubuntu-latest` — always `[self-hosted, haven]`
