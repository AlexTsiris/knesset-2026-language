"""Синтетические данные для проверки пайплайна.

ЭТО ВЫДУМАННЫЕ ТВИТЫ. Ни одно предложение здесь не является настоящей цитатой
какого-либо политика. Файл существует ровно для одного: прогнать
prepare -> analyze -> report и убедиться, что конвейер работает, до того как
поднимать аккаунты X.

  python -m src.collect.make_sample
  python -m src.collect.make_sample --per-politician 120
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random

from src.config import CFG, DATA_RAW

# Шаблоны по риторическим ролям. Заполняются подстановками, чтобы получить
# правдоподобное распределение частот, а не одинаковые строки.
TEMPLATES = {
    "attack": [
        "{opp} ממשיך לשקר לציבור. זה כישלון מוחלט של {opp}",
        "המחדל של {opp} לא יישכח. הגיע הזמן שיתפטר",
        "{opp} מסוכן למדינה. אנחנו לא ניתן לזה לקרות",
        "בושה. {opp} בחר בפוליטיקה במקום באחריות",
    ],
    "program": [
        "אנחנו נקדם תוכנית אמיתית להורדת יוקר החיים",
        "נבנה מדינה חזקה יותר. זו התוכנית שלנו",
        "אבטיח לכם: נחזיר את הביטחון לרחובות",
        "נשקם את הכלכלה ונוריד את המחירים",
    ],
    "hostages": [
        "נחזיר את החטופים הביתה. כל החטופים, עד האחרון",
        "משפחות החטופים ראויות לתשובות. אנחנו איתכם",
        "אין שום דבר חשוב יותר מהשבת החטופים הביתה",
    ],
    "security": [
        "צה\"ל פועל בעוצמה נגד חמאס. אנחנו מנצחים",
        "הביטחון של אזרחי ישראל הוא מעל הכל",
        "נמשיך לפעול נגד הטרור בכל הזירות",
        "איראן היא האיום המרכזי. לא ניתן לה להתחמש",
    ],
    "draft": [
        "חוק הגיוס חייב לעבור. שוויון בנטל עכשיו",
        "לא ייתכן שחלק מהציבור לא מתגייס. זו לא מדינה",
        "לימוד תורה הוא ערך עליון ואנחנו נגן עליו",
    ],
    "judiciary": [
        "בג\"ץ חורג מסמכותו. נחזיר את האיזון בין הרשויות",
        "הדמוקרטיה הישראלית בסכנה. נגן על בית המשפט",
        "רפורמה במערכת המשפט היא הכרח",
    ],
    "campaign": [
        "ב-27 באוקטובר נצא להצביע. כל מנדט קובע",
        "הסקרים לא קובעים. הציבור קובע בקלפי",
        "אנחנו בדרך לניצחון. יחד ננצח",
    ],
    "economy": [
        "יוקר החיים שובר את מעמד הביניים. נשנה את זה",
        "התקציב הזה פוגע בחלשים. נילחם בו",
        "מחירי הדיור בלתי אפשריים לצעירים",
    ],
}

# Профиль каждого политика: веса тем + стилевые параметры.
# Специально сделаны разными, чтобы метрики показали различия.
PROFILES = {
    "netanyahu":  {"w": {"security": 5, "hostages": 2, "campaign": 3, "attack": 3, "program": 2, "judiciary": 1}, "excl": 1.2, "emoji": 0.1, "en": 0.25},
    "bennett":    {"w": {"attack": 4, "program": 4, "campaign": 3, "economy": 2, "draft": 2}, "excl": 0.6, "emoji": 0.2, "en": 0.15},
    "lapid":      {"w": {"attack": 4, "economy": 3, "judiciary": 3, "campaign": 2, "hostages": 2}, "excl": 0.8, "emoji": 0.1, "en": 0.2},
    "lieberman":  {"w": {"draft": 5, "attack": 4, "economy": 2, "security": 2}, "excl": 0.4, "emoji": 0.0, "en": 0.05},
    "golan":      {"w": {"judiciary": 4, "hostages": 4, "attack": 3, "program": 2}, "excl": 0.9, "emoji": 0.3, "en": 0.1},
    "smotrich":   {"w": {"economy": 4, "security": 3, "judiciary": 3, "draft": 2}, "excl": 0.5, "emoji": 0.0, "en": 0.1},
    "ben_gvir":   {"w": {"security": 6, "attack": 3, "judiciary": 2, "campaign": 2}, "excl": 2.1, "emoji": 0.4, "en": 0.05},
    "abbas":      {"w": {"economy": 3, "program": 3, "campaign": 2, "hostages": 1}, "excl": 0.3, "emoji": 0.1, "en": 0.1},
    "tibi":       {"w": {"attack": 4, "judiciary": 3, "campaign": 2, "economy": 2}, "excl": 0.7, "emoji": 0.0, "en": 0.15},
    "maoz":       {"w": {"draft": 3, "judiciary": 2, "campaign": 2}, "excl": 0.4, "emoji": 0.0, "en": 0.0},
    "haskel":     {"w": {"program": 4, "economy": 3, "campaign": 3, "security": 2}, "excl": 0.6, "emoji": 0.2, "en": 0.35},
}

EN_TEMPLATES = [
    "Israel will not apologize for defending itself.",
    "We must bring all the hostages home. Now.",
    "The world must stand with Israel against terror.",
    "Our economy needs real reform, not slogans.",
]

HASHTAGS = ["בחירות2026", "החזירו_אותם_הביתה", "שוויון_בנטל", "יוקר_החיים",
            "ביטחון", "27באוקטובר"]


def pick_opponent(pid: str, rng: random.Random) -> str:
    others = [p for p in CFG.politicians if p.id != pid and p.id in PROFILES]
    if not others:
        return "היריב"
    return rng.choice(others).name_he.split()[-1]


def make_tweet(pid: str, prof: dict, when: dt.datetime, rng: random.Random,
               idx: int) -> dict:
    if rng.random() < prof["en"]:
        text = rng.choice(EN_TEMPLATES)
    else:
        cats = list(prof["w"].keys())
        weights = list(prof["w"].values())
        cat = rng.choices(cats, weights=weights)[0]
        text = rng.choice(TEMPLATES[cat]).format(opp=pick_opponent(pid, rng))
        if rng.random() < 0.3:
            text += " #" + rng.choice(HASHTAGS)

    text += "!" * min(3, int(rng.random() * prof["excl"] * 2))
    if rng.random() < prof["emoji"]:
        text += " " + rng.choice(["🇮🇱", "💪", "🙏", "🔥"])

    is_rt = rng.random() < 0.12
    is_reply = rng.random() < 0.10
    base = rng.randint(200, 9000)

    return {
        "politician_id": pid,
        "tweet_id": f"SYNTH{pid}{idx:05d}",
        "url": f"https://x.com/SYNTHETIC/status/{idx}",
        "date": when.isoformat(),
        "author_handle": CFG.by_id(pid).handle,
        "text": text,
        "lang_x": "he",
        "likes": base, "retweets": base // 6, "replies": base // 12,
        "quotes": base // 20, "bookmarks": base // 30, "views": base * 40,
        "is_retweet": is_rt,
        "retweet_of": (pick_opponent(pid, rng) if is_rt else None),
        "is_quote": rng.random() < 0.08, "quote_of": None,
        "is_reply": is_reply, "reply_to_handle": None,
        "mentions": [], "hashtags": [h for h in HASHTAGS if "#" + h in text],
        "links": [], "has_media": rng.random() < 0.35,
        "_synthetic": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-politician", type=int, default=90)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    camp = CFG.campaign
    span = (camp.end - camp.start).days or 1

    total = 0
    for pid, prof in PROFILES.items():
        try:
            CFG.by_id(pid)
        except KeyError:
            continue
        n = int(args.per_politician * rng.uniform(0.5, 1.5))
        rows = []
        for i in range(n):
            when = dt.datetime.combine(
                camp.start + dt.timedelta(days=rng.randint(0, span)),
                dt.time(rng.randint(5, 23), rng.randint(0, 59)),
            )
            rows.append(make_tweet(pid, prof, when, rng, i))
        out = DATA_RAW / f"{pid}.jsonl"
        with open(out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        total += len(rows)
        print(f"  {pid:12s} {len(rows):4d} синтетических твитов")

    print(f"\nВСЕГО {total} ВЫДУМАННЫХ твитов в {DATA_RAW}")
    print("Это НЕ реальные данные. Удали data/raw/*.jsonl перед настоящим сбором.")


if __name__ == "__main__":
    main()
