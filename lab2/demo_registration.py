import argparse

from web3 import Web3
from web3.contract import Contract

from lab_client import (
    DECIMALS,
    REGISTRATION_PRICE,
    TOTAL_SUPPLY,
    balances,
    connect,
    event_args,
    format_tokens,
    load_contract,
    to_units,
    transact,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def current_state(token: Contract, access: Contract, owner: str, user: str) -> tuple:
    return (
        *balances(token, owner, user),
        token.functions.allowance(user, access.address).call(),
        access.functions.isRegistered(user).call(),
    )


def show_state(label: str, state: tuple) -> None:
    owner_balance, user_balance, allowance, registered = state
    print(f"\n{label}")
    print(f"Владелец: {format_tokens(owner_balance)} MMMSIS")
    print(f"Пользователь: {format_tokens(user_balance)} MMMSIS")
    print(f"Разрешение сервису: {format_tokens(allowance)} MMMSIS")
    print(f"Зарегистрирован: {registered}")


def run_demo(
    w3: Web3,
    token: Contract,
    access: Contract,
    owner: str,
    user: str,
    *,
    check_only: bool = False,
) -> None:
    supply, price = to_units(TOTAL_SUPPLY), to_units(REGISTRATION_PRICE)
    require(owner != user, "Нужны разные аккаунты владельца и пользователя.")
    require(token.functions.name().call() == "MMMsis token", "Не то название токена.")
    require(token.functions.symbol().call() == "MMMSIS", "Не тот символ токена.")
    require(token.functions.decimals().call() == DECIMALS, "Ожидалось 18 знаков.")
    require(token.functions.totalSupply().call() == supply, "Ожидалось 2026 MMMSIS.")
    require(access.functions.token().call() == token.address, "Сервис связан с другим токеном.")
    require(access.functions.owner().call() == owner, "Аккаунт №0 должен владеть сервисом.")
    require(access.functions.REGISTRATION_PRICE().call() == price, "Цена должна быть 67 MMMSIS.")
    require(token.functions.balanceOf(access.address).call() == 0, "Неожиданный баланс сервиса.")

    initial = (supply, 0, 0, False)
    funded = (supply - price, price, 0, False)
    approved = (supply - price, price, price, False)
    complete = (supply, 0, 0, True)

    state = current_state(token, access, owner, user)
    print(f"Токен: {token.address}")
    print(f"Сервис: {access.address}")
    print(f"Владелец (аккаунт №0): {owner}")
    print(f"Пользователь (аккаунт №1): {user}")
    show_state("Состояние при запуске", state)
    require(
        state in (initial, funded, approved, complete),
        "Состояние отличается от сценария. Новые транзакции не отправлены. "
        "Проверь аккаунты или разверни новую пару контрактов.",
    )
    if check_only:
        print("Проверка завершена. Транзакции не отправлялись.")
        return
    if state == complete:
        print("Демонстрация уже завершена. Повторные переводы не отправлены.")
        return

    if state == initial:
        receipt = transact(w3, token.functions.transfer(user, price), owner, "Перевод 67 MMMSIS")
        require(
            event_args(token, "Transfer", receipt) == [{"from": owner, "to": user, "value": price}],
            "Не найден ожидаемый Transfer пользователю.",
        )
        state = current_state(token, access, owner, user)
        require(state == funded, "Неверное состояние после перевода.")
        show_state("После перевода", state)

    if state == funded:
        receipt = transact(
            w3, token.functions.approve(access.address, price), user, "Разрешение на 67 MMMSIS"
        )
        require(
            event_args(token, "Approval", receipt)
            == [{"owner": user, "spender": access.address, "value": price}],
            "Не найден ожидаемый Approval.",
        )
        state = current_state(token, access, owner, user)
        require(state == approved, "Неверное состояние после approve.")
        show_state("После разрешения", state)

    if state == approved:
        receipt = transact(w3, access.functions.register(), user, "Оплата и регистрация")
        require(
            event_args(token, "Transfer", receipt) == [{"from": user, "to": owner, "value": price}],
            "Не найден ожидаемый Transfer оплаты.",
        )
        require(
            event_args(access, "Registered", receipt) == [{"user": user, "amount": price}],
            "Не найден ожидаемый Registered.",
        )

    final = current_state(token, access, owner, user)
    require(final == complete, "Итоговое состояние не соответствует сценарию.")
    require(token.functions.totalSupply().call() == supply, "Эмиссия изменилась.")
    require(token.functions.balanceOf(access.address).call() == 0, "Оплата осталась в сервисе.")
    show_state("Итог", final)
    print(f"Общая эмиссия: {TOTAL_SUPPLY} MMMSIS")
    print("Оплата услуги — 67 MMMSIS. ETH использован только для газа.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Оплата регистрации токенами MMMSIS")
    parser.add_argument("--check", action="store_true", help="Только чтение, без транзакций")
    args = parser.parse_args()

    w3 = connect()
    accounts = w3.eth.accounts
    require(len(accounts) >= 2, "Нужны два разблокированных аккаунта Ganache.")
    run_demo(
        w3,
        load_contract(w3, "MMMsisToken"),
        load_contract(w3, "MMMsisAccess"),
        accounts[0],
        accounts[1],
        check_only=args.check,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Ошибка: {error}") from error
