"""data/raw/*.jsonl -> data/processed/tweets.jsonl

Один проход: чистка, определение языка, лемматизация. Лемматизация -- самая
дорогая операция во всём проекте, поэтому её результат кэшируется здесь,
а все метрики потом читают готовые леммы.

  python -m src.process.prepare
  python -m src.process.prepare --lemmatizer rules   # быстрый прогон без stanza
"""
from __future__ import annotations

import argparse
import json

from src.config import CFG, DATA_RAW, DATA_PROCESSED
from src.process.hebrew import (clean_text, detect_language, drop_noise,
                                is_stopword, lemmatize, normalize_for_match,
                                resolve_backend, tokenize)

OUT = DATA_PROCESSED / "tweets.jsonl"
META = DATA_PROCESSED / "prepare_meta.json"
BATCH = 200


def load_raw() -> list[dict]:
    rows: list[dict] = []
    files = sorted(DATA_RAW.glob("*.jsonl"))
    if not files:
        raise SystemExit(
            f"В {DATA_RAW} нет файлов. Сначала собери данные:\n"
            "  python -m src.collect.scrape collect"
        )
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in rows:
        key = r["tweet_id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def reclassify_and_filter(rows: list[dict]) -> tuple[list[dict], dict]:
    """Две чистки, критичные для корректности текстовых метрик:

    1. Чужой автор -> это ретвит. Флаг include:nativeretweets притащил в
       выгрузку нативные ретвиты, а поле retweetedTweet их не пометило:
       X показывает их как оригинал чужого автора. Такой твит с
       is_retweet=false молча попадал в «собственные» слова политика и
       засорял n-граммы/keyness ЧУЖИМ текстом. Помечаем is_retweet=true:
       в активности учтётся, из текстовых метрик уйдёт.

    2. Вне окна кампании -> выбрасываем. since:/until: на стороне X не
       абсолютны (закреплённые/старые твиты просачиваются). Дата -- истина.
    """
    handle_by_id = {p.id: (p.handle or "").lower() for p in CFG.politicians}
    start = CFG.campaign.start.isoformat()
    end = CFG.campaign.end.isoformat()

    kept: list[dict] = []
    stats = {"reclassified_retweet": 0, "dropped_out_of_window": 0}
    for r in rows:
        d = (r.get("date") or "")[:10]
        if not (start <= d <= end):
            stats["dropped_out_of_window"] += 1
            continue
        want = handle_by_id.get(r.get("politician_id"), "")
        author = (r.get("author_handle") or "").lower()
        if want and author and author != want and not r.get("is_retweet"):
            r["is_retweet"] = True
            r["retweet_of"] = r.get("retweet_of") or r.get("author_handle")
            r["_reclassified_native_rt"] = True
            stats["reclassified_retweet"] += 1
        kept.append(r)
    return kept, stats


def enrich(rows: list[dict], backend: str) -> list[dict]:
    # чистка и язык -- дёшево, делаем сразу
    for r in rows:
        r["clean"] = clean_text(r.get("text") or "")
        r["lang"] = detect_language(r["clean"])
        r["n_chars"] = len(r.get("text") or "")
        r["n_words"] = len(tokenize(r["clean"]))

    # лемматизируем только иврит (для en/ar лемм не нужно, там lowercase хватает)
    he_idx = [i for i, r in enumerate(rows) if r["lang"] == "he"]
    print(f"[prepare] лемматизация: {len(he_idx)} твитов на иврите, бэкенд={backend}")

    for start in range(0, len(he_idx), BATCH):
        chunk = he_idx[start:start + BATCH]
        lemmas = lemmatize([rows[i]["clean"] for i in chunk], backend=backend)
        for i, lem in zip(chunk, lemmas):
            # выбрасываем отделённые MWT клитики (ה/ו/ב/ל/...) и пунктуацию:
            # отдельным словом они не бывают и только засоряют n-граммы
            lm, ps = drop_noise([normalize_for_match(l) for l, _pos in lem],
                                [pos for _l, pos in lem])
            rows[i]["lemmas"] = lm
            rows[i]["pos"] = ps
            rows[i]["content_lemmas"] = [
                l for l in rows[i]["lemmas"] if not is_stopword(l)
            ]
        done = min(start + BATCH, len(he_idx))
        print(f"  {done}/{len(he_idx)}", flush=True)

    # не-иврит: токены как есть
    for r in rows:
        if "lemmas" not in r:
            toks = [normalize_for_match(t) for t in tokenize(r["clean"])]
            r["lemmas"] = toks
            r["pos"] = ["X"] * len(toks)
            r["content_lemmas"] = [t for t in toks if not is_stopword(t)]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lemmatizer", default=None,
                    help="stanza | dicta | rules (по умолчанию из settings.yaml)")
    args = ap.parse_args()
    requested = args.lemmatizer or CFG.analysis["lemmatizer"]
    # разрешаем бэкенд заранее, чтобы в метаданные попал фактический
    backend = resolve_backend(requested)
    if backend != requested:
        print(f"[prepare] запрошен {requested}, фактически используется {backend}")

    rows = load_raw()
    before = len(rows)
    rows = dedupe(rows)
    print(f"[prepare] загружено {before}, после дедупликации {len(rows)}")

    rows, clean_stats = reclassify_and_filter(rows)
    print(f"[prepare] нативных ретвитов переклассифицировано: "
          f"{clean_stats['reclassified_retweet']}; вне окна отброшено: "
          f"{clean_stats['dropped_out_of_window']}; осталось {len(rows)}")

    rows = enrich(rows, backend)

    with open(OUT, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    META.write_text(json.dumps({
        "lemmatizer_requested": requested,
        "lemmatizer_used": backend,
        "n_tweets": len(rows),
        "synthetic": any(r.get("_synthetic") for r in rows),
        "native_retweets_reclassified": clean_stats["reclassified_retweet"],
        "dropped_out_of_window": clean_stats["dropped_out_of_window"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    by_lang: dict[str, int] = {}
    for r in rows:
        by_lang[r["lang"]] = by_lang.get(r["lang"], 0) + 1
    print(f"[prepare] записано {len(rows)} -> {OUT}")
    print(f"[prepare] по языкам: {by_lang}")


if __name__ == "__main__":
    main()
