// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract MMMsisAccess is ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable token;
    address public immutable owner;
    uint256 public constant REGISTRATION_PRICE = 67 * 10 ** 18;

    mapping(address => bool) private registrations;

    event Registered(address indexed user, uint256 amount);

    constructor(address tokenAddress) {
        require(tokenAddress.code.length > 0, "Token must be a contract");
        token = IERC20(tokenAddress);
        owner = msg.sender;
    }

    function register() external nonReentrant {
        require(!registrations[msg.sender], "Already registered");

        // SafeERC20 отменит операцию, если списание токенов не удалось.
        token.safeTransferFrom(msg.sender, owner, REGISTRATION_PRICE);
        registrations[msg.sender] = true;

        emit Registered(msg.sender, REGISTRATION_PRICE);
    }

    function isRegistered(address account) external view returns (bool) {
        return registrations[account];
    }
}
