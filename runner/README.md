# iyziops CI runner

Single Hetzner VM that hosts the self-hosted GitHub Actions runner pool for this repo. Separated from the platform cluster on purpose — compromised CI workloads must never share state or SSH keys with production.

## Files

| File | Purpose |
|---|---|
| `backend.tf` | Hetzner Object Storage S3 backend (`iyziops-tfstate-runner`) |
| `providers.tf` | hcloud only |
| `versions.tf` | Provider pins |
| `variables.tf` | All inputs |
| `main.tf` | SSH key, cloud-init render, VM |
| `outputs.tf` | Public IPv4, SSH key path |
| `runner.auto.tfvars` | Non-sensitive config (git-tracked) |
| `templates/runner-cloud-init.yaml.tpl` | cloud-init (Docker, crane, Node 20, GitHub runner systemd units) |

## Bootstrap

### 1. Get a one-shot GitHub runner registration token

```
gh api -X POST repos/NimbusProTch/InfraForge-Haven/actions/runners/registration-token --jq .token
```

Store it in Keychain:

```
security add-generic-password -U -a iyziops -s github-runner-token -w "<token>"
```

The `iyziops-env` shell function exports it as `TF_VAR_github_runner_token`.

⚠️ The token is single-use and expires in ~1 hour. If `tofu apply` fails, grab a fresh one before retrying.

### 2. Gitignore negation — make runner.auto.tfvars git-tracked

`runner.auto.tfvars` lives at `/runner/runner.auto.tfvars`. The repo `.gitignore` already handles prod; add a similar negation for the runner path (done in the same commit that introduced this file).

### 3. Apply

```
iyziops-env                                  # load Keychain creds
cd runner
tofu init                                    # remote backend
tofu plan -out=../logs/tofu-plan-runner-$(date +%Y%m%d%H%M).tfplan
tofu apply ../logs/tofu-plan-runner-$(date +%Y%m%d%H%M).tfplan
```

First apply takes ~3-4 min: VM boot (~60 s) + cloud-init install (~2 min) + runner registration (~30 s).

### 4. Verify

- GitHub → Settings → Actions → Runners — three runners with labels `self-hosted, iyziops`.
- SSH: `ssh -i ../logs/iyziops-runner-ssh.pem root@<runner_public_ipv4>`
- `systemctl status github-runner-1 github-runner-2 github-runner-3`

## Destroy

```
tofu destroy -auto-approve
```

Reminder: after destroy, remove the runners from the GitHub repo settings — they linger as "offline" until manually deleted.
