import json
from pathlib import Path

from web3 import Web3
from web3.contract import Contract

RPC_URL = "http://127.0.0.1:7545"
ARTIFACT_PATH = Path(__file__).resolve().parent / "build/contracts/MMMsisToken.json"
TOTAL_SUPPLY = 1000
TRANSFER_AMOUNT = 67


def load_contract(w3: Web3) -> Contract:
    if not ARTIFACT_PATH.is_file():
        raise RuntimeError("Нет результата сборки. Сначала выполни truffle compile.")

    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    network_id = w3.net.version
    deployment = artifact["networks"].get(network_id)
    if deployment is None:
        raise RuntimeError(f"Контракт не развёрнут в сети {network_id}.")

    address = Web3.to_checksum_address(deployment["address"])
    if not w3.eth.get_code(address):
        raise RuntimeError(
            "По сохранённому адресу нет контракта. "
            "Если Ganache был сброшен, разверни контракт заново."
        )

    return w3.eth.contract(address=address, abi=artifact["abi"])


def get_balances(contract: Contract, sender: str, recipient: str) -> tuple[int, int]:
    return (
        contract.functions.balanceOf(sender).call(),
        contract.functions.balanceOf(recipient).call(),
    )


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        raise RuntimeError(f"Нет подключения к Ganache: {RPC_URL}")

    contract = load_contract(w3)
    accounts = w3.eth.accounts
    if len(accounts) < 2:
        raise RuntimeError("Для перевода нужны два аккаунта Ganache.")
    sender, recipient = accounts[:2]

    before = get_balances(contract, sender, recipient)
    total_supply = contract.functions.totalSupply().call()
    expected = (TOTAL_SUPPLY - TRANSFER_AMOUNT, TRANSFER_AMOUNT)

    print(f"Контракт: {contract.address}")
    print(f"Аккаунт №0: {sender}")
    print(f"Аккаунт №1: {recipient}")
    print(f"Балансы до перевода: {before[0]} и {before[1]} MMMSIS")

    if total_supply != TOTAL_SUPPLY or contract.functions.decimals().call() != 0:
        raise RuntimeError("Эмиссия или единицы токена отличаются от условий лабораторной.")
    if before == expected:
        print("Балансы уже 933 и 67. Повторный перевод не отправлен.")
        return
    if before != (TOTAL_SUPPLY, 0):
        raise RuntimeError("Ожидались начальные балансы 1000 и 0. Перевод не отправлен.")

    # Ganache подписывает транзакцию своим разблокированным тестовым аккаунтом.
    tx_hash = contract.functions.transfer(recipient, TRANSFER_AMOUNT).transact(
        {"from": sender}
    )
    print(f"Transaction hash: {Web3.to_hex(tx_hash)}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt["status"] != 1:
        raise RuntimeError("Транзакция завершилась неуспешно.")

    after = get_balances(contract, sender, recipient)
    total_supply = contract.functions.totalSupply().call()
    if after != expected or total_supply != TOTAL_SUPPLY:
        raise RuntimeError("Итоговые балансы или эмиссия не соответствуют ожидаемым.")

    print(f"Block number: {receipt['blockNumber']}")
    print(f"Gas used: {receipt['gasUsed']}")
    print(f"Status: {receipt['status']} (успешно)")
    print(f"Балансы после перевода: {after[0]} и {after[1]} MMMSIS")
    print(f"Общая эмиссия: {total_supply} MMMSIS")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Ошибка: {error}") from error
