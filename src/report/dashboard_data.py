"""Компактный срез analysis.json для интерактивной доски.

Доска читает НЕ весь analysis.json (там методология и сырые keyness по всем n),
а сжатый набор ровно под визуализацию. Так HTML остаётся лёгким.

  python -m src.report.dashboard_data   # -> docs/data.json
"""
from __future__ import annotations

import json

from src.config import CFG, OUTPUTS, ROOT

IN = OUTPUTS / "analysis.json"
OUT = ROOT / "docs" / "data.json"

# Ивритские подписи тем для доски (аудитория — израильская).
TOPIC_HE = {
    "security_war": "ביטחון ומלחמה", "hostages": "חטופים", "gaza": "עזה",
    "economy": "כלכלה ויוקר המחיה", "haredi_draft": "גיוס חרדים",
    "judiciary": "מערכת המשפט", "religion_state": "דת ומדינה",
    "arab_society": "החברה הערבית", "settlements": "התנחלויות וריבונות",
    "diplomacy": "יחסי חוץ", "netanyahu_trial": "משפט נתניהו",
    "oct7_inquiry": "7 באוקטובר וּועדת חקירה", "campaign_politics": "פוליטיקה ובחירות",
}
TOPIC_HE_SHORT = {
    "security_war": "ביטחון", "hostages": "חטופים", "gaza": "עזה",
    "economy": "כלכלה", "haredi_draft": "גיוס", "judiciary": "משפט",
    "religion_state": "דת ומדינה", "arab_society": "חברה ערבית",
    "settlements": "התנחלויות", "diplomacy": "חוץ", "netanyahu_trial": "משפט נתניהו",
    "oct7_inquiry": "7 באוקטובר", "campaign_politics": "בחירות",
}
RHET_HE = {"attack": "התקפה", "program": "תוכנית", "unity": "אחדות",
           "we_words": "«אנחנו»", "they_words": "«הם»"}

# Имена НЕ-кандидатов (журналисты и т.п.), которые keyness может выцепить как
# «характерное слово», но которые сбивают с толку как «слово-отпечаток» —
# это имя человека, а не тема. Убираем из отображаемого keyness.
# «סגל»/«עמית» -- журналист Амит Сегаль (עמית סגל), которого часто упоминает
# Бен-Гвир. Имена реальных КАНДИДАТОВ (напр. «איזנקוט») не трогаем: упоминание
# соперника -- осмысленный отпечаток.
KEYNESS_NAME_STOP = {"סגל", "עמית"}

# Сколько слов лексикона показывать в подсказке на доске.
LEX_SAMPLE = 8

# Ивритская методология для доски (концентрированная; полная версия по-русски
# в METHODOLOGY.md). Каждая метрика: источник, популяция, формула, ограничения.
METHODOLOGY_HE = {
    "populations": {
        "all": "כל הציוצים של החשבון בחלון הבחירות (כולל ריטוויטים, תגובות, ציטוטים).",
        "own": "ציוצים עצמיים: הכל למעט ריטוויטים. ריטוויט = מילים של אחר.",
        "own_he": "ציוצים עצמיים בעברית (own + שפה=עברית).",
        "all_he": "כל הציוצים בעברית.",
    },
    "metrics": {
        "פעילות": {"src": "tweet_id, date · own", "f": "מספר ציוצים ליום = סך ציוצים / מספר ימי החלון.",
                   "lim": "ממוצע על פני החלון; תלוי גם במגבלת האיסוף."},
        "התקפה מול תוכנית": {"src": "לקסיקון · own", "f": "אחוז ציוצים עם שפת האשמה (שקר, כישלון…) מול שפת הבטחה (נקדם, נבנה…).",
                             "lim": "מדד לקסיקלי של טון, לא ניתוח משמעות. אירוניה לא נתפסת."},
        "מילת טביעת אצבע (keyness)": {"src": "lemmas · own_he",
            "f": "log-likelihood (G²): משווה תדירות מילה אצל הפוליטיקאי מול כל השאר. גבוה = ייחודי לו.",
            "lim": "מראה ייחוד, לא חשיבות. מילה נפוצה אצל כולם (ישראל) לא תופיע."},
        "נושאים": {"src": "lemmas מול לקסיקון נושאים · own",
            "f": "ציוץ שייך לנושא אם נמצאה בו לפחות לממה אחת מהלקסיקון. אחוז = חלק הציוצים שנגעו בנושא.",
            "lim": "לקסיקונים ידניים וחלקיים; ציוץ יכול לגעת בכמה נושאים (סכום מעל 100%)."},
        "«אנחנו» / «הם»": {"src": "כינויי גוף · own_he",
            "f": "יחס כינויי גוף ראשון־רבים (אנחנו, שלנו) לשלישי־רבים (הם, שלהם). גבוה = שפה מאחדת.",
            "lim": "מדד גס."},
        "מי על מי": {"src": "אזכורים בשם ובתגית · own",
            "f": "קשת א→ב אם בציוץ של א מופיע שמו/תגיתו של ב. משקל = מספר הציוצים.",
            "lim": "אזכור אינו התקפה: הטון אינו מובחן."},
        "גיוון לשוני (STTR)": {"src": "content_lemmas · own_he",
            "f": ("הטקסט נחתך לחלונות של 500 מילות תוכן; בכל חלון נמדד "
                  "מילים ייחודיות / 500, והממוצע הוא הציון. חלון זהה לכולם — "
                  "לכן הערכים בני־השוואה. גבוה = אוצר מילים עשיר."),
            "lim": ("היחס הגולמי (ייחודיות / סך הטקסט) יורד מכניסטית עם אורך "
                    "הטקסט ולכן אינו כשיר להשוואה — משום כך החלון. שארית "
                    "קצרה מחלון אינה נספרת.")},
        "ציוץ בולט": {"src": "likes · own", "f": "הציוץ העצמי עם מירב הלייקים.",
                      "lim": "נקודה אחת, לא מאפיינת את הטון הממוצע."},
        "מעורבות": {"src": "likes, retweets · all", "f": "חציון הלייקים/ריטוויטים. חציון עמיד לויראליות חד־פעמית.",
                    "lim": "מספרים מוחלטים תלויים בגודל הקהל — אין להשוות בין פוליטיקאים."},
    },
    "note": ("ריטוויטים הוצאו מכל מדדי הטקסט (מילים של אחר). לממטיזציה בעברית (stanza): "
             "מילה בצורות שונות = מילה אחת. ציוצים מחוץ לחלון או של מחבר אחר (ריטוויט מקומי) סוננו."),
}


def build() -> dict:
    d = json.loads(IN.read_text(encoding="utf-8"))
    P = d["politicians"]
    topic_ru = {k: v["ru"] for k, v in CFG.topics.items()}
    topic_short = {k: v.get("short", v["ru"]) for k, v in CFG.topics.items()}
    rhet_ru = {k: v["ru"] for k, v in CFG.rhetoric.items()}
    # Примеры слов лексикона -- чтобы читатель доски видел, ЧЕМ измерена тема,
    # а не верил подписи на слово. Берём первые LEX_SAMPLE терминов (в yaml
    # они выписаны от самых характерных) + общий размер лексикона.
    topic_terms = {k: {"n": len(v["he"]), "ex": v["he"][:LEX_SAMPLE]}
                   for k, v in CFG.topics.items()}
    rhet_terms = {k: {"n": len(v["he"]), "ex": v["he"][:LEX_SAMPLE]}
                  for k, v in CFG.rhetoric.items()}

    # порядок тем — по доле в корпусе
    topic_order = [k for k, _ in sorted(
        d["corpus"]["topics"].items(),
        key=lambda kv: -kv[1]["share_of_tweets"])]

    pols = []
    for pid, p in P.items():
        o = p["overview"]
        rh = p["rhetoric"]
        kn1 = p["keyness"].get("1", [])
        pols.append({
            "id": pid,
            "name": p["profile"]["name_ru"],
            "name_he": p["profile"]["name_he"],
            "party": p["profile"]["party"],
            "party_he": p["profile"].get("party_he") or p["profile"]["party"],
            "bloc": p["profile"]["bloc"],
            "handle": p["profile"]["handle"],
            "tweets": o["tweets_total"],
            "own": o["tweets_own"],
            "per_day": o["per_day"],
            "retweet_share": o["retweet_share"],
            "reply_share": o["reply_share"],
            "hebrew_share": o["hebrew_share"],
            "self_3p": o.get("self_third_person_tweets", 0),
            "attack": rh["attack"]["share_of_tweets"],
            "program": rh["program"]["share_of_tweets"],
            "unity": rh["unity"]["share_of_tweets"],
            "we": rh["we_words"]["hits"],
            "they": rh["they_words"]["hits"],
            "ttr": (p.get("lexical_diversity") or {}).get("ttr", 0),
            "sttr": (p.get("lexical_diversity") or {}).get("sttr", 0),
            "ttr_uniq": (p.get("lexical_diversity") or {}).get("unique", 0),
            "ttr_total": (p.get("lexical_diversity") or {}).get("total", 0),
            "sttr_windows": (p.get("lexical_diversity") or {}).get("sttr_windows", 0),
            "focus_hhi": (p.get("topic_concentration") or {}).get("hhi", 0),
            "focus_top": (p.get("topic_concentration") or {}).get("top_topic"),
            "topics": {k: round(v["share_of_tweets"], 4)
                       for k, v in p["topics"].items()},
            "keyness": [{"w": x["phrase"], "ratio": x.get("ratio"),
                         "g2": x["g2"], "count": x["count"]}
                        for x in kn1 if x["phrase"] not in KEYNESS_NAME_STOP][:8],
            "keyphrases": [{"w": x["phrase"], "count": x["count"]}
                           for x in p["keyness"].get("3", [])[:3]],
            "style": {
                "excl": p["style"]["exclamations_per_tweet"],
                "emoji": p["style"]["emoji_per_tweet"],
                "words": p["style"]["avg_words"],
                "media": p["style"]["media_share"],
                "hours": p["style"]["hour_histogram"],
            },
            "engagement": {
                "median_likes": p["engagement"]["median_likes"],
                "median_rt": p["engagement"]["median_retweets"],
            },
            "viral": p.get("viral_tweet"),
            "weekly": d["timeline"]["weekly_volume"].get(pid, {}),
        })

    # Граф упоминаний. Источником может быть только политик из выборки (пишет
    # он сам), а ЦЕЛЬЮ -- любой политик из конфига, включая тех, у кого нет
    # аккаунта в X: лидеры харедимных партий (Дери, Гафни, Гольдкнопф) и
    # Аббас не твитят, но их упоминают, и без них картина «кто кого тащит в
    # разговор» неполна. Такие «молчащие» отдаются отдельным списком, чтобы
    # доска подписала их как не-твитящих, а не как политиков с нулём метрик.
    ids = {p["id"] for p in pols}
    cfg_ids = {p.id for p in CFG.politicians}
    edges = [e for e in d["mentions"]["edges"]
             if e["source"] in ids and e["target"] in cfg_ids]
    silent = [{"id": c.id, "name": c.name_ru, "name_he": c.name_he,
               "party_he": getattr(c, "party_he", None) or c.party,
               "bloc": c.bloc, "handle": c.handle}
              for c in CFG.politicians if c.id not in ids]

    return {
        "meta": {
            "generated_at": d["meta"]["generated_at"],
            "campaign_start": d["meta"]["campaign_start"],
            "campaign_end": d["meta"]["campaign_end"],
            "election_day": d["meta"]["election_day"],
            "days": d["meta"]["days"],
            "n_tweets": d["meta"]["n_tweets_total"],
            "n_politicians": d["meta"]["n_politicians"],
            "lemmatizer": d["meta"]["lemmatizer"],
        },
        "topic_order": topic_order,
        "topic_ru": topic_ru,
        "topic_short": topic_short,
        "topic_he": TOPIC_HE,
        "topic_he_short": TOPIC_HE_SHORT,
        "rhet_ru": rhet_ru,
        "topic_terms": topic_terms,
        "rhet_terms": rhet_terms,
        "sttr_window": 500,
        "rhet_he": RHET_HE,
        "methodology_he": METHODOLOGY_HE,
        "politicians": pols,
        "silent": silent,
        "corpus_topics": {k: round(v["share_of_tweets"], 4)
                          for k, v in d["corpus"]["topics"].items()},
        "corpus_ngrams": {
            n: [{"w": x["phrase"], "c": x["count"]}
                for x in d["corpus"]["ngrams"].get(n, [])[:20]]
            for n in ("1", "2", "3")
        },
        "mentions": {
            "edges": edges,
            "most_talked": [[p, w] for p, w in d["mentions"]["most_talked_about"]
                            if p in cfg_ids],
            "most_talkative": [[p, w] for p, w in d["mentions"]["most_talkative"]
                               if p in ids],
        },
        "methodology": d["meta"].get("methodology", {}),
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"[dashboard_data] -> {OUT} ({OUT.stat().st_size // 1024} КБ), "
          f"{len(data['politicians'])} политиков")


if __name__ == "__main__":
    main()
