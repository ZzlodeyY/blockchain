import json
from pathlib import Path

import pytest
from web3 import Web3
from web3.exceptions import ContractLogicError, Web3RPCError

ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "build/contracts/MMMsisToken.json"
ZERO_ADDRESS = "0x" + "0" * 40


@pytest.fixture(scope="module")
def w3():
    connection = Web3(
        Web3.HTTPProvider("http://127.0.0.1:7545", request_kwargs={"timeout": 10})
    )
    if not connection.is_connected():
        pytest.fail("Открой Ganache на http://127.0.0.1:7545 перед запуском тестов.")
    assert connection.net.version == "5777", "Ожидалась локальная сеть 5777."
    return connection


@pytest.fixture(scope="module")
def accounts(w3):
    available = w3.eth.accounts
    assert len(available) >= 2, "Нужны два разблокированных аккаунта Ganache."
    return available[:2]


@pytest.fixture
def token(w3, accounts):
    """Отдельный новый контракт для каждого теста, без изменения артефакта Truffle."""
    if not ARTIFACT_PATH.is_file():
        pytest.fail("Сначала скомпилируй контракт через Truffle.")
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    factory = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = factory.constructor().transact({"from": accounts[0]})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    assert receipt["status"] == 1, "Не удалось развернуть тестовый контракт."
    return w3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])


def balances(token, accounts):
    return tuple(token.functions.balanceOf(account).call() for account in accounts)


def test_initial_supply_and_metadata(token, accounts):
    assert token.functions.name().call() == "MMMsis token"
    assert token.functions.symbol().call() == "MMMSIS"
    assert token.functions.decimals().call() == 0
    assert token.functions.totalSupply().call() == 1000
    assert balances(token, accounts) == (1000, 0)


@pytest.mark.parametrize("amount", [0, 67, 1000])
def test_transfer_and_event(w3, token, accounts, amount):
    sender, recipient = accounts
    transfer = token.functions.transfer(recipient, amount)
    assert transfer.call({"from": sender}) is True

    tx_hash = transfer.transact({"from": sender})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    assert receipt["status"] == 1
    assert balances(token, accounts) == (1000 - amount, amount)
    assert token.functions.totalSupply().call() == 1000

    events = token.events.Transfer().process_receipt(receipt)
    assert len(events) == 1
    assert dict(events[0]["args"]) == {
        "from": sender,
        "to": recipient,
        "value": amount,
    }


@pytest.mark.parametrize("sender_index, amount", [(0, 1001), (1, 1)])
def test_rejects_insufficient_balance(token, accounts, sender_index, amount):
    sender = accounts[sender_index]
    recipient = accounts[1 - sender_index]

    # При оценке gas Ganache выполняет код и отклоняет заведомо ошибочный вызов.
    with pytest.raises((ContractLogicError, Web3RPCError), match="Insufficient balance"):
        token.functions.transfer(recipient, amount).transact({"from": sender})

    assert balances(token, accounts) == (1000, 0)
    assert token.functions.totalSupply().call() == 1000


def test_rejects_zero_address(token, accounts):
    with pytest.raises(
        (ContractLogicError, Web3RPCError), match="Recipient cannot be zero address"
    ):
        token.functions.transfer(ZERO_ADDRESS, 67).transact({"from": accounts[0]})

    assert balances(token, accounts) == (1000, 0)
    assert token.functions.totalSupply().call() == 1000


def test_self_transfer_preserves_balance(w3, token, accounts):
    sender = accounts[0]
    tx_hash = token.functions.transfer(sender, 67).transact({"from": sender})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    assert receipt["status"] == 1
    assert balances(token, accounts) == (1000, 0)
    assert token.functions.totalSupply().call() == 1000
