// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MMMsisToken is ERC20 {
    constructor() ERC20("MMMsis token", "MMMSIS") {
        _mint(msg.sender, 2026 * 10 ** decimals());
    }
}
