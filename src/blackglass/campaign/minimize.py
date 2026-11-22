"""Shrink a failing call list to the shortest list that still breaks the property."""

from __future__ import annotations

from collections.abc import Callable

from blackglass.campaign.models import CallStep

Breaks = Callable[[list[CallStep]], bool]


def shrink(steps: list[CallStep], breaks: Breaks) -> list[CallStep]:
    if not steps or not breaks(steps):
        return list(steps)
    current = list(steps)
    changed = True
    while changed and len(current) > 1:
        changed = False
        for index in range(len(current)):
            trial = current[:index] + current[index + 1 :]
            if trial and breaks(trial):
                current = trial
                changed = True
                break
    return current


def render_minimized_test(steps: list[CallStep]) -> str:
    """A Forge test that replays the shrunk sequence against both pools."""
    body = ["        vm.deal(address(this), 100 ether);"]
    for step in steps:
        amount = "1 ether" if step.arg is None else str(step.arg)
        if step.name == "deposit":
            body.append(f"        pool.deposit{{value: {amount}}}();")
        elif step.name == "withdraw":
            body.append(f"        pool.withdraw({amount});")
    replay = "\n".join(body)
    return f"""// SPDX-License-Identifier: MIT
// Replay artifact. Copy this file to lab/lending/test before running it.
pragma solidity 0.8.24;

import {{VulnerablePool}} from "../src/VulnerablePool.sol";
import {{PatchedPool}} from "../src/PatchedPool.sol";

interface Vm {{
    function deal(address account, uint256 newBalance) external;
}}

contract MinimizedVulnerable {{
    Vm internal constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    VulnerablePool internal pool;

    constructor() {{
        pool = new VulnerablePool();
    }}

    receive() external payable {{}}

    function IS_TEST() external pure returns (bool) {{
        return true;
    }}

    function test_minimized() public {{
{replay}
        assert(address(pool).balance >= pool.liabilities());
    }}
}}

contract MinimizedPatched {{
    Vm internal constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    PatchedPool internal pool;

    constructor() {{
        pool = new PatchedPool();
    }}

    receive() external payable {{}}

    function IS_TEST() external pure returns (bool) {{
        return true;
    }}

    function test_minimized() public {{
{replay}
        assert(address(pool).balance >= pool.liabilities());
    }}
}}
"""
