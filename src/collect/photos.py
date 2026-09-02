"""Скачивает фото профилей политиков из X в docs/assets/photos/<id>.jpg.

Публичные фигуры, официальные аккаунты; аватары для аналитического дашборда.
  python -m src.collect.photos
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
import httpx
from src.config import CFG, ROOT

OUT = ROOT / "docs" / "assets" / "photos"


async def main() -> None:
    from twscrape import API
    api = API(str(ROOT / "config" / "accounts.db"))
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for p in CFG.with_handles:
            try:
                u = await api.user_by_login(p.handle)
            except Exception as e:
                print(f"  {p.id}: ошибка {e}"); continue
            if not u or not getattr(u, "profileImageUrl", None):
                print(f"  {p.id}: нет фото"); continue
            # _normal.jpg -> _400x400.jpg (крупнее)
            url = u.profileImageUrl.replace("_normal.", "_400x400.")
            try:
                r = await client.get(url)
                r.raise_for_status()
                (OUT / f"{p.id}.jpg").write_bytes(r.content)
                meta[p.id] = {"handle": p.handle, "displayname": u.displayname,
                              "followers": u.followersCount}
                print(f"  {p.id}: {len(r.content)//1024} КБ  ({u.followersCount:,} подписчиков)")
            except Exception as e:
                print(f"  {p.id}: скачивание не удалось {e}")
    import json
    (OUT / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nскачано: {len(meta)} фото -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
