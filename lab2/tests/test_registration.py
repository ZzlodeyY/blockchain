import pytest
from web3 import Web3
from web3.exceptions import Web3RPCError

from demo_registration import current_state, run_demo
from lab_client import (
    REGISTRATION_PRICE,
    TOTAL_SUPPLY,
    balances,
    connect,
    event_args,
    load_artifact,
    to_units,
)

ZERO_ADDRESS = "0x" + "0" * 40
SUPPLY = to_units(TOTAL_SUPPLY)
PRICE = to_units(REGISTRATION_PRICE)


@pytest.fixture(scope="module")
def w3():
    return connect()


@pytest.fixture(scope="module")
def accounts(w3):
    available = w3.eth.accounts
    assert len(available) >= 3, "Для тестов нужны три аккаунта Ganache."
    return available[:3]


def successful(w3, function, sender):
    tx_hash = function.transact({"from": sender, "value": 0})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    assert receipt["status"] == 1
    assert w3.eth.get_transaction(tx_hash)["value"] == 0
    return receipt


def factory(w3, name):
    artifact = load_artifact(name)
    return w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])


@pytest.fixture
def system(w3, accounts):
    """Новая пара контрактов на каждый тест; адреса Truffle не переписываются."""
    token_factory = factory(w3, "MMMsisToken")
    token_receipt = successful(w3, token_factory.constructor(), accounts[0])
    token = w3.eth.contract(address=token_receipt["contractAddress"], abi=token_factory.abi)

    access_factory = factory(w3, "MMMsisAccess")
    access_receipt = successful(w3, access_factory.constructor(token.address), accounts[0])
    access = w3.eth.contract(address=access_receipt["contractAddress"], abi=access_factory.abi)
    return token, access


def fund_and_approve(w3, token, access, accounts, *, funding=PRICE, approval=PRICE):
    owner, user = accounts[:2]
    successful(w3, token.functions.transfer(user, funding), owner)
    successful(w3, token.functions.approve(access.address, approval), user)


def snapshot(w3, token, access, accounts):
    owner, user, third = accounts
    return (
        tuple(token.functions.balanceOf(account).call() for account in [*accounts, access.address]),
        token.functions.allowance(user, access.address).call(),
        token.functions.allowance(owner, third).call(),
        tuple(access.functions.isRegistered(account).call() for account in accounts),
        token.functions.totalSupply().call(),
        w3.eth.get_balance(access.address),
    )


def reverted_receipt(w3, send_transaction):
    try:
        tx_hash = send_transaction()
    except Web3RPCError as error:
        # Ganache может вернуть RPC-ошибку уже включённой в блок транзакции.
        response = error.rpc_response or {}
        data = response.get("error", {}).get("data")
        if not isinstance(data, dict) or data.get("message") != "revert":
            raise
        tx_hash = data.get("hash")
        if not isinstance(tx_hash, str) or len(tx_hash) != 66:
            raise

    # Исключение само по себе не доказывает отказ: нужна настоящая квитанция.
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    assert receipt["status"] == 0
    assert receipt["logs"] == []
    return receipt


def assert_reverted_unchanged(w3, token, access, accounts, function, sender):
    before = snapshot(w3, token, access, accounts)
    # Явный gas позволяет отправить ошибочную операцию в блок, минуя оценку gas.
    reverted_receipt(
        w3, lambda: function.transact({"from": sender, "gas": 500_000, "value": 0})
    )
    assert snapshot(w3, token, access, accounts) == before


def test_initial_supply_metadata_and_service(system, accounts):
    token, access = system
    owner, user = accounts[:2]
    assert token.functions.name().call() == "MMMsis token"
    assert token.functions.symbol().call() == "MMMSIS"
    assert token.functions.decimals().call() == 18
    assert token.functions.totalSupply().call() == SUPPLY
    assert balances(token, owner, user) == (SUPPLY, 0)
    assert access.functions.owner().call() == owner
    assert access.functions.token().call() == token.address
    assert access.functions.REGISTRATION_PRICE().call() == PRICE
    assert access.functions.isRegistered(user).call() is False


def test_erc20_interface_and_no_external_mint(system):
    token, _ = system
    functions = {item["name"] for item in token.abi if item["type"] == "function"}
    events = {item["name"] for item in token.abi if item["type"] == "event"}
    assert {
        "name", "symbol", "decimals", "totalSupply", "balanceOf",
        "transfer", "approve", "allowance", "transferFrom",
    } <= functions
    assert {"Transfer", "Approval"} <= events
    assert "mint" not in functions


@pytest.mark.parametrize("amount", [0, REGISTRATION_PRICE, TOTAL_SUPPLY])
def test_transfer_balances_supply_and_event(w3, system, accounts, amount):
    token, _ = system
    owner, user = accounts[:2]
    units = to_units(amount)
    assert token.functions.transfer(user, units).call({"from": owner}) is True
    receipt = successful(w3, token.functions.transfer(user, units), owner)
    assert balances(token, owner, user) == (SUPPLY - units, units)
    assert token.functions.totalSupply().call() == SUPPLY
    assert event_args(token, "Transfer", receipt) == [{"from": owner, "to": user, "value": units}]


def test_approve_sets_allowance_without_moving_tokens(w3, system, accounts):
    token, access = system
    owner = accounts[0]
    assert token.functions.approve(access.address, PRICE).call({"from": owner}) is True
    receipt = successful(w3, token.functions.approve(access.address, PRICE), owner)
    assert token.functions.allowance(owner, access.address).call() == PRICE
    assert balances(token, *accounts[:2]) == (SUPPLY, 0)
    assert event_args(token, "Approval", receipt) == [
        {"owner": owner, "spender": access.address, "value": PRICE}
    ]


def test_transfer_from_spends_only_the_approved_amount(w3, system, accounts):
    token, _ = system
    owner, user, spender = accounts
    successful(w3, token.functions.approve(spender, to_units(100)), owner)
    assert token.functions.transferFrom(owner, user, PRICE).call({"from": spender}) is True
    receipt = successful(w3, token.functions.transferFrom(owner, user, PRICE), spender)
    assert token.functions.allowance(owner, spender).call() == to_units(33)
    assert balances(token, owner, user) == (SUPPLY - PRICE, PRICE)
    assert token.functions.totalSupply().call() == SUPPLY
    assert event_args(token, "Transfer", receipt) == [{"from": owner, "to": user, "value": PRICE}]


def test_transfer_from_without_permission_is_rejected(w3, system, accounts):
    token, access = system
    owner, user, spender = accounts
    assert_reverted_unchanged(
        w3, token, access, accounts, token.functions.transferFrom(owner, user, PRICE), spender
    )


@pytest.mark.parametrize("case", ["zero_address", "insufficient_balance"])
def test_invalid_transfer_is_rejected(w3, system, accounts, case):
    token, access = system
    recipient = ZERO_ADDRESS if case == "zero_address" else accounts[1]
    amount = PRICE if case == "zero_address" else SUPPLY + 1
    assert_reverted_unchanged(
        w3, token, access, accounts, token.functions.transfer(recipient, amount), accounts[0]
    )


def test_approval_to_zero_address_is_rejected(w3, system, accounts):
    token, access = system
    assert_reverted_unchanged(
        w3, token, access, accounts, token.functions.approve(ZERO_ADDRESS, PRICE), accounts[0]
    )


def test_registration_transfers_payment_and_emits_both_events(w3, system, accounts):
    token, access = system
    owner, user = accounts[:2]
    fund_and_approve(w3, token, access, accounts)
    assert current_state(token, access, owner, user) == (SUPPLY - PRICE, PRICE, PRICE, False)

    receipt = successful(w3, access.functions.register(), user)

    assert current_state(token, access, owner, user) == (SUPPLY, 0, 0, True)
    assert token.functions.totalSupply().call() == SUPPLY
    assert token.functions.balanceOf(access.address).call() == 0
    assert w3.eth.get_balance(access.address) == 0
    assert w3.eth.get_transaction(receipt["transactionHash"])["to"] == access.address
    assert event_args(token, "Transfer", receipt) == [{"from": user, "to": owner, "value": PRICE}]
    assert event_args(access, "Registered", receipt) == [{"user": user, "amount": PRICE}]


@pytest.mark.parametrize("case", ["no_allowance", "insufficient_allowance", "insufficient_balance"])
def test_failed_payment_does_not_register_or_change_state(w3, system, accounts, case):
    token, access = system
    funding = PRICE - 1 if case == "insufficient_balance" else PRICE
    approval = {"no_allowance": 0, "insufficient_allowance": PRICE - 1, "insufficient_balance": PRICE}[case]
    fund_and_approve(w3, token, access, accounts, funding=funding, approval=approval)

    assert_reverted_unchanged(w3, token, access, accounts, access.functions.register(), accounts[1])
    assert access.functions.isRegistered(accounts[1]).call() is False


def test_repeated_registration_is_rejected_even_with_funds_and_approval(w3, system, accounts):
    token, access = system
    fund_and_approve(w3, token, access, accounts)
    successful(w3, access.functions.register(), accounts[1])
    fund_and_approve(w3, token, access, accounts)

    assert_reverted_unchanged(w3, token, access, accounts, access.functions.register(), accounts[1])
    assert access.functions.isRegistered(accounts[1]).call() is True


def test_registration_is_stored_separately_for_each_user(w3, system, accounts):
    token, access = system
    owner = accounts[0]
    for user in accounts[1:]:
        successful(w3, token.functions.transfer(user, PRICE), owner)
        successful(w3, token.functions.approve(access.address, PRICE), user)
        successful(w3, access.functions.register(), user)
        assert access.functions.isRegistered(user).call() is True
        assert token.functions.balanceOf(user).call() == 0
    assert token.functions.balanceOf(owner).call() == SUPPLY
    assert access.functions.isRegistered(owner).call() is False


def test_registration_rejects_eth_as_payment(w3, system, accounts):
    token, access = system
    fund_and_approve(w3, token, access, accounts)
    before = snapshot(w3, token, access, accounts)
    # Отправляем сырой вызов: ABI иначе отклонит value ещё на стороне Python.
    reverted_receipt(w3, lambda: w3.eth.send_transaction({
        "from": accounts[1],
        "to": access.address,
        "data": access.encode_abi("register"),
        "value": 1,
        "gas": 500_000,
    }))
    assert snapshot(w3, token, access, accounts) == before


@pytest.mark.parametrize("address_kind", ["zero", "account"])
def test_service_cannot_be_deployed_without_a_token_contract(w3, accounts, address_kind):
    address = ZERO_ADDRESS if address_kind == "zero" else accounts[2]
    reverted_receipt(
        w3,
        lambda: factory(w3, "MMMsisAccess").constructor(address).transact({
            "from": accounts[0], "gas": 3_000_000,
        }),
    )


@pytest.mark.parametrize("stage", ["initial", "funded", "approved"])
def test_demo_continues_without_repeating_completed_steps(w3, system, accounts, stage):
    token, access = system
    owner, user = accounts[:2]
    if stage in {"funded", "approved"}:
        successful(w3, token.functions.transfer(user, PRICE), owner)
    if stage == "approved":
        successful(w3, token.functions.approve(access.address, PRICE), user)
    before = tuple(w3.eth.get_transaction_count(account) for account in [owner, user])

    run_demo(w3, token, access, owner, user)

    after = tuple(w3.eth.get_transaction_count(account) for account in [owner, user])
    expected = {"initial": (1, 2), "funded": (0, 2), "approved": (0, 1)}[stage]
    assert tuple(end - start for start, end in zip(before, after)) == expected
    assert current_state(token, access, owner, user) == (SUPPLY, 0, 0, True)


def test_completed_demo_does_not_send_more_transactions(w3, system, accounts):
    token, access = system
    owner, user = accounts[:2]
    run_demo(w3, token, access, owner, user)
    before = tuple(w3.eth.get_transaction_count(account) for account in [owner, user])

    run_demo(w3, token, access, owner, user)

    assert tuple(w3.eth.get_transaction_count(account) for account in [owner, user]) == before
    assert current_state(token, access, owner, user) == (SUPPLY, 0, 0, True)


def test_check_mode_does_not_send_transactions(w3, system, accounts):
    token, access = system
    owner, user = accounts[:2]
    before = snapshot(w3, token, access, accounts)
    nonces = tuple(w3.eth.get_transaction_count(account) for account in [owner, user])

    run_demo(w3, token, access, owner, user, check_only=True)

    assert snapshot(w3, token, access, accounts) == before
    assert tuple(w3.eth.get_transaction_count(account) for account in [owner, user]) == nonces
