// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {VulnerablePool} from "../src/VulnerablePool.sol";

interface Vm {
    function deal(address account, uint256 newBalance) external;
}

contract VulnerableSequence {
    Vm internal constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);

    receive() external payable {}

    function IS_TEST() external pure returns (bool) {
        return true;
    }

    function test_solvency_sequence() public {
        VulnerablePool pool = new VulnerablePool();
        vm.deal(address(this), 1 ether);
        pool.deposit{value: 1 ether}();
        pool.withdraw(1 ether);
        assert(address(pool).balance >= pool.liabilities());
    }
}

contract VulnerableInvariant {
    Vm internal constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    VulnerablePool public pool;

    function setUp() public {
        pool = new VulnerablePool();
        vm.deal(address(this), 100 ether);
    }

    receive() external payable {}

    function IS_TEST() external pure returns (bool) {
        return true;
    }

    function deposit(uint96 amount) public {
        uint256 size = _bound(amount, 1, 1 ether);
        if (address(this).balance < size) return;
        pool.deposit{value: size}();
    }

    function withdraw(uint96 amount) public {
        uint256 balance = pool.balanceOf(address(this));
        if (balance == 0) return;
        pool.withdraw(_bound(amount, 1, balance));
    }

    function property_solvency() public view returns (bool) {
        return address(pool).balance >= pool.liabilities();
    }

    function invariant_solvency() public view {
        assert(address(pool).balance >= pool.liabilities());
    }

    function _bound(uint256 value, uint256 low, uint256 high) internal pure returns (uint256) {
        if (high <= low) return low;
        return low + (value % (high - low + 1));
    }
}
