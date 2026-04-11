# Code Conventions

## Running Commands — ALWAYS use Makefile
The project has a `Makefile` at the root. Use `make <target>` for ALL operations.
NEVER type raw commands when a Makefile target exists. If a needed command is missing
from the Makefile, ADD it first, then use it.

| Task | Command |
|------|---------|
| Run backend tests | `make api-test` |
| Run tests verbose | `make api-test-v` |
| Run tests + coverage | `make api-test-cov` |
| Count tests | `make api-test-count` |
| Lint Python | `make api-lint` |
| Fix lint | `make api-lint-fix` |
| Lint UI | `make ui-lint` |
| Build UI | `make ui-build` |
| Full local CI | `make ci` |
| Full CI + UI | `make ci-full` |
| Playwright E2E | `make e2e` |
| Deploy status | `make deploy-check` |
| API health | `make api-check` |
| Wait for rollout | `make pod-wait` |
| Haven 15/15 | `make haven-check` |
| PR CI status | `make pr-status` |
| Create PR | `make pr-create` |
| View logs | `make logs` |
| Infra plan | `make infra-plan` |
| Clean artifacts | `make clean` |

If you need to run something not listed → add it to Makefile first → then use it.

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
