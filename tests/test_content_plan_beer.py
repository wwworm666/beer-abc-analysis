"""Контент-план 2026-10-23: сорт в посте, повтор в канале, «На другие бары», перенос по календарю.

Решения владельца 2026-10-23:
1. «Если пива нет на кране, мы не просто ставим пост на паузу, а быстро переписываем под нужный
   и отправляем» — сверка строки про сорт перед выходом (core/content_beer.py, отправщик) и
   «Поставить сорт» вручную (ContentPlanStore.set_beer).
2. «Хорошие посты с других точек можно в следующем месяце переносить на другие бары. В одном
   канале посты не должны дублироваться» — DuplicateIndex (код готовности duplicate) и
   ContentPlanStore.copy_to_bars.
3. Календарь — главная страница, таблица — подстраница; плашки перетаскиваются между днями —
   ContentPlanStore.move_placements и маршруты страниц.

Краны и реестр — поддельные (tests/test_content_beer.py), Telegram — FakeTelegram
(tests/test_content_publisher.py).
"""
import os
import sys
from contextlib import contextmanager
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import core.content_plan as cp  # noqa: E402
import core.taplist_post as taplist_post  # noqa: E402
import test_content_beer as tcb  # noqa: E402
import test_content_publisher as tpub  # noqa: E402

USER = tpub.USER
AGENT = tpub.AGENT

STORY = 'Как Мюнхен сдался светлому\n\n' + 'Мюнхен варил тёмное и был в нём уверен. ' * 4
LINE = 'Сегодня на восьмом кране «Культуры Каск» — Riegele Feines Urhell, хеллес из Аугсбурга, 4,7%.'
POST = STORY.rstrip() + '\n\n' + LINE


class Taps:
    """Подменяемые краны: taps_fn хранилища -> (снимок, реестр)."""

    def __init__(self, **bars):
        self.bars = bars

    def __call__(self):
        snapshot = {tcb.BAR_IDS[bar]: {'name': bar, 'taps': taps} for bar, taps in self.bars.items()}
        return snapshot, tcb.REGISTRY


@contextmanager
def _names():
    saved = taplist_post.load_names
    taplist_post.load_names = lambda path=None: tcb.NAMES
    try:
        yield
    finally:
        taplist_post.load_names = saved


def _env(taps, moment=tpub.SETUP):
    env = tpub.Env(moment)
    env.store.taps_fn = taps
    return env


def _refresh(env):
    env.store._beer_cache = None


# --------------------------------------------------------------------------- 1. сорт в посте

def test_beer_info_in_views_and_compact():
    taps = Taps(ligovskiy=[tcb._tap(8, 'riegele'), tcb._tap(5, 'festhaus')])
    env = _env(taps)
    with _names():
        material = env.material(base_text=POST)
        pid = env.placement(material['id'], bars=['ligovskiy'], date='2026-10-11', time='19:00')
        info = env.view(pid)['beer_info']
        assert info['state'] == 'on_tap' and info['beers'][0]['tap'] == 8 and info['new_line'] is None
        taps.bars['ligovskiy'] = [tcb._tap(5, 'festhaus')]          # Riegele сняли
        _refresh(env)
        info = env.view(pid)['beer_info']
        assert info['state'] == 'swap' and info['replacement']['name'] == 'Festhaus Helles'
        assert info['new_line'] == 'Сегодня на пятом кране «Культуры Каск» — Festhaus Helles, светлый лагер, 4,5%.'
        compact = env.store.month_payload('2026-10', compact=True)
        row = next(m for m in compact['materials'] if m['id'] == material['id'])
        assert row['placements'][0]['beer_state'] == 'swap'
        # таплист (live), Instagram и рассылка — без сверки
        ig = env.placement(material['id'], channel='instagram', date='2026-10-11', time='18:00')
        assert env.view(ig)['beer_info'] is None
    # без кранов (тесты, отдельное хранилище) — сверки нет
    plain = tpub.Env()
    m2 = plain.material(base_text=POST)
    p2 = plain.placement(m2['id'], bars=['ligovskiy'])
    assert plain.view(p2)['beer_info'] is None


def test_publisher_swaps_gone_beer_and_logs():
    taps = Taps(ligovskiy=[tcb._tap(5, 'festhaus'), tcb._tap(1, 'stout')])
    env = _env(taps)
    with _names():
        env.enable(bars=('ligovskiy',))
        mid, pid = tpub._post(env, text=POST, bars=['ligovskiy'])
        env.at(12, 0)
        report = env.run()
        assert report['sent'] == 1, report
        sent = env.tg.sends()[0]['payload']['text']
        assert sent.endswith('Сегодня на пятом кране «Культуры Каск» — Festhaus Helles, светлый лагер, 4,5%.')
        assert sent.startswith(STORY.rstrip())
        raw = env.raw(pid)
        assert raw['status'] == 'published' and raw['delivery']['sent_text'] == sent
        assert raw['delivery']['beer']['to'] == 'Festhaus Helles' and raw['delivery']['beer']['state'] == 'swap'
        assert raw['approved_snapshot']['text'] == POST                    # утверждённый текст не трогается
        assert env.view(pid)['effective_text'] == sent                     # карточка — что ушло
        log = env.store.log_for(mid)
        assert any(e['action'] == 'auto_publish' and 'пост вышел с «Festhaus Helles»' in e['text'] for e in log)


def test_publisher_fixes_moved_tap_and_keeps_on_tap_text():
    taps = Taps(ligovskiy=[tcb._tap(11, 'riegele')])
    env = _env(taps)
    with _names():
        env.enable(bars=('ligovskiy',))
        _mid, pid = tpub._post(env, text=POST, bars=['ligovskiy'])
        env.at(12, 0)
        env.run()
        sent = env.tg.sends()[0]['payload']['text']
        assert 'Сегодня на одиннадцатом кране «Культуры Каск» — Riegele Feines Urhell, хеллес из Аугсбурга' in sent
        assert env.raw(pid)['delivery']['beer']['state'] == 'moved'
    # сорт на своём кране — текст ровно как утверждён, без отметок
    taps2 = Taps(ligovskiy=[tcb._tap(8, 'riegele')])
    env2 = _env(taps2)
    with _names():
        env2.enable(bars=('ligovskiy',))
        _mid, pid2 = tpub._post(env2, text=POST, bars=['ligovskiy'])
        env2.at(12, 0)
        env2.run()
        assert env2.tg.sends()[0]['payload']['text'] == POST
        assert 'beer' not in env2.raw(pid2)['delivery'] and 'sent_text' not in env2.raw(pid2)['delivery']


def test_publisher_stops_when_nothing_to_swap():
    taps = Taps(ligovskiy=[tcb._tap(4, 'cider')])
    env = _env(taps)
    with _names():
        env.enable(bars=('ligovskiy',))
        _mid, pid = tpub._post(env, text=POST, bars=['ligovskiy'])
        env.at(12, 0)
        report = env.run()
        assert report['failed'] == 1 and env.tg.sends() == []
        raw = env.raw(pid)
        assert raw['status'] == 'failed'
        assert '«Riegele Feines Urhell» сняли с крана, а пива для замены на кранах бара нет' in raw['failed_error']


def test_set_beer_rewrites_last_paragraph():
    taps = Taps(ligovskiy=[tcb._tap(5, 'festhaus'), tcb._tap(6, 'pils')],
                varshavskaya=[tcb._tap(2, 'ipa')])
    env = _env(taps)
    with _names():
        material = env.material(base_text=POST)
        pid = env.placement(material['id'], bars=['ligovskiy'], date='2026-10-11', time='19:00')
        env.approve(pid)
        view, unapproved = env.store.set_beer(pid, '6', USER)
        assert unapproved == [pid]                                          # правка содержания
        assert view['base_text'] == STORY.rstrip() + '\n\nСегодня на шестом кране «Культуры Каск» — Zubr Gold, ' \
                                                      'чешский пилснер, 4,6%.'
        # в последнем абзаце сорта нет — строка добавляется абзацем
        m2 = env.material(base_text='История без строки про сорт.\n\nЖдём вас.')
        p2 = env.placement(m2['id'], bars=['ligovskiy'])
        view, _u = env.store.set_beer(p2, 5, USER)
        assert view['base_text'].endswith('Ждём вас.\n\nСегодня на пятом кране «Культуры Каск» — Festhaus Helles, '
                                          'светлый лагер, 4,5%.')
        # у материала есть размещение другого бара с общим текстом — у этого появляется своя версия
        p3 = env.placement(m2['id'], bars=['varshavskaya'])
        view, _u = env.store.set_beer(p3, 2, USER)
        own = next(p for p in view['placements'] if p['id'] == p3)
        assert own['text'].endswith('«Культуры» — Хмель Hop Storm, американский IPA, 6,5%.')
        assert 'Festhaus Helles' in view['base_text']                       # общий текст не тронут
        for bad, message in ((('99',), 'На кране 99'), (('',), 'Укажите номер крана')):
            try:
                env.store.set_beer(pid, bad[0], USER)
                raise AssertionError('ожидалась ошибка')
            except ValueError as e:
                assert message in str(e)
        ig = env.placement(m2['id'], channel='instagram')
        try:
            env.store.set_beer(ig, 5, USER)
            raise AssertionError('Instagram — без сорта')
        except ValueError as e:
            assert 'Telegram-канале конкретного бара' in str(e)


# --------------------------------------------------------------------------- 2. повтор в канале

BODY = 'Чужая привычка, ставшая стилем\n\n' + 'В 1870-х Эжен Роденбах ездил в Англию учиться. ' * 3


def test_duplicate_in_same_channel_blocks_approval():
    env = tpub.Env()
    first = env.material(title='Крем, 10 окт — Фламандский', base_text=BODY + '\n\nСегодня на кране 12.')
    p1 = env.placement(first['id'], bars=['kremenchugskaya'], date='2026-10-10', time='19:00')
    second = env.material(title='Крем, 25 окт — Фламандский', base_text=BODY + '\n\nСегодня на кране 3.')
    p2 = env.placement(second['id'], bars=['kremenchugskaya'], date='2026-10-25', time='19:00')
    other_bar = env.placement(second['id'], bars=['varshavskaya'], date='2026-10-25', time='19:00')
    view = env.view(p2)
    assert view['display_state'] == 'incomplete'
    assert [m['code'] for m in view['missing']] == ['duplicate']
    assert 'этот пост уже есть в канале TG Крем: «Крем, 10 окт — Фламандский», 10 окт' in view['missing'][0]['text']
    assert env.view(p1)['display_state'] == 'ready'                        # первый по дате — оригинал
    assert env.view(other_bar)['display_state'] == 'ready'                 # другой канал — можно
    preview = env.store.approve_preview('2026-10')
    assert p2 in [s['placement_id'] for s in preview['stays_draft']]
    result = env.store.approve([p1, p2, other_bar], USER)
    assert result['approved'] == [p1, other_bar]
    assert result['skipped'][0]['id'] == p2 and 'уже есть в канале TG Крем' in result['skipped'][0]['reasons'][0]
    # короткие служебные объявления повторяются законно
    short = env.material(base_text='Сегодня работаем до двух')
    a = env.placement(short['id'], bars=['bolshoy'], date='2026-10-09')
    b = env.placement(short['id'], bars=['bolshoy'], date='2026-10-16')
    assert env.view(a)['display_state'] == env.view(b)['display_state'] == 'ready'


def test_copy_to_bars_next_month_with_adapted_beer_line():
    taps = Taps(kremenchugskaya=[tcb._tap(12, 'stout')], varshavskaya=[tcb._tap(3, 'porter')],
                bolshoy=[tcb._tap(13, 'stout')])
    env = _env(taps)
    with _names():
        text = BODY + '\n\nСегодня на двенадцатом кране «Культуры» — Black Sheep Irish Stout, 4%.'
        source = env.material(title='Крем, 11 окт — Стаут', base_text=text, agent_rationale='Почему')
        pid = env.placement(source['id'], bars=['kremenchugskaya'], date='2026-10-11', time='19:00')
        result = env.store.copy_to_bars(source['id'], {'bars': ['varshavskaya', 'bolshoy', 'kremenchugskaya']},
                                        USER)
        # 11 октября — 2-е воскресенье; во 2-е воскресенье ноября — 8 ноября
        assert result['date'] == '2026-11-08' and result['time'] == '19:00'
        assert [s['bar'] for s in result['skipped']] == ['kremenchugskaya']   # там пост уже есть
        assert len(result['created']) == 2
        copies = {env.store.get_material(mid)['placements'][0]['bar']: env.store.get_material(mid)
                  for mid in result['created']}
        var, vo = copies['varshavskaya'], copies['bolshoy']
        assert var['title'] == 'Вар, 8 ноя — Стаут' and var['copied_from'] == source['id'] and var['month'] == '2026-11'
        assert var['base_text'].endswith('Сегодня на третьем кране «Культуры» — Тёмная Baltic Night, балтийский '
                                         'портер, 7%.')                    # стаута нет — тёмное
        assert vo['base_text'].endswith('Сегодня на тринадцатом кране «Культуры» — Black Sheep Irish Stout, '
                                        'ирландский стаут, 4%.')            # тот же сорт на своём кране
        assert var['placements'][0]['status'] == 'draft' and var['placements'][0]['time'] == '19:00'
        assert var['agent_rationale'].startswith('Повтор поста «Крем, 11 окт — Стаут» (TG Крем)')
        assert 'copy_bars' in env.log(source['id'])
        # повтор в те же бары — уже есть
        again = env.store.copy_to_bars(source['id'], {'bars': ['varshavskaya']}, USER)
        assert again['created'] == [] and 'уже есть в канале TG Вар' in again['skipped'][0]['reason']
        # таплист — 400
        live = env.material(kind='live', live_source='taplist', base_text=cp.TAPLIST_TEMPLATE)
        try:
            env.store.copy_to_bars(live['id'], {'bars': ['bolshoy']}, USER)
            raise AssertionError('таплист не повторяется')
        except ValueError as e:
            assert 'Таплист' in str(e)
        assert pid


# --------------------------------------------------------------------------- 3. перенос по календарю

def test_move_placements_keeps_approval_and_theme_date():
    env = tpub.Env(datetime(2026, 10, 7, 11, 0))
    material = env.material(planned_date='2026-10-11', base_text='Текст поста')
    pids = [env.placement(material['id'], bars=[b], date='2026-10-11', time='19:00')
            for b in ('bolshoy', 'ligovskiy')]
    env.approve(*pids)
    result = env.store.move_placements({'placement_ids': pids, 'date': '2026-10-18'}, USER)
    assert result['moved'] == pids
    view = result['materials'][0]
    assert view['planned_date'] == '2026-10-18' and all(p['status'] == 'approved' for p in view['placements'])
    assert all(p['date'] == '2026-10-18' for p in view['placements'])
    log = env.store.log_for(material['id'])
    assert 'перенесено на 18 окт; утверждение сохранено' in log[0]['text']
    # в прошлое утверждённое — нельзя, и ничего не переносится (всё или ничего)
    draft_material = env.material(base_text='Черновик')
    draft = env.placement(draft_material['id'], bars=['bolshoy'], date='2026-10-20', time='12:00')
    try:
        env.store.move_placements({'placement_ids': [draft, pids[0]], 'date': '2026-10-01'}, USER)
        raise AssertionError('утверждённое в прошлое — 400')
    except ValueError as e:
        assert 'нельзя перенести утверждённую публикацию в прошлое' in str(e)
    assert env.raw(draft)['date'] == '2026-10-20'
    # черновик можно и в прошлое (покажет «время выхода уже прошло»)
    env.store.move_placements({'placement_ids': [draft], 'date': '2026-10-01'}, USER)
    assert env.raw(draft)['date'] == '2026-10-01'
    # вышедшее — нет
    env.set(pids[1], status='published')
    try:
        env.store.move_placements({'placement_ids': [pids[1]], 'date': '2026-10-25'}, USER)
        raise AssertionError('вышедшее не переносится')
    except ValueError as e:
        assert 'уже вышло' in str(e)
    # одна плашка из двух дней материала — дата темы остаётся
    two = env.material(planned_date='2026-10-14', base_text='Анонс')
    a = env.placement(two['id'], bars=['bolshoy'], date='2026-10-14', time='12:00')
    env.placement(two['id'], channel='instagram', date='2026-10-14', time='18:00')
    env.store.move_placements({'placement_ids': [a], 'date': '2026-10-15'}, USER)
    assert env.store.get_material(two['id'])['planned_date'] == '2026-10-14'


def test_agent_moves_only_own_drafts():
    env = tpub.Env()
    human = env.material(base_text='Пост людей')
    pid = env.placement(human['id'], bars=['bolshoy'], date='2026-10-20')
    try:
        env.store.move_placements({'placement_ids': [pid], 'date': '2026-10-21'}, dict(AGENT, mcp_mode='draft'))
    except cp.ContentPlanConflict:
        pass
    else:
        raise AssertionError('агент в режиме черновиков чужое не двигает')


# --------------------------------------------------------------------------- маршруты

def test_pages_and_routes():
    taps = Taps(ligovskiy=[tcb._tap(5, 'festhaus')])
    env = _env(taps)
    calls = []
    saved_render = tpub.rcp.render_template
    tpub.rcp.render_template = lambda name, **ctx: calls.append((name, ctx.get('cp_view'))) or 'ok'
    try:
        with tpub._client(env) as c:
            assert c.get('/content-plan').status_code == 200
            assert c.get('/content-plan/table?month=2026-10').status_code == 200
            old = c.get('/content-plan?view=table&month=2026-10&state=failed')
            assert old.status_code == 302
            assert old.headers['Location'].endswith('/content-plan/table?month=2026-10&state=failed')
            assert c.get('/content-plan?view=calendar').status_code == 200
    finally:
        tpub.rcp.render_template = saved_render
    assert calls == [('content_plan.html', 'calendar'), ('content_plan.html', 'table'),
                     ('content_plan.html', 'calendar')]
    with _names(), tpub._client(env) as c:
        material = env.material(base_text=POST)
        pid = env.placement(material['id'], bars=['ligovskiy'], date='2026-10-11', time='19:00')
        r = c.post(f'/api/content-plan/placements/{pid}/beer', json={'tap': '5'})
        assert r.status_code == 200 and 'Festhaus Helles' in r.get_json()['material']['base_text']
        r = c.post(f'/api/content-plan/placements/{pid}/beer', json={'tap': '77'})
        assert r.status_code == 400
        r = c.post('/api/content-plan/placements/move', json={'placement_ids': [pid], 'date': '2026-10-14'})
        assert r.status_code == 200 and r.get_json()['moved'] == [pid]
        r = c.post('/api/content-plan/placements/move', json={'placement_ids': [], 'date': '2026-10-14'})
        assert r.status_code == 400
        r = c.post(f'/api/content-plan/materials/{material["id"]}/copy-to-bars',
                   json={'bars': ['varshavskaya'], 'date': '2026-11-08', 'time': '19:00'})
        body = r.get_json()
        assert r.status_code == 200 and len(body['created']) == 1 and body['date'] == '2026-11-08'
        # краны бара для «Поставить сорт»: строка — ровно та, что встанет в пост
        r = c.get('/api/content-plan/beer-options?bar=ligovskiy')
        body = r.get_json()
        assert r.status_code == 200 and [t['tap'] for t in body['taps']] == [5], body
        assert body['taps'][0]['line'] == ('Сегодня на пятом кране «Культуры Каск» — Festhaus Helles, '
                                           'светлый лагер, 4,5%.')
        assert c.get('/api/content-plan/beer-options?bar=all').status_code == 400
        assert c.get('/api/content-plan/beer-options?bar=moon').status_code == 400


def test_beer_options_lists_bar_taps():
    taps = Taps(ligovskiy=[tcb._tap(6, 'pils'), tcb._tap(5, 'festhaus'), tcb._tap(7)],
                varshavskaya=[tcb._tap(2, 'ipa')])
    env = _env(taps)
    with _names():
        got = env.store.beer_options('ligovskiy')
        assert got['bar'] == 'ligovskiy' and got['error'] is None and got['stale'] is None
        # по номеру крана, пустой кран не в списке; имя, стиль и крепость — как в строке поста
        assert [(t['tap'], t['name'], t['style_ru'], t['abv']) for t in got['taps']] == [
            (5, 'Festhaus Helles', 'светлый лагер', 4.5), (6, 'Zubr Gold', 'чешский пилснер', 4.6)]
        assert got['taps'][1]['line'] == 'Сегодня на шестом кране «Культуры Каск» — Zubr Gold, чешский пилснер, 4,6%.'
        assert all(t['mapped'] for t in got['taps'])
        # у другого бара — своё название в строке
        assert env.store.beer_options('varshavskaya')['taps'][0]['line'].startswith('Сегодня на втором кране «Культуры» — ')
        # краны не прочитались — пустой список и причина, а не ошибка страницы
        env.store.taps_fn = lambda: (_ for _ in ()).throw(OSError('нет файла'))
        _refresh(env)
        broken = env.store.beer_options('ligovskiy')
        assert broken['taps'] == [] and broken['error'] == 'Краны бара не прочитались'
        for bad in ('all', '', 'moon'):
            try:
                env.store.beer_options(bad)
                raise AssertionError(f'бар {bad!r} принят')
            except ValueError:
                pass


# --------------------------------------------------------------------------- самозапуск

if __name__ == '__main__':
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('ok   ', name)
        except Exception as e:  # noqa: BLE001 — отчёт по каждому тесту
            failed += 1
            print('FAIL ', name, '-', repr(e)[:800])
    print('\n' + str(len(tests) - failed) + ' passed, ' + str(failed) + ' failed')
    sys.exit(1 if failed else 0)
