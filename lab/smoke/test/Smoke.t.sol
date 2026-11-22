// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Smoke} from "../src/Smoke.sol";

contract SmokeTest {
    function test_ping() external {
        Smoke target = new Smoke();
        require(target.ping() == 1, "ping");
    }
}
