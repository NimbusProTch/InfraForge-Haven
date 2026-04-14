# iyziops (Haven Platform)

![VNG Haven 15/15](https://img.shields.io/badge/VNG_Haven-15%2F15-brightgreen?logo=kubernetes&logoColor=white)
![CNCF Kubernetes](https://img.shields.io/badge/Kubernetes-RKE2_v1.32-326CE5?logo=kubernetes&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue.svg)

Haven-compliant self-service DevOps platform (PaaS) for Dutch municipalities.
Heroku/Railway-like experience on top of Kubernetes, with EU data sovereignty
guaranteed via Hetzner (dev) and Cyso Cloud Amsterdam (prod).

## Compliance

This repository targets the **VNG Haven 15/15 baseline** as verified by the
official upstream [`haven` CLI](https://gitlab.com/commonground/haven/haven).
Run the compliance gate with:

```bash
make haven          # 15/15 score (human output)
make haven-json     # same, machine-readable JSON
make haven-cis      # + external CIS Kubernetes Benchmark
```

## Infra quick start

```bash
make infra-plan     # tofu plan against environments/prod
make infra-apply    # tofu apply
make kubeconfig     # SCP kubeconfig from first master
make haven          # verify 15/15
```

## Project memory

- `CLAUDE.md` — project instructions (Turkish)
- `.claude/CLAUDE.md` — architecture decisions (English)
- `docs/sprints/` — sprint history + active roadmap
- `haven/` — official Haven CLI binary, baseline reports, remediation notes
