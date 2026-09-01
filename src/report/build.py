"""outputs/analysis.json -> outputs/report.html

Самодостаточный HTML: без CDN, без внешних шрифтов, всё inline. Открывается
двойным кликом. Ивритские фразы выводятся в правильном RTL-направлении.

  python -m src.report.build
"""
from __future__ import annotations

import datetime as dt
import html
import json

from src.config import CFG, OUTPUTS

IN = OUTPUTS / "analysis.json"
OUT = OUTPUTS / "report.html"

# --- палитра (проверена scripts/validate_palette.js, оба режима) ---
CSS = """
:root {
  color-scheme: light;
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --ink-1: #0b0b0b; --ink-2: #52514e; --ink-muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;


  --warn: #fab219; --crit: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --ink-1: #ffffff; --ink-2: #c3c2b7; --ink-muted: #898781;
    --grid: #2c2c2a; --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-1: #1a1a19; --page: #0d0d0d;
  --ink-1: #ffffff; --ink-2: #c3c2b7; --ink-muted: #898781;
  --grid: #2c2c2a; --axis: #383835;
  --border: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--page); color: var(--ink-1);
  font: 14px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 19px; margin: 44px 0 4px; letter-spacing: -0.01em; }
h3 { font-size: 14px; margin: 0 0 10px; color: var(--ink-2); font-weight: 600; }
.sub { color: var(--ink-2); margin: 0 0 4px; }
.hint { color: var(--ink-muted); font-size: 12.5px; margin: 0 0 16px; max-width: 74ch; }
.card {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 18px 20px; margin: 14px 0;
}
.banner {
  border-left: 3px solid var(--warn); background: var(--surface-1);
  border-radius: 6px; padding: 12px 16px; margin: 0 0 24px;
  border-top: 1px solid var(--border); border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.banner strong { color: var(--crit); }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 8px; }
.tile {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 18px; min-width: 130px; flex: 1 1 130px;
}
.tile .v { font-size: 26px; font-weight: 650; letter-spacing: -0.02em; }
.tile .k { font-size: 12px; color: var(--ink-2); margin-top: 2px; }
.he { direction: rtl; unicode-bidi: isolate; font-size: 14px; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px,1fr)); gap: 14px; }
.grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px,1fr)); gap: 14px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--grid); }
th { color: var(--ink-2); font-weight: 600; font-size: 12px; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12.5px;
          color: var(--ink-2); margin: 0 0 10px; }
.legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block;
            margin-right: 5px; vertical-align: -1px; }
.bar-row { display: grid; grid-template-columns: 150px 1fr 62px; gap: 10px;
           align-items: center; margin: 3px 0; font-size: 13px; }
.bar-track { background: var(--grid); border-radius: 4px; height: 12px;
             position: relative; display: block; overflow: hidden; }
/* display:block обязателен: span -- инлайновый, у инлайна width игнорируется,
   и заливка не рисуется вовсе (виден только пустой трек). */
.bar-fill { display: block; height: 12px; border-radius: 0 4px 4px 0;
            background: var(--s1); min-width: 2px; }
.bar-val { text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-2); }
.name { color: var(--ink-1); overflow: hidden; text-overflow: ellipsis;
        white-space: nowrap; }
.chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chip {
  border: 1px solid var(--border); border-radius: 5px; padding: 3px 8px;
  background: var(--surface-1); font-size: 13px;
}
.chip b { color: var(--ink-muted); font-weight: 500; font-size: 11.5px;
          margin-left: 5px; font-variant-numeric: tabular-nums; }
.hm td { padding: 0; border: none; }
.hm .cell { width: 100%; height: 26px; display: flex; align-items: center;
            justify-content: center; font-size: 11.5px;
            font-variant-numeric: tabular-nums; border: 1px solid var(--surface-1); }
.hm th.rot { font-size: 11px; color: var(--ink-2); vertical-align: bottom;
             padding-bottom: 6px; white-space: nowrap; }

/* Последовательная шкала: один тон, «около нуля» уходит к подложке.
   В светлом режиме это светлые шаги, в тёмном -- тёмные, поэтому режимы
   идут в противоположных направлениях и подбираются каждый под свою
   подложку, а не переворачиваются автоматически. */
.lv0 { background: var(--grid); color: var(--ink-muted); }
.lv1 { background: #cde2fb; color: #0b0b0b; }
.lv2 { background: #9ec5f4; color: #0b0b0b; }
.lv3 { background: #6da7ec; color: #0b0b0b; }
.lv4 { background: #2a78d6; color: #ffffff; }
.lv5 { background: #184f95; color: #ffffff; }
.lv6 { background: #0d366b; color: #ffffff; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .lv1 { background: #0d366b; color: #ffffff; }
  :root:not([data-theme="light"]) .lv2 { background: #184f95; color: #ffffff; }
  :root:not([data-theme="light"]) .lv3 { background: #256abf; color: #ffffff; }
  :root:not([data-theme="light"]) .lv4 { background: #3987e5; color: #0b0b0b; }
  :root:not([data-theme="light"]) .lv5 { background: #6da7ec; color: #0b0b0b; }
  :root:not([data-theme="light"]) .lv6 { background: #9ec5f4; color: #0b0b0b; }
}
:root[data-theme="dark"] .lv1 { background: #0d366b; color: #ffffff; }
:root[data-theme="dark"] .lv2 { background: #184f95; color: #ffffff; }
:root[data-theme="dark"] .lv3 { background: #256abf; color: #ffffff; }
:root[data-theme="dark"] .lv4 { background: #3987e5; color: #0b0b0b; }
:root[data-theme="dark"] .lv5 { background: #6da7ec; color: #0b0b0b; }
:root[data-theme="dark"] .lv6 { background: #9ec5f4; color: #0b0b0b; }
details { margin-top: 10px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 12.5px; }
footer { margin-top: 56px; color: var(--ink-muted); font-size: 12px;
         border-top: 1px solid var(--grid); padding-top: 16px; }
svg .grid-line { stroke: var(--grid); stroke-width: 1; }
svg .spark { fill: none; stroke: var(--s1); stroke-width: 2;
             stroke-linecap: round; stroke-linejoin: round; }
"""

E = html.escape


def he(text: str) -> str:
    """Ивритская строка в LTR-документе: изолируем направление, иначе
    пунктуация и цифры прыгают в начало строки."""
    return f'<span class="he">{E(text)}</span>'


def seq_class(v: float) -> str:
    """Ступень последовательной шкалы. Возвращается КЛАСС, а не цвет: пара
    фон+текст для светлого и тёмного режима задана в CSS. В тёмном режиме
    шкала идёт в обратную сторону (тёмный = «около нуля», ближе к подложке),
    поэтому подобрать её в Python по одному значению нельзя."""
    if v <= 0:
        return "lv0"
    return f"lv{min(6, 1 + int(v * 6))}"


def bar_rows(items: list[tuple[str, float, str]], color: str = "var(--s1)") -> str:
    """items: (подпись, доля 0..1, отображаемое значение). Значение подписано
    у каждой полосы -- это и есть «relief» для цветов с низким контрастом."""
    out = []
    for label, frac, shown in items:
        w = max(1.0, min(100.0, frac * 100))
        out.append(
            f'<div class="bar-row"><span class="name" title="{E(label)}">{E(label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" '
            f'style="width:{w:.1f}%;background:{color}"></span></span>'
            f'<span class="bar-val">{E(shown)}</span></div>'
        )
    return "".join(out)


def sparkline(values: list[float], w: int = 190, h: int = 34) -> str:
    if not values:
        return ""
    mx = max(values) or 1
    n = len(values)
    step = w / max(1, n - 1)
    pts = " ".join(
        f"{i * step:.1f},{h - 3 - (v / mx) * (h - 8):.1f}" for i, v in enumerate(values)
    )
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-hidden="true">'
            f'<line class="grid-line" x1="0" y1="{h-3}" x2="{w}" y2="{h-3}"/>'
            f'<polyline class="spark" points="{pts}"/></svg>')


# --------------------------------------------------------------------------

def build(d: dict) -> str:
    meta = d["meta"]
    pols = d["politicians"]
    order = sorted(pols, key=lambda p: -pols[p]["overview"]["tweets_total"])

    def nm(pid: str) -> str:
        return pols[pid]["profile"]["name_ru"] if pid in pols else pid

    topic_ru = {k: v["ru"] for k, v in CFG.topics.items()}
    topic_short = {k: v.get("short", v["ru"]) for k, v in CFG.topics.items()}
    rhet_ru = {k: v["ru"] for k, v in CFG.rhetoric.items()}

    P: list[str] = []
    A = P.append

    # ---------- шапка ----------
    days_left = (dt.date.fromisoformat(meta["election_day"])
                 - dt.date.fromisoformat(meta["campaign_end"])).days
    A('<div class="wrap">')
    A("<h1>Язык предвыборной кампании</h1>")
    A(f'<p class="sub">Твиты лидеров партий, {meta["campaign_start"]} — '
      f'{meta["campaign_end"]}. Выборы в Кнессет — {meta["election_day"]}.</p>')
    A('<p class="hint">Не политическая оценка, а частотная сводка: что и как '
      'часто говорят. Ретвиты исключены из всех текстовых метрик — это чужие '
      'слова. Лемматизация иврита обязательна, иначе одно слово в четырёх '
      f'формах считалось бы четырьмя разными (бэкенд: <b>{E(meta["lemmatizer"])}</b>).</p>')

    if meta.get("synthetic_data"):
        A('<div class="banner"><strong>ДАННЫЕ СИНТЕТИЧЕСКИЕ.</strong> '
          'Это прогон конвейера на выдуманных твитах из '
          '<code>src/collect/make_sample.py</code>. Ни одна фраза ниже не '
          'является настоящей цитатой. Цифры проверяют работу кода, а не '
          'описывают реальность. Не публиковать и не пересылать.</div>')
    if meta["lemmatizer"] == "rules":
        A('<div class="banner">Лемматизация в режиме <code>rules</code> — '
          'эвристика на приставках. Часть слов будет обрезана неверно. '
          'Для настоящей сводки нужен <code>--lemmatizer stanza</code>.</div>')

    A('<div class="tiles">')
    for v, k in [
        (f'{meta["n_tweets_total"]:,}'.replace(",", " "), "твитов в корпусе"),
        (meta["n_politicians"], "политиков"),
        (meta["days"], "дней кампании"),
        (days_left, "дней до выборов"),
    ]:
        A(f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>')
    A("</div>")

    # ---------- 1. объём ----------
    A("<h2>Кто сколько говорит</h2>")
    A('<p class="hint">Твитов в день за период кампании. Один ряд — одна '
      'величина, поэтому цвет здесь ничего не кодирует.</p>')
    A('<div class="card">')
    mx = max(pols[p]["overview"]["per_day"] for p in order) or 1
    A(bar_rows([(nm(p), pols[p]["overview"]["per_day"] / mx,
                 f'{pols[p]["overview"]["per_day"]:.1f}/дн') for p in order]))
    A("</div>")

    A('<div class="grid2">')
    A('<div class="card"><h3>Доля ретвитов</h3>')
    rt = sorted(order, key=lambda p: -pols[p]["overview"]["retweet_share"])
    A(bar_rows([(nm(p), pols[p]["overview"]["retweet_share"],
                 f'{pols[p]["overview"]["retweet_share"]:.0%}') for p in rt],
               "var(--s2)"))
    A('<p class="hint" style="margin:10px 0 0">Высокая доля = усиливает чужой '
      'голос, а не говорит сам.</p></div>')
    A('<div class="card"><h3>Доля твитов на иврите</h3>')
    hb = sorted(order, key=lambda p: -pols[p]["overview"]["hebrew_share"])
    A(bar_rows([(nm(p), pols[p]["overview"]["hebrew_share"],
                 f'{pols[p]["overview"]["hebrew_share"]:.0%}') for p in hb],
               "var(--s3)"))
    A('<p class="hint" style="margin:10px 0 0">Остаток — англ./арабский: '
      'обращение к внешней аудитории.</p></div>')
    A("</div>")

    # ---------- 2. характерная лексика ----------
    A("<h2>Характерная лексика</h2>")
    A('<p class="hint">Не самые частые слова, а самые <i>отличительные</i>: '
      'log-likelihood (G²) частоты у этого политика против всех остальных. '
      'Слово «Израиль» частое у всех и потому здесь не появится.</p>')
    A('<div class="grid2">')
    for p in order:
        k1 = pols[p]["keyness"].get("1", [])[:10]
        if not k1:
            continue
        A(f'<div class="card"><h3>{E(nm(p))} '
          f'<span style="color:var(--ink-muted);font-weight:400">'
          f'{E(pols[p]["profile"]["party"])}</span></h3><div class="chips">')
        for it in k1:
            ratio = f'×{it["ratio"]:.1f}' if it.get("ratio") else "только он"
            A(f'<span class="chip">{he(it["phrase"])}<b>{E(ratio)}</b></span>')
        A("</div>")
        k3 = pols[p]["keyness"].get("3", [])[:3]
        if k3:
            A('<div style="margin-top:10px"><h3 style="margin-bottom:6px">'
              'Характерные фразы</h3>')
            for it in k3:
                A(f'<div>{he(it["phrase"])} '
                  f'<span style="color:var(--ink-muted);font-size:12px">'
                  f'{it["count"]}×</span></div>')
            A("</div>")
        A("</div>")
    A("</div>")

    # ---------- 3. темы ----------
    A("<h2>Темы</h2>")
    A('<p class="hint">Доля собственных твитов, затронувших тему. Один тон, '
      'чем насыщеннее клетка, тем выше доля: кодируется величина, '
      'а не категория. Сумма по строке '
      'больше 100% — твит может касаться нескольких тем.</p>')
    tkeys = sorted(topic_ru, key=lambda t: -d["corpus"]["topics"][t]["share_of_tweets"])
    A('<div class="card scroll"><table class="hm"><thead><tr><th></th>')
    for t in tkeys:
        A(f'<th class="rot" title="{E(topic_ru[t])}">{E(topic_short[t])}</th>')
    A("</tr></thead><tbody>")
    for p in order:
        A(f'<tr><th style="font-size:12px;white-space:nowrap">{E(nm(p))}</th>')
        for t in tkeys:
            s = pols[p]["topics"][t]["share_of_tweets"]
            v = min(1.0, s / 0.45)  # 45% и выше -- максимум шкалы
            A(f'<td><div class="cell {seq_class(v)}" '
              f'title="{E(nm(p))} — {E(topic_ru[t])}: {s:.0%}">'
              f'{"" if s < 0.03 else f"{s:.0%}"}</div></td>')
        A("</tr>")
    A("</tbody></table></div>")

    # ---------- 4. атака vs программа ----------
    A("<h2>Атака или программа</h2>")
    A('<p class="hint">Доля твитов с лексикой обвинения («ложь», «провал», '
      '«позор») против лексики обещаний («продвинем», «построим», «план»). '
      'Два ряда — есть легенда и подписи значений.</p>')
    A('<div class="card">')
    A('<div class="legend"><span><i style="background:var(--s2)"></i>атака</span>'
      '<span><i style="background:var(--s1)"></i>программа</span></div>')
    atk = sorted(order, key=lambda p: -pols[p]["rhetoric"]["attack"]["share_of_tweets"])
    for p in atk:
        a = pols[p]["rhetoric"]["attack"]["share_of_tweets"]
        g = pols[p]["rhetoric"]["program"]["share_of_tweets"]
        A(f'<div style="margin:8px 0"><div style="font-size:13px">{E(nm(p))}</div>')
        A(bar_rows([("атака", min(1, a / 0.5), f"{a:.0%}")], "var(--s2)"))
        A(bar_rows([("программа", min(1, g / 0.5), f"{g:.0%}")], "var(--s1)"))
        A("</div>")
    A("</div>")

    # ---------- 5. мы / они ----------
    A("<h2>«Мы» против «они»</h2>")
    A('<p class="hint">Отношение местоимений первого лица множественного числа '
      'к третьему. Высокое — язык сплочения, низкое — язык противостояния.</p>')
    A('<div class="card"><table><thead><tr><th>Политик</th>'
      '<th class="num">«мы»</th><th class="num">«они»</th>'
      '<th class="num">мы/они</th></tr></thead><tbody>')
    def wt(p):
        w = pols[p]["rhetoric"]["we_words"]["hits"]
        t = pols[p]["rhetoric"]["they_words"]["hits"]
        return w, t, (w / t if t else float("inf"))
    for p in sorted(order, key=lambda x: -wt(x)[2]):
        w, t, r = wt(p)
        A(f'<tr><td>{E(nm(p))}</td><td class="num">{w}</td>'
          f'<td class="num">{t}</td><td class="num">'
          f'{"—" if t == 0 else f"{r:.1f}"}</td></tr>')
    A("</tbody></table></div>")

    # ---------- 6. упоминания ----------
    A("<h2>Кто про кого</h2>")
    A('<p class="hint">Упоминания по @-хэндлу и по имени в тексте на иврите — '
      'в иврите второй канал основной. Строка — кто говорит, столбец — о ком.</p>')
    mm = d["mentions"]
    ids = [p for p in order]
    emap = {(e["source"], e["target"]): e["weight"] for e in mm["edges"]}
    mxw = max(emap.values()) if emap else 1
    A('<div class="card scroll"><table class="hm"><thead><tr>'
      '<th style="font-size:11px;color:var(--ink-muted)">говорит ↓ / о ком →</th>')
    for t in ids:
        A(f'<th class="rot">{E(nm(t).split()[-1])}</th>')
    A("</tr></thead><tbody>")
    for s in ids:
        A(f'<tr><th style="font-size:12px;white-space:nowrap">{E(nm(s))}</th>')
        for t in ids:
            if s == t:
                A('<td><div class="cell lv0">·</div></td>')
                continue
            w = emap.get((s, t), 0)
            v = w / mxw if mxw else 0
            A(f'<td><div class="cell {seq_class(v)}" '
              f'title="{E(nm(s))} → {E(nm(t))}: {w}">{w or ""}</div></td>')
        A("</tr>")
    A("</tbody></table></div>")

    A('<div class="grid2">')
    A('<div class="card"><h3>О ком говорят больше всего</h3>')
    tb = [(nm(p), w) for p, w in mm["most_talked_about"] if p in pols][:10]
    m = max([w for _n, w in tb] or [1])
    A(bar_rows([(n, w / m, str(w)) for n, w in tb], "var(--s2)"))
    A("</div><div class=\"card\"><h3>Кто больше всех говорит о других</h3>")
    tk = [(nm(p), w) for p, w in mm["most_talkative"] if p in pols][:10]
    m = max([w for _n, w in tk] or [1])
    A(bar_rows([(n, w / m, str(w)) for n, w in tk], "var(--s1)"))
    A("</div></div>")

    # ---------- 7. динамика ----------
    A("<h2>Динамика по неделям</h2>")
    A('<p class="hint">Собственные твиты по неделям. Малые кратные: одна '
      'величина в каждой ячейке, шкала внутри ячейки своя — сравнивается '
      'форма кривой, не высота.</p>')
    wv = d["timeline"]["weekly_volume"]
    weeks = sorted({w for v in wv.values() for w in v})
    A('<div class="grid3">')
    for p in order:
        series = [wv.get(p, {}).get(w, 0) for w in weeks]
        A(f'<div class="card" style="padding:12px 14px"><h3 style="margin-bottom:4px">'
          f'{E(nm(p))}</h3>{sparkline(series)}'
          f'<div style="font-size:11.5px;color:var(--ink-muted)">'
          f'макс {max(series) if series else 0} тв/нед · '
          f'{weeks[0] if weeks else ""}→{weeks[-1] if weeks else ""}</div></div>')
    A("</div>")

    A('<div class="card"><h3>Кто первым поднял тему</h3>')
    A('<p class="hint">Дата второго твита по теме — второй, чтобы отсечь '
      'случайное упоминание.</p><table><thead><tr><th>Тема</th>'
      '<th>Первый</th><th>Второй</th><th>Третий</th></tr></thead><tbody>')
    for t in tkeys:
        fm = d["timeline"]["topic_first_movers"].get(t, [])
        if not fm:
            continue
        cells = "".join(
            f'<td>{E(nm(x["politician_id"]))} '
            f'<span style="color:var(--ink-muted);font-size:11.5px">'
            f'{E(x["date"][5:])}</span></td>' for x in fm[:3])
        cells += "<td></td>" * (3 - len(fm[:3]))
        A(f"<tr><td>{E(topic_ru[t])}</td>{cells}</tr>")
    A("</tbody></table></div>")

    # ---------- 8. стиль ----------
    A("<h2>Стиль</h2>")
    A('<p class="hint">Форма, а не содержание. Восклицания и эмодзи — '
      'интонация; длина — насколько развёрнут аргумент.</p>')
    A('<div class="card scroll"><table><thead><tr><th>Политик</th>'
      '<th class="num">! / твит</th><th class="num">? / твит</th>'
      '<th class="num">эмодзи</th><th class="num">слов</th>'
      '<th class="num">знаков</th><th class="num">с медиа</th>'
      '</tr></thead><tbody>')
    for p in sorted(order, key=lambda x: -pols[x]["style"]["exclamations_per_tweet"]):
        s = pols[p]["style"]
        A(f'<tr><td>{E(nm(p))}</td>'
          f'<td class="num">{s["exclamations_per_tweet"]}</td>'
          f'<td class="num">{s["questions_per_tweet"]}</td>'
          f'<td class="num">{s["emoji_per_tweet"]}</td>'
          f'<td class="num">{s["avg_words"]}</td>'
          f'<td class="num">{s["avg_chars"]}</td>'
          f'<td class="num">{s["media_share"]:.0%}</td></tr>')
    A("</tbody></table></div>")

    A('<div class="card"><h3>Час публикации (время Израиля)</h3>')
    A('<p class="hint">Ось 0—23 ч. Позднее вечернее время = ручное ведение, '
      'ровный дневной график = работа штаба.</p><div class="grid3">')
    for p in order:
        hh = pols[p]["style"]["hour_histogram"]
        series = [hh.get(str(i), 0) for i in range(24)]
        A(f'<div><div style="font-size:12.5px">{E(nm(p))}</div>'
          f'{sparkline(series, 190, 30)}</div>')
    A("</div></div>")

    # ---------- 9. слоганы ----------
    A("<h2>Повторяемость</h2>")
    A('<p class="hint">Самая частая 4-грамма и доля твитов, где она есть. '
      'Высокая доля — заученная мантра; низкая — живой язык.</p>')
    A('<div class="card scroll"><table><thead><tr><th>Политик</th>'
      '<th>Самая частая фраза</th><th class="num">в % твитов</th>'
      '<th class="num">разных 4-грамм</th></tr></thead><tbody>')
    for p in sorted(order, key=lambda x: -pols[x]["slogans"]["share_of_tweets"]):
        s = pols[p]["slogans"]
        A(f'<tr><td>{E(nm(p))}</td>'
          f'<td>{he(s["top_phrase"]) if s["top_phrase"] else "—"}</td>'
          f'<td class="num">{s["share_of_tweets"]:.0%}</td>'
          f'<td class="num">{s.get("distinct_4grams", 0)}</td></tr>')
    A("</tbody></table></div>")

    # ---------- 10. что залетает ----------
    A("<h2>Что «залетает»</h2>")
    A('<p class="hint">Медианные лайки твитов с фразой, поделённые на общую '
      'медиану политика. Медиана, а не среднее: один виральный твит не должен '
      'решать всё. Только фразы, встретившиеся не меньше 5 раз.</p>')
    A('<div class="grid2">')
    for p in order:
        pe = pols[p]["phrase_engagement"][:6]
        if not pe:
            continue
        A(f'<div class="card"><h3>{E(nm(p))}</h3><table><tbody>')
        for it in pe:
            A(f'<tr><td>{he(it["phrase"])}</td>'
              f'<td class="num">×{it["lift"]:.1f}</td>'
              f'<td class="num" style="color:var(--ink-muted)">'
              f'{it["count"]}×</td></tr>')
        A("</tbody></table></div>")
    A("</div>")

    # ---------- корпус ----------
    A("<h2>Общий словарь кампании</h2>")
    A('<p class="hint">Самые частые фразы по всем политикам вместе — язык '
      'кампании как таковой.</p>')
    A('<div class="grid2">')
    for n, title in [("1", "Слова"), ("2", "Пары"), ("3", "Тройки"), ("4", "Четвёрки")]:
        items = d["corpus"]["ngrams"].get(n, [])[:14]
        if not items:
            continue
        A(f'<div class="card"><h3>{title}</h3><div class="chips">')
        for it in items:
            A(f'<span class="chip">{he(it["phrase"])}<b>{it["count"]}</b></span>')
        A("</div></div>")
    A("</div>")

    A(f'<footer>Собрано {E(meta["generated_at"])}. '
      f'Лемматизация: {E(meta["lemmatizer"])}. '
      'Источник — публичные твиты; ретвиты исключены из текстовых метрик. '
      'Метрики описывают частоту слов, а не правоту говорящего.</footer>')
    A("</div>")

    return ("<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Язык предвыборной кампании</title>"
            f"<style>{CSS}</style></head><body>{''.join(P)}</body></html>")


def main() -> None:
    if not IN.exists():
        raise SystemExit(f"Нет {IN}. Сначала: python -m src.analyze.run")
    d = json.loads(IN.read_text(encoding="utf-8"))
    OUT.write_text(build(d), encoding="utf-8")
    print(f"[report] -> {OUT}  ({OUT.stat().st_size / 1024:.0f} КБ)")
    if d["meta"].get("synthetic_data"):
        print("[report] ВНИМАНИЕ: отчёт построен на синтетических данных.")


if __name__ == "__main__":
    main()
