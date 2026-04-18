"""Tests for the longhorn-multipath-fixer DaemonSet + cloud-init multipath quarantine.

Both halves were added to close the worker-2 Longhorn deadlock that surfaced
during the permanent demo bring-up (2026-04-18). Multipath-tools (an
open-iscsi Recommends from the Hetzner Ubuntu base image) had created a stale
mpath* device-mapper table on worker-2 that blocked mke2fs on every Longhorn
volume. These tests guard against future regressions of either half.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DAEMONSET_PATH = REPO_ROOT / "platform" / "argocd" / "apps" / "platform" / "node-prep" / "daemonset.yaml"
APPSET_PATH = REPO_ROOT / "platform" / "argocd" / "appsets" / "platform-raw.yaml"
CLOUD_INIT_TEMPLATES = [
    REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "master-cloud-init.yaml.tpl",
    REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "worker-cloud-init.yaml.tpl",
    REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "joining-master-cloud-init.yaml.tpl",
]


def _load_daemonset() -> dict:
    docs = list(yaml.safe_load_all(DAEMONSET_PATH.read_text()))
    daemonsets = [d for d in docs if d and d.get("kind") == "DaemonSet"]
    assert len(daemonsets) == 1, "exactly one DaemonSet expected in daemonset.yaml"
    return daemonsets[0]


def test_daemonset_yaml_parses_and_is_in_longhorn_system():
    ds = _load_daemonset()
    assert ds["metadata"]["name"] == "longhorn-multipath-fixer"
    # longhorn-system is PSA privileged AND outside the haven.io/managed=true
    # Kyverno gate, so a privileged DS is permitted there. Don't move it
    # without re-checking namespace policy + Kyverno webhook namespaceSelector.
    assert ds["metadata"]["namespace"] == "longhorn-system"


def test_daemonset_uses_initcontainer_plus_pause_pattern():
    """One-shot work in initContainer; pause as presence marker. Re-runs on
    pod restart (e.g. node reboot). NOT a 60s-loop CPU spinner."""
    ds = _load_daemonset()
    init = ds["spec"]["template"]["spec"]["initContainers"]
    assert len(init) == 1
    assert init[0]["name"] == "fix-multipath"

    main = ds["spec"]["template"]["spec"]["containers"]
    assert len(main) == 1
    assert main[0]["name"] == "pause"
    assert main[0]["image"].startswith("registry.k8s.io/pause"), "main container must be the K8s pause image"


def test_daemonset_does_not_mount_etc_hostpath():
    """Regression guard: mounting /etc rw is dangerous (could clobber sshd_config,
    sudoers, etc.). The DaemonSet writes /etc/* via nsenter into the host mount
    namespace instead — see Plan-agent critique 2026-04-18."""
    ds = _load_daemonset()
    for vol in ds["spec"]["template"]["spec"].get("volumes", []):
        hp = vol.get("hostPath", {}).get("path", "")
        assert hp != "/etc", f"hostPath /etc forbidden — found in volume {vol.get('name')}"
        assert not hp.startswith("/etc/"), f"hostPath under /etc forbidden — found {hp}"


def test_daemonset_volumes_are_dev_rw_and_sys_ro_only():
    ds = _load_daemonset()
    spec = ds["spec"]["template"]["spec"]
    vols = {v["name"]: v for v in spec.get("volumes", [])}
    assert set(vols.keys()) == {"dev", "sys"}, f"unexpected volume set: {set(vols.keys())}"
    assert vols["dev"]["hostPath"]["path"] == "/dev"
    assert vols["sys"]["hostPath"]["path"] == "/sys"

    # initContainer should mount /dev rw (default), /sys ro
    init = spec["initContainers"][0]
    mounts = {m["name"]: m for m in init.get("volumeMounts", [])}
    assert mounts["dev"]["mountPath"] == "/dev"
    assert mounts["dev"].get("readOnly", False) is False
    assert mounts["sys"]["mountPath"] == "/sys"
    assert mounts["sys"].get("readOnly") is True, "/sys must be readOnly (we only read dm-* metadata)"


def test_daemonset_has_hostpid_for_nsenter():
    """nsenter -t 1 needs hostPID to see PID 1 of the host."""
    ds = _load_daemonset()
    assert ds["spec"]["template"]["spec"].get("hostPID") is True


def test_daemonset_tolerations_cover_noschedule_and_noexecute():
    """Must land on every node, including cordoned (NoSchedule) and tainted
    (NoExecute) ones. operator: Exists with both effects."""
    ds = _load_daemonset()
    tols = ds["spec"]["template"]["spec"].get("tolerations", [])
    effects = {t.get("effect") for t in tols if t.get("operator") == "Exists"}
    assert "NoSchedule" in effects
    assert "NoExecute" in effects


def test_daemonset_pause_container_is_psa_restricted_compatible():
    """The presence-marker container itself must NOT be privileged. Only the
    initContainer needs that. Otherwise we'd be running a root pid forever."""
    ds = _load_daemonset()
    pause = ds["spec"]["template"]["spec"]["containers"][0]
    sec = pause.get("securityContext", {})
    assert sec.get("runAsNonRoot") is True
    assert sec.get("allowPrivilegeEscalation") is False
    assert sec.get("readOnlyRootFilesystem") is True
    assert sec.get("capabilities", {}).get("drop") == ["ALL"]


def test_daemonset_init_script_has_safety_guards_and_mpath_filter():
    """The init script must:
    1. Filter to names starting with `mpath` (no mpath_*, lvm_*, crypt_*).
    2. Check dmsetup open-count == 0 before remove (don't kill busy devices).
    3. nsenter -t 1 -m for host mount namespace work.
    4. apt-get -y purge multipath-tools idempotently.
    """
    script = "\n".join(_load_daemonset()["spec"]["template"]["spec"]["initContainers"][0]["args"])
    assert "mpath*" in script, "must filter to mpath* dm names"
    assert "dmsetup info -c --noheadings -o open" in script, "open-count safety check missing"
    assert "dmsetup remove" in script, "must call dmsetup remove on stale tables"
    assert "nsenter -t 1 -m" in script, "must enter host mount namespace via nsenter"
    assert "apt-get -y purge multipath-tools" in script, "must purge multipath-tools when present"
    assert "/etc/apt/preferences.d/99-no-multipath" in script, "must write apt pin file"
    assert "/etc/multipath.conf" in script, "must write multipath blacklist conf"


def test_platform_raw_appset_lists_node_prep():
    """The DaemonSet only deploys if the platform-raw ApplicationSet picks it up.
    Guard against accidental removal of the list element."""
    appset = yaml.safe_load(APPSET_PATH.read_text())
    elements = appset["spec"]["generators"][0]["list"]["elements"]
    node_prep = next((e for e in elements if e["name"] == "node-prep"), None)
    assert node_prep is not None, "platform-raw appset must include the 'node-prep' element"
    assert node_prep["namespace"] == "longhorn-system"
    assert node_prep["syncWave"] == "0"
    assert node_prep["path"] == "platform/argocd/apps/platform/node-prep"


def test_cloud_init_templates_have_apt_pin_for_multipath():
    """Every cloud-init template must write the Pin-Priority -1 file so apt
    cannot reinstall multipath-tools (e.g. as an open-iscsi Recommends).
    Without this, multipath-tools comes back on the next apt upgrade."""
    for tpl in CLOUD_INIT_TEMPLATES:
        assert tpl.exists(), f"missing {tpl}"
        body = tpl.read_text()
        assert "/etc/apt/preferences.d/99-no-multipath" in body, f"missing apt pin in {tpl.name}"
        assert "Package: multipath-tools" in body, f"missing pin Package line in {tpl.name}"
        assert "Pin-Priority: -1" in body, f"missing -1 priority in {tpl.name}"


def test_cloud_init_templates_have_multipath_blacklist():
    for tpl in CLOUD_INIT_TEMPLATES:
        body = tpl.read_text()
        assert "/etc/multipath.conf" in body, f"missing multipath.conf write in {tpl.name}"
        assert 'devnode "^sd[a-z0-9]+"' in body, f"missing sd* blacklist in {tpl.name}"


def test_cloud_init_templates_purge_multipath_tools_in_runcmd():
    """Defense-in-depth on top of the pin file: if the package shipped pre-installed
    in the base image, the pin file alone won't remove it — runcmd does."""
    for tpl in CLOUD_INIT_TEMPLATES:
        body = tpl.read_text()
        assert "apt-get -y purge multipath-tools" in body, f"missing purge in {tpl.name}"
