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


def build() -> dict:
    d = json.loads(IN.read_text(encoding="utf-8"))
    P = d["politicians"]
    topic_ru = {k: v["ru"] for k, v in CFG.topics.items()}
    topic_short = {k: v.get("short", v["ru"]) for k, v in CFG.topics.items()}
    rhet_ru = {k: v["ru"] for k, v in CFG.rhetoric.items()}

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
            "ttr_total": (p.get("lexical_diversity") or {}).get("total", 0),
            "focus_hhi": (p.get("topic_concentration") or {}).get("hhi", 0),
            "focus_top": (p.get("topic_concentration") or {}).get("top_topic"),
            "topics": {k: round(v["share_of_tweets"], 4)
                       for k, v in p["topics"].items()},
            "keyness": [{"w": x["phrase"], "ratio": x.get("ratio"),
                         "g2": x["g2"], "count": x["count"]} for x in kn1[:8]],
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

    # граф упоминаний: только рёбра между политиками из выборки
    ids = {p["id"] for p in pols}
    edges = [e for e in d["mentions"]["edges"]
             if e["source"] in ids and e["target"] in ids]

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
        "rhet_ru": rhet_ru,
        "politicians": pols,
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
                            if p in ids],
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
