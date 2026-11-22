// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// Local harness pool. Withdraw pays the caller and forgets to reduce liabilities.
contract VulnerablePool {
    mapping(address => uint256) public balanceOf;
    uint256 public liabilities;

    function deposit() external payable {
        balanceOf[msg.sender] += msg.value;
        liabilities += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        (bool ok,) = payable(msg.sender).call{value: amount}("");
        require(ok, "send");
    }
}
