"""Нормализация и лемматизация иврита.

Зачем: в иврите богатая аффиксация. «חטופים / החטופים / לחטופים / ולחטופים»
это одно слово в четырёх формах. Без приведения к лемме частотный анализ
покажет мусор, а TF-IDF размажет сигнал по вариантам.

Три бэкенда, выбираются в config/settings.yaml -> analysis.lemmatizer:
  stanza  -- нейросетевая модель (лучшее качество, разовая загрузка ~400МБ)
  dicta   -- API Dicta (dicta.org.il), отличное качество, но нужен интернет
  rules   -- эвристика на префиксах, без внешних зависимостей (fallback)
"""
from __future__ import annotations

import functools
import html
import re
import unicodedata

# --- диапазоны символов ---
NIQQUD = re.compile(r"[֑-ׇ]")            # огласовки и кантилляция
HEBREW_LETTER = re.compile(r"[א-ת]")
ARABIC_LETTER = re.compile(r"[ؠ-ي]")
LATIN_LETTER = re.compile(r"[A-Za-z]")

# --- шум твитов ---
URL = re.compile(r"https?://\S+|t\.co/\S+|www\.\S+")
MENTION = re.compile(r"@[A-Za-z0-9_]{1,15}")
HASHTAG = re.compile(r"#[\w֐-׿ؠ-ي]+")
RT_PREFIX = re.compile(r"^RT @[A-Za-z0-9_]{1,15}:\s*")
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "⬀-⯿️←-⇿]"
)

# конечные формы -> обычные (для сопоставления лемм)
FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})

# варианты гереш/гершаим, которые ломают сравнение строк
QUOTES = str.maketrans({"׳": "'", "״": '"', "’": "'", "‘": "'",
                        "“": '"', "”": '"'})

# Стоп-слова иврита: служебные, связки, частотный шум.
# NB: местоимений «мы/они» здесь НЕТ намеренно -- они считаются как метрика.
HEBREW_STOPWORDS = set("""
של את על עם אל מן כי גם רק אם או אבל אז כך כמו זה זו זאת אלה אלו יש אין
היה היא הוא הם הן אני אתה אתם אתן כל כלל יותר פחות מאוד
אשר לפי בין תוך אחרי לפני מול נגד בלי ללא אצל עד כדי בגלל למרות אולי
כאשר איך מה מי איפה למה מתי כמה האם לא כן פה שם עוד כבר עכשיו היום
אמר אמרה אומר אומרת יכול יכולה צריך צריכה רוצה בא בואו הנה ובכן
אחד אחת שני שתי שלוש ארבע חמש אלף מאה
ה ו ב ל מ כ ש
כול נו
""".split())
# כול -- лемма stanza для כל («весь/каждый»), служебное.
# נו -- отделённый суффикс 1л.мн.ч. (שלנו->של+נו): нужен для метрики «мы»,
# но как самостоятельное «частое слово» это шум, поэтому в стоп-словах.
# Односимвольные ם/ן (суффикс 3л.мн.ч.) уже отсекаются правилом len<2.
# ВАЖНО: метрика «мы/они» читает СЫРЫЕ леммы, а не content_lemmas, поэтому
# от попадания сюда она не страдает.

ENGLISH_STOPWORDS = set("""
the a an and or but if of to in on at for with by from as is are was were be
been being this that these those it its i you he she they we us our your their
not no yes do does did done have has had will would can could should may might
""".split())


def strip_niqqud(text: str) -> str:
    return NIQQUD.sub("", text)


def clean_text(text: str, drop_urls: bool = True, drop_mentions: bool = True,
               keep_hashtag_word: bool = True) -> str:
    """Убирает технический шум, оставляя человеческий текст."""
    text = unicodedata.normalize("NFC", text or "")
    # X отдаёт текст с HTML-сущностями: &gt; &lt; &amp; &#39;. Без декода
    # «&gt; &gt;» попадает в биграммы как «слово».
    text = html.unescape(text)
    text = RT_PREFIX.sub("", text)
    if drop_urls:
        text = URL.sub(" ", text)
    if drop_mentions:
        text = MENTION.sub(" ", text)
    if keep_hashtag_word:
        # #החזירו_אותם_הביתה -> "החזירו אותם הביתה": хэштег часто и есть слоган
        text = HASHTAG.sub(lambda m: m.group(0)[1:].replace("_", " "), text)
    else:
        text = HASHTAG.sub(" ", text)
    text = strip_niqqud(text)
    text = text.translate(QUOTES)
    text = EMOJI.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_language(text: str) -> str:
    """Грубое определение языка по алфавиту. Твиты короткие, статистика по
    символам надёжнее вероятностных детекторов."""
    he = len(HEBREW_LETTER.findall(text))
    ar = len(ARABIC_LETTER.findall(text))
    la = len(LATIN_LETTER.findall(text))
    total = he + ar + la
    if total < 5:
        return "unknown"
    if he / total > 0.35:
        return "he"
    if ar / total > 0.35:
        return "ar"
    if la / total > 0.5:
        return "en"
    return "mixed"


def tokenize(text: str) -> list[str]:
    """Слова на иврите/арабском/латинице. Апостроф внутри слова сохраняем
    (סמוטריץ' -- часть имени)."""
    pattern = (r"[א-תؠ-يA-Za-z]"
               r"[א-תؠ-يA-Za-z'\"]*")
    return re.findall(pattern, text)


# --------------------------------------------------------------------------
# Бэкенд 1: правила (fallback, без зависимостей)
# --------------------------------------------------------------------------

_PREFIXES = ("ולכש", "וכש", "כשה", "מהש", "ולה", "שה", "וה", "ול", "וב", "וכ",
             "ומ", "לה", "בה", "כה", "מה", "ה", "ו", "ב", "ל", "כ", "מ", "ש")

# Слова, у которых ל/ב/מ/כ/ש/ה -- часть корня, а не приставка. Без этого
# списка эвристика калечит именно ту лексику, которая нам и нужна:
# לימוד -> ימוד, שוויון -> וויון, בושה -> ושה, מלחמה -> לחמה.
# Список закрыт по частотной политической лексике; полноценное решение --
# бэкенд stanza, здесь мы лишь снижаем ущерб fallback-режима.
_NO_STRIP = frozenset("""
לימוד לימודים שוויון שוויוני בושה בגידה בוגד ביטחון בחירות בית ביתה בנט
מלחמה מדינה משפט משפטי משפחה משפחות מחדל ממשלה מנדט מפלגה מס מסוכן מחבל
כלכלה כנסת כישלון כתב כשל כוח לאום לאומי להב לפיד ליברמן להם
שקר שקרן שנאה שחיתות שבוי שבויים שומרון שופט שלום שליחות שיקום שבת
בקעה בידוד בזבוז בחר בטחון בעד בלבד ברור בעיה
הסתה הכרה הצבעה הסכם התנחלות התיישבות הפיכה
ועדה ועדת וינטר
""".split())


def lemma_rules(token: str) -> str:
    """Снимает наиболее частые проклитики. Крайне грубо, но лучше, чем ничего:
    гарантирует, что слово не короче 3 букв после отсечения."""
    t = token.strip("'\"")
    if not HEBREW_LETTER.search(t):
        return t.lower()
    if t in _NO_STRIP:
        return t
    for p in _PREFIXES:
        if t.startswith(p) and len(t) - len(p) >= 3:
            return t[len(p):]
    return t


# --------------------------------------------------------------------------
# Бэкенд 2: stanza
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _stanza_pipeline():
    import stanza
    kwargs = dict(lang="he", processors="tokenize,mwt,pos,lemma",
                  use_gpu=False, verbose=False)
    try:
        return stanza.Pipeline(download_method=None, **kwargs)
    except Exception:
        stanza.download("he", verbose=False)
        return stanza.Pipeline(**kwargs)


def lemmatize_stanza(texts: list[str]) -> list[list[tuple[str, str]]]:
    """Возвращает по документу список (лемма, POS).

    Исключение для местоимений: stanza сводит «אנחנו», «הם», «אני» к одной
    лемме «הוא». Для нормального разбора это верно, но метрика «мы vs они»
    держится ровно на этом различии, и лемма её уничтожает. Поэтому у PRON
    сохраняем поверхностную форму."""
    import stanza
    nlp = _stanza_pipeline()
    docs = [stanza.Document([], text=t if t.strip() else ".") for t in texts]
    out = nlp(docs)
    return [
        [((w.text if (w.upos or "") == "PRON" else (w.lemma or w.text)),
          w.upos or "X")
         for s in d.sentences for w in s.words]
        for d in out
    ]


# --------------------------------------------------------------------------
# Бэкенд 3: Dicta API
# --------------------------------------------------------------------------

DICTA_URL = "https://parser.dicta.org.il/api/nakdanit"


def lemmatize_dicta(texts: list[str]) -> list[list[tuple[str, str]]]:
    import httpx
    results: list[list[tuple[str, str]]] = []
    with httpx.Client(timeout=60) as client:
        for t in texts:
            try:
                r = client.post(DICTA_URL,
                                json={"task": "nakdan", "data": t, "genre": "modern"})
                r.raise_for_status()
                lem: list[tuple[str, str]] = []
                for item in r.json():
                    opts = item.get("options") or []
                    if opts:
                        lem.append((opts[0].get("lemma") or item.get("word", ""), "X"))
                results.append(lem)
            except Exception:
                results.append([(lemma_rules(w), "X") for w in tokenize(t)])
    return results


# --------------------------------------------------------------------------
# Единый вход
# --------------------------------------------------------------------------

def resolve_backend(backend: str) -> str:
    """Определяет фактический бэкенд ОДИН раз, до обработки.

    Без этого откат случался внутри каждого батча: сообщение печаталось
    многократно, а в метаданные шёл запрошенный бэкенд, а не сработавший --
    отчёт заявлял stanza, работая на rules."""
    if backend != "stanza":
        return backend
    try:
        _stanza_pipeline()
        return "stanza"
    except Exception as exc:
        print(f"[hebrew] stanza недоступна ({exc}); откат на rules")
        return "rules"


def lemmatize(texts: list[str], backend: str = "stanza") -> list[list[tuple[str, str]]]:
    """backend должен быть уже разрешён через resolve_backend()."""
    if backend == "stanza":
        return lemmatize_stanza(texts)
    if backend == "dicta":
        return lemmatize_dicta(texts)
    return [[(lemma_rules(w), "X") for w in tokenize(t)] for t in texts]


# Односимвольные ивритские токены, которые stanza отделяет от слова:
# определённый артикль ה, союз ו, предлоги ב/ל/כ/מ, относительное ש.
# Отдельным словом в иврите ни один из них не бывает, поэтому в потоке лемм
# это чистый шум: «המחדל» -> «ה» + «מחדל» засоряет биграммы («ה מחדל») и
# сдвигает окна n-грамм.
CLITIC_TOKENS = frozenset("הובלכמש")


def is_clitic(lemma: str) -> bool:
    return len(lemma) == 1 and lemma in CLITIC_TOKENS


_HAS_CONTENT = re.compile(r"[\wא-תؠ-ي]")


def has_content(lemma: str) -> bool:
    """Токен несёт смысл, если в нём есть буква или цифра.

    stanza отдаёт пунктуацию отдельными токенами, и она пролезает внутрь
    n-грамм: «מדינה . אנחנו», «! ! התפטר». Это не только выглядит сломанным,
    но и разрывает настоящие фразы на части. Цифры сохраняем: «27 באוקטובר»
    -- осмысленная фраза."""
    return bool(_HAS_CONTENT.search(lemma))


def drop_noise(lemmas: list[str], pos: list[str] | None = None):
    """Убирает отделённые клитики и пунктуацию. Применяется И к корпусу, И к
    термам лексиконов -- обе стороны сравнения должны жить в одном
    пространстве, иначе лексикон «חוק הגיוס» никогда не совпадёт с
    разобранным «חוק ה גיוס»."""
    def keep(l: str) -> bool:
        return not is_clitic(l) and has_content(l)

    if pos is None:
        return [l for l in lemmas if keep(l)]
    pairs = [(l, p) for l, p in zip(lemmas, pos) if keep(l)]
    return [l for l, _ in pairs], [p for _, p in pairs]



def lemmatize_terms(terms: list[str], backend: str) -> list[list[str]]:
    """Термы лексикона -> леммы, тем же бэкендом, что и корпус.

    Без этого лексиконы, написанные со слитным артиклем («משפחות החטופים»,
    «בית המשפט»), не совпадают с разобранным корпусом, и темы молча
    обнуляются при переходе на stanza."""
    out: list[list[str]] = []
    for lem in lemmatize(list(terms), backend=backend):
        words = drop_noise([normalize_for_match(l) for l, _pos in lem])
        out.append([w for w in words if w])
    return out


def normalize_for_match(word: str) -> str:
    """Каноническая форма леммы. Конечные буквы НЕ сворачиваются: лемма идёт
    в отчёт как есть, а «ניתן -> ניתנ» ломает читаемость. Сворачивание нужно
    только в момент сравнения -- см. fold()."""
    return strip_niqqud(word).translate(QUOTES).strip("'\"").lower()


def fold(word: str) -> str:
    """Форма для СРАВНЕНИЯ: конечные буквы сведены к обычным. Применяется к
    обеим сторонам сравнения, поэтому в отчёт не попадает."""
    return normalize_for_match(word).translate(FINALS)


# Частые словоизменительные суффиксы. Нужны, когда лемматизация работает в
# режиме rules: лексиконы написаны леммами (חטוף), а rules отдаёт поверхностную
# форму (חטופים). Со stanza этот запас не мешает, но и не вредит.
INFLECTION_SUFFIXES = ("ים", "ות", "יות", "ינו", "יהם", "נו", "כם", "הם", "יו",
                       "ית", "ה", "ת", "י", "ם", "ן", "א")

# Сравнение идёт по свёрнутым формам, поэтому и суффиксы должны быть свёрнуты:
# иначе «חטופים» (-> חטופימ) никогда не совпадёт с «חטוף» (-> חטופ), т.к.
# остаток «ימ» не найдётся в списке, где лежит «ים».
_SUFFIXES_FOLDED = frozenset(s.translate(FINALS) for s in INFLECTION_SUFFIXES)


def stem_matches(lemma: str, term: str) -> bool:
    """lemma совпадает с term точно либо отличается одним словоизменительным
    суффиксом. Требуем основу не короче 3 букв, иначе ловится всё подряд."""
    a, b = fold(lemma), fold(term)
    if a == b:
        return True
    if len(b) < 3:
        return False
    if a.startswith(b):
        return a[len(b):] in _SUFFIXES_FOLDED
    if b.startswith(a) and len(a) >= 3:
        return b[len(a):] in _SUFFIXES_FOLDED
    return False


def is_stopword(lemma: str) -> bool:
    low = lemma.strip("'\"").lower()
    return (low in HEBREW_STOPWORDS or low in ENGLISH_STOPWORDS
            or len(low) < 2 or low.isdigit())
