# =============================================================================
#  iyziops CI runner — non-sensitive values (git-tracked)
# =============================================================================
#  Sensitive values (hcloud_token, github_runner_token) come from Keychain
#  via TF_VAR_* exported by the iyziops-env shell function.
# =============================================================================

name        = "iyziops-ci-runner"
github_repo = "NimbusProTch/InfraForge-Haven"

location    = "fsn1"
server_type = "cx23"
os_image    = "ubuntu-24.04"

runner_count   = 3
runner_labels  = ["self-hosted", "iyziops", "haven"]
runner_version = "2.321.0"
