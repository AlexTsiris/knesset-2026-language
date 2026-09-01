"""Прогон всего конвейера одной командой.

  python run.py --sample          синтетика -> отчёт (проверка, что всё живо)
  python run.py                   реальные данные из data/raw -> отчёт
  python run.py --collect         сбор из X, затем всё остальное
"""
import argparse
import subprocess
import sys


def step(title, module, *args):
    print(f"\n=== {title} ===", flush=True)
    r = subprocess.run([sys.executable, "-m", module, *args])
    if r.returncode != 0:
        sys.exit(f"Шаг «{title}» упал (код {r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="сгенерировать синтетику вместо реального сбора")
    ap.add_argument("--collect", action="store_true",
                    help="собрать твиты из X перед анализом")
    ap.add_argument("--lemmatizer", default=None, help="stanza | dicta | rules")
    args = ap.parse_args()

    if args.sample:
        step("Синтетические данные", "src.collect.make_sample")
        lemma = args.lemmatizer or "rules"
    else:
        if args.collect:
            step("Сбор из X", "src.collect.scrape", "collect")
        lemma = args.lemmatizer or "stanza"

    step("Обработка и лемматизация", "src.process.prepare", "--lemmatizer", lemma)
    step("Метрики", "src.analyze.run")
    step("Отчёт", "src.report.build")
    print("\nГотово. Открой outputs/report.html")


if __name__ == "__main__":
    main()
