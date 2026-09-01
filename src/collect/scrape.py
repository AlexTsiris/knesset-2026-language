"""Сбор твитов лидеров партий за окно предвыборной кампании.

Гостевой доступ X закрыт: без залогиненной сессии скрейпинг не работает.
Два способа дать доступ (достаточно одного):

  A. cookies (надёжнее, пароль не нужен)
     config/cookies/<username>.txt -- cookies открытой сессии X.
     Обязательны auth_token и ct0. Парольный вход часто упирается в капчу
     и подтверждение по почте, вход по cookies -- нет.

  B. пароль
     config/accounts.txt, по строке на аккаунт:
       username:password:email:email_password

Использование:
  python -m src.collect.scrape cookies   # вход по cookies сессии (без пароля)
  python -m src.collect.scrape login     # вход по паролю из accounts.txt
  python -m src.collect.scrape verify    # проверить хэндлы из politicians.yaml
  python -m src.collect.scrape collect   # собрать твиты в data/raw/*.jsonl
  python -m src.collect.scrape collect --only netanyahu,bennett
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from src.config import CFG, DATA_RAW, CONFIG_DIR

ACCOUNTS_FILE = CONFIG_DIR / "accounts.txt"
DB_FILE = CONFIG_DIR / "accounts.db"
COOKIES_DIR = CONFIG_DIR / "cookies"


def _api():
    try:
        from twscrape import API
    except ImportError:
        sys.exit("Нет twscrape. Установи: pip install twscrape")
    return API(str(DB_FILE))


async def cmd_login() -> None:
    """Заводит аккаунты из accounts.txt в пул и логинит их."""
    if not ACCOUNTS_FILE.exists():
        sys.exit(
            f"Нет {ACCOUNTS_FILE}.\n"
            "Создай файл, по строке на аккаунт:\n"
            "  username:password:email:email_password"
        )
    api = _api()
    added = 0
    for line in ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 4:
            print(f"[login] пропущена строка (нужно 4 поля): {parts[0]}")
            continue
        user, pwd, email, email_pwd = parts[:4]
        try:
            await api.pool.add_account(user, pwd, email, email_pwd)
            added += 1
        except Exception as exc:
            print(f"[login] {user}: {exc}")
    print(f"[login] в пул добавлено/обновлено: {added}")
    await api.pool.login_all()
    print(await api.pool.accounts_info())


async def cmd_cookies() -> None:
    """Заводит аккаунты по cookies уже открытой сессии X -- без пароля.

    twscrape считает аккаунт активным, как только у него есть auth_token и
    ct0, и логин по паролю не выполняется вовсе. Это заметно надёжнее:
    парольный вход часто упирается в капчу и подтверждение по почте.

    Формат: config/cookies/<username>.txt, где <username> -- логин X без @,
    а содержимое -- cookies в любом из видов, которые понимает twscrape:
    строка «auth_token=...; ct0=...», JSON-словарь или выгрузка расширения.
    """
    if not COOKIES_DIR.exists() or not any(COOKIES_DIR.iterdir()):
        sys.exit(
            f"Нет файлов в {COOKIES_DIR}.\n"
            "Положи по файлу на аккаунт: <username>.txt (имя файла = логин X\n"
            "без @), внутри -- cookies сессии. Нужны как минимум auth_token\n"
            "и ct0. Строка вида «auth_token=abc; ct0=def» подойдёт."
        )

    api = _api()
    added = 0
    skipped: list[str] = []
    for f in sorted(COOKIES_DIR.iterdir()):
        if not f.is_file():
            continue
        # О пропусках сообщаем ГРОМКО. Молчаливый skip -- худший вариант:
        # файл на месте, ошибок нет, а в пуле пусто, и причина неочевидна.
        if f.name.startswith("."):
            continue
        if f.suffix.lower() not in (".txt", ".json"):
            skipped.append(f"{f.name} — нет расширения .txt/.json")
            continue
        username = f.stem.lstrip("@")
        raw = f.read_text(encoding="utf-8").strip()
        if not raw:
            skipped.append(f"{f.name} — файл пустой")
            continue
        if "auth_token" not in raw or "ct0" not in raw:
            skipped.append(
                f"{f.name} — внутри нет пары auth_token/ct0. Нужна строка "
                "вида «auth_token=...; ct0=...», одного значения мало"
            )
            continue
        try:
            # пароль и почта не нужны: вход по cookies их не использует
            await api.pool.add_account(
                username, "-", f"{username}@cookies.local", "-", cookies=raw
            )
            added += 1
        except Exception as exc:
            print(f"[cookies] {username}: {exc}")

    if skipped:
        print("[cookies] ПРОПУЩЕНЫ файлы:")
        for msg in skipped:
            print(f"    - {msg}")
    print(f"[cookies] принято файлов: {added}")
    if added == 0:
        sys.exit(
            "Ни один файл не подошёл. Проще не собирать файл вручную:\n"
            "    python setup_cookies.py\n"
            "скрипт спросит логин и оба cookie и запишет всё сам."
        )
    info = await api.pool.accounts_info()
    active = [a for a in info if a.get("active")]
    for a in info:
        mark = "активен" if a.get("active") else "НЕ активен"
        print(f"  {a.get('username')}: {mark}")
    if not active:
        sys.exit(
            "Ни один аккаунт не стал активным. Почти всегда причина одна: "
            "в cookies нет auth_token или ct0 — twscrape требует оба."
        )
    print(f"[cookies] активных аккаунтов: {len(active)} — можно запускать verify")


async def require_pool(api) -> None:
    """Без залогиненных аккаунтов X отдаёт пустоту на КАЖДЫЙ запрос. Если это
    не проверить заранее, verify отрапортует «аккаунт не найден» про все
    хэндлы подряд, и причина будет выглядеть как неверный список политиков,
    а не как отсутствие доступа."""
    try:
        info = await api.pool.accounts_info()
    except Exception as exc:
        sys.exit(f"Не читается пул аккаунтов ({DB_FILE}): {exc}")

    if not info:
        sys.exit(
            "В пуле нет ни одного аккаунта X — собрать ничего не получится.\n"
            "Способ A (без пароля, рекомендуется):\n"
            "  1) python setup_cookies.py\n"
            "  2) python -m src.collect.scrape cookies\n"
            "Способ B (по паролю):\n"
            f"  1) создай {ACCOUNTS_FILE}:\n"
            "     username:password:email:email_password\n"
            "  2) python -m src.collect.scrape login"
        )

    active = [a for a in info if a.get("active")]
    print(f"[пул] аккаунтов: {len(info)}, активных: {len(active)}")
    if not active:
        sys.exit(
            "Ни один аккаунт не активен: логин не прошёл, cookies устарели "
            "или аккаунт заблокирован. Запусти `cookies` / `login` и "
            "посмотри на ошибки."
        )


async def cmd_verify() -> None:
    """Проверяет, что хэндлы существуют, и печатает готовый патч для YAML."""
    api = _api()
    await require_pool(api)
    ok, bad = [], []
    for p in CFG.politicians:
        if not p.handle:
            bad.append((p.id, None, "handle: null в конфиге"))
            continue
        try:
            u = await api.user_by_login(p.handle)
        except Exception as exc:
            bad.append((p.id, p.handle, f"ошибка: {exc}"))
            continue
        if u is None:
            bad.append((p.id, p.handle, "аккаунт не найден"))
        else:
            ok.append((p.id, p.handle, u.displayname, u.followersCount, u.statusesCount))

    print("\n=== НАЙДЕНЫ ===")
    for pid, h, disp, followers, tweets in ok:
        print(f"  {pid:12s} @{h:20s} {disp!r:30s} {followers:>10,} подписчиков, {tweets:>7,} твитов")
    print("\n=== ТРЕБУЮТ ВНИМАНИЯ ===")
    for pid, h, why in bad:
        print(f"  {pid:12s} @{h if h else '-':20s} {why}")
    print(f"\nИтого: {len(ok)} ок, {len(bad)} под вопросом")
    print("Подтверждённым можно ставить verified: true в config/politicians.yaml")


def _tweet_to_row(t, politician_id: str) -> dict:
    """Плоская запись. Сохраняем ВСЁ, что понадобится метрикам, включая
    engagement и структуру ответов/ретвитов."""
    rt = getattr(t, "retweetedTweet", None)
    qt = getattr(t, "quotedTweet", None)
    return {
        "politician_id": politician_id,
        "tweet_id": str(t.id),
        "url": t.url,
        "date": t.date.isoformat() if t.date else None,
        "author_handle": t.user.username if t.user else None,
        "text": t.rawContent,
        "lang_x": getattr(t, "lang", None),
        # engagement
        "likes": getattr(t, "likeCount", 0) or 0,
        "retweets": getattr(t, "retweetCount", 0) or 0,
        "replies": getattr(t, "replyCount", 0) or 0,
        "quotes": getattr(t, "quoteCount", 0) or 0,
        "bookmarks": getattr(t, "bookmarkedCount", 0) or 0,
        "views": getattr(t, "viewCount", 0) or 0,
        # структура
        "is_retweet": rt is not None,
        "retweet_of": (rt.user.username if rt and rt.user else None),
        "is_quote": qt is not None,
        "quote_of": (qt.user.username if qt and qt.user else None),
        "is_reply": getattr(t, "inReplyToTweetId", None) is not None,
        "reply_to_handle": (t.inReplyToUser.username
                            if getattr(t, "inReplyToUser", None) else None),
        # сущности
        "mentions": [u.username for u in (getattr(t, "mentionedUsers", None) or [])],
        "hashtags": list(getattr(t, "hashtags", None) or []),
        "links": [l.url for l in (getattr(t, "links", None) or [])],
        "has_media": bool(getattr(t, "media", None) and (
            t.media.photos or t.media.videos or t.media.animated)),
    }


def merge_existing(path) -> dict[str, dict]:
    """Уже собранные твиты этого политика, ключ -- tweet_id."""
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # обрезанная строка от прерванной записи
            if r.get("tweet_id"):
                out[r["tweet_id"]] = r
    return out


def write_atomic(path, rows) -> None:
    """Пишем в .tmp и переименовываем: прерывание на середине записи не
    оставит покалеченный файл вместо уже собранных данных."""
    tmp = path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


async def collect_one(api, p, since: str, until: str, limit: int) -> list[dict]:
    """Собирает через search-запрос: фильтр по датам делает сам X, экономим запросы."""
    from twscrape import gather

    # Поиск X: until: ЭКСКЛЮЗИВНЫЙ (день добавлен вызывающей стороной), а
    # ретвиты из результатов from: исключены ПО УМОЛЧАНИЮ -- чтобы они попали
    # в выгрузку, нужен явный include:nativeretweets.
    parts = [f"from:{p.handle}", f"since:{since}", f"until:{until}"]
    if CFG.collection.get("include_retweets", True):
        parts.append("include:nativeretweets")
    if not CFG.collection.get("include_replies", True):
        parts.append("-filter:replies")
    q = " ".join(parts)

    rows: list[dict] = []
    try:
        tweets = await gather(api.search(q, limit=limit))
    except Exception as exc:
        print(f"  [{p.id}] search упал ({exc}); пробую user_tweets")
        try:
            u = await api.user_by_login(p.handle)
            if u is None:
                return []
            tweets = await gather(api.user_tweets_and_replies(u.id, limit=limit))
            tweets = [t for t in tweets if t.date
                      and since <= t.date.date().isoformat() <= until]
        except Exception as exc2:
            print(f"  [{p.id}] и user_tweets упал: {exc2}")
            return []

    for t in tweets:
        rows.append(_tweet_to_row(t, p.id))
    return rows


async def cmd_collect(only: str | None) -> None:
    camp = CFG.campaign
    since = camp.start.isoformat()
    # until в X-поиске эксклюзивный, берём день после конца окна
    import datetime as dt
    until = (camp.end + dt.timedelta(days=1)).isoformat()
    limit = CFG.collection["max_tweets_per_account"]
    delay = CFG.collection["delay_between_accounts"]

    targets = CFG.with_handles
    if only:
        wanted = {s.strip() for s in only.split(",")}
        targets = [p for p in targets if p.id in wanted]
    if not targets:
        sys.exit("Нечего собирать: ни у одного политика нет handle.")

    api = _api()
    await require_pool(api)
    print(f"Окно: {since} .. {camp.end} | аккаунтов: {len(targets)} | лимит {limit}/акк")

    total = new_total = 0
    for i, p in enumerate(targets, 1):
        out = DATA_RAW / f"{p.id}.jsonl"
        print(f"[{i}/{len(targets)}] {p.id} (@{p.handle}) ...", end=" ", flush=True)
        rows = await collect_one(api, p, since, until, limit)

        # Кампания идёт до дня выборов, и сбор запускается повторно. Поэтому
        # НЕ перезаписываем: сливаем с уже собранным и дедуплицируем по
        # tweet_id. Иначе неудачный прогон затирал бы хорошие данные, а
        # твиты, удалённые автором после прошлого сбора, исчезали бы из
        # выборки -- это молчаливое искажение корпуса.
        existing = merge_existing(out)
        if not rows and not existing:
            print("0 твитов (ничего не собрано)")
            continue
        if not rows and existing:
            print(f"0 новых; сохранено прежних {len(existing)}")
            continue

        merged = existing | {r["tweet_id"]: r for r in rows}
        added = len(merged) - len(existing)
        write_atomic(out, merged.values())
        print(f"{len(rows)} получено, +{added} новых, всего {len(merged)}")
        total += len(merged)
        new_total += added
        if i < len(targets):
            await asyncio.sleep(delay)

    print(f"\nГотово: в корпусе {total} твитов (+{new_total} за этот прогон), "
          f"{DATA_RAW}")
    if total == 0:
        print("Ноль результатов обычно значит: аккаунты не залогинены "
              "(запусти `login`) или все хэндлы неверны (запусти `verify`).")
    elif new_total == 0:
        print("Новых твитов нет -- либо всё уже собрано, либо X отдаёт пусто.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Сбор твитов израильских политиков")
    ap.add_argument("command",
                    choices=["login", "cookies", "verify", "collect"])
    ap.add_argument("--only", help="список id политиков через запятую")
    args = ap.parse_args()

    if args.command == "login":
        asyncio.run(cmd_login())
    elif args.command == "cookies":
        asyncio.run(cmd_cookies())
    elif args.command == "verify":
        asyncio.run(cmd_verify())
    else:
        asyncio.run(cmd_collect(args.only))


if __name__ == "__main__":
    main()
