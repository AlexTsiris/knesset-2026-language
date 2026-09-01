"""Запись cookies сессии X в config/cookies/<username>.txt

Запускать САМОМУ, в своём терминале:

    python setup_cookies.py

Скрипт спросит логин и два cookie и сам создаст файл с правильным именем и
форматом. Значения вводятся скрыто (не отображаются и не попадают в историю
терминала).

Где взять cookies:
    открой x.com в браузере, где ты уже вошёл
    F12 -> Application -> Cookies -> https://x.com
    нужны две строки: auth_token и ct0 (копируется столбец Value)
"""
from __future__ import annotations

import re
import sys
from getpass import getpass
from pathlib import Path

COOKIES_DIR = Path(__file__).resolve().parent / "config" / "cookies"

# Признаки того, что человек скопировал не то: подсказку вместо значения.
PLACEHOLDERS = {"значение", "znachenie", "value", "auth_token", "ct0",
                "здесь", "тут", "xxx", "..."}


def ask(prompt: str, *, secret: bool, min_len: int) -> str:
    """Спрашивает значение и не отдаёт управление, пока оно не осмысленно."""
    while True:
        raw = (getpass(prompt) if secret else input(prompt)).strip()
        # из DevTools часто копируется в кавычках или как "name=value"
        raw = raw.strip('"\'' ).strip()
        if "=" in raw and not raw.startswith("http"):
            name, _, val = raw.partition("=")
            if name.strip() in ("auth_token", "ct0"):
                raw = val.strip()

        if not raw:
            print("  пусто, попробуй ещё раз")
            continue
        if raw.lower() in PLACEHOLDERS:
            print(f"  {raw!r} -- это подсказка из инструкции, а не значение.")
            print("  нужно то, что стоит в столбце Value у этой cookie.")
            continue
        if len(raw) < min_len:
            print(f"  слишком коротко ({len(raw)} симв., ожидается от {min_len}).")
            print("  похоже, скопировалось не полностью.")
            continue
        return raw


def main() -> None:
    print(__doc__)
    print("-" * 68)

    DEFAULT_USERNAME = "alextsiris"
    raw_user = input(f"Логин X без @ [Enter = {DEFAULT_USERNAME}]: ").strip()
    username = (raw_user or DEFAULT_USERNAME).lstrip("@")
    if "@" in username:
        sys.exit("Это похоже на email. Нужен логин X -- то, что в адресе "
                 "твоего профиля: x.com/<логин>.")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
        sys.exit("Логин X состоит из латиницы, цифр и _ (до 15 символов). "
                 f"Получено: {username!r}")

    print()
    print("Дальше два значения. Вводятся скрыто -- на экране ничего не появится,")
    print("это нормально. Вставляй (Ctrl+V или правая кнопка) и жми Enter.")
    print()
    auth_token = ask("  auth_token: ", secret=True, min_len=30)
    ct0 = ask("  ct0       : ", secret=True, min_len=30)

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    out = COOKIES_DIR / f"{username}.txt"
    out.write_text(f"auth_token={auth_token}; ct0={ct0}", encoding="utf-8")

    print()
    print(f"Записано: {out}")
    print(f"  логин       : {username}")
    print(f"  auth_token  : {len(auth_token)} симв.")
    print(f"  ct0         : {len(ct0)} симв.")
    print()
    print("Файл в .gitignore. Дальше:")
    print("  python -m src.collect.scrape cookies")

    # Пустой файл-недоразумение из прошлых попыток только мешает
    for stray in COOKIES_DIR.iterdir():
        if stray.is_file() and stray != out and stray.stat().st_size == 0:
            stray.unlink()
            print(f"(удалён пустой файл {stray.name})")


if __name__ == "__main__":
    main()
