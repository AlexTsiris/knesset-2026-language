"""Все метрики за один проход -> outputs/analysis.json

  python -m src.analyze.run

Что считается (по политику и по корпусу):
  overview   -- объём, темп, доля ретвитов/ответов, языки, длина, медиа
  ngrams     -- топ n-грамм по леммам (n=1..4)
  keyness    -- log-likelihood: чем этот политик отличается от остальных
  topics     -- доля твитов по темам из config/topics.yaml
  rhetoric   -- атака / программа / единство, «мы» vs «они»
  mentions   -- граф «кто про кого» (по хэндлам и по ивритским алиасам)
  timeline   -- недельная динамика объёма и тем, кто первым поднял тему
  style      -- восклицания, CAPS, эмодзи, хэштеги, час публикации (по Израилю)
  engagement -- какие фразы реально «залетают»
  slogans    -- насколько политик повторяет сам себя
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter, defaultdict

from src.config import CFG, DATA_PROCESSED, OUTPUTS
from src.process.hebrew import (EMOJI, fold, is_stopword, lemmatize_terms,
                                normalize_for_match, stem_matches)
from src.analyze.methodology import as_dict as _methodology

IN = DATA_PROCESSED / "tweets.jsonl"
PREP_META = DATA_PROCESSED / "prepare_meta.json"
OUT = OUTPUTS / "analysis.json"

# Израиль в июле-октябре живёт в IDT = UTC+3. Твиты приходят в UTC.
IL_OFFSET = dt.timedelta(hours=3)


# --------------------------------------------------------------------------
# загрузка
# --------------------------------------------------------------------------

def load() -> list[dict]:
    if not IN.exists():
        raise SystemExit(f"Нет {IN}. Сначала: python -m src.process.prepare")
    rows = []
    with open(IN, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    for r in rows:
        r["_dt"] = dt.datetime.fromisoformat(r["date"]) if r.get("date") else None
        if r["_dt"] is not None:
            local = r["_dt"] + IL_OFFSET
            r["_hour_il"] = local.hour
            r["_date_il"] = local.date().isoformat()
            r["_week"] = local.date().isocalendar()[:2]
        else:
            r["_hour_il"] = None
            r["_date_il"] = None
            r["_week"] = None
    return rows


def group_by_politician(rows: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        g[r["politician_id"]].append(r)
    return g


def own_tweets(rows: list[dict]) -> list[dict]:
    """Только собственный текст: без ретвитов. Ретвит -- это чужие слова,
    в анализ «какие фразы использует ОН» его пускать нельзя."""
    return [r for r in rows if not r.get("is_retweet")]


# --------------------------------------------------------------------------
# n-граммы
# --------------------------------------------------------------------------

def ngrams_from(lemmas: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(lemmas[i:i + n]) for i in range(len(lemmas) - n + 1)]


def count_ngrams(rows: list[dict], n: int, lang: str = "he") -> Counter:
    """Для n=1 берём только содержательные леммы. Для n>=2 берём полные
    последовательности (служебные слова внутри фразы -- часть фразы), но
    отбрасываем n-граммы, целиком состоящие из служебных слов."""
    c: Counter = Counter()
    for r in rows:
        if lang and r.get("lang") != lang:
            continue
        if n == 1:
            c.update(r.get("content_lemmas") or [])
        else:
            for g in ngrams_from(r.get("lemmas") or [], n):
                if all(is_stopword(w) for w in g):
                    continue
                c[" ".join(g)] += 1
    return c


def top_ngrams(rows: list[dict], sizes, min_count: int, top_n: int, lang="he") -> dict:
    out = {}
    for n in sizes:
        c = count_ngrams(rows, n, lang)
        out[str(n)] = [
            {"phrase": p, "count": k}
            for p, k in c.most_common(top_n) if k >= min_count
        ]
    return out


# --------------------------------------------------------------------------
# keyness (log-likelihood G2)
# --------------------------------------------------------------------------

def log_likelihood(a: int, b: int, c: int, d: int) -> float:
    """a -- частота в целевом корпусе, b -- в референсном,
    c/d -- размеры корпусов. Знак: + значит переиспользование."""
    if c == 0 or d == 0:
        return 0.0
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    g = 0.0
    if a > 0 and e1 > 0:
        g += a * math.log(a / e1)
    if b > 0 and e2 > 0:
        g += b * math.log(b / e2)
    g *= 2
    return g if (a / c) >= (b / d if d else 0) else -g


def keyness(target: Counter, reference: Counter, min_count: int, top_n: int) -> list[dict]:
    """Что характерно ИМЕННО для этого политика на фоне остальных."""
    c = sum(target.values())
    d = sum(reference.values())
    scored = []
    for phrase, a in target.items():
        if a < min_count:
            continue
        b = reference.get(phrase, 0)
        g = log_likelihood(a, b, c, d)
        if g <= 0:
            continue
        rel_target = a / c * 10_000
        rel_ref = (b / d * 10_000) if d else 0.0
        scored.append({
            "phrase": phrase,
            "count": a,
            "per_10k_self": round(rel_target, 2),
            "per_10k_others": round(rel_ref, 2),
            "ratio": round(rel_target / rel_ref, 2) if rel_ref > 0 else None,
            "g2": round(g, 1),
        })
    scored.sort(key=lambda x: -x["g2"])
    return scored[:top_n]


# --------------------------------------------------------------------------
# лексиконы: темы и риторика
# --------------------------------------------------------------------------

def build_matcher(terms: list[str], backend: str | None = None
                  ) -> tuple[list[str], list[tuple[str, ...]]]:
    """Однословные термы -> список, многословные -> список кортежей.
    Сравнение идёт через stem_matches, поэтому set по точному ключу не годится.

    backend задан -> термы прогоняются через тот же лемматизатор, что и
    корпус. Это обязательно: лексиконы написаны со слитным артиклем
    («חוק הגיוס»), а stanza его отделяет, и без общей нормализации темы
    молча обнуляются."""
    if backend:
        term_lemmas = lemmatize_terms(terms, backend)
    else:
        term_lemmas = [[normalize_for_match(w) for w in t.split()] for t in terms]

    single: list[str] = []
    multi: list[tuple[str, ...]] = []
    for parts in term_lemmas:
        parts = [p for p in parts if p]
        if not parts:
            continue
        if len(parts) == 1:
            single.append(parts[0])
        else:
            multi.append(tuple(parts))
    return single, multi


def lexicon_hits(row: dict, single: list[str], multi: list[tuple[str, ...]]) -> int:
    lemmas = row.get("lemmas") or []
    hits = 0
    for lem in lemmas:
        if any(stem_matches(lem, term) for term in single):
            hits += 1
    for m in multi:
        n = len(m)
        for i in range(len(lemmas) - n + 1):
            window = lemmas[i:i + n]
            if all(stem_matches(w, t) for w, t in zip(window, m)):
                hits += 1
    return hits


def compile_lexicons(spec: dict, backend: str | None = None) -> dict:
    return {k: build_matcher(v["he"], backend) for k, v in spec.items()}


def score_lexicons(rows: list[dict], compiled: dict) -> dict:
    """Доля твитов, затронувших тему + плотность попаданий на 1000 лемм."""
    n = len(rows) or 1
    total_lemmas = sum(len(r.get("lemmas") or []) for r in rows) or 1
    out = {}
    for key, (single, multi) in compiled.items():
        tweets_with = 0
        total_hits = 0
        for r in rows:
            h = lexicon_hits(r, single, multi)
            if h:
                tweets_with += 1
                total_hits += h
        out[key] = {
            "tweets": tweets_with,
            "share_of_tweets": round(tweets_with / n, 4),
            "hits": total_hits,
            "per_1k_lemmas": round(total_hits / total_lemmas * 1000, 2),
        }
    return out


# --------------------------------------------------------------------------
# граф упоминаний
# --------------------------------------------------------------------------

def build_alias_index(backend: str | None = None
                      ) -> list[tuple[str, set[str], list[tuple[str, ...]]]]:
    """Индекс имён/алиасов для графа упоминаний. В отличие от тематических
    лексиконов, здесь ТОЧНЫЙ матч по свёрнутой форме, без допуска на суффикс:
    имена собственные почти не склоняются, а допуск ловит ложные совпадения
    (алиас «עודה» иначе матчит частое слово «עוד» -- «ещё/более»)."""
    idx = []
    for p in CFG.politicians:
        text_terms = [t for t in p.aliases if not t.startswith("@")] + [p.name_he]
        term_lemmas = (lemmatize_terms(text_terms, backend) if backend
                       else [[normalize_for_match(w) for w in t.split()]
                             for t in text_terms])
        single: set[str] = set()
        multi: list[tuple[str, ...]] = []
        for parts in term_lemmas:
            parts = [fold(x) for x in parts if x]
            if not parts:
                continue
            if len(parts) == 1:
                single.add(parts[0])
            else:
                multi.append(tuple(parts))
        idx.append((p.id, single, multi))
    return idx


def alias_hit(row: dict, single: set[str], multi: list[tuple[str, ...]]) -> bool:
    """Точное совпадение имени/алиаса в тексте (по свёрнутым леммам)."""
    lemmas = [fold(l) for l in (row.get("lemmas") or [])]
    if any(l in single for l in lemmas):
        return True
    for m in multi:
        n = len(m)
        for i in range(len(lemmas) - n + 1):
            if tuple(lemmas[i:i + n]) == m:
                return True
    return False


def mentions_graph(by_pol: dict[str, list[dict]]) -> dict:
    idx = build_alias_index()
    handle_to_id = {p.handle.lower(): p.id for p in CFG.politicians if p.handle}

    edges: Counter = Counter()
    for src, rows in by_pol.items():
        for r in own_tweets(rows):
            targets = set()
            # 1) явные @-упоминания
            for m in (r.get("mentions") or []):
                tid = handle_to_id.get(str(m).lower())
                if tid:
                    targets.add(tid)
            for field in ("reply_to_handle", "quote_of"):
                tid = handle_to_id.get(str(r.get(field) or "").lower())
                if tid:
                    targets.add(tid)
            # 2) упоминание по имени в тексте (основной канал в иврите)
            for pid, single, multi in idx:
                if pid == src:
                    continue
                if alias_hit(r, single, multi):
                    targets.add(pid)
            for t in targets:
                if t != src:
                    edges[(src, t)] += 1

    # кого упоминают чаще всего
    in_deg: Counter = Counter()
    out_deg: Counter = Counter()
    for (s, t), w in edges.items():
        in_deg[t] += w
        out_deg[s] += w

    return {
        "edges": [{"source": s, "target": t, "weight": w}
                  for (s, t), w in edges.most_common()],
        "most_talked_about": in_deg.most_common(),
        "most_talkative": out_deg.most_common(),
    }


# --------------------------------------------------------------------------
# стиль
# --------------------------------------------------------------------------

EXCLAM = re.compile(r"!")
QUESTION = re.compile(r"\?")
CAPS_WORD = re.compile(r"\b[A-Z]{3,}\b")


def style(rows: list[dict]) -> dict:
    n = len(rows) or 1
    ex = sum(len(EXCLAM.findall(r.get("text") or "")) for r in rows)
    qu = sum(len(QUESTION.findall(r.get("text") or "")) for r in rows)
    emo = sum(len(EMOJI.findall(r.get("text") or "")) for r in rows)
    caps = sum(len(CAPS_WORD.findall(r.get("text") or "")) for r in rows)
    tags = Counter()
    for r in rows:
        tags.update(str(h).lower() for h in (r.get("hashtags") or []))

    hours = Counter(r["_hour_il"] for r in rows if r["_hour_il"] is not None)
    dows = Counter()
    for r in rows:
        if r["_dt"]:
            dows[(r["_dt"] + IL_OFFSET).weekday()] += 1

    return {
        "exclamations_per_tweet": round(ex / n, 3),
        "questions_per_tweet": round(qu / n, 3),
        "emoji_per_tweet": round(emo / n, 3),
        "caps_words_per_tweet": round(caps / n, 3),
        "avg_chars": round(sum(r.get("n_chars", 0) for r in rows) / n, 1),
        "avg_words": round(sum(r.get("n_words", 0) for r in rows) / n, 1),
        "media_share": round(sum(1 for r in rows if r.get("has_media")) / n, 4),
        "link_share": round(sum(1 for r in rows if r.get("links")) / n, 4),
        "top_hashtags": tags.most_common(15),
        "hour_histogram": {str(h): hours.get(h, 0) for h in range(24)},
        "weekday_histogram": {str(d): dows.get(d, 0) for d in range(7)},
    }


# --------------------------------------------------------------------------
# engagement
# --------------------------------------------------------------------------

def engagement_stats(rows: list[dict]) -> dict:
    def med(vals):
        v = sorted(vals)
        if not v:
            return 0
        m = len(v) // 2
        return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2

    likes = [r.get("likes", 0) for r in rows]
    rts = [r.get("retweets", 0) for r in rows]
    views = [r.get("views", 0) for r in rows if r.get("views")]
    return {
        "median_likes": med(likes),
        "median_retweets": med(rts),
        "median_views": med(views),
        "mean_likes": round(sum(likes) / (len(likes) or 1), 1),
        "total_likes": sum(likes),
        "total_retweets": sum(rts),
    }


def phrase_engagement(rows: list[dict], n: int = 2, min_count: int = 5,
                      top_n: int = 25) -> list[dict]:
    """Медианные лайки твитов, содержащих фразу, против общей медианы.
    Медиана, а не среднее: один виральный твит не должен решать всё."""
    def med(v):
        v = sorted(v)
        if not v:
            return 0.0
        m = len(v) // 2
        return float(v[m]) if len(v) % 2 else (v[m - 1] + v[m]) / 2

    baseline = med([r.get("likes", 0) for r in rows])
    buckets: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.get("lang") != "he":
            continue
        seen = set()
        for g in ngrams_from(r.get("lemmas") or [], n):
            if all(is_stopword(w) for w in g):
                continue
            key = " ".join(g)
            if key not in seen:
                seen.add(key)
                buckets[key].append(r.get("likes", 0))

    scored = []
    for phrase, vals in buckets.items():
        if len(vals) < min_count:
            continue
        m = med(vals)
        scored.append({
            "phrase": phrase,
            "count": len(vals),
            "median_likes": m,
            "lift": round(m / baseline, 2) if baseline else None,
        })
    scored.sort(key=lambda x: -(x["lift"] or 0))
    return scored[:top_n]


# --------------------------------------------------------------------------
# повторяемость слоганов
# --------------------------------------------------------------------------

def slogan_repetition(rows: list[dict], n: int = 4) -> dict:
    """Доля твитов, содержащих самую частую 4-грамму политика. Высокое
    значение = заученная мантра, низкое = живой язык."""
    c = count_ngrams(rows, n, "he")
    he_rows = [r for r in rows if r.get("lang") == "he"]
    if not c or not he_rows:
        return {"top_phrase": None, "share_of_tweets": 0.0, "hhi": 0.0}
    top_phrase, top_count = c.most_common(1)[0]
    tokens = tuple(top_phrase.split())
    hits = sum(1 for r in he_rows
               if tokens in set(ngrams_from(r.get("lemmas") or [], n)))
    total = sum(c.values())
    # индекс концентрации: насколько лексика сосредоточена в немногих фразах
    hhi = sum((v / total) ** 2 for v in c.values()) * 10_000
    return {
        "top_phrase": top_phrase,
        "top_phrase_count": top_count,
        "share_of_tweets": round(hits / len(he_rows), 4),
        "phrase_concentration_hhi": round(hhi, 2),
        "distinct_4grams": len(c),
    }


def lexical_diversity(rows: list[dict]) -> dict:
    """Type-token ratio по содержательным леммам иврита: уникальных / всего.
    Выше = богаче словарь. Честно сравнивать только при близких объёмах,
    поэтому объём отдаём рядом."""
    tokens: list[str] = []
    for r in rows:
        if r.get("lang") == "he":
            tokens.extend(r.get("content_lemmas") or [])
    if not tokens:
        return {"ttr": 0.0, "unique": 0, "total": 0}
    uniq = len(set(tokens))
    return {"ttr": round(uniq / len(tokens), 4), "unique": uniq, "total": len(tokens)}


def viral_tweet(rows: list[dict]) -> dict | None:
    """Собственный твит с максимумом лайков. Одна точка -- для иллюстрации,
    не для средних выводов."""
    cand = [r for r in rows if not r.get("is_retweet")]
    if not cand:
        return None
    t = max(cand, key=lambda r: r.get("likes", 0))
    return {
        "text": t.get("text"),
        "url": t.get("url"),
        "date": t.get("date"),
        "likes": t.get("likes", 0),
        "retweets": t.get("retweets", 0),
        "views": t.get("views", 0),
        "lang": t.get("lang"),
    }


def topic_concentration(topic_scores: dict) -> dict:
    """HHI по долям тем: сумма квадратов нормированных долей. Высокий = политик
    одной темы, низкий = говорит обо всём."""
    shares = [v["share_of_tweets"] for v in topic_scores.values()]
    s = sum(shares)
    if s <= 0:
        return {"hhi": 0.0, "top_topic": None}
    norm = [x / s for x in shares]
    hhi = sum(x * x for x in norm)
    top = max(topic_scores.items(), key=lambda kv: kv[1]["share_of_tweets"])[0]
    return {"hhi": round(hhi, 4), "top_topic": top}


# --------------------------------------------------------------------------
# динамика
# --------------------------------------------------------------------------

def week_key(r: dict) -> str | None:
    if not r["_week"]:
        return None
    y, w = r["_week"]
    return f"{y}-W{w:02d}"


def timeline(by_pol: dict[str, list[dict]], compiled_topics: dict) -> dict:
    volume: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    topic_weeks: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int)))

    for pid, rows in by_pol.items():
        for r in own_tweets(rows):
            wk = week_key(r)
            if not wk:
                continue
            volume[pid][wk] += 1
            for topic, (single, multi) in compiled_topics.items():
                if lexicon_hits(r, single, multi):
                    topic_weeks[topic][wk][pid] += 1

    # кто первым поднял тему: первая дата с >=2 твитами по теме
    first_movers = {}
    for topic, (single, multi) in compiled_topics.items():
        per_pol_first: list[tuple[str, str]] = []
        for pid, rows in by_pol.items():
            dates = sorted(
                r["_date_il"] for r in own_tweets(rows)
                if r["_date_il"] and lexicon_hits(r, single, multi)
            )
            if len(dates) >= 2:
                per_pol_first.append((dates[1], pid))  # 2-й твит = не случайность
        per_pol_first.sort()
        first_movers[topic] = [{"politician_id": p, "date": d}
                               for d, p in per_pol_first[:5]]

    return {
        "weekly_volume": {p: dict(sorted(w.items())) for p, w in volume.items()},
        "weekly_topics": {t: {w: dict(v) for w, v in sorted(ws.items())}
                          for t, ws in topic_weeks.items()},
        "topic_first_movers": first_movers,
    }


# --------------------------------------------------------------------------
# сборка
# --------------------------------------------------------------------------

def main() -> None:
    a = CFG.analysis
    global METHODOLOGY
    METHODOLOGY = _methodology()
    sizes = a["ngram_sizes"]
    min_c = a["min_ngram_count"]
    top_n = a["top_n"]

    prep_meta = (json.loads(PREP_META.read_text(encoding="utf-8"))
                 if PREP_META.exists() else {})

    rows = load()
    by_pol = group_by_politician(rows)
    lemma_backend = prep_meta.get("lemmatizer_used")
    compiled_topics = compile_lexicons(CFG.topics, lemma_backend)
    compiled_rhet = compile_lexicons(CFG.rhetoric, lemma_backend)
    alias_idx = build_alias_index(lemma_backend)

    camp = CFG.campaign
    corpus_own = own_tweets(rows)

    # общекорпусные счётчики для keyness
    global_counts = {n: count_ngrams(corpus_own, n, "he") for n in sizes}
    per_pol_counts = {
        pid: {n: count_ngrams(own_tweets(r), n, "he") for n in sizes}
        for pid, r in by_pol.items()
    }

    result: dict = {
        "meta": {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "campaign_start": camp.start.isoformat(),
            "campaign_end": camp.end.isoformat(),
            "election_day": camp.election_day.isoformat(),
            "days": camp.days,
            "lemmatizer": prep_meta.get("lemmatizer_used", "unknown"),
            "synthetic_data": prep_meta.get("synthetic", False),
            "n_tweets_total": len(rows),
            "n_politicians": len(by_pol),
            "note": ("Ретвиты исключены из всех ТЕКСТОВЫХ метрик (n-граммы, "
                     "keyness, темы, риторика): ретвит -- чужие слова. В "
                     "overview/style/engagement они учитываются как активность."),
            "methodology": METHODOLOGY,
        },
        "politicians": {},
        "corpus": {},
        "mentions": mentions_graph(by_pol),
        "timeline": timeline(by_pol, compiled_topics),
    }

    for pid, all_rows in by_pol.items():
        p = CFG.by_id(pid)
        own = own_tweets(all_rows)
        n_all = len(all_rows) or 1

        langs = Counter(r.get("lang") for r in all_rows)
        # референс = вся корпусная частотность минус свой вклад
        ref = {n: Counter(global_counts[n]) for n in sizes}
        for n in sizes:
            ref[n].subtract(per_pol_counts[pid][n])
            ref[n] = +ref[n]  # выкинуть нули и отрицательные

        # сколько раз говорит о себе в третьем лице
        own_single, own_multi = next(
            (s, m) for i, s, m in alias_idx if i == pid)
        third_person = sum(1 for r in own
                           if alias_hit(r, own_single, own_multi))

        topic_scores = score_lexicons(own, compiled_topics)
        result["politicians"][pid] = {
            "profile": {
                "name_ru": p.name_ru, "name_he": p.name_he,
                "party": p.party, "party_he": p.party_he,
                "bloc": p.bloc, "handle": p.handle,
            },
            "overview": {
                "tweets_total": len(all_rows),
                "tweets_own": len(own),
                "per_day": round(len(all_rows) / camp.days, 2),
                "retweet_share": round(
                    sum(1 for r in all_rows if r.get("is_retweet")) / n_all, 4),
                "reply_share": round(
                    sum(1 for r in all_rows if r.get("is_reply")) / n_all, 4),
                "quote_share": round(
                    sum(1 for r in all_rows if r.get("is_quote")) / n_all, 4),
                "languages": dict(langs),
                "hebrew_share": round(langs.get("he", 0) / n_all, 4),
                "self_third_person_tweets": third_person,
            },
            "ngrams": top_ngrams(own, sizes, min_c, top_n),
            "keyness": {
                str(n): keyness(per_pol_counts[pid][n], ref[n],
                                max(min_c, 3), 25)
                for n in sizes
            },
            "topics": topic_scores,
            "topic_concentration": topic_concentration(topic_scores),
            "rhetoric": score_lexicons(own, compiled_rhet),
            "lexical_diversity": lexical_diversity(own),
            "style": style(all_rows),
            "engagement": engagement_stats(all_rows),
            "phrase_engagement": phrase_engagement(own),
            "slogans": slogan_repetition(own),
            "viral_tweet": viral_tweet(own),
        }

    result["corpus"] = {
        "ngrams": top_ngrams(corpus_own, sizes, min_c, 60),
        "topics": score_lexicons(corpus_own, compiled_topics),
        "rhetoric": score_lexicons(corpus_own, compiled_rhet),
        "style": style(rows),
    }

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[analyze] {len(rows)} твитов, {len(by_pol)} политиков -> {OUT}")
    print(f"[analyze] размер отчёта: {OUT.stat().st_size / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
