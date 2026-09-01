"""Генерация METHODOLOGY.md из реестра src/analyze/methodology.py.

Док всегда синхронен с кодом: единственный источник правды -- реестр.

  python -m src.report.methodology_doc
"""
from __future__ import annotations

from pathlib import Path

from src.analyze.methodology import as_dict

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "METHODOLOGY.md"


def build() -> str:
    m = as_dict()
    L: list[str] = []
    L.append("# Методология\n")
    L.append("Как посчитана каждая метрика и откуда взяты данные. Документ "
             "сгенерирован из `src/analyze/methodology.py` — единственного "
             "источника правды, поэтому он не расходится с кодом.\n")
    L.append("Любую цифру в отчёте можно проследить: метрика → популяция "
             "(какие твиты) → поле исходного твита → формула.\n")

    L.append("## Исходные данные\n")
    L.append("Один твит в `data/raw/<politician>.jsonl` — это запись с полями:\n")
    L.append("| Поле | Что это |")
    L.append("|---|---|")
    for field, desc in [
        ("tweet_id", "уникальный id (ключ дедупликации)"),
        ("date", "время публикации (UTC)"),
        ("text", "исходный текст твита"),
        ("likes / retweets / replies / quotes / views", "счётчики вовлечённости"),
        ("is_retweet / is_reply / is_quote", "тип твита"),
        ("mentions / reply_to_handle / quote_of", "к кому обращён"),
        ("hashtags / links / has_media", "вложения"),
    ]:
        L.append(f"| `{field}` | {desc} |")
    L.append("")

    L.append("## Обработка (общий пайплайн)\n")
    for key, desc in m["pipeline"].items():
        L.append(f"- **{key}** — {desc}")
    L.append("")

    L.append("## Популяции (какие твиты берутся)\n")
    for key, desc in m["populations"].items():
        L.append(f"- **`{key}`** — {desc}")
    L.append("")

    L.append("## Метрики\n")
    for key, spec in m["metrics"].items():
        L.append(f"### {spec['ru']} (`{key}`)\n")
        L.append(f"- **Источник:** {spec['source']}")
        L.append(f"- **Популяция:** `{spec['population']}` — "
                 f"{m['populations'].get(spec['population'], '')}")
        L.append(f"- **Формула:** {spec['formula']}")
        L.append(f"- **Единица:** {spec['unit']}")
        L.append(f"- **Ограничения:** {spec['limits']}")
        L.append("")

    L.append("## Принципиальные решения\n")
    L.append("- **Ретвиты вне текстовых метрик.** N-граммы, keyness, темы и "
             "риторика считаются только по собственным твитам: ретвит — чужой "
             "текст. В объёме, стиле и вовлечённости ретвиты учитываются как "
             "активность.")
    L.append("- **Keyness вместо голой частоты.** Частое у всех слово "
             "(«Израиль») неинформативно; log-likelihood показывает, что "
             "политик говорит непропорционально часто на фоне остальных.")
    L.append("- **Медиана вместо среднего в вовлечённости.** Один виральный "
             "твит не должен определять оценку.")
    L.append("- **Лемматизация обязательна.** Без неё одно ивритское слово в "
             "четырёх формах считалось бы четырьмя разными.")
    L.append("- **Лексиконы лемматизируются тем же движком, что и корпус** — "
             "иначе слитный артикль в терме («חוק הגיוס») не совпал бы с "
             "разобранным текстом.")
    L.append("")

    L.append("## Чего эти цифры НЕ показывают\n")
    L.append("- Не измеряют правоту, искренность или качество аргумента — "
             "только частоту слов и форму подачи.")
    L.append("- Сарказм, цитирование оппонента и отрицание считаются как "
             "употребление слова.")
    L.append("- Выборка смещена в сторону тех, кто активно ведёт X; часть "
             "политиков (религиозные партии) там почти не пишет.")
    L.append("- Абсолютную вовлечённость нельзя сравнивать между политиками "
             "(разный размер аудитории) — только динамику внутри одного.")
    L.append("")
    return "\n".join(L)


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"[methodology] -> {OUT} ({OUT.stat().st_size} байт)")


if __name__ == "__main__":
    main()
