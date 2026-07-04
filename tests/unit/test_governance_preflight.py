from __future__ import annotations

import subprocess


def test_governance_preflight_passes_with_local_fallback() -> None:
    result = subprocess.run(
        ["/usr/bin/bash", "scripts/governance-preflight.sh"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Governance preflight passed." in result.stdout
