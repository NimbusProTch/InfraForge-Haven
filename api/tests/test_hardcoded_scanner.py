"""Regression tests for scripts/hardcoded-scan.sh and its fixture smoke test.

Architect follow-up (NB-1 / NB-2) on PR #176:
  NB-1 — scripts/test_hardcoded_scan.sh fixture reference lines must carry
         `# hardcoded-scan: allow` markers so they do not themselves count as
         P0 hits.
  NB-2 — the in-script assertion that `api/app/config.py` rejection-list
         literals are suppressed must be content-based (not pinned to the
         line numbers 82-83, which drift as config.py changes).

These pytest cases guard the scanner against regressions in a language
(Python/CI) we already run on every push, instead of relying solely on the
shell smoke test.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "hardcoded-scan.sh"
SMOKE_TEST = REPO_ROOT / "scripts" / "test_hardcoded_scan.sh"
BASELINE = REPO_ROOT / "scripts" / ".hardcoded-baseline.txt"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_scanner_runs_and_emits_report_header() -> None:
    result = _run([str(SCANNER)])
    assert result.returncode == 0, f"scanner failed: {result.stderr}"
    assert "=== Hardcoded scan report ===" in result.stdout


def test_scanner_diff_clean_against_baseline() -> None:
    """If this fails, someone introduced new hardcoded literals or the
    committed baseline drifted. Fix the literal or re-run --baseline."""
    result = _run([str(SCANNER), "--diff"])
    assert result.returncode == 0, (
        f"scanner --diff reported new hits beyond baseline.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_scanner_smoke_test_script_passes() -> None:
    result = _run([str(SMOKE_TEST)])
    assert result.returncode == 0, (
        f"scripts/test_hardcoded_scan.sh failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_smoke_test_script_itself_not_flagged_as_p0() -> None:
    """NB-1 guard: the fixture reference lines in test_hardcoded_scan.sh
    must carry allow-markers so they are not themselves counted as hits."""
    result = _run([str(SCANNER)])
    assert result.returncode == 0
    offending = [line for line in result.stdout.splitlines() if "scripts/test_hardcoded_scan.sh" in line]
    assert offending == [], (
        "scripts/test_hardcoded_scan.sh fixture lines are being counted as P0 "
        "hits. Add `# hardcoded-scan: allow` markers to the offending lines.\n" + "\n".join(offending)
    )


def test_baseline_header_counts_match_live_scan() -> None:
    """If someone hand-edits the baseline body without regenerating the
    header, or adds a literal and forgets `--baseline`, counts diverge. This
    test catches both."""
    header_text = "\n".join(BASELINE.read_text().splitlines()[:5])
    assert "# hardcoded-scan baseline" in header_text

    scan_stdout = _run([str(SCANNER)]).stdout
    count_re = re.compile(r"P0=(\d+)\s+P1=(\d+)\s+total=(\d+)")

    scan_match = count_re.search(scan_stdout)
    assert scan_match, f"could not parse scan output:\n{scan_stdout}"

    header_match = count_re.search(header_text)
    assert header_match, f"could not parse baseline header:\n{header_text}"

    assert scan_match.groups() == header_match.groups(), (
        f"Baseline header drifted from live scan. "
        f"Scan: P0={scan_match.group(1)} P1={scan_match.group(2)} "
        f"total={scan_match.group(3)} vs Baseline header: "
        f"P0={header_match.group(1)} P1={header_match.group(2)} "
        f"total={header_match.group(3)}. "
        "Run `scripts/hardcoded-scan.sh --baseline` to rebaseline."
    )
