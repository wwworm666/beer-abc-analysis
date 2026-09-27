"""Диагностика отзывов Яндекс Бизнеса (этап 0): вход, филиалы, последние отзывы.

Ничего не пишет ни в хранилище отзывов, ни в Яндекс — только читает кабинет
и печатает, что получено, чтобы до подключения к странице /reviews проверить
на реальных данных: наши ли филиалы, их permanent_id, формат отзыва (оценка,
дата — секунды или миллисекунды, ответ организации), работает ли пагинация.
Модуль и правила — docs/yandex-reviews.md; клиент — core/yandex_business.py.

Cookies берутся из окружения или из .env в корне репозитория (он в .gitignore):
    YANDEX_BUSINESS_SESSION_ID=<значение cookie Session_id>
    YANDEX_BUSINESS_SESSION_ID2=<значение cookie sessionid2>
Скрипт их не печатает и не сохраняет.

Запуск из корня репозитория:
    py -3 scripts/yandex_reviews_probe.py                 филиалы + 5 последних отзывов каждого
    py -3 scripts/yandex_reviews_probe.py --last 10       10 последних
    py -3 scripts/yandex_reviews_probe.py --walk          + пройти все страницы и сверить число
                                                            отзывов со счётчиком Яндекса
    py -3 scripts/yandex_reviews_probe.py --dump DIR      + сохранить сырые ответы в DIR
                                                            (служебные токены вырезаются)
    py -3 scripts/yandex_reviews_probe.py --only 1,2      отзывы только этих организаций
                                                            (permanent_id через запятую)

Коды выхода: 0 — всё прочитано; 2 — нет cookies; 3 — сессия не принята;
4 — капча; 5 — иной сбой.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.yandex_business import (MAX_REVIEW_PAGES, YandexAuthError,  # noqa: E402
                                  YandexBusinessClient, YandexBusinessError, YandexCaptchaError,
                                  parse_review)

ENV_SESSION_ID = 'YANDEX_BUSINESS_SESSION_ID'
ENV_SESSION_ID2 = 'YANDEX_BUSINESS_SESSION_ID2'
TEXT_PREVIEW = 90   # знаков текста отзыва в строке вывода


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, '.env'), override=False)
    except ImportError:
        pass


def _strip_tokens(value):
    """Копия ответа без служебных токенов (csrf ответа, токены чата) — для --dump."""
    if isinstance(value, dict):
        return {k: _strip_tokens(v) for k, v in value.items()
                if 'csrf' not in k.lower() and 'token' not in k.lower()}
    if isinstance(value, list):
        return [_strip_tokens(v) for v in value]
    return value


def _dump(dump_dir, name, data):
    if not dump_dir:
        return
    os.makedirs(dump_dir, exist_ok=True)
    with open(os.path.join(dump_dir, name), 'w', encoding='utf-8') as f:
        json.dump(_strip_tokens(data), f, ensure_ascii=False, indent=2)


def _line(r):
    text = r['text'].replace('\n', ' ')
    if len(text) > TEXT_PREVIEW:
        text = text[:TEXT_PREVIEW - 1] + '…'
    reply = 'ответ: нет'
    if r['owner_reply']:
        reply = f'ответ: есть ({r["owner_reply"]["at"] or "без даты"})'
    rating = f'{r["rating"]}/5' if r['rating'] is not None else 'без оценки'
    return (f'    {r["created_at"] or "????-??-??T??:??"}  {rating:<10}  {r["author"] or "(без имени)"}'
            f'  [{r["author_privacy"] or "-"}]  «{text}»  {reply}'
            + (f'  фото: {len(r["photos"])}' if r['photos'] else ''))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Диагностика отзывов Яндекс Бизнеса (только чтение).')
    ap.add_argument('--last', type=int, default=5, help='сколько последних отзывов показать у филиала')
    ap.add_argument('--walk', action='store_true', help='пройти все страницы и сверить число со счётчиком')
    ap.add_argument('--dump', metavar='DIR', help='сохранить сырые ответы (без токенов) в DIR')
    ap.add_argument('--only', metavar='ID,ID', default='',
                    help='читать отзывы только этих организаций (permanent_id через запятую)')
    args = ap.parse_args(argv)
    only = {int(x) for x in args.only.replace(' ', '').split(',') if x.isdigit()}
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:  # noqa: BLE001 — старый поток вывода, печатаем как есть
        pass

    _load_env()
    sid, sid2 = os.environ.get(ENV_SESSION_ID, ''), os.environ.get(ENV_SESSION_ID2, '')
    if not sid.strip() or not sid2.strip():
        print(f'Нет cookies: задайте {ENV_SESSION_ID} и {ENV_SESSION_ID2} в .env или окружении.')
        return 2

    try:
        with YandexBusinessClient(sid, sid2) as api:
            raw_companies = api.list_companies()
            _dump(args.dump, 'companies.json', raw_companies)
            print(f'Вход выполнен. Организаций в аккаунте: {len(raw_companies)}')
            branches = api.branches()
            print(f'\nФилиалы (type ordinal, сети раскрыты): {len(branches)}')
            for b in branches:
                print(f'  permanent_id={b["permanent_id"]}  «{b["name"]}»  {b["address"]}'
                      f'  статус={b["publishing_status"] or "-"}  рейтинг={b["rating"]}'
                      f'  отзывов по счётчику={b["reviews_count"]}'
                      + (f'  сеть «{b["via_chain"]}»' if b['via_chain'] else ''))

            summary = []
            for b in branches:
                pid = b['permanent_id']
                if only and pid not in only:
                    continue
                print(f'\n[{pid}] «{b["name"]}»')
                got, pages, total, problems = 0, 0, None, 0
                shown = 0
                # Без --walk — только первая страница (самые новые отзывы).
                for pg in api.iter_review_pages(pid, max_pages=MAX_REVIEW_PAGES if args.walk else 1):
                    pages += 1
                    total = pg['total']
                    _dump(args.dump, f'reviews_{pid}_p{pg["page"]}.json', pg['items'])
                    for raw in pg['items']:
                        r = parse_review(raw)
                        got += 1
                        if r['problems']:
                            problems += 1
                            print(f'    ! {r["external_id"] or "(без id)"}: ' + '; '.join(r['problems']))
                        if shown < args.last:
                            print(_line(r))
                            shown += 1
                summary.append((pid, b['name'], total, got, pages, problems))

            print('\nИтог по филиалам:')
            for pid, name, total, got, pages, problems in summary:
                check = ''
                if args.walk and total is not None:
                    check = '  совпадает со счётчиком' if got == total else f'  РАСХОЖДЕНИЕ: счётчик {total}'
                print(f'  [{pid}] «{name}»: счётчик Яндекса {total}, получено {got} за {pages} стр.,'
                      f' с замечаниями разбора {problems}{check}')
    except YandexAuthError as e:
        print(f'Сессия не принята: {e}')
        return 3
    except YandexCaptchaError as e:
        print(f'Капча: {e}')
        return 4
    except YandexBusinessError as e:
        print(f'Сбой: {e}')
        return 5
    return 0


if __name__ == '__main__':
    sys.exit(main())
