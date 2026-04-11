# Kod Konvansiyonları

## Python / FastAPI
- Python 3.12+, type hints zorunlu
- Pydantic v2 (model_validator, field_validator)
- SQLAlchemy 2.0 async (mapped_column, DeclarativeBase)
- Ruff linter + formatter (line-length = 120)
- Import sırası: stdlib → third-party → local
- Router: `api/app/routers/{resource}.py`
- Service: `api/app/services/{domain}.py`
- Test: `api/tests/test_{module}.py`

## TypeScript / Next.js
- Next.js 14 App Router
- shadcn/ui components
- `export const dynamic = "force-dynamic"` on pages with useSearchParams
- Suspense boundary required for useSearchParams()

## OpenTofu / HCL
- Module: `infrastructure/modules/{provider}-{resource}/`
- Environment: `infrastructure/environments/{env}/`
- Helm templates: module `templates/*.yaml.tpl`
- Secrets: tfvars (gitignored), ASLA hardcode yapma

## Git
- Conventional commits: feat:, fix:, infra:, docs:
- Kod yorumları İngilizce
- CLAUDE.md ve docs Türkçe
- Feature branch → PR → review → merge
- Her model değişikliğinde Alembic migration

## CI/CD
- Self-hosted runner: `runs-on: [self-hosted, haven]`
- PostgreSQL: docker run step (service container değil)
- Workflow'larda `ubuntu-latest` KULLANMA → `[self-hosted, haven]`
