# Logs Directory Convention

All scratch output from CLI tools lives in `logs/` at the repo root. The directory is gitignored (only `.gitkeep` is tracked). Its purpose is to keep project directories clean and to give every command a known place to write its output.

## Rules

1. **Scratch output goes to `logs/`**, not into any project directory.
2. `logs/` is gitignored. Only `logs/.gitkeep` is tracked.
3. **After task completion, delete all files in `logs/`.** Leave only `.gitkeep`. A task is not "done" until `ls logs/ | wc -l` returns 1.
4. Never write output into `infrastructure/environments/*/`, `runner/`, `api/`, `ui/`, or any other project directory.

## Naming conventions

| Kind | Pattern |
|---|---|
| Tofu plan | `logs/tofu-plan-<env>-<YYYYMMDDHHMM>.tfplan` |
| Tofu apply log | `logs/tofu-apply-<env>-<YYYYMMDDHHMM>.log` |
| Tofu destroy log | `logs/tofu-destroy-<env>-<YYYYMMDDHHMM>.log` |
| Kubectl debug dump | `logs/kubectl-<topic>-<YYYYMMDDHHMM>.log` |
| Helm render | `logs/helm-render-<chart>-<YYYYMMDDHHMM>.yaml` |
| Generic scratch | `logs/scratch-<topic>-<YYYYMMDDHHMM>.txt` |

## Verification at task end

Before marking any task done, run:

```bash
ls logs/ | wc -l    # must be 1 (only .gitkeep)
```

If there are leftover files, either delete them or move useful content into `docs/` / commit messages and then delete.
