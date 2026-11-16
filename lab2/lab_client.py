import json
from pathlib import Path

from web3 import Web3
from web3.contract import Contract
from web3.contract.contract import ContractFunction
from web3.logs import DISCARD
from web3.types import TxReceipt

RPC_URL = "http://127.0.0.1:7545"
ARTIFACT_DIR = Path(__file__).resolve().parent / "build/contracts"
TOTAL_SUPPLY = 2026
REGISTRATION_PRICE = 67
DECIMALS = 18


def to_units(amount: int, decimals: int = DECIMALS) -> int:
    """Суммы сценария целые; для расчётов не используем float."""
    return amount * 10 ** decimals


def format_tokens(amount: int, decimals: int = DECIMALS) -> str:
    whole, fraction = divmod(amount, 10 ** decimals)
    if not fraction:
        return str(whole)
    return f"{whole}.{fraction:0{decimals}d}".rstrip("0")


def connect() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        raise RuntimeError(f"Открой Ganache на {RPC_URL}.")
    if w3.net.version != "5777" or w3.eth.chain_id != 1337:
        raise RuntimeError("Ожидалась локальная сеть Ganache: network 5777, chain 1337.")
    return w3


def load_artifact(name: str) -> dict:
    path = ARTIFACT_DIR / f"{name}.json"
    if not path.is_file():
        raise RuntimeError(f"Нет {path.name}. Сначала выполни truffle compile из lab2.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract(w3: Web3, name: str) -> Contract:
    artifact = load_artifact(name)
    deployment = artifact.get("networks", {}).get(w3.net.version)
    if deployment is None:
        raise RuntimeError(f"{name} не развёрнут. Выполни миграцию из lab2.")
    address = Web3.to_checksum_address(deployment["address"])
    if not w3.eth.get_code(address):
        raise RuntimeError(f"По адресу {name} нет кода. После сброса Ganache нужен деплой.")
    return w3.eth.contract(address=address, abi=artifact["abi"])


def balances(token: Contract, owner: str, user: str) -> tuple[int, int]:
    return (
        token.functions.balanceOf(owner).call(),
        token.functions.balanceOf(user).call(),
    )


def transact(
    w3: Web3, function: ContractFunction, sender: str, label: str
) -> TxReceipt:
    tx_hash = function.transact({"from": sender, "value": 0})
    print(f"\n{label}")
    print(f"Transaction hash: {Web3.to_hex(tx_hash)}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    print(f"Block number: {receipt['blockNumber']}")
    print(f"Gas used: {receipt['gasUsed']}; status: {receipt['status']}")
    if receipt["status"] != 1:
        raise RuntimeError(f"Операция «{label}» не выполнена.")
    if w3.eth.get_transaction(tx_hash)["value"] != 0:
        raise RuntimeError("В демонстрации не должно быть оплаты услуги в ETH.")
    return receipt


def event_args(contract: Contract, event_name: str, receipt: TxReceipt) -> list[dict]:
    event = getattr(contract.events, event_name)()
    return [
        dict(log["args"])
        for log in event.process_receipt(receipt, errors=DISCARD)
        if log["address"].lower() == contract.address.lower()
    ]
