"""Проверка отзывов на публичных страницах баров на Яндекс Картах — без входа и без записи.

Читает страницы https://yandex.ru/maps/org/<id>/reviews/ четырёх баров так же,
как загрузка (core/yandex_maps_reviews.py), и печатает, что разобралось: число
отзывов и откуда оно взято, номер страницы и число страниц, последние отзывы,
замечания разбора. Ничего не пишет ни в хранилище отзывов, ни куда-либо ещё.
Нужен, чтобы проверить формат страницы на реальных данных: на сервере и с
домашнего адреса Яндекс может отвечать по-разному. Модуль — docs/yandex-reviews.md.

Запуск из корня репозитория:
    py -3 scripts/yandex_maps_reviews_probe.py              первая страница каждого бара, 5 отзывов
    py -3 scripts/yandex_maps_reviews_probe.py --last 10    10 отзывов
    py -3 scripts/yandex_maps_reviews_probe.py --walk       + пролистать все страницы и сверить
                                                              число полученных с числом на Картах
    py -3 scripts/yandex_maps_reviews_probe.py --dump DIR   + сохранить страницы как есть в DIR
    py -3 scripts/yandex_maps_reviews_probe.py --only 31434555884
                                                            только эти организации (id через запятую)

Коды выхода: 0 — всё прочитано и разобрано; 4 — капча; 5 — иной сбой или
листание не сошлось со счётчиком.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import yandex_maps_reviews as mr  # noqa: E402
from core.yandex_reviews_sync import BAR_BY_PERMANENT_ID, BAR_NAMES  # noqa: E402

TEXT_PREVIEW = 90   # знаков текста отзыва в строке вывода


def _fetcher(dump_dir):
    """fetch(org, page) как mr.fetch_page, но с сохранением страницы в dump_dir."""
    import requests

    def get(url, **kw):
        response = requests.get(url, **kw)
        if dump_dir:
            name = url.rstrip('/').split('/org/')[1].replace('/', '_').replace('?', '_')
            with open(os.path.join(dump_dir, name + '.html'), 'w', encoding='utf-8') as f:
                f.write(response.text)
        return response

    return lambda org, page: mr.fetch_page(org, page, get=get)


def _print_reviews(raws, last):
    for raw in raws[:last]:
        item = mr.parse_review(raw)
        reply = 'ответ есть' if item['owner_reply'] else 'без ответа'
        text = item['text'].replace('\n', ' ')
        text = text if len(text) <= TEXT_PREVIEW else text[:TEXT_PREVIEW - 1] + '…'
        print(f'    {item["created_at"]}  {item["rating"]}/5  {item["author"] or "без имени"}  [{reply}]  '
              f'id {item["external_id"]}')
        print(f'      «{text}»')
        for problem in item['problems']:
            print(f'      ! {problem}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--last', type=int, default=5)
    parser.add_argument('--walk', action='store_true')
    parser.add_argument('--dump')
    parser.add_argument('--only')
    args = parser.parse_args(argv)
    if args.dump:
        os.makedirs(args.dump, exist_ok=True)
    only = {int(x) for x in args.only.split(',')} if args.only else None
    fetch = _fetcher(args.dump)
    code = 0
    for index, (org, bar) in enumerate(BAR_BY_PERMANENT_ID.items()):
        if only and org not in only:
            continue
        if index:
            time.sleep(mr.PAUSE_SEC)
        print(f'\n{BAR_NAMES.get(bar, bar)} — организация {org}, {mr.reviews_url(org)}')
        try:
            first = fetch(org, 1)
        except mr.MapsCaptchaError as error:
            print(f'  КАПЧА: {error}')
            return 4
        except mr.MapsReviewsError as error:
            print(f'  ОШИБКА: {error}')
            code = 5
            continue
        print(f'  на странице: {len(first["reviews"])} отзывов; на Картах всего: {first["count"]} '
              f'(источник числа: {first["count_source"] or "не найдено"}); страница {first["page"]} '
              f'из {first["total_pages"]}, по {first["limit"]} на странице')
        _print_reviews(first['reviews'], args.last)
        if args.walk:
            walk = mr.collect_pages(org, first, fetch=fetch)
            got = len({str(r.get('reviewId')) for r in walk['reviews']})
            same = first['count'] is not None and got == first['count']
            print(f'  листание: страниц {walk["pages"]}, получено {got}, на Картах {first["count"]} — '
                  + ('сходится' if same else 'НЕ сходится')
                  + (f'; ошибка: {walk["error"]}' if walk['error'] else ''))
            if walk['captcha']:
                return 4
            if not same or walk['error']:
                code = 5
    return code


if __name__ == '__main__':
    sys.exit(main())
