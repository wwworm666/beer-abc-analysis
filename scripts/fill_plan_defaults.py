"""
Дописать в файл планов дефолты новых необязательных полей (PlansManager.PLAN_DEFAULTS).

Зачем: с 2026-09-05 у карточки «Доля чеков с картой» (cardChecksShare) есть план,
по умолчанию 70% за любой месяц (решение владельца). На чтении PlansManager подставляет
дефолт сам (with_defaults), но в файле у старых месяцев поля нет. Скрипт один раз
дописывает 70 туда, где поля нет, чтобы значение было видно в файле, бэкапах и при
правке руками. Существующие значения и таймстампы не трогаются; ключи не месячного
формата (например 2025-11-17_2025-11-23) пропускаются и перечисляются в отчёте.
Идемпотентен: повторный запуск ничего не меняет. Перед записью PlansManager делает
копию <файл>.backup. Инициализация PlansManager штатно проверяет daily_plans.json,
как при старте приложения.

Запуск локально (файл по умолчанию - штатный путь PlansManager через core/storage_paths:
/kultura/plansdashboard.json на проде, data/plansdashboard.json локально):
    py -3 -X utf8 scripts/fill_plan_defaults.py --dry-run     # только показать
    py -3 -X utf8 scripts/fill_plan_defaults.py               # записать
    py -3 -X utf8 scripts/fill_plan_defaults.py --file data/plansdashboard.json

На проде (Selectel, контейнер beer-app) - сначала dry-run, затем без флага:
    docker exec beer-app python scripts/fill_plan_defaults.py --dry-run
    docker exec beer-app python scripts/fill_plan_defaults.py
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.plans_manager import PlansManager  # noqa: E402


def print_keys(title, keys):
    """Заголовок со счётчиком и ключи по одному в строке."""
    print(f"{title} ({len(keys)}):")
    for key in keys:
        print(f"  {key}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Дописать дефолты необязательных полей (PLAN_DEFAULTS) в файл планов")
    parser.add_argument('--dry-run', action='store_true',
                        help='только показать, что будет дописано; файл не менять')
    parser.add_argument('--file', default=None,
                        help='путь к файлу планов (по умолчанию штатный путь PlansManager)')
    args = parser.parse_args(argv)

    # Русский вывод и под docker exec без терминала
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

    manager = PlansManager(data_file=args.file) if args.file else PlansManager()
    result = manager.fill_missing_defaults(dry_run=args.dry_run)

    print()
    print(f"Файл планов: {result['file']}")
    print(f"Дефолты: {PlansManager.PLAN_DEFAULTS}")
    if result['dry_run']:
        print("Режим: dry-run, файл не изменён")
        print_keys("Будет обновлено", result['updated'])
    else:
        print("Режим: запись" + ("" if result['updated'] else " (дописывать нечего, файл не изменён)"))
        print_keys("Обновлено", result['updated'])
    print_keys("Без изменений", result['unchanged'])
    print_keys("Пропущено (не месячный ключ)", result['skipped'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
