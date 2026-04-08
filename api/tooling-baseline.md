# Static Analysis Baseline (Sprint H4 / P3.1)

Captured 2026-04-09 against `main` (post Sprint H0 merge, post P1.1+P1.2 PRs).

This file is the **baseline snapshot** that the Sprint H4 CI workflow
(P3.2) will compare against. It is intentionally NOT zero — fixing every
finding is out of scope for the H4 onboarding work. The goal is:

1. Document the current state honestly (no more "15/15 ✅" lies)
2. Make every new PR run the same tools and report deltas
3. Tighten thresholds incrementally — start in "warn-only" mode, then
   block on regressions, then chip away at the existing debt

---

## Tooling

```toml
[project.optional-dependencies]
quality = [
    "bandit>=1.7.10",   # Python security linting
    "vulture>=2.13",    # Dead code detection
    "xenon>=0.9.1",     # Cyclomatic complexity gates
    "mypy>=1.13.0",     # Static type checking
]
```

Install: `pip install -e .[quality]`
Run individually: see commands below.

---

## Bandit (security)

Command:
```bash
bandit -r app -lll          # HIGH severity only (used for CI gate)
bandit -r app -ll           # MEDIUM+ (informational)
bandit -r app               # ALL findings
```

| Severity | Count |
|---|---|
| **High** | **11** |
| Medium | 3 |
| Low | 16 |

### High-severity findings (must address in Sprint H1e)

| Test ID | Issue | Locations |
|---|---|---|
| `B501` | `httpx.AsyncClient(verify=False)` — disables TLS cert validation | `argocd_service.py` ×6 lines (43, 122, 150, 195, 218, 247), `cluster_service.py:134`, `everest_client.py:62,75`, `harbor_service.py:193` |
| `B701` | Jinja2 template environment with `autoescape=False` (XSS vector) | `gitops_scaffold.py:26` |

**Why these exist:** ArgoCD, Harbor, Everest, and Cluster services run with self-signed TLS certs in dev. The `verify=False` is a dev shortcut. Sprint **H1e (encryption)** will fix this by:
1. Cert-Manager-issued certs for in-cluster service-to-service TLS
2. CA bundle injected into haven-api pod via ESO/Vault
3. `verify=` set to the CA path, never `False`

The Jinja2 finding is more nuanced — `gitops_scaffold` renders YAML/HCL where HTML escaping would break the output. Will be addressed by switching to a YAML-safe renderer (PyYAML.dump) and removing Jinja from non-template paths.

### Acceptance threshold for Sprint H4 CI

- Block on **new** B501 findings in PRs (existing 11 grandfathered)
- Block on any new B7xx (template injection) findings
- Block on any **B6xx** (input validation) findings (currently 0)
- Warn on Medium

---

## Vulture (dead code)

Command:
```bash
vulture app --min-confidence 80   # CI gate (currently 0 findings — clean)
vulture app --min-confidence 60   # Includes likely false positives
```

| Confidence | Count |
|---|---|
| 90%+ | **0** |
| 80% | **0** |
| 60% | **309** |

The 309 entries at 60% confidence are **mostly false positives** from:

- **SQLAlchemy `mapped_column` and `relationship()`** — vulture doesn't know
  about ORM attribute access patterns. Every `Mapped[X]` declaration
  appears unused but is read at the SQL/instance level.
- **FastAPI exception handlers** registered via `app.add_exception_handler()`
  in `main.py` — vulture sees the function definition but not the
  registration call.
- **Pydantic `model_config`** declarations.
- **Enum members** that are referenced via string lookup (`Enum("foo")`).

To get useful signal from vulture in this codebase, we need a `--ignore-names`
allowlist for these patterns. That's a Sprint H4 P3.2 follow-up.

### Real findings (manually triaged from the 60% list)

The following look like genuine dead code worth verifying:

- `app/auth/rbac.py:39` `require_tenant_member` — confirmed dead
  (the H0 routers all have inline duplicates; the canonical helper
  is what Sprint H3 P2.5 will consolidate to)
- `app/deps.py:92` `get_tenant_or_404` — same situation
- `app/main.py:286,295,304` exception handlers — false positive
  (registered via `add_exception_handler`)

### Acceptance threshold

- Block on `--min-confidence 80` regressions (currently 0 → must stay 0)
- Warn on 60% confidence
- Sprint H4 P3.2 will add `--ignore-names` allowlist for ORM/FastAPI patterns

---

## Xenon (cyclomatic complexity)

Command:
```bash
xenon app --max-absolute B --max-modules B --max-average A
```

Failing thresholds (= functions ranked **C** or worse):

| Rank | Count |
|---|---|
| **E** | 2 |
| **D** | 4 |
| **C** | 28 |
| **Total above B** | **34 functions + 2 modules** |

### Top offenders (E + D rank)

| File:Line | Function | Rank | Notes |
|---|---|---|---|
| `app/routers/applications.py:88` | `create_application` | **E** | Main app creation handler — does too much (DB write + K8s + GitOps + audit + service connection) |
| `app/services/pipeline.py:41` | `run_pipeline` | **E** | Build+deploy orchestration — should split into stage classes |
| `app/services/managed_service.py:244` | `_sync_from_pod` | **D** | DB status sync from pod conditions |
| `app/services/managed_service.py:445` | `_crd_sync_status` | **D** | CRD-based status sync (Redis/RabbitMQ) |
| `app/services/detection_service.py:68` | `detect_dependencies` | **D** | Multi-language dep detector |
| `app/services/deploy_service.py:111` | `wait_for_ready` | **D** | Pod readiness polling with many failure modes |
| `app/routers/observability.py:151` | `get_pods` | **D** | Pod list + metrics merge |

### Real offenders worth refactoring

Most of these are honest complexity debt — handlers that grew over time.
The top targets:

1. **`run_pipeline`** (E) — split into StageClone, StageBuild, StagePush, StageDeploy
2. **`create_application`** (E) — extract `_provision_initial_state()` helper
3. **`_sync_from_pod` / `_crd_sync_status`** (D) — extract per-DB-type strategy classes

Sprint H3 P2.5 (`_get_tenant_or_404` consolidation) will incidentally
reduce the C-rank count by ~6 (the duplicated helpers each contribute
one).

### Acceptance threshold

- CI gate: `xenon --max-absolute C` (block any NEW E/D/C functions, allow grandfathered)
- Eventually tighten to `--max-absolute B` once the existing E/D are refactored

---

## Mypy strict (type checking)

Command:
```bash
mypy app --strict
```

| Result |  |
|---|---|
| Errors | **361** |
| Files | 58 of 101 |

`mypy --strict` is **way too strict** for this codebase as the entry point.
Most errors are:

- Missing return type annotations on FastAPI handlers (`-> None` etc.)
- `Any` returns from `httpx.AsyncClient.json()`
- SQLAlchemy ORM attribute typing (need `sqlalchemy[mypy]` plugin)
- Pydantic v2 internals
- Decorator typing for `@router.get(...)` etc.

### Strategy

NOT enabling `--strict` repo-wide. Instead:

1. **Sprint H4 P3.2**: enable `mypy --no-strict-optional --check-untyped-defs`
   on `app/auth/`, `app/models/`, `app/schemas/` only — these are pure types
2. **Sprint H4 follow-up**: per-module strictness via `[[tool.mypy.overrides]]`
   for `app.routers.*` and `app.services.*`
3. **Long term**: install `sqlalchemy[mypy]` plugin + Pydantic plugin to handle
   ORM/schema patterns
4. **Goal**: zero errors on the auth layer first (highest security value),
   then expand outward

### Acceptance threshold

- `mypy app/auth/ --strict` → must be 0 (gate)
- `mypy app/models/` `--check-untyped-defs` → must be 0 (gate)
- `mypy app/ --strict` → 361 baseline, track delta only

---

## Snapshot files

Full output captured at this commit (in `/tmp/` during the H4a session):

| File | Size | Description |
|---|---|---|
| `/tmp/bandit-high-full.txt` | 7.5 KB | Full HIGH severity findings |
| `/tmp/vulture-60.txt` | 25 KB | All 309 entries at min-confidence 60 |
| `/tmp/xenon-baseline.txt` | (empty — output goes to stderr) | See raw shell output |
| `/tmp/mypy-strict.txt` | 42 KB | All 361 type errors |

These are NOT committed to the repo (too noisy + generated). Sprint H4
P3.2 will add the CI workflow that re-runs them on every PR and reports
deltas in the GitHub Security tab via SARIF upload.

---

## Next steps (Sprint H4 P3.2 / P3.3)

- [ ] **P3.2**: `.github/workflows/code-quality.yml` — runs all 4 tools in parallel, uploads SARIF
- [ ] **P3.3**: `.pre-commit-config.yaml` — gitleaks (secret scan) + ruff format
- [ ] **Follow-up**: `vulture --ignore-names` allowlist for ORM/FastAPI patterns
- [ ] **Follow-up**: per-module mypy strictness in `[tool.mypy.overrides]`
- [ ] **Sprint H1e**: address the 11 high-severity B501 findings (cert-manager TLS)
- [ ] **Sprint H3 P2.5**: `_get_tenant_or_404` consolidation will incidentally cut ~6 xenon C-rank functions
