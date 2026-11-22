"""Read Foundry text output. The runner never treats a compile error as a failed property."""

from __future__ import annotations

import re

from blackglass.campaign.models import CallStep

_RESULT = re.compile(
    r"\[(?P<kind>PASS|FAIL)[^\]]*\]\s*(?P<name>test_[A-Za-z0-9_]+|invariant_[A-Za-z0-9_]+)\("
)
_CALL = re.compile(
    r"calldata=(?P<name>[A-Za-z_][A-Za-z0-9_]*)\([^)]*\)\s+args=\[(?P<args>[^\]]*)\]"
)
_NUMBER = re.compile(r"\d+")


def suite_failed(output: str, return_code: int) -> bool | None:
    """True when a test failed, False when the suite passed, None when Forge did not report tests."""
    if "Compiler run failed" in output or "Compilation failed" in output:
        return None
    found = {match.group("name"): match.group("kind") == "FAIL" for match in _RESULT.finditer(output)}
    if found:
        return any(found.values())
    if return_code == 0 and "[PASS]" in output and "[FAIL" not in output:
        return False
    if return_code != 0 and "[FAIL" in output:
        return True
    return None


def parse_sequence(output: str) -> list[CallStep]:
    steps: list[CallStep] = []
    for match in _CALL.finditer(output):
        number = _NUMBER.search(match.group("args"))
        steps.append(
            CallStep(
                name=match.group("name"),
                arg=int(number.group()) if number else None,
            )
        )
    return steps
