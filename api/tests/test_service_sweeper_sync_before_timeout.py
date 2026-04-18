"""Regression test: service sweeper calls sync_details BEFORE age-based timeout.

2026-04-18 overnight sprint: Kafka cluster was alive on cluster (Kafka CR
status.conditions[type=Ready] == True) but API's background sweeper kept
marking it `failed` because age check ran before sync_details — even after
retry() put it back to provisioning, the creation timestamp was unchanged
so age was still 2h+ and > service_provision_timeout.

Fix: sync_details first, then timeout check. A service that has actually
reached ready on the cluster should get promoted to READY even if it took
longer than the timeout window.
"""

from __future__ import annotations

from pathlib import Path

MAIN_PY = Path(__file__).parent.parent / "app" / "main.py"


def test_sweeper_calls_sync_before_timeout():
    """The sweeper must call sync_details BEFORE the age-based FAILED stamp."""
    src = MAIN_PY.read_text()
    sync_call = src.index("provisioner.sync_details")
    timeout_stamp = src.index('"Service timed out after')
    assert sync_call < timeout_stamp, (
        "sync_details must run BEFORE timeout stamp; otherwise services that "
        "reach ready past the sweeper window never get promoted to READY"
    )
