# /haven-check — Haven 15/15 Compliance Verification

## TL;DR

```bash
make haven                 # Default: human-readable scoreboard
make haven-json            # JSON output (pipe to jq)
make haven-cis             # + CIS Kubernetes Benchmark
make haven-all             # + CIS + Kubescape (full external)
make haven-rationale       # Show rationale for every check (no run)
make haven-version         # Show pinned CLI version
make haven-install         # Force re-download (after bumping haven/VERSION)
```

First run auto-downloads official **VNG Haven Compliancy Checker** (currently `haven/VERSION` = v12.8.0) from GitLab packages to `haven/bin/haven`.

## Source of truth

- Official docs: https://haven.commonground.nl/techniek/compliancy-checker
- Official repo: https://gitlab.com/commonground/haven/haven
- Local wrapper: `haven/` folder (this repo)

**Check definitions, exit codes, output format — all owned upstream by the VNG Common Ground team.** DO NOT reimplement checks in this repo. The previous custom bash audit has been deleted (it was less accurate than the binary).

## Upgrading the pinned CLI version

```bash
echo v12.9.0 > haven/VERSION
make haven-install
make haven
```

## Known FAILs (deferred to future sprints, not bugs in this sprint)

See `haven/remediation/` for per-item pointer docs:

- `01-multi-az.md` — `multiaz` ACCEPTED (Hetzner fsn1 single region)
- `07-private-networking.md` — `privatenetworking` investigation needed
- `13-log-aggregation.md` — `logs` deferred to Sprint H-obs-loki

## Current baseline (2026-04-13, iyziops prod)

**12/15 PASS** per official Haven CLI v12.8.0 output. Full report: `haven/reports/baseline-20260413.{txt,json}`.
