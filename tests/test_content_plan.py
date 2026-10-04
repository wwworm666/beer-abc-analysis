"""
Тесты контент-плана раздела «Гости»: core/content_plan.py, core/content_media.py,
routes/content_plan.py.

Self-runnable: `py -3 tests/test_content_plan.py` (совместимо с pytest).

Данные — временные файлы; часы магазина заморожены (now_fn), поэтому «сегодня»
всегда 2026-10-07 12:00 по Москве (среда). Приложение — голый Flask только с
content_plan_bp (app.py не импортируется: он запускает боевой Telegram).
Живые данные таплиста — поддельные снимок кранов и реестр Untappd.

Что проверяется:
- каждый код готовности и их порядок; display_state/display_label; правила
  сводки материала (1..9) и дата материала;
- утверждение только готовых, confirm_bot для рассылок бота (400, ничего не
  утверждается), предпросмотр «Утвердить готовые» с фильтрами;
- авто-снятие утверждения при правке общего текста и текста размещения
  (список unapproved), перенос даты сохраняет утверждение, запрет переноса в
  прошлое, вышедшее/отменённое — только чтение;
- все переходы статусов (таблица из спецификации) и 409 на остальные;
- пауза по бару и по сети (сетевые 'all' пауза одного бара не трогает),
  сдвиг с защитой от прошлого, повтор по дням недели, копирование месяца
  (n-й день недели, 5-й -> последний, серии, очистка содержания, 409, прошлое);
- живой предпросмотр: формат строк и каждое правило остановки;
- файлы: сигнатуры, плохие имена -> 404, общий файл удаляется только без ссылок;
- битый файл -> 503 и файл не перезаписан; сохранение между экземплярами;
- attention_counts, create_material, масштаб месяца (in_month), журнал,
  массовые действия, страница /content-plan.
- правки по ревью 2026-09-27: вид «по всем месяцам» (?state=overdue|failed без
  month); вышедшее размещение показывает снимок (content_source, media_items),
  remove_media не трогает вышедшие/отменённые; предел длины живых данных по
  площадке и фото; подписи «Шаблон утверждён…», «Вышло: N из M», «Не хватает:
  … — где»; kind в предпросмотре утверждения; copy_month — опорная дата со
  сдвигом (порядок и интервалы) и объединение размещений серии.
- ИИ-агент (MCP, 2026-09-27): origin ставит сервер по via_mcp (в теле — 400),
  подпись «anna · агент» в журнале и *_by; agent_rationale / shot_list —
  сохранение, пределы, не снимают утверждение; старые данные — 'human',
  неизвестный origin — 503; копии (повтор, копирование месяца) — origin того,
  кто копирует, пояснения — вместе с содержанием; «Удалить черновики ИИ»
  (правило черновика, явные id, файлы, журнал); фильтр origin в предпросмотре
  утверждения.
"""

import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import types
from contextlib import contextmanager
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import core.content_media as cm  # noqa: E402
import core.content_plan as cp  # noqa: E402
import routes.content_plan as rcp  # noqa: E402
from routes.content_plan import content_plan_bp  # noqa: E402

# Владелец — администратор: утверждение и снятие паузы с 2026-09-28 только для
# администратора (routes/content_plan.py, admin_required); права бармена —
# tests/test_content_publisher.py::test_admin_only_routes.
USER = {'login': 'anna', 'display_name': 'Анна', 'is_admin': True}
# Тот же владелец, но через MCP: так его видит маршрут, когда мост
# core/mcp/bridge.py исполняет инструмент агента (поле login прежнее).
AGENT = {'login': 'anna', 'display_name': 'Анна', 'is_admin': True, 'via_mcp': True, 'mcp_client': 'Claude',
         'mcp_token_id': 't1'}
NOW = datetime(2026, 10, 7, 12, 0)      # среда
NOW_STR = '2026-10-07T12:00'
MONTH = '2026-10'

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
WEBP = b'RIFF\x00\x00\x00\x00WEBPVP8 ' + b'\x00' * 16
MP4 = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 32
HEIC = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 32


# --------------------------------------------------------------------------- помощники

class Clock:
    """Подменяемые часы магазина."""

    def __init__(self, moment=NOW):
        self.moment = moment

    def __call__(self):
        return self.moment


def _tmpdir():
    tmp = tempfile.mkdtemp(prefix='content_plan_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def _store(moment=NOW):
    clock = Clock(moment)
    store = cp.ContentPlanStore(os.path.join(_tmpdir(), 'content_plan.json'), now_fn=clock)
    store.clock = clock
    return store


@contextmanager
def _client(store, user=USER):
    """Голое приложение с content_plan_bp; user — кто «вошёл» (AGENT — вызов
    через MCP: мост кладёт 'via_mcp': True в пользователя)."""
    saved = (rcp._store, rcp.current_user)
    rcp._store = lambda: store
    rcp.current_user = lambda: user
    try:
        app = Flask('test_content_plan')
        app.register_blueprint(content_plan_bp)
        yield app.test_client()
    finally:
        rcp._store, rcp.current_user = saved


def _material(store, **fields):
    base = {'month': MONTH, 'title': 'Октоберфест', 'base_text': 'Приходите на Октоберфест'}
    base.update(fields)
    return store.create_material(base, USER)


def _add(store, material_id, **fields):
    """Добавить размещения (по умолчанию Telegram ВО, 9 октября 16:00) -> [pid]."""
    fields.setdefault('channel', 'telegram')
    if fields['channel'] == 'telegram':
        fields.setdefault('bars', ['bolshoy'])
    fields.setdefault('date', '2026-10-09')
    fields.setdefault('time', '16:00')
    _m, created = store.add_placements(material_id, fields, USER)
    return created


def _raw(store, pid):
    return store.get_placement_raw(pid)[1]


def _view(store, pid):
    material, _p = store.get_placement_raw(pid)
    return next(p for p in store.get_material(material['id'])['placements'] if p['id'] == pid)


def _set(store, pid, **fields):
    """Поставить размещению поля напрямую (статусы, в которые API не переводит)."""
    with store._tx() as (data, _after):
        _m, placement = store._placement(data, pid)
        placement.update(fields)


def _log_actions(store, material_id):
    return [e['action'] for e in store.log_for(material_id)]


def _pm(**kw):
    material = {'id': 'm_x', 'month': MONTH, 'title': 'T', 'kind': 'fixed', 'live_source': None,
                'base_text': 'Текст', 'media': [], 'media_required': False, 'placements': []}
    material.update(kw)
    return material


def _pp(**kw):
    placement = {'id': 'p_x', 'channel': 'telegram', 'bar': 'bolshoy', 'date': '2026-10-09',
                 'time': '16:00', 'text': None, 'media': None, 'audience': None, 'status': 'draft'}
    placement.update(kw)
    return placement


def _files(n):
    return [{'name': f'cp_20261007_{i:012x}.jpg', 'kind': 'image'} for i in range(n)]


def _codes(material, placement):
    return [m['code'] for m in cp.readiness(material, placement, NOW_STR)]


def _texts(material, placement):
    return [m['text'] for m in cp.readiness(material, placement, NOW_STR)]


def _skip(reason):
    """Под pytest — pytest.skip; при самостоятельном запуске — просто сообщение."""
    if __name__ == '__main__':
        print(f'skip: {reason}')
        return
    import pytest
    pytest.skip(reason)


def _upload(c, material_id, data, filename='photo.png'):
    return c.post(f'/api/content-plan/materials/{material_id}/media',
                  data={'file': (io.BytesIO(data), filename)}, content_type='multipart/form-data')


# --------------------------------------------------------------------------- готовность

def test_readiness_each_code():
    assert _codes(_pm(), _pp()) == []
    # no_text: пустой общий текст; своя пустая версия перекрывает общий текст
    assert _codes(_pm(base_text='   '), _pp()) == ['no_text']
    assert _texts(_pm(base_text=''), _pp()) == ['нет текста']
    assert _codes(_pm(base_text=''), _pp(text='Своё')) == []
    assert _codes(_pm(base_text='Общий'), _pp(text='')) == ['no_text']
    # живые данные: источник, шаблон, подстановки
    assert _codes(_pm(kind='live', base_text=''), _pp()) == ['no_live_source', 'no_template']
    assert _texts(_pm(kind='live', base_text=''), _pp())[1] == 'нет шаблона'
    live = _pm(kind='live', live_source='taplist', base_text='{бар} {дата} {таплист} {кранов} {цена} {цена} {Бар}')
    assert _texts(live, _pp()) == ['неизвестная подстановка {цена}', 'неизвестная подстановка {Бар}']
    assert _codes(_pm(base_text='Цена {цена}'), _pp()) == []          # у готовой публикации {…} — просто текст
    assert _codes(_pm(kind='live', live_source='taplist', base_text='x' * 5000), _pp()) == []  # длину живого проверяет предпросмотр
    # no_media: Instagram без файлов; «Нужно фото»; пустая подборка размещения
    assert _codes(_pm(), _pp(channel='instagram', bar='all')) == ['no_media']
    assert _texts(_pm(), _pp(channel='instagram', bar='all')) == ['нет фото']
    assert _codes(_pm(media=_files(1)), _pp(channel='instagram', bar='all')) == []
    assert _codes(_pm(media_required=True), _pp()) == ['no_media']
    assert _codes(_pm(media_required=True, media=_files(1)), _pp()) == []
    assert _codes(_pm(media=_files(2)), _pp(channel='instagram', bar='all', media=[])) == ['no_media']
    # too_many_media
    assert _codes(_pm(media=_files(10), base_text='x'), _pp()) == []
    assert _texts(_pm(media=_files(11), base_text='x'), _pp()) == ['больше 10 файлов']
    # text_too_long: 4096 без медиа, 1024 подпись с медиа, Instagram 2200
    assert _codes(_pm(base_text='x' * 4096), _pp()) == []
    assert _texts(_pm(base_text='x' * 4097), _pp()) == ['текст длиннее 4096 знаков']
    assert _codes(_pm(base_text='x' * 1024, media=_files(1)), _pp()) == []
    assert _texts(_pm(base_text='x' * 1025, media=_files(1)), _pp()) == ['текст длиннее 1024 знаков']
    assert _codes(_pm(base_text='x' * 2200, media=_files(1)), _pp(channel='instagram', bar='all')) == []
    assert _texts(_pm(base_text='x' * 2201, media=_files(1)),
                  _pp(channel='instagram', bar='all')) == ['текст длиннее 2200 знаков']
    assert _texts(_pm(base_text='x' * 1025, media=_files(1)),
                  _pp(channel='bot', bar='all', audience={'segment': 'bot_all'})) == ['текст длиннее 1024 знаков']
    # подборка без файлов -> лимит без медиа
    assert _codes(_pm(base_text='x' * 1025, media=_files(1)), _pp(media=[])) == []
    # no_bar
    assert _texts(_pm(), _pp(bar='all')) == ['не выбран бар']
    assert _codes(_pm(), _pp(channel='bot', bar='all', audience={'segment': 'bot_bar'})) == ['no_bar']
    assert _codes(_pm(), _pp(channel='bot', bar='all', audience={'segment': 'bot_all'})) == []
    assert _codes(_pm(), _pp(channel='bot', bar='bolshoy', audience={'segment': 'bot_bar'})) == []
    assert _texts(_pm(kind='live', live_source='taplist', base_text='{таплист}', media=_files(1)),
                  _pp(channel='instagram', bar='all')) == ['для таплиста выберите бар']
    # no_audience
    assert _texts(_pm(), _pp(channel='bot', bar='bolshoy')) == ['не выбрана аудитория']
    # no_date / no_time
    assert _texts(_pm(), _pp(date=None, time=None)) == ['нет даты', 'нет времени']
    # in_past: сравнение с точностью до минуты
    assert _texts(_pm(), _pp(date='2026-10-07', time='11:59')) == ['время выхода уже прошло']
    assert _codes(_pm(), _pp(date='2026-10-07', time='12:00')) == []
    # не черновик — готовность не проверяется
    assert _codes(_pm(base_text=''), _pp(status='approved', date=None)) == []


def test_readiness_order():
    assert _codes(_pm(base_text='x' * 5000, media=_files(11)), _pp(bar='all', date=None, time=None)) == [
        'too_many_media', 'text_too_long', 'no_bar', 'no_date', 'no_time']
    assert _codes(_pm(base_text=''), _pp(channel='bot', bar='all', date='2026-10-01', time='10:00')) == [
        'no_text', 'no_audience', 'in_past']
    assert _codes(_pm(kind='live', base_text='{x}'), _pp(channel='instagram', bar='all')) == [
        'no_live_source', 'bad_placeholder', 'no_media', 'no_bar']


def test_effective_text_and_media():
    material = _pm(base_text='Общий', media=_files(3))
    names = [f['name'] for f in material['media']]
    assert cp.effective_text(material, _pp()) == 'Общий'
    assert cp.effective_text(material, _pp(text='Своё')) == 'Своё'
    assert cp.effective_media(material, _pp()) == names
    unknown = 'cp_20261007_ffffffffffff.jpg'
    assert cp.effective_media(material, _pp(media=[names[2], unknown, names[0], names[2]])) == [names[2], names[0]]


def test_display_state_and_labels():
    state, missing = cp.display_state(_pm(base_text=''), _pp(date=None), NOW_STR)
    assert state == 'incomplete' and cp.display_label(state, missing) == 'Не хватает: нет текста, нет даты'
    state, missing = cp.display_state(_pm(), _pp(), NOW_STR)
    assert (state, missing, cp.display_label(state, missing)) == ('ready', [], 'Готово к утверждению')
    expected = [
        (_pp(status='approved'), 'scheduled', 'Запланировано'),
        (_pp(status='approved', date='2026-10-07', time='12:00'), 'scheduled', 'Запланировано'),
        (_pp(status='approved', date='2026-10-07', time='11:59'), 'overdue', 'Время вышло, выход не отмечен'),
        (_pp(status='paused'), 'paused', 'На паузе'),
        (_pp(status='paused', date='2026-10-01'), 'paused', 'На паузе'),
        (_pp(status='published'), 'published', 'Вышло'),
        (_pp(status='failed'), 'failed', 'Ошибка отправки'),
        (_pp(status='cancelled'), 'cancelled', 'Отменено'),
    ]
    for placement, want_state, want_label in expected:
        state, missing = cp.display_state(_pm(), placement, NOW_STR)
        assert (state, cp.display_label(state, missing)) == (want_state, want_label), placement


def test_summary_rules():
    def s(*states):
        return cp.material_summary(list(states))

    def miss(*texts):
        return [{'code': 'x', 'text': t} for t in texts]

    r = s()
    assert (r['label'], r['tone'], r['total'], r['ready'], r['counts']) == ('Только тема', 'muted', 0, 0, {})
    r = s(('cancelled', []), ('cancelled', []))
    assert (r['label'], r['tone'], r['total'], r['counts']) == ('Отменено', 'muted', 0, {'cancelled': 2})
    r = s(('failed', []), ('incomplete', miss('нет текста')), ('cancelled', []))
    assert (r['label'], r['tone']) == ('Ошибка отправки: 1', 'danger')
    r = s(('incomplete', miss('нет текста', 'нет даты')), ('incomplete', miss('нет даты', 'нет фото')),
          ('overdue', []), ('ready', []))
    assert (r['label'], r['tone']) == ('Не хватает: нет текста, нет даты, нет фото', 'warning')
    r = s(('overdue', []), ('overdue', []), ('ready', []))
    assert (r['label'], r['tone']) == ('Время вышло: 2', 'warning')
    r = s(('ready', []), ('ready', []), ('cancelled', []))
    assert (r['label'], r['tone'], r['ready'], r['total']) == ('Готово к утверждению', 'accent', 2, 2)
    r = s(('ready', []), ('scheduled', []), ('published', []))
    assert (r['label'], r['tone']) == ('Готово к утверждению: 1 из 3', 'accent')
    r = s(('published', []), ('published', []), ('cancelled', []))
    assert (r['label'], r['tone'], r['total'], r['counts']) == ('Вышло', 'success', 2,
                                                                {'published': 2, 'cancelled': 1})
    # 8: часть вышла, остальные запланированы или на паузе — «Вышло: N из M»
    r = s(('paused', []), ('scheduled', []), ('published', []))
    assert (r['label'], r['tone'], r['rule'], r['state']) == ('Вышло: 1 из 3', 'success', 8, 'published')
    r = s(('scheduled', []), ('published', []), ('published', []), ('cancelled', []))
    assert (r['label'], r['tone']) == ('Вышло: 2 из 3', 'success')
    # 9: на паузе, ничего не вышло
    r = s(('paused', []), ('scheduled', []))
    assert (r['label'], r['tone'], r['rule']) == ('На паузе: 1', 'muted', 9)
    # 10: все запланированы
    r = s(('scheduled', []), ('scheduled', []))
    assert (r['label'], r['tone'], r['rule'], r['state']) == ('Запланировано', 'success', 10, 'scheduled')
    assert s()['state'] == 'empty' and s(('cancelled', []))['state'] == 'cancelled'
    assert len(cp.SUMMARY_RULES) == 11          # заголовок + десять правил для подсказки


def test_live_labels_and_missing_by_place():
    # Живой материал: утверждён шаблон, данные подставятся при выходе (ревью 2026-09-27).
    assert cp.LIVE_SCHEDULED_LABEL == 'Шаблон утверждён, данные — при выходе'
    assert cp.display_label('scheduled', [], live=True) == cp.LIVE_SCHEDULED_LABEL
    assert cp.display_label('scheduled', []) == 'Запланировано'
    assert cp.display_label('overdue', [], live=True) == 'Время вышло, выход не отмечен'
    r = cp.material_summary([('scheduled', []), ('scheduled', [])], live=True)
    assert (r['label'], r['tone'], r['state']) == (cp.LIVE_SCHEDULED_LABEL, 'success', 'scheduled')
    assert cp.material_summary([('scheduled', []), ('published', [])], live=True)['label'] == 'Вышло: 1 из 2'

    store = _store()
    live = _material(store, title='Таплист', kind='live', live_source='taplist', base_text='{таплист}')
    pids = _add(store, live['id'], bars=['bolshoy', 'varshavskaya'])
    store.approve(pids, USER)
    view = store.get_material(live['id'])
    assert [p['display_state'] for p in view['placements']] == ['scheduled', 'scheduled']
    assert {p['display_label'] for p in view['placements']} == {cp.LIVE_SCHEDULED_LABEL}
    assert view['summary']['label'] == cp.LIVE_SCHEDULED_LABEL
    _set(store, pids[0], status='published')
    assert store.get_material(live['id'])['summary']['label'] == 'Вышло: 1 из 2'
    assert store.month_payload(MONTH)['live_scheduled_label'] == cp.LIVE_SCHEDULED_LABEL

    # «Не хватает»: Telegram-посты готовы, Instagram без фото — сказано, где именно.
    ann = _material(store, title='Анонс')
    _add(store, ann['id'], bars=['varshavskaya', 'ligovskiy'])
    _add(store, ann['id'], channel='instagram')
    summary = store.get_material(ann['id'])['summary']
    assert summary['label'] == 'Не хватает: нет фото — IG Сеть'
    assert summary['missing'] == [{'code': 'no_media', 'text': 'нет фото', 'where': ['IG Сеть'],
                                   'everywhere': False}]
    # одинаковые причины собираются вместе; причина во всех размещениях — «везде»
    many = _material(store, title='Без текста', base_text='')
    ok, photo = store.media.save(PNG, '2026-10-07')
    store.add_media(many['id'], photo, len(PNG), 'a.png', USER)
    _add(store, many['id'], bars=['bolshoy'])
    _add(store, many['id'], bars=['ligovskiy', 'varshavskaya'], time=None)
    _add(store, many['id'], channel='instagram')
    assert store.get_material(many['id'])['summary']['label'] == (
        'Не хватает: нет текста — везде; нет времени — TG Лиг, TG Вар')
    # одно неотменённое размещение — прежний вид, без мест
    one = _material(store, title='Один')
    _add(store, one['id'], channel='instagram', time=None)
    p_cancel = _add(store, one['id'], bars=['bolshoy'], time=None)[0]
    _set(store, p_cancel, status='cancelled')
    assert store.get_material(one['id'])['summary']['label'] == 'Не хватает: нет фото, нет времени'
    # без мест (двойки) — тоже прежний вид
    r = cp.material_summary([('incomplete', [{'code': 'no_text', 'text': 'нет текста'}]),
                             ('incomplete', [{'code': 'no_date', 'text': 'нет даты'}])])
    assert r['label'] == 'Не хватает: нет текста, нет даты'

    # предпросмотр утверждения помечает тип материала
    preview = store.approve_preview(MONTH)
    kinds = {i['title']: i['kind'] for i in preview['will_approve'] + preview['stays_draft']}
    assert kinds['Анонс'] == 'fixed'
    fresh = _material(store, title='Таплист 2', kind='live', live_source='taplist', base_text='{таплист}')
    _add(store, fresh['id'], bars=['varshavskaya'])
    assert [i['kind'] for i in store.approve_preview(MONTH)['will_approve'] if i['title'] == 'Таплист 2'] == ['live']


def test_material_date():
    material = _pm(planned_date='2026-10-20', placements=[
        _pp(date='2026-10-15'), _pp(date='2026-10-05', status='cancelled'), _pp(date=None)])
    assert cp.material_date(material) == '2026-10-15'
    assert cp.material_date(_pm(planned_date='2026-10-20')) == '2026-10-20'
    assert cp.material_date(_pm(planned_date=None, placements=[_pp(date='2026-10-05', status='cancelled')])) is None


# --------------------------------------------------------------------------- материалы

def test_create_material_and_validation():
    store = _store()
    with _client(store) as c:
        r = c.post('/api/content-plan/materials', json={'month': MONTH, 'title': '  Октоберфест   2026 '})
        assert r.status_code == 200, r.get_json()
        m = r.get_json()['material']
        assert m['id'].startswith('m_') and len(m['id']) == 14
        assert (m['title'], m['kind'], m['month'], m['created_by'], m['created_at']) == (
            'Октоберфест 2026', 'fixed', MONTH, 'anna', NOW_STR)
        assert m['summary']['label'] == 'Только тема' and m['in_month'] is True and m['placements'] == []
        assert m['date'] is None
        # дата темы задаёт месяц
        m2 = c.post('/api/content-plan/materials', json={'month': MONTH, 'title': 'Ноябрь',
                                                         'planned_date': '2026-11-03'}).get_json()['material']
        assert m2['month'] == '2026-11' and m2['date'] == '2026-11-03'
        bad = [
            ({'month': MONTH}, 'Название обязательно'),
            ({'month': MONTH, 'title': '   '}, 'Название обязательно'),
            ({'month': '2026-13', 'title': 'x'}, None),
            ({'title': 'x'}, None),
            ({'month': MONTH, 'title': 'x', 'kind': 'poster'}, None),
            ({'month': MONTH, 'title': 'x', 'live_source': 'taplist'}, None),
            ({'month': MONTH, 'title': 'x', 'kind': 'live', 'live_source': 'weather'}, None),
            ({'month': MONTH, 'title': 'x' * 201}, None),
            ({'month': MONTH, 'title': 'x', 'base_text': 'x' * 10001}, None),
            ({'month': MONTH, 'title': 'x', 'planned_date': '2026-02-30'}, None),
            ({'month': MONTH, 'title': 'x', 'media_required': 'может быть'}, None),
        ]
        for body, text in bad:
            r = c.post('/api/content-plan/materials', json=body)
            assert r.status_code == 400, body
            if text:
                assert r.get_json()['error'] == text
    # публичный create_material (его зовёт routes/reviews.py)
    made = store.create_material({'month': MONTH, 'title': 'Отзыв гостя — ВО', 'kind': 'fixed',
                                  'base_text': '«Спасибо»\n— Ира', 'source_review_id': 'r_abc',
                                  'media_required': 'false'}, USER)
    assert made['source_review_id'] == 'r_abc' and made['media_required'] is False and made['month'] == MONTH
    assert store.log_for(made['id'])[0]['text'] == 'Создан материал «Отзыв гостя — ВО» из отзыва гостя'
    live = store.create_material({'month': MONTH, 'title': 'Таплист', 'kind': 'live', 'live_source': 'taplist'}, None)
    assert live['live_source'] == 'taplist' and live['created_by'] == 'unknown'


def test_update_material_fields_and_kind():
    store = _store()
    m = _material(store, kind='live', live_source='taplist', base_text='{таплист}')
    with _client(store) as c:
        r = c.patch(f'/api/content-plan/materials/{m["id"]}', json={'kind': 'fixed'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['material']['kind'] == 'fixed' and body['material']['live_source'] is None
        assert c.patch(f'/api/content-plan/materials/{m["id"]}', json={'live_source': 'taplist'}).status_code == 400
        r = c.patch(f'/api/content-plan/materials/{m["id"]}', json={'planned_date': '2026-11-02'})
        assert r.get_json()['material']['month'] == '2026-11'
        assert c.patch('/api/content-plan/materials/m_nope', json={'title': 'x'}).status_code == 404
        assert c.get(f'/api/content-plan/materials/{m["id"]}').get_json()['material']['id'] == m['id']
        assert c.get('/api/content-plan/materials/m_nope').status_code == 404


# --------------------------------------------------------------------------- утверждение

def test_approve_only_ready_and_bot_confirmation():
    store = _store()
    m = _material(store)
    p_ready = _add(store, m['id'])[0]
    p_nobar = _add(store, m['id'], bars=['all'])[0]
    p_bot = _add(store, m['id'], channel='bot', audience={'segment': 'bot_all'})[0]
    p_ready2 = _add(store, m['id'], bars=['ligovskiy'])[0]
    with _client(store) as c:
        r = c.post('/api/content-plan/approve', json={'placement_ids': [p_ready, p_nobar]})
        assert r.status_code == 200
        assert r.get_json() == {'approved': [p_ready], 'skipped': [{'id': p_nobar, 'reasons': ['не выбран бар']}]}
        raw = _raw(store, p_ready)
        assert (raw['status'], raw['approved_at'], raw['approved_by']) == ('approved', NOW_STR, 'anna')
        assert raw['approved_snapshot'] == {'text': 'Приходите на Октоберфест', 'media': []}
        assert _view(store, p_ready)['display_state'] == 'scheduled'
        # рассылка бота без подтверждения: 400 и НИЧЕГО не утверждается
        r = c.post('/api/content-plan/approve', json={'placement_ids': [p_ready2, p_bot]})
        assert r.status_code == 400 and r.get_json()['error'] == 'Подтвердите аудиторию рассылки'
        assert _raw(store, p_ready2)['status'] == 'draft' and _raw(store, p_bot)['status'] == 'draft'
        r = c.post('/api/content-plan/approve', json={'placement_ids': [p_bot], 'confirm_bot': 'false'})
        assert r.status_code == 400
        r = c.post('/api/content-plan/approve', json={'placement_ids': [p_ready2, p_bot], 'confirm_bot': True})
        assert r.get_json()['approved'] == [p_ready2, p_bot]
        r = c.post('/api/content-plan/approve', json={'placement_ids': [p_ready, 'p_nope']})
        assert r.get_json() == {'approved': [], 'skipped': [
            {'id': p_ready, 'reasons': ['уже не черновик (утверждено)']},
            {'id': 'p_nope', 'reasons': ['размещение не найдено']}]}
        assert c.post('/api/content-plan/approve', json={'placement_ids': []}).status_code == 400
        assert c.post('/api/content-plan/approve', json={}).status_code == 400
    assert _log_actions(store, m['id']).count('approve') == 3


def test_approve_preview():
    store = _store()
    a = _material(store, title='А')
    a_bol = _add(store, a['id'])[0]
    a_lig = _add(store, a['id'], bars=['ligovskiy'], time='18:00')[0]
    a_ig = _add(store, a['id'], channel='instagram')[0]                     # без фото -> остаётся черновиком
    a_bot = _add(store, a['id'], channel='bot', audience='bot_all')[0]
    a_done = _add(store, a['id'], bars=['kremenchugskaya'])[0]
    store.approve([a_done], USER)                                           # не черновик — вне предпросмотра
    b = _material(store, title='Б', month='2026-09')
    b_var = _add(store, b['id'], bars=['varshavskaya'], date='2026-10-12')[0]
    _add(store, b['id'], bars=['varshavskaya'], date='2026-09-30')          # сентябрь — вне масштаба
    c_mat = _material(store, title='В', month='2026-11')
    _add(store, c_mat['id'], date='2026-11-02')
    with _client(store) as c:
        r = c.get('/api/content-plan/approve-preview?month=2026-10')
        assert r.status_code == 200
        p = r.get_json()
        assert [i['placement_id'] for i in p['will_approve']] == [a_bol, a_lig, b_var]
        assert set(p['will_approve'][0]) == {'placement_id', 'material_id', 'title', 'kind', 'origin', 'channel',
                                             'bar', 'date', 'time'}
        assert p['will_approve'][0]['kind'] == 'fixed' and p['will_approve'][0]['origin'] == 'human'
        assert [i['placement_id'] for i in p['bot']] == [a_bot]
        assert p['bot'][0]['audience']['name'] == 'Все подписчики бота' and p['bot'][0]['audience']['size'] is None
        assert [i['placement_id'] for i in p['stays_draft']] == [a_ig]
        assert p['stays_draft'][0]['missing'][0]['code'] == 'no_media'
        p = c.get('/api/content-plan/approve-preview?month=2026-10&bar=bolshoy').get_json()
        assert [i['placement_id'] for i in p['will_approve']] == [a_bol]
        assert [i['placement_id'] for i in p['bot']] == [a_bot]                 # сетевое 'all' входит в бар
        assert [i['placement_id'] for i in p['stays_draft']] == [a_ig]
        p = c.get('/api/content-plan/approve-preview?month=2026-10&channel=telegram').get_json()
        assert (len(p['will_approve']), p['bot'], p['stays_draft']) == (3, [], [])
        assert c.get('/api/content-plan/approve-preview?month=2026-10&bar=moon').status_code == 400
        assert c.get('/api/content-plan/approve-preview?month=2026-10&channel=vk').status_code == 400
        assert c.get('/api/content-plan/approve-preview?month=10-2026').status_code == 400
        assert c.get('/api/content-plan/approve-preview').get_json()['month'] == MONTH


# --------------------------------------------------------------------------- правки

def test_auto_unapprove_on_base_text_edit():
    store = _store()
    m = _material(store, base_text='Текст')
    p_common = _add(store, m['id'])[0]
    p_own = _add(store, m['id'], bars=['ligovskiy'], text='Своя версия')[0]
    store.approve([p_common, p_own], USER)
    with _client(store) as c:
        url = f'/api/content-plan/materials/{m["id"]}'
        # не содержание: название, заметка, дата темы, «нужно фото»
        for body in ({'title': 'Новое'}, {'note': 'заметка'}, {'planned_date': '2026-10-09'},
                     {'media_required': True}):
            r = c.patch(url, json=body)
            assert r.status_code == 200 and r.get_json()['unapproved'] == [], body
        assert _raw(store, p_common)['status'] == 'approved'
        # тот же текст — не правка
        assert c.patch(url, json={'base_text': 'Текст'}).get_json()['unapproved'] == []
        r = c.patch(url, json={'base_text': 'Текст, исправленный'})
        assert r.get_json()['unapproved'] == [p_common]
        raw = _raw(store, p_common)
        assert (raw['status'], raw['approved_at'], raw['approved_by'], raw['approved_snapshot']) == (
            'draft', None, None, None)
        assert _raw(store, p_own)['status'] == 'approved'                   # своя версия текста не изменилась
        entry = store.log_for(m['id'])[0]
        assert (entry['action'], entry['placement_id']) == ('unapprove_auto', p_common)
        # смена типа материала — тоже содержание
        store.approve([p_common], USER)
        store.update_material(m['id'], {'base_text': '{таплист}'}, USER)
        r = c.patch(url, json={'kind': 'live', 'live_source': 'taplist'})
        assert set(r.get_json()['unapproved']) == {p_own}


def test_auto_unapprove_on_placement_edit_and_date_rules():
    store = _store()
    m = _material(store)
    pid = _add(store, m['id'])[0]
    store.approve([pid], USER)
    url = f'/api/content-plan/placements/{pid}'
    with _client(store) as c:
        r = c.patch(url, json={'text': 'Своя версия'})
        assert r.status_code == 200 and r.get_json()['unapproved'] == [pid]
        assert _raw(store, pid)['status'] == 'draft'
        store.approve([pid], USER)
        r = c.patch(url, json={'text': None})                               # null — снова общий текст
        assert r.get_json()['unapproved'] == [pid] and _raw(store, pid)['text'] is None
        store.approve([pid], USER)
        # перенос даты/времени сохраняет утверждение
        r = c.patch(url, json={'date': '2026-10-10', 'time': '18:30'})
        assert r.status_code == 200 and r.get_json()['unapproved'] == []
        raw = _raw(store, pid)
        assert (raw['status'], raw['date'], raw['time']) == ('approved', '2026-10-10', '18:30')
        # в прошлое — нельзя, ничего не меняется
        r = c.patch(url, json={'date': '2026-10-01'})
        assert r.status_code == 400 and r.get_json()['error'] == 'Нельзя перенести утверждённую публикацию в прошлое'
        assert _raw(store, pid)['date'] == '2026-10-10'
        assert c.patch(url, json={'date': '2026-10-07', 'time': '11:00'}).status_code == 400
        assert c.patch(url, json={'time': None}).status_code == 400       # стереть время у утверждённого
        # пауза: перенос сохраняет паузу, смена бара снимает утверждение
        c.post(f'{url}/action', json={'action': 'pause'})
        assert c.patch(url, json={'time': '19:00'}).get_json()['unapproved'] == []
        assert _raw(store, pid)['status'] == 'paused'
        r = c.patch(url, json={'bar': 'ligovskiy'})
        assert r.get_json()['unapproved'] == [pid] and _raw(store, pid)['status'] == 'draft'
        # черновик можно перенести в прошлое: он просто покажет in_past
        r = c.patch(url, json={'date': '2026-10-01'})
        assert r.status_code == 200 and 'in_past' in [x['code'] for x in _view(store, pid)['missing']]
        # проверки ввода
        assert c.patch(url, json={'audience': 'bot_all'}).status_code == 400
        assert c.patch(url, json={'bar': 'moon'}).status_code == 400
        assert c.patch(url, json={'time': '25:00'}).status_code == 400
        assert c.patch(url, json={'media': ['cp_20261007_aaaaaaaaaaaa.jpg']}).status_code == 400
        assert c.patch('/api/content-plan/placements/p_nope', json={'time': '10:00'}).status_code == 404
        # вышедшее и отменённое — только чтение
        _set(store, pid, status='published')
        r = c.patch(url, json={'text': 'x'})
        assert r.status_code == 400 and r.get_json()['error'] == 'Размещение уже вышло'
        r = c.delete(url)
        assert r.status_code == 409
        r = c.delete(f'/api/content-plan/materials/{m["id"]}')
        assert r.status_code == 409 and r.get_json()['error'] == (
            'У материала есть вышедшие размещения: отмените остальные, а материал оставьте для истории')
        _set(store, pid, status='cancelled')
        r = c.patch(url, json={'date': '2026-10-20'})
        assert r.status_code == 400 and r.get_json()['error'] == 'Размещение отменено'
        # удалить отменённое размещение и материал без вышедших — можно
        assert c.delete(url).status_code == 200
        assert c.delete(f'/api/content-plan/materials/{m["id"]}').get_json() == {'deleted': True}
        assert c.delete(f'/api/content-plan/materials/{m["id"]}').status_code == 404


def test_add_placements_mass_assign():
    store = _store()
    m = _material(store, planned_date='2026-10-09')
    with _client(store) as c:
        url = f'/api/content-plan/materials/{m["id"]}/placements'
        r = c.post(url, json={'channel': 'telegram', 'bars': ['bolshoy', 'ligovskiy', 'bolshoy'], 'time': '16:00'})
        assert r.status_code == 200
        body = r.get_json()
        assert len(body['created']) == 2
        placements = body['material']['placements']
        assert [p['bar'] for p in placements] == ['bolshoy', 'ligovskiy']
        assert all(p['date'] == '2026-10-09' and p['status'] == 'draft' and p['ready'] for p in placements)
        assert c.post(url, json={'channel': 'telegram', 'bars': []}).status_code == 400
        assert c.post(url, json={'channel': 'vk', 'bars': ['bolshoy']}).status_code == 400
        assert c.post(url, json={'channel': 'telegram', 'bars': ['all', 'bolshoy']}).status_code == 400
        assert c.post(url, json={'channel': 'telegram', 'bars': ['bolshoy'], 'audience': 'bot_all'}).status_code == 400
        r = c.post(url, json={'channel': 'instagram'})
        ig = r.get_json()['material']['placements'][-1]
        assert (ig['bar'], ig['display_state'], ig['missing'][0]['code']) == ('all', 'incomplete', 'no_media')
        r = c.post(url, json={'channel': 'bot', 'audience': {'segment': 'bot_recent_30'}, 'time': '12:00'})
        bot = r.get_json()['material']['placements'][-1]
        assert bot['audience_info'] == {'segment': 'bot_recent_30', 'name': 'Были в баре за последние 30 дней',
                                        'needs_bar': False, 'size': None, 'size_note': cp.AUDIENCE_SIZE_NOTE}
        assert bot['datetime'] == '2026-10-09T12:00' and bot['effective_text'] == 'Приходите на Октоберфест'
        assert c.post('/api/content-plan/materials/m_nope/placements',
                      json={'channel': 'telegram', 'bars': ['bolshoy']}).status_code == 404


# --------------------------------------------------------------------------- переходы статусов

SPEC_TRANSITIONS = {
    'pause': ({'approved'}, 'paused'),
    'resume': ({'paused'}, 'approved'),
    'unapprove': ({'approved', 'paused'}, 'draft'),
    'mark_published': ({'approved', 'paused', 'failed'}, 'published'),
    'cancel': ({'draft', 'approved', 'paused', 'failed'}, 'cancelled'),
    'restore': ({'cancelled'}, 'draft'),
    'retry': ({'failed'}, 'approved'),
}


def test_every_action_transition():
    store = _store()
    m = _material(store)
    pid = _add(store, m['id'])[0]
    url = f'/api/content-plan/placements/{pid}/action'
    with _client(store) as c:
        for action, (allowed, target) in SPEC_TRANSITIONS.items():
            for status in cp.STATUSES:
                _set(store, pid, status=status, date='2026-10-09', time='16:00', failed_error='сеть')
                r = c.post(url, json={'action': action})
                if status in allowed:
                    assert r.status_code == 200, (action, status, r.get_json())
                    raw = _raw(store, pid)
                    assert raw['status'] == target, (action, status)
                    assert r.get_json()['material']['placements'][0]['status'] == target
                    if action == 'mark_published':
                        assert (raw['published_at'], raw['published_by']) == (NOW_STR, 'anna')
                    if action == 'retry':
                        assert raw['failed_error'] is None
                    if target == 'draft':
                        assert raw['approved_at'] is None and raw['approved_snapshot'] is None
                else:
                    assert r.status_code == 409, (action, status, r.status_code)
                    assert r.get_json()['error'] and _raw(store, pid)['status'] == status
        # снять паузу, когда время выхода прошло — 400
        _set(store, pid, status='paused', date='2026-10-01')
        r = c.post(url, json={'action': 'resume'})
        assert r.status_code == 400 and r.get_json()['error'] == 'Время выхода прошло — перенесите дату'
        assert _raw(store, pid)['status'] == 'paused'
        assert c.post(url, json={'action': 'explode'}).status_code == 400
        assert c.post('/api/content-plan/placements/p_nope/action', json={'action': 'pause'}).status_code == 404
    assert {'pause', 'resume', 'unapprove', 'mark_published', 'cancel', 'restore', 'retry'} <= set(
        _log_actions(store, m['id']))


def test_bulk_pause_by_bar_and_network():
    store = _store()
    m = _material(store, media_required=False)
    a = _add(store, m['id'])[0]                                               # ВО, 9 окт
    b = _add(store, m['id'], channel='instagram')[0]                          # сеть, 9 окт
    cc = _add(store, m['id'], bars=['ligovskiy'], date='2026-10-20')[0]       # Лиг, 20 окт
    d = _add(store, m['id'], date='2026-10-05')[0]                            # ВО, уже прошло
    for pid in (a, b, cc, d):
        _set(store, pid, status='approved')
    with _client(store) as c:
        r = c.post('/api/content-plan/bulk-pause', json={'bar': 'bolshoy', 'action': 'pause'})
        assert r.status_code == 200 and r.get_json() == {'changed': 1, 'skipped': []}
        assert [_raw(store, p)['status'] for p in (a, b, cc, d)] == ['paused', 'approved', 'approved', 'approved']
        r = c.post('/api/content-plan/bulk-pause', json={'bar': 'all', 'action': 'pause'})
        assert r.get_json()['changed'] == 2
        assert [_raw(store, p)['status'] for p in (a, b, cc, d)] == ['paused', 'paused', 'paused', 'approved']
        store.clock.moment = datetime(2026, 10, 9, 17, 0)
        r = c.post('/api/content-plan/bulk-pause', json={'bar': 'all', 'action': 'resume'})
        body = r.get_json()
        assert body['changed'] == 1 and sorted(s['id'] for s in body['skipped']) == sorted([a, b])
        assert all('время выхода прошло' in s['reason'] for s in body['skipped'])
        assert [_raw(store, p)['status'] for p in (a, b, cc, d)] == ['paused', 'paused', 'approved', 'approved']
        assert c.post('/api/content-plan/bulk-pause', json={'bar': 'moon', 'action': 'pause'}).status_code == 400
        assert c.post('/api/content-plan/bulk-pause', json={'bar': 'all', 'action': 'stop'}).status_code == 400
    actions = _log_actions(store, m['id'])
    assert actions.count('bulk_pause') == 3 and actions.count('bulk_resume') == 1


def test_shift_guard():
    store = _store()
    m = _material(store, planned_date='2026-10-09')
    p_app = _add(store, m['id'])[0]
    p_draft = _add(store, m['id'], bars=['ligovskiy'], date='2026-10-10')[0]
    p_pub = _add(store, m['id'], bars=['kremenchugskaya'], date='2026-10-05')[0]
    p_can = _add(store, m['id'], bars=['varshavskaya'], date='2026-10-06')[0]
    store.approve([p_app], USER)
    _set(store, p_pub, status='published')
    _set(store, p_can, status='cancelled')
    url = f'/api/content-plan/materials/{m["id"]}/shift'
    with _client(store) as c:
        r = c.post(url, json={'days': -3})                                     # утверждённое уйдёт на 6 окт
        assert r.status_code == 400 and 'в прошлом' in r.get_json()['error']
        assert (_raw(store, p_app)['date'], _raw(store, p_draft)['date']) == ('2026-10-09', '2026-10-10')
        assert store.get_material_raw(m['id'])['planned_date'] == '2026-10-09'
        r = c.post(url, json={'days': 2})
        assert r.status_code == 200
        assert [_raw(store, p)['date'] for p in (p_app, p_draft, p_pub, p_can)] == [
            '2026-10-11', '2026-10-12', '2026-10-05', '2026-10-06']
        assert _raw(store, p_app)['status'] == 'approved'
        assert r.get_json()['material']['planned_date'] == '2026-10-11'
        for days in (0, 61, -61, 1.5, 'abc', None, True):
            assert c.post(url, json={'days': days}).status_code == 400, days
        # сдвиг через границу месяца переносит и месяц темы
        r = c.post(url, json={'days': 25})
        assert r.get_json()['material']['month'] == '2026-11'
        assert c.post('/api/content-plan/materials/m_nope/shift', json={'days': 1}).status_code == 404


# --------------------------------------------------------------------------- повтор и копия месяца

def test_repeat_by_weekdays():
    store = _store()
    src = _material(store, planned_date='2026-10-09')                         # пятница
    _add(store, src['id'], time='18:00', text='Своя')
    p_cancel = _add(store, src['id'], bars=['ligovskiy'])[0]
    _set(store, p_cancel, status='cancelled')
    with _client(store) as c:
        url = f'/api/content-plan/materials/{src["id"]}/repeat'
        r = c.post(url, json={'weekdays': [4], 'month': MONTH})
        assert r.status_code == 200
        created = r.get_json()['created']
        assert len(created) == 3                                              # 16, 23, 30 окт (2-е прошло, 9-е — сам)
        copies = [store.get_material_raw(i) for i in created]
        assert sorted(x['planned_date'] for x in copies) == ['2026-10-16', '2026-10-23', '2026-10-30']
        series_id = store.get_material_raw(src['id'])['series']['id']
        assert series_id.startswith('s_')
        for x in copies:
            assert x['series'] == {'id': series_id, 'weekdays': [4]}
            assert (x['title'], x['base_text'], x['month']) == ('Октоберфест', 'Приходите на Октоберфест', MONTH)
            assert len(x['placements']) == 1                                  # отменённое не копируется
            p = x['placements'][0]
            assert (p['date'], p['time'], p['text'], p['status']) == (x['planned_date'], '18:00', 'Своя', 'draft')
        # повтор ещё раз — даты заняты серией
        assert c.post(url, json={'weekdays': [4], 'month': MONTH}).get_json()['created'] == []
        # с копии серии — те же занятые даты
        assert c.post(f'/api/content-plan/materials/{created[0]}/repeat',
                      json={'weekdays': [4]}).get_json()['created'] == []
        # добавить субботы: месяц по умолчанию — месяц материала
        r = c.post(url, json={'weekdays': [5]})
        assert len(r.get_json()['created']) == 4                              # 10, 17, 24, 31 окт
        assert store.get_material_raw(src['id'])['series']['weekdays'] == [4, 5]
        assert store.get_material_raw(created[0])['series']['weekdays'] == [4, 5]
        for bad in ([], [7], ['пт'], 'fri', None):
            assert c.post(url, json={'weekdays': bad, 'month': MONTH}).status_code == 400, bad
        assert c.post(url, json={'weekdays': [4], 'month': '2026-1'}).status_code == 400
        assert c.post('/api/content-plan/materials/m_nope/repeat', json={'weekdays': [4]}).status_code == 404


def test_map_nth_weekday():
    assert cp.map_nth_weekday('2026-10-09', 1) == ('2026-11-13', None)        # 2-я пятница
    assert cp.map_nth_weekday('2026-10-30', 1) == ('2026-11-27', (5, 4))      # 5-я пятница -> последняя
    assert cp.map_nth_weekday('2026-10-01', 1) == ('2026-11-05', None)        # 1-й четверг
    assert cp.map_nth_weekday('2026-12-31', 1) == ('2027-01-28', (5, 3))      # через год
    assert cp.map_nth_weekday('2026-10-04', -1) == ('2026-09-06', None)       # 1-е воскресенье


def test_copy_month():
    store = _store()
    ok, name = store.media.save(PNG, '2026-10-07')
    assert ok
    # обычный материал с фото, своей версией текста и утверждённым Instagram
    m1 = _material(store, title='Октоберфест', planned_date='2026-10-09', base_text='Текст')
    store.add_media(m1['id'], name, len(PNG), 'a.png', USER)
    p1 = _add(store, m1['id'], text='Своя')[0]
    p1_ig = _add(store, m1['id'], channel='instagram')[0]
    store.approve([p1_ig], USER)
    p1_cancel = _add(store, m1['id'], bars=['ligovskiy'])[0]
    _set(store, p1_cancel, status='cancelled')
    m2 = _material(store, title='Пятница', planned_date='2026-10-30')          # 5-я пятница
    _add(store, m2['id'], date='2026-10-30')
    m3 = _material(store, title='Таплист', kind='live', live_source='taplist', base_text='{таплист}',
                   planned_date='2026-10-01')
    _add(store, m3['id'], date='2026-10-01', bars=['varshavskaya'])
    m4 = _material(store, title='Идея', base_text='Черновик идеи')            # без даты
    # серия: пятницы 9, 16, 23, 30 октября
    s1 = _material(store, title='Серия', planned_date='2026-10-16', base_text='Серийный')
    _add(store, s1['id'], date='2026-10-16')
    store.repeat(s1['id'], [4], MONTH, USER)
    old_series = store.get_material_raw(s1['id'])['series']['id']
    _material(store, title='Сентябрь', month='2026-09')                        # другой месяц — не копируется

    with _client(store) as c:
        r = c.post('/api/content-plan/copy-month', json={'from': MONTH, 'to': '2026-11'})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body['created'] == 8                                           # 4 обычных + 4 пятницы ноября
        assert '«Пятница»: 5-я пятница → последняя' in body['notes']
        nov = c.get('/api/content-plan?month=2026-11').get_json()['materials']
        by_from = {}
        for x in nov:
            by_from.setdefault(x['copied_from'], []).append(x)
        c1 = by_from[m1['id']][0]
        assert (c1['planned_date'], c1['base_text'], c1['media'], c1['month']) == ('2026-11-13', '', [], '2026-11')
        assert len(c1['placements']) == 2                                     # отменённое не копируется
        for p in c1['placements']:
            assert (p['date'], p['status'], p['text'], p['media'], p['approved_at']) == (
                '2026-11-13', 'draft', None, None, None)
        assert by_from[m2['id']][0]['planned_date'] == '2026-11-27'
        assert by_from[m2['id']][0]['placements'][0]['date'] == '2026-11-27'
        c3 = by_from[m3['id']][0]
        assert (c3['planned_date'], c3['base_text'], c3['kind'], c3['live_source']) == (
            '2026-11-05', '{таплист}', 'live', 'taplist')                      # шаблон живых данных остаётся
        c4 = by_from[m4['id']][0]
        assert (c4['planned_date'], c4['date'], c4['base_text']) == (None, None, '')
        series = [x for x in nov if x['series']]
        assert sorted(x['planned_date'] for x in series) == ['2026-11-06', '2026-11-13', '2026-11-20', '2026-11-27']
        new_ids = {x['series']['id'] for x in series}
        assert len(new_ids) == 1 and old_series not in new_ids
        assert all(x['series']['weekdays'] == [4] and x['base_text'] == '' for x in series)
        assert len({x['copied_from'] for x in series}) == 1
        assert all(x['in_month'] for x in nov)
        # повторное копирование — 409
        r = c.post('/api/content-plan/copy-month', json={'from': MONTH, 'to': '2026-11'})
        assert r.status_code == 409 and r.get_json()['error'] == 'Этот месяц уже скопирован'
        # копия с текстами и фото; from по умолчанию — предыдущий месяц
        r = c.post('/api/content-plan/copy-month', json={'from': MONTH, 'to': '2026-12', 'with_content': True})
        assert r.get_json()['created'] == 8
        dec = c.get('/api/content-plan?month=2026-12').get_json()['materials']
        d1 = next(x for x in dec if x['copied_from'] == m1['id'])
        assert (d1['base_text'], [f['name'] for f in d1['media']]) == ('Текст', [name])
        assert sorted(p['text'] for p in d1['placements'] if p['text']) == ['Своя']
        assert d1['planned_date'] == '2026-12-11'                               # 2-я пятница декабря
        # прошедший месяц и совпадающие месяцы — 400
        r = c.post('/api/content-plan/copy-month', json={'from': '2026-08', 'to': '2026-09'})
        assert r.status_code == 400 and r.get_json()['error'] == 'Нельзя копировать в прошедший месяц'
        assert c.post('/api/content-plan/copy-month', json={'from': MONTH, 'to': MONTH}).status_code == 400
        assert c.post('/api/content-plan/copy-month', json={'to': 'xx'}).status_code == 400
        # пустой месяц-источник
        r = c.post('/api/content-plan/copy-month', json={'from': '2026-05', 'to': '2027-01'})
        assert r.get_json()['created'] == 0 and r.get_json()['notes']
    # файл общий у источника и декабрьской копии: он на диске
    assert store.media.exists(name)


def test_copy_month_past_dates_note():
    store = _store()
    sep = _material(store, title='Сентябрьская', month='2026-09', planned_date='2026-09-04')   # 1-я пятница
    _add(store, sep['id'], date='2026-09-04')
    later = _material(store, title='Поздняя', month='2026-09', planned_date='2026-09-25')      # 4-я пятница
    _add(store, later['id'], date='2026-09-25')
    with _client(store) as c:
        r = c.post('/api/content-plan/copy-month', json={'to': MONTH})            # from = сентябрь
        body = r.get_json()
        assert r.status_code == 200 and body['created'] == 2
        assert any(n.startswith('«Сентябрьская»: 2 окт') and 'дата уже прошла' in n for n in body['notes'])
        assert not any(n.startswith('«Поздняя»') for n in body['notes'])            # 23 окт — впереди
        oct_ = c.get(f'/api/content-plan?month={MONTH}').get_json()['materials']
        copy_ = next(x for x in oct_ if x['copied_from'] == sep['id'])
        p = copy_['placements'][0]
        assert (p['date'], p['status']) == ('2026-10-02', 'draft')
        assert 'in_past' in [x['code'] for x in p['missing']]


def test_copy_anchor():
    assert cp.copy_anchor(_pm(planned_date='2026-10-03', placements=[_pp(date='2026-09-30')])) == '2026-10-03'
    # без даты темы — самая ранняя дата ВНУТРИ месяца материала, а не анонс из прошлого месяца
    assert cp.copy_anchor(_pm(placements=[_pp(date='2026-10-03'), _pp(date='2026-09-28'),
                                          _pp(date='2026-10-01', status='cancelled')])) == '2026-10-03'
    assert cp.copy_anchor(_pm(placements=[_pp(date='2026-11-05'), _pp(date='2026-11-02')])) == '2026-11-02'
    assert cp.copy_anchor(_pm(placements=[_pp(date=None), _pp(date='2026-10-05', status='cancelled')])) is None


def test_copy_month_keeps_order_and_spacing():
    """Регрессия ревью 2026-09-27: каждая дата материала переносилась отдельно по
    «n-й неделе», и анонс (5-я среда) уезжал на 28-е — после события (1-я суббота)."""
    store = _store()
    ev = _material(store, title='Событие', planned_date='2026-10-03')             # 1-я суббота
    _add(store, ev['id'], bars=['bolshoy'], date='2026-09-30')                    # ср — анонс
    _add(store, ev['id'], channel='instagram', date='2026-10-01')                 # чт
    _add(store, ev['id'], channel='bot', audience='bot_all', date='2026-10-02')   # пт — напоминание
    _add(store, ev['id'], bars=['ligovskiy'], date='2026-10-03')                  # сб — сам день
    out = _material(store, title='Выход', planned_date='2026-10-04')              # 1-е воскресенье
    _add(store, out['id'], date='2026-09-30')                                     # за 4 дня
    free = _material(store, title='Без темы')                                     # опора — 3 окт, не 28 сен
    _add(store, free['id'], date='2026-09-28')
    _add(store, free['id'], bars=['ligovskiy'], date='2026-10-03')
    last = _material(store, title='Пятая', planned_date='2026-10-31')             # 5-я суббота
    _add(store, last['id'], date='2026-10-27')                                    # вт, за 4 дня
    body = store.copy_month(MONTH, '2026-11', False, USER)
    assert body['created'] == 4
    nov = {m['copied_from']: m for m in store.month_payload('2026-11')['materials'] if m['copied_from']}

    def dates(material_id):
        return [p['date'] for p in nov[material_id]['placements']]

    # опора 3 окт -> 7 ноя (1-я суббота), сдвиг +35: ср, чт, пт, сб — порядок и дни недели те же
    assert nov[ev['id']]['planned_date'] == '2026-11-07'
    assert dates(ev['id']) == ['2026-11-04', '2026-11-05', '2026-11-06', '2026-11-07']
    from datetime import date as _d
    assert [_d.fromisoformat(x).weekday() for x in dates(ev['id'])] == [2, 3, 4, 5]
    # опора 4 окт -> 1 ноя, сдвиг +28: анонс 30 сен -> 28 окт, вне ноября — заметка
    assert (nov[out['id']]['planned_date'], dates(out['id'])) == ('2026-11-01', ['2026-10-28'])
    assert any(n.startswith('«Выход»: 28 окт — вне месяца') for n in body['notes'])
    # без даты темы: опора — 3 окт (в месяце), 28 сен идёт следом на тот же сдвиг
    assert dates(free['id']) == ['2026-11-02', '2026-11-07']
    assert nov[free['id']]['month'] == '2026-11'
    # 5-я суббота -> последняя (28 ноя), вторник за 4 дня — 24 ноя
    assert (nov[last['id']]['planned_date'], dates(last['id'])) == ('2026-11-28', ['2026-11-24'])
    assert '«Пятая»: 5-я суббота → последняя' in body['notes']
    assert not any('Событие' in n or 'Без темы' in n for n in body['notes'])


def _friday_series(store, title='Таплист пятницы'):
    """Живой таплист по пятницам октября (9, 16, 23, 30) на четыре бара, 18:00."""
    src = _material(store, title=title, kind='live', live_source='taplist', base_text='{таплист}',
                    planned_date='2026-10-09')
    _add(store, src['id'], bars=list(cp.BAR_KEYS), date='2026-10-09', time='18:00')
    copies = store.repeat(src['id'], [4], MONTH, USER)['created']
    members = [src['id']] + copies
    assert [store.get_material_raw(m)['planned_date'] for m in members] == [
        '2026-10-09', '2026-10-16', '2026-10-23', '2026-10-30']
    return members


def _nov_series(store):
    materials = [m for m in store.month_payload('2026-11')['materials'] if m['series']]
    return sorted(materials, key=lambda m: m['planned_date'])


def test_copy_month_series_union_of_days():
    """Регрессия ревью 2026-09-27: образцом серии был самый ранний день, и разовая
    отмена одного бара в этот день пропадала из всех дней следующего месяца."""
    bars = sorted(cp.BAR_KEYS)
    # 1) в первую пятницу отменён Лиговский, у второй пятницы свой текст
    store = _store()
    members = _friday_series(store)
    lig = next(p['id'] for p in store.get_material_raw(members[0])['placements'] if p['bar'] == 'ligovskiy')
    store.placement_action(lig, 'cancel', USER)
    store.update_material(members[1], {'base_text': 'Особый {таплист}'}, USER)
    body = store.copy_month(MONTH, '2026-11', False, USER)
    nov = _nov_series(store)
    assert [m['planned_date'] for m in nov] == ['2026-11-06', '2026-11-13', '2026-11-20', '2026-11-27']
    for m in nov:
        assert sorted(p['bar'] for p in m['placements']) == bars, m['planned_date']
        assert all((p['time'], p['date'], p['status']) == ('18:00', m['planned_date'], 'draft')
                   for p in m['placements'])
        assert (m['base_text'], m['copied_from']) == ('{таплист}', members[0])
    assert body['created'] == 4
    assert ('Серия «Таплист пятницы»: не во все дни были одинаковые размещения (9 окт — нет TG Лиг 18:00) '
            '— в копию взяты размещения всех дней серии') in body['notes']
    assert 'Серия «Таплист пятницы»: тексты или файлы дней серии различались — в копию взяты из дня 9 окт' \
        in body['notes']

    # 2) первая пятница отменена целиком (праздник): образец — вторая пятница
    store = _store()
    members = _friday_series(store)
    store.cancel_material(members[0], USER)
    body = store.copy_month(MONTH, '2026-11', False, USER)
    nov = _nov_series(store)
    assert all(sorted(p['bar'] for p in m['placements']) == bars for m in nov)
    assert {m['copied_from'] for m in nov} == {members[1]}
    assert any('9 окт — все размещения отменены' in n for n in body['notes'])
    assert store.get_material(nov[0]['id'])['summary']['label'] != 'Только тема'

    # 3) в одну пятницу ВО перенесли на 19:00: берутся оба времени, заметка просит убрать лишнее
    store = _store()
    members = _friday_series(store)
    bol = next(p['id'] for p in store.get_material_raw(members[2])['placements'] if p['bar'] == 'bolshoy')
    store.update_placement(bol, {'time': '19:00'}, USER)
    body = store.copy_month(MONTH, '2026-11', False, USER)
    nov = _nov_series(store)
    assert sorted(p['time'] for p in nov[0]['placements'] if p['bar'] == 'bolshoy') == ['18:00', '19:00']
    assert ('Серия «Таплист пятницы»: TG ВО — в разные дни разное время (18:00, 19:00): '
            'в копию взято каждое время, лишнее удалите') in body['notes']

    # 4) все дни серии отменены — копии без размещений, с заметкой
    store = _store()
    members = _friday_series(store)
    for mid in members:
        store.cancel_material(mid, USER)
    body = store.copy_month(MONTH, '2026-11', False, USER)
    assert all(m['placements'] == [] for m in _nov_series(store))
    assert 'Серия «Таплист пятницы»: все размещения отменены — копии созданы без размещений' in body['notes']

    # подборка файлов из другого дня серии — к файлам копии
    assert cp._fit_subset(None, ['a']) is None
    assert cp._fit_subset(['a', 'b'], ['b']) == ['b']
    assert cp._fit_subset(['x'], ['b']) is None             # выбранных фото у копии нет -> «все файлы»
    assert cp._fit_subset([], ['b']) == []                  # «без фото» остаётся «без фото»


# --------------------------------------------------------------------------- живые данные

GUID_A = '11111111-1111-4111-8111-111111111111'
GUID_B = '22222222-2222-4222-8222-222222222222'
GUID_UNKNOWN = '33333333-3333-4333-8333-333333333333'


def _registry_row(guid, bid):
    return {'iiko_product_id': guid, 'iiko_name': f'КЕГ {bid}', 'iiko_article': bid, 'status': 'verified',
            'untappd_beer_id': bid,
            'decision': {'status': 'verified', 'untappd_beer_id': bid, 'reason': 'тест',
                         'reviewed_at': '2026-09-01', 'evidence_urls': [f'https://untappd.com/b/beer/{bid}']}}


def _card(bid, name, brewery, style, abv):
    return {'id': bid, 'url': f'https://untappd.com/b/beer/{bid}', 'beer_name': name, 'brewery': brewery,
            'observed_at': '2026-09-01', 'source_method': 'manual', 'style': style, 'abv_percent': abv}


REGISTRY = {
    'schema_version': 1,
    'products': {GUID_A: _registry_row(GUID_A, '101'), GUID_B: _registry_row(GUID_B, '102')},
    'beers': {'101': _card('101', 'Пилзнер', 'Пивоварня А', 'Pilsner - Czech / Bohemian', 5.0),
              '102': _card('102', 'IPA', 'Б', 'IPA - American', 6.5)},
}
# Краны стоят с 20 сентября: на NOW (7 октября) это не новинки. Свежесть кранов —
# по снятию 1 октября (_fresh): без него последнее изменение было бы 20 сентября,
# 17 дней назад, и пост остановило бы правило stale_taps.
TAP_STARTED = '2026-09-20T12:00:00+03:00'


def _tap(number, beer, guid, status='active', started=TAP_STARTED, history=None):
    active = status == 'active'
    if history is None:
        history = [{'timestamp': started, 'action': 'start', 'beer_name': beer,
                    'iiko_product_id': guid}] if active and beer else []
    return {'tap_number': number, 'current_beer': beer, 'status': status, 'iiko_product_id': guid,
            'started_at': started if active else None, 'history': history}


def _fresh(number):
    """Пустой кран, с которого 1 октября сняли кегу: свежая отметка на странице кранов."""
    return _tap(number, None, None, status='empty', history=[
        {'timestamp': '2026-09-10T12:00:00+03:00', 'action': 'start', 'beer_name': 'КЕГ Старое'},
        {'timestamp': '2026-10-01T12:00:00+03:00', 'action': 'stop', 'beer_name': 'КЕГ Старое'}])


SNAPSHOT = {
    'bar1': {'name': 'Большой пр. В.О', 'taps': [_tap(1, None, None, status='empty')]},
    'bar2': {'name': 'Лиговский', 'taps': [_tap(4, 'КЕГ Неизвестное', GUID_UNKNOWN),
                                           _tap(5, 'КЕГ Без карточки', None),
                                           _tap(6, 'КЕГ Пилзнер', GUID_A), _fresh(9)]},
    'bar4': {'name': 'Варшавская', 'taps': [_tap(2, 'КЕГ Пилзнер', GUID_A), _tap(1, 'КЕГ IPA', GUID_B),
                                            _tap(3, None, None, status='empty'),
                                            _tap(7, 'КЕГ Старое', GUID_A, status='finished'), _fresh(8)]},
}
TEMPLATE = 'Сегодня в баре «{бар}» ({дата}), кранов: {кранов}\n{таплист}'


def _render(bar, template=TEMPLATE, **kw):
    kw.setdefault('snapshot', SNAPSHOT)
    kw.setdefault('registry', REGISTRY)
    return cp.render_live('taplist', bar, template, now=NOW, **kw)


def test_taplist_line_format():
    """Формат владельца 2026-10-04: «{кран}. {пивоварня и название} — {стиль}, {крепость}%[, новинка]»,
    стиль по-русски из словаря, без цен. Правила имени — tests/test_taplist_post.py."""
    assert cp.format_abv(5.0) == '5' and cp.format_abv(6.5) == '6,5' and cp.format_abv('7.25') == '7,25'
    assert cp.format_abv(4.555) == '4,56' and cp.format_abv(4.545) == '4,55' and cp.format_abv('abc') is None
    assert cp.taplist_line({'tap_number': 3, 'beer_name': 'Лагер'}) == '3. Лагер'
    row = {'tap_number': 3, 'beer_name': 'Лагер', 'brewery': 'АФ', 'style': 'Lager - Helles', 'abv': 4.7}
    assert cp.taplist_line(row) == '3. АФ Лагер — светлый лагер, 4,7%'
    assert cp.taplist_line(row, is_new=True) == '3. АФ Лагер — светлый лагер, 4,7%, новинка'
    assert cp.taplist_line({'tap_number': 3, 'beer_name': 'Лагер', 'brewery': 'АФ', 'abv': 0}) == '3. АФ Лагер'
    assert cp.taplist_line({'tap_number': 3, 'beer_name': 'Сидр', 'abv': 6}) == '3. Сидр — 6%'
    # стиля нет в словаре — по-английски в пост не пишем
    assert cp.taplist_line({'tap_number': 3, 'beer_name': 'Сидр', 'style': 'Unknown Style', 'abv': 6}) == '3. Сидр — 6%'


def test_render_live_ok_and_stop_rules():
    r = _render('varshavskaya', pub_date='2026-10-09')
    assert r['ok'] is True and r['problems'] == []
    assert r['text'] == ('Сегодня в баре «Варшавская» (9 октября), кранов: 2\n'
                         '1. Б IPA — американский IPA, 6,5%\n'
                         '2. Пивоварня А Пилзнер — чешский пилснер, 5%')
    assert (r['length'], r['limit'], r['data_at']) == (len(r['text']), 4096, NOW_STR)
    assert [row['tap_number'] for row in r['rows']] == [1, 2] and r['rows'][0]['line'].startswith('1. Б')
    assert (r['rows'][0]['name'], r['rows'][0]['new'], r['rows'][0]['untappd_url']) == (
        'Б IPA', False, 'https://untappd.com/b/beer/102')
    # названия — ссылки на Untappd: сущности Telegram, offset и length в UTF-16
    assert r['entities'] == [
        {'type': 'text_link', 'offset': r['text'].index('Б IPA'), 'length': 5, 'url': 'https://untappd.com/b/beer/102'},
        {'type': 'text_link', 'offset': r['text'].index('Пивоварня А Пилзнер'), 'length': 19,
         'url': 'https://untappd.com/b/beer/101'}]
    assert r['taps_changed_at'] == '2026-10-01T12:00'
    assert '(7 октября)' in _render('varshavskaya')['text']                    # {дата} по умолчанию — сегодня

    def codes(result):
        return [p['code'] for p in result['problems']]

    r = _render('all')
    assert r['ok'] is False and codes(r) == ['no_bar']
    assert r['problems'][0]['text'] == 'для таплиста выберите бар'
    assert codes(_render('')) == ['no_bar']
    r = _render('bolshoy')
    assert codes(r) == ['no_data'] and r['problems'][0]['text'] == 'На кранах бара нет активных позиций'
    r = _render('kremenchugskaya')                                              # бара нет в снимке
    assert codes(r) == ['no_data']
    r = _render('ligovskiy')
    assert codes(r) == ['unverified', 'unverified']
    assert [p['text'] for p in r['problems']] == ['Кран 4: Нет проверенной связи с Untappd',
                                                   'Кран 5: Уточните сорт на кране']
    assert '4. КЕГ Неизвестное\n' in r['text'] and '6. Пивоварня А Пилзнер — чешский пилснер, 5%' in r['text']
    # у крана без карточки Untappd ссылки нет
    assert [e['url'] for e in r['entities']] == ['https://untappd.com/b/beer/101']
    r = _render('varshavskaya', template='{таплист} {цена}')
    assert codes(r) == ['bad_placeholder'] and r['problems'][0]['text'] == 'неизвестная подстановка {цена}'
    r = _render('varshavskaya', template='x' * 4097)
    assert codes(r) == ['text_too_long'] and r['length'] == 4097
    assert _render('varshavskaya', template='x' * 4096)['ok'] is True
    r = cp.render_live(None, 'varshavskaya', TEMPLATE, snapshot=SNAPSHOT, registry=REGISTRY, now=NOW)
    assert codes(r) == ['no_live_source']
    # сбой чтения данных — проблема, а не 500
    r = cp.render_live('taplist', 'varshavskaya', TEMPLATE, snapshot={'bar4': None}, registry=REGISTRY, now=NOW)
    assert codes(r) == ['no_data'] and r['ok'] is False


def test_live_preview_route():
    store = _store()
    m = _material(store, title='Таплист', kind='live', live_source='taplist', base_text=TEMPLATE)
    saved = cp.load_live_data
    cp.load_live_data = lambda registry=None: (SNAPSHOT, REGISTRY)
    try:
        with _client(store) as c:
            r = c.get(f'/api/content-plan/live-preview?material_id={m["id"]}&bar=varshavskaya&date=2026-10-09')
            assert r.status_code == 200
            body = r.get_json()
            assert body['ok'] is True and body['text'].startswith('Сегодня в баре «Варшавская» (9 октября)')
            r = c.get('/api/content-plan/live-preview', query_string={
                'material_id': m['id'], 'bar': 'varshavskaya', 'template': 'Кранов: {кранов}'})
            assert r.get_json()['text'] == 'Кранов: 2'
            r = c.get('/api/content-plan/live-preview', query_string={'source': 'taplist', 'bar': 'bolshoy',
                                                                     'template': '{таплист}'})
            assert r.get_json()['problems'][0]['code'] == 'no_data'
            r = c.post('/api/content-plan/live-preview', json={'material_id': m['id'], 'bar': 'varshavskaya'})
            assert r.status_code == 200 and r.get_json()['ok'] is True
            assert c.get(f'/api/content-plan/live-preview?material_id={m["id"]}&bar=varshavskaya'
                         '&date=09.10.2026').status_code == 400
            assert c.get('/api/content-plan/live-preview?material_id=m_nope&bar=varshavskaya').status_code == 404
            r = c.get('/api/content-plan/live-preview?bar=varshavskaya&template=x')
            assert r.get_json()['problems'][0]['code'] == 'no_live_source'
    finally:
        cp.load_live_data = saved


def test_live_limit_by_channel():
    """Регрессия ревью 2026-09-27: живой предпросмотр всегда мерил 4096, хотя
    подпись к фото в Telegram — 1024, а Instagram — 2200."""
    def codes(result):
        return [p['code'] for p in result['problems']]

    text = 'x' * 1500
    r = _render('varshavskaya', template=text)
    assert (r['ok'], r['limit'], r['channel']) == (True, 4096, None)          # без площадки — как раньше
    assert '4096' in r['limit_note']
    r = _render('varshavskaya', template=text, channel='telegram', has_media=True)
    assert (r['ok'], r['limit'], codes(r)) == (False, 1024, ['text_too_long'])
    assert r['problems'][0]['text'] == 'текст длиннее 1024 знаков' and 'подпись до 1024' in r['limit_note']
    assert _render('varshavskaya', template=text, channel='telegram', has_media=False)['limit'] == 4096
    assert _render('varshavskaya', template=text, channel='bot', has_media=True)['limit'] == 1024
    r = _render('varshavskaya', template=text, channel='instagram')
    assert (r['ok'], r['limit']) == (True, 2200)
    assert codes(_render('varshavskaya', template='x' * 2201, channel='instagram')) == ['text_too_long']
    try:
        _render('varshavskaya', channel='vk')
        raise AssertionError('неизвестная площадка должна давать ValueError')
    except ValueError:
        pass

    store = _store()
    m = _material(store, title='Таплист', kind='live', live_source='taplist', base_text=TEMPLATE)
    ok, photo = store.media.save(PNG, '2026-10-07')
    store.add_media(m['id'], photo, len(PNG), 'bar.png', USER)
    p_photo = _add(store, m['id'], bars=['varshavskaya'])[0]                  # все файлы -> с фото
    p_plain = _add(store, m['id'], bars=['varshavskaya'], media=[])[0]        # без фото
    other = _material(store, title='Другой')
    saved = cp.load_live_data
    cp.load_live_data = lambda registry=None: (SNAPSHOT, REGISTRY)
    try:
        with _client(store) as c:
            url = '/api/content-plan/live-preview'
            r = c.get(url, query_string={'placement_id': p_photo}).get_json()
            # из размещения: бар, дата, площадка и «есть фото»
            assert (r['limit'], r['channel'], r['has_media']) == (1024, 'telegram', True)
            assert r['text'].startswith('Сегодня в баре «Варшавская» (9 октября)')
            assert c.get(url, query_string={'placement_id': p_plain}).get_json()['limit'] == 4096
            r = c.get(url, query_string={'placement_id': p_photo, 'has_media': 'false'}).get_json()
            assert r['limit'] == 4096                                            # переданное главнее
            r = c.post(url, json={'placement_id': p_photo, 'has_media': False}).get_json()
            assert r['limit'] == 4096
            q = {'material_id': m['id'], 'bar': 'varshavskaya'}
            assert c.get(url, query_string=q).get_json()['limit'] == 4096            # без площадки
            assert c.get(url, query_string=dict(q, channel='telegram')).get_json()['limit'] == 1024
            assert c.get(url, query_string=dict(q, channel='instagram')).get_json()['limit'] == 2200
            assert c.get(url, query_string=dict(q, channel='vk')).status_code == 400
            assert c.get(url, query_string={'placement_id': 'p_nope'}).status_code == 404
            r = c.get(url, query_string={'placement_id': p_photo, 'material_id': other['id']})
            assert r.status_code == 400
    finally:
        cp.load_live_data = saved


# --------------------------------------------------------------------------- файлы

def test_media_signatures_and_names():
    assert cm.check(PNG) == (True, 'png') and cm.check(JPEG) == (True, 'jpg')
    assert cm.check(WEBP) == (True, 'webp') and cm.check(MP4) == (True, 'mp4')
    assert cm.check(b'') == (False, 'Файл пустой')
    assert cm.check(b'GIF89a' + b'\x00' * 20) == (False, cm.UNSUPPORTED_TEXT)
    assert cm.check(b'RIFF\x00\x00\x00\x00WAVEfmt ')[0] is False
    ok, err = cm.check(HEIC)
    assert ok is False and 'HEIC' in err
    big = PNG + b'\x00' * cm.MAX_IMAGE_BYTES
    assert cm.check(big) == (False, 'Фото больше 10 МБ')
    for good in ('cp_20261007_abcdef012345.jpg', 'cp_20261007_abcdef012345.mp4'):
        assert cm.is_valid_name(good)
    for bad in ('../content_plan.json', 'cp_20261007_abcdef012345.gif', 'cp_20261007_ABCDEF012345.jpg',
                'cp_2026107_abcdef012345.jpg', 'cp_20261007_abcdef012345.jpg/..', 'x.png', '',
                None, 'cp_20261007_abcdef01234.jpg', '/etc/passwd', 'cp_20261007_abcdef012345.jpg\n'):
        assert not cm.is_valid_name(bad), bad
    media = cm.MediaStore(_tmpdir())
    assert media.path('../x') is None and media.delete('../x') is False and media.exists('x.png') is False
    name = cm.make_name('2026-10-07', 'png')
    assert cm.NAME_RE.match(name) and name.startswith('cp_20261007_')


def test_media_upload_serve_and_delete():
    store = _store()
    m = _material(store)
    pid = _add(store, m['id'])[0]
    store.approve([pid], USER)
    with _client(store) as c:
        r = _upload(c, m['id'], PNG, 'Фото 1.png')
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body['unapproved'] == [pid]                                  # «все файлы» — содержание изменилось
        item = body['material']['media'][0]
        name = item['name']
        assert cm.NAME_RE.match(name) and name.startswith('cp_20261007_') and name.endswith('.png')
        assert (item['kind'], item['size'], item['original_name'], item['uploaded_by'], item['url']) == (
            'image', len(PNG), 'Фото 1.png', 'anna', '/api/content-plan/media/' + name)
        assert os.path.isfile(os.path.join(store.media.directory, name))
        r = c.get(item['url'])
        assert r.status_code == 200 and r.data == PNG and r.mimetype == 'image/png'
        assert r.headers['X-Content-Type-Options'] == 'nosniff'
        r.close()
        for data, fname, kind in ((JPEG, 'a.jpg', 'image'), (WEBP, 'b.webp', 'image'), (MP4, 'c.mov', 'video')):
            got = _upload(c, m['id'], data, fname).get_json()['material']['media'][-1]
            assert got['kind'] == kind
        video = c.get('/api/content-plan/media/' + got['name'])
        assert video.mimetype == 'video/mp4'
        video.close()
        files_before = sorted(os.listdir(store.media.directory))
        # отказы: сигнатура, HEIC, пусто, нет поля, нет материала, слишком большое тело
        r = _upload(c, m['id'], b'hello world, not an image', 'x.png')
        assert r.status_code == 400 and r.get_json()['error'] == cm.UNSUPPORTED_TEXT
        assert 'HEIC' in _upload(c, m['id'], HEIC, 'x.heic').get_json()['error']
        assert _upload(c, m['id'], b'', 'x.png').status_code == 400
        r = c.post(f'/api/content-plan/materials/{m["id"]}/media', data={}, content_type='multipart/form-data')
        assert r.status_code == 400 and r.get_json()['error'] == 'Выберите файл'
        assert _upload(c, 'm_nope', PNG).status_code == 404
        saved_max = rcp.UPLOAD_BODY_MAX
        rcp.UPLOAD_BODY_MAX = 64
        try:
            assert _upload(c, m['id'], PNG + b'\x00' * 100).status_code == 413
        finally:
            rcp.UPLOAD_BODY_MAX = saved_max
        assert sorted(os.listdir(store.media.directory)) == files_before     # отказ не оставляет файлов
        # плохие и неизвестные имена — 404 без обращения к диску
        for bad in ('x.png', 'cp_20261007_zzzzzzzzzzzz.png', 'cp_20261007_abcdef012345.gif',
                    '..%2Fcontent_plan.json', 'cp_20261007_abcdef012345.jpg'):
            assert c.get('/api/content-plan/media/' + bad).status_code == 404, bad
        assert c.delete(f'/api/content-plan/materials/{m["id"]}/media/x.png').status_code == 404
        assert c.delete(f'/api/content-plan/materials/{m["id"]}/media/cp_20261007_abcdef012345.jpg').status_code == 404
        # подборка размещения: удаление файла убирает его из подборки
        c.patch(f'/api/content-plan/placements/{pid}', json={'media': [name]})
        r = c.delete(f'/api/content-plan/materials/{m["id"]}/media/{name}')
        assert r.status_code == 200
        assert _raw(store, pid)['media'] == [] and not os.path.exists(os.path.join(store.media.directory, name))
    assert 'media_add' in _log_actions(store, m['id']) and 'media_delete' in _log_actions(store, m['id'])


def test_material_media_limit():
    store = _store()
    m = _material(store)
    for _ in range(cp.MATERIAL_MEDIA_MAX):
        ok, name = store.media.save(PNG, '2026-10-07')
        store.add_media(m['id'], name, len(PNG), 'x.png', USER)
    with _client(store) as c:
        before = len(os.listdir(store.media.directory))
        r = _upload(c, m['id'], PNG)
        assert r.status_code == 400 and str(cp.MATERIAL_MEDIA_MAX) in r.get_json()['error']
        assert len(os.listdir(store.media.directory)) == before


def test_shared_media_deleted_only_when_unreferenced():
    store = _store()
    a = _material(store, planned_date='2026-10-09')
    _add(store, a['id'])
    ok, name = store.media.save(PNG, '2026-10-07')
    store.add_media(a['id'], name, len(PNG), 'a.png', USER)
    copies = store.repeat(a['id'], [4], MONTH, USER)['created']              # 16, 23, 30 окт делят файл
    assert len(copies) == 3
    path = os.path.join(store.media.directory, name)
    with _client(store) as c:
        for mid in [a['id']] + copies[:-1]:
            assert c.delete(f'/api/content-plan/materials/{mid}/media/{name}').status_code == 200
            assert os.path.isfile(path), mid                                  # последняя копия ещё ссылается
        assert [f['name'] for f in store.get_material_raw(copies[-1])['media']] == [name]
        assert c.delete(f'/api/content-plan/materials/{copies[-1]}/media/{name}').status_code == 200
        assert not os.path.exists(path)
    # удаление материала: файл уходит с диска, только если больше не нужен
    ok, shared = store.media.save(JPEG, '2026-10-07')
    store.add_media(a['id'], shared, len(JPEG), 's.jpg', USER)
    thursdays = store.repeat(a['id'], [3], MONTH, USER)['created']            # 8, 15, 22, 29 окт — с файлом
    assert len(thursdays) == 4
    store.delete_material(a['id'], USER)
    for mid in thursdays[:-1]:
        store.delete_material(mid, USER)
        assert store.media.exists(shared), mid
    store.delete_material(thursdays[-1], USER)
    assert not store.media.exists(shared)


def test_published_placement_shows_snapshot():
    """Регрессия ревью 2026-09-27: вышедший пост показывал ТЕКУЩИЙ текст и файлы
    материала, а не то, что вышло; удаление файла переписывало подборку вышедшего."""
    store = _store()
    ok, photo = store.media.save(PNG, '2026-10-07')
    m = _material(store, base_text='Приходите 10 октября')
    store.add_media(m['id'], photo, len(PNG), 'афиша.png', USER)
    tg = _add(store, m['id'], media=[photo])[0]
    ig = _add(store, m['id'], channel='instagram')[0]
    cancelled = _add(store, m['id'], bars=['ligovskiy'], media=[photo])[0]
    store.approve([tg], USER)
    store.placement_action(tg, 'mark_published', USER)
    store.placement_action(cancelled, 'cancel', USER)
    before = {p['id']: p for p in store.get_material(m['id'])['placements']}
    assert before[tg]['media_items'] == [{'name': photo, 'kind': 'image', 'url': '/api/content-plan/media/' + photo,
                                          'original_name': 'афиша.png'}]
    # правка общего текста и удаление фото ради Instagram-черновика
    store.update_material(m['id'], {'base_text': 'Перенесли на 17 октября'}, USER)
    store.remove_media(m['id'], photo, USER)
    view = {p['id']: p for p in store.get_material(m['id'])['placements']}
    p = view[tg]
    assert (p['status'], p['content_source'], p['effective_text'], p['effective_media']) == (
        'published', 'snapshot', 'Приходите 10 октября', [photo])
    # файла у материала уже нет, но ссылка строится: вид по расширению, URL — раздача
    assert p['media_items'] == [{'name': photo, 'kind': 'image', 'url': '/api/content-plan/media/' + photo,
                                 'original_name': None}]
    q = view[ig]
    assert (q['content_source'], q['effective_text'], q['effective_media'], q['media_items']) == (
        'current', 'Перенесли на 17 октября', [], [])
    # вышедшее и отменённое — только чтение: их подборка не переписана
    assert _raw(store, tg)['media'] == [photo] and _raw(store, cancelled)['media'] == [photo]
    # файл нужен снимку — он на диске и раздаётся
    assert store.media.exists(photo)
    with _client(store) as c:
        r = c.get(p['media_items'][0]['url'])
        assert r.status_code == 200 and r.data == PNG
        r.close()
    # failed со снимком — тоже снимок; мусорное имя в снимке отбрасывается
    _set(store, ig, status='failed', approved_snapshot={'text': 'Старый', 'media': ['../x.png', photo]})
    f = next(x for x in store.get_material(m['id'])['placements'] if x['id'] == ig)
    assert (f['content_source'], f['effective_text'], f['effective_media']) == ('snapshot', 'Старый', [photo])
    # вышедшее без снимка (старые данные) — текущие данные
    _set(store, tg, approved_snapshot=None)
    old = next(x for x in store.get_material(m['id'])['placements'] if x['id'] == tg)
    assert (old['content_source'], old['effective_text']) == ('current', 'Перенесли на 17 октября')
    # у черновика всегда current, даже если снимок остался в данных
    assert all(x['content_source'] == 'current' for x in store.get_material(m['id'])['placements']
               if x['status'] == 'draft')


# --------------------------------------------------------------------------- хранилище

def test_corrupt_file_503_and_not_overwritten():
    for content in ('not json {', '{"version": 1, "materials": []}',
                    '{"version": 1, "materials": {"m_1": {"id": "m_1", "month": "2026-10", '
                    '"placements": [{"id": "p_1", "channel": "vk", "status": "draft"}]}}}'):
        store = _store()
        with open(store.data_file, 'w', encoding='utf-8') as f:
            f.write(content)
        with _client(store) as c:
            calls = (('get', '/api/content-plan', None),
                     ('post', '/api/content-plan/materials', {'month': MONTH, 'title': 'x'}),
                     ('patch', '/api/content-plan/materials/m_1', {'title': 'x'}),
                     ('post', '/api/content-plan/approve', {'placement_ids': ['p_1']}),
                     ('post', '/api/content-plan/bulk-pause', {'bar': 'all', 'action': 'pause'}),
                     ('post', '/api/content-plan/copy-month', {'from': MONTH, 'to': '2026-11'}),
                     ('get', '/api/content-plan/approve-preview', None),
                     ('get', '/api/content-plan/materials/m_1/log', None))
            for method, url, body in calls:
                r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
                assert r.status_code == 503, (content, method, url, r.status_code)
                assert r.get_json()['code'] == 'content_plan_unavailable' and r.get_json()['error']
            r = _upload(c, 'm_1', PNG)
            assert r.status_code == 503
        try:
            store.attention_counts()
            raise AssertionError('attention_counts must raise')
        except cp.ContentPlanUnavailable:
            pass
        with open(store.data_file, encoding='utf-8') as f:
            assert f.read() == content
        assert not os.path.isdir(store.media.directory) or os.listdir(store.media.directory) == []


def test_persistence_across_instances():
    store = _store()
    m = _material(store, note='внутреннее')
    pid = _add(store, m['id'])[0]
    store.approve([pid], USER)
    again = cp.ContentPlanStore(store.data_file, now_fn=store.clock)
    assert again.get_material(m['id']) == store.get_material(m['id'])
    assert again.get_material(m['id'])['placements'][0]['status'] == 'approved'
    assert [e['action'] for e in again.log_for(m['id'])] == ['approve', 'add_placement', 'create']
    with open(store.data_file, encoding='utf-8') as f:
        data = json.load(f)
    assert data['version'] == 1 and set(data) == {'version', 'materials', 'log'}
    assert again.media.directory == store.media.directory
    # пустой план без файла
    fresh = _store()
    assert fresh.month_payload(MONTH)['materials'] == [] and not os.path.exists(fresh.data_file)


def test_log_limit():
    store = _store()
    saved = cp.LOG_MAX
    cp.LOG_MAX = 5
    try:
        m = _material(store)
        for i in range(6):
            store.update_material(m['id'], {'note': f'n{i}'}, USER)
        with open(store.data_file, encoding='utf-8') as f:
            assert len(json.load(f)['log']) == 5
    finally:
        cp.LOG_MAX = saved


def test_attention_counts():
    store = _store()
    m = _material(store)
    p1 = _add(store, m['id'], date='2026-10-07', time='18:00')[0]
    p2 = _add(store, m['id'], channel='instagram', date='2026-10-07', time='10:00')[0]
    p3 = _add(store, m['id'], bars=['ligovskiy'], date='2026-10-07', time='20:00')[0]
    p4 = _add(store, m['id'], date='2026-10-05')[0]
    p5 = _add(store, m['id'], bars=['varshavskaya'], date='2026-10-01')[0]
    _add(store, m['id'], date='2026-10-07', time='19:00')                     # черновик — не считается
    p7 = _add(store, m['id'], date='2026-10-07', time='11:00')[0]
    for pid, status in ((p1, 'approved'), (p2, 'published'), (p3, 'paused'), (p4, 'approved'),
                        (p5, 'failed'), (p7, 'approved')):
        _set(store, pid, status=status)
    net = {'publications_today': 4, 'delivery_errors': 1, 'overdue': 2}
    assert store.attention_counts() == net
    assert store.attention_counts(bar='all') == net and store.attention_counts(bar='') == net
    assert store.attention_counts(bar='bolshoy') == {'publications_today': 3, 'delivery_errors': 0, 'overdue': 2}
    assert store.attention_counts(bar='ligovskiy') == {'publications_today': 2, 'delivery_errors': 0, 'overdue': 0}
    assert store.attention_counts(bar='varshavskaya') == {'publications_today': 1, 'delivery_errors': 1,
                                                          'overdue': 0}
    # явный момент: утром 7-го ничего ещё не просрочено, кроме 5-го
    assert store.attention_counts(now='2026-10-07T09:00')['overdue'] == 1
    assert store.attention_counts(now=datetime(2026, 10, 8, 9, 0))['publications_today'] == 0


def test_month_scope_and_payload():
    store = _store()
    a = _material(store, title='А', planned_date='2026-10-20')
    _add(store, a['id'], date='2026-11-02')                                   # размещение в ноябре
    _add(store, a['id'], date='2026-10-20', bars=['ligovskiy'])
    b = _material(store, title='Б', month='2026-11')
    _add(store, b['id'], date='2026-11-05')
    cm_ = _material(store, title='В')                                           # без даты
    with _client(store) as c:
        nov = c.get('/api/content-plan?month=2026-11').get_json()
        ids = {x['id']: x for x in nov['materials']}
        assert set(ids) == {a['id'], b['id']}
        assert ids[a['id']]['in_month'] is False and ids[b['id']]['in_month'] is True
        assert nov['stats']['materials'] == 1 and nov['stats']['placements'] == 2
        oct_ = c.get('/api/content-plan?month=2026-10').get_json()
        assert [x['id'] for x in oct_['materials']] == [cm_['id'], a['id']]    # «без даты» первыми
        assert all(x['in_month'] for x in oct_['materials'])
        assert oct_['stats'] == {'materials': 2, 'placements': 2, 'by_state': {'ready': 2}}
        default = c.get('/api/content-plan').get_json()
        assert (default['month'], default['now'], default['today']) == (MONTH, NOW_STR, '2026-10-07')
        assert [b_['key'] for b_ in default['bars']] == ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']
        assert default['bars'][0] == {'key': 'bolshoy', 'name': 'Большой пр. В.О', 'short': 'ВО'}
        channels = {ch['key']: ch for ch in default['channels']}
        assert channels['telegram'] == {'key': 'telegram', 'name': 'Telegram', 'bar_rule': 'required',
                                        'text_limit': 4096, 'caption_limit': 1024, 'media_max': 10,
                                        'media_required': False}
        assert (channels['instagram']['bar_rule'], channels['instagram']['text_limit'],
                channels['instagram']['media_required']) == ('network', 2200, True)
        assert channels['bot']['bar_rule'] == 'optional'
        assert [x['key'] for x in default['audiences']] == ['bot_all', 'bot_bar', 'bot_recent_30', 'bot_lapsed_60']
        assert all(x['size'] is None and x['size_note'] for x in default['audiences'])
        assert default['audiences'][1]['needs_bar'] is True
        assert default['live_sources'][0]['key'] == 'taplist'
        assert [p['token'] for p in default['live_sources'][0]['placeholders']] == ['{бар}', '{дата}', '{таплист}',
                                                                                    '{кранов}']
        assert default['delivery_connected'] == {'telegram': False, 'instagram': False, 'bot': False}
        view = ids[a['id']]
        assert view['date'] == '2026-10-20' and view['summary']['label'] == 'Готово к утверждению'
        p = view['placements'][0]
        for key in ('effective_text', 'effective_media', 'missing', 'ready', 'display_state', 'display_label',
                    'datetime', 'audience_info'):
            assert key in p, key
        assert c.get('/api/content-plan?month=2026-13').status_code == 400
        # ?month= у изменяющих запросов задаёт in_month ответа
        r = c.patch(f'/api/content-plan/materials/{a["id"]}?month=2026-11', json={'note': 'x'})
        assert r.get_json()['material']['in_month'] is False
        assert (default['scope'], default['state']) == ('month', None)


def test_cross_month_state_view():
    """Регрессия ревью 2026-09-27: «Время вышло» в полосе внимания считал все месяцы,
    а ссылка открывала только текущий — августовский просроченный пост не находился."""
    store = _store()
    aug = _material(store, title='Август', month='2026-08')
    p_aug = _add(store, aug['id'], date='2026-08-30', time='18:00')[0]
    sep = _material(store, title='Сентябрь', month='2026-09')
    p_sep_future = _add(store, sep['id'], date='2026-10-20')[0]
    p_sep_failed = _add(store, sep['id'], bars=['ligovskiy'], date='2026-09-15')[0]
    octm = _material(store, title='Октябрь')
    p_oct = _add(store, octm['id'], date='2026-10-05')[0]
    nov = _material(store, title='Ноябрь', month='2026-11')
    _add(store, nov['id'], date='2026-11-03')                                     # черновик — не в виде
    for pid, status in ((p_aug, 'approved'), (p_sep_future, 'approved'), (p_sep_failed, 'failed'),
                        (p_oct, 'approved')):
        _set(store, pid, status=status)
    with _client(store) as c:
        r = c.get('/api/content-plan?state=overdue')
        assert r.status_code == 200
        body = r.get_json()
        assert (body['scope'], body['state'], body['month'], body['today']) == ('state', 'overdue', MONTH,
                                                                                '2026-10-07')
        assert [m['id'] for m in body['materials']] == [aug['id'], octm['id']]      # по дате, любой месяц
        assert all(m['in_month'] for m in body['materials'])
        assert body['stats'] == {'materials': 2, 'placements': 2, 'by_state': {'overdue': 2}}
        assert body['bars'] and body['channels'] and body['summary_rules']          # справочники как у месяца
        # столько же, сколько считает полоса внимания
        counts = store.attention_counts()
        assert counts['overdue'] == sum(m['summary']['counts'].get('overdue', 0) for m in body['materials'])
        body = c.get('/api/content-plan?state=failed').get_json()
        assert [m['id'] for m in body['materials']] == [sep['id']]
        assert body['stats'] == {'materials': 1, 'placements': 2, 'by_state': {'scheduled': 1, 'failed': 1}}
        assert counts['delivery_errors'] == 1
        # с month — обычный месяц (фильтр ?state= — на экране), с другим state — тоже
        body = c.get('/api/content-plan?state=overdue&month=2026-08').get_json()
        assert (body['scope'], body['month'], [m['id'] for m in body['materials']]) == ('month', '2026-08',
                                                                                       [aug['id']])
        body = c.get('/api/content-plan?state=ready').get_json()
        assert (body['scope'], body['month']) == ('month', MONTH)
    try:
        store.state_payload('ready')
        raise AssertionError('state_payload принимает только overdue и failed')
    except ValueError:
        pass


def test_journal_and_bulk():
    store = _store()
    a = _material(store, title='А')
    pa = _add(store, a['id'])[0]
    b = _material(store, title='Б')
    pb = _add(store, b['id'])[0]
    _set(store, pb, status='published')
    cc = _material(store, title='В')
    with _client(store) as c:
        entries = c.get(f'/api/content-plan/materials/{a["id"]}/log').get_json()['entries']
        assert [e['action'] for e in entries] == ['add_placement', 'create']
        assert set(entries[0]) == {'at', 'by', 'action', 'material_id', 'placement_id', 'text'}
        assert (entries[0]['by'], entries[0]['placement_id'], entries[0]['at']) == ('anna', pa, NOW_STR)
        assert c.get('/api/content-plan/materials/m_nope/log').status_code == 404
        r = c.post('/api/content-plan/bulk', json={'material_ids': [a['id'], 'm_nope'], 'action': 'shift', 'days': 1})
        assert r.get_json() == {'done': 1, 'failed': [{'id': 'm_nope', 'error': 'Материал не найден'}]}
        assert _raw(store, pa)['date'] == '2026-10-10'
        r = c.post('/api/content-plan/bulk', json={'material_ids': [b['id'], cc['id']], 'action': 'delete'})
        body = r.get_json()
        assert body['done'] == 1 and body['failed'][0]['id'] == b['id'] and 'вышедшие' in body['failed'][0]['error']
        r = c.post('/api/content-plan/bulk', json={'material_ids': [a['id'], a['id']], 'action': 'cancel'})
        assert r.get_json() == {'done': 1, 'failed': []}
        assert _raw(store, pa)['status'] == 'cancelled'
        assert store.get_material(a['id'])['summary']['label'] == 'Отменено'
        # журнал удалённого материала остаётся доступен
        assert c.get(f'/api/content-plan/materials/{cc["id"]}/log').get_json()['entries'][0]['action'] == 'delete'
        assert c.post('/api/content-plan/bulk', json={'material_ids': [a['id']], 'action': 'explode'}).status_code == 400
        assert c.post('/api/content-plan/bulk', json={'material_ids': [], 'action': 'cancel'}).status_code == 400
        assert c.post('/api/content-plan/bulk', json={'material_ids': [a['id']], 'action': 'shift'}).status_code == 400


# --------------------------------------------------------------------------- ИИ-агент (MCP)

def test_origin_set_by_server_and_agent_signature():
    store = _store()
    with _client(store, AGENT) as c:
        r = c.post('/api/content-plan/materials', json={
            'month': MONTH, 'title': 'Черновик агента', 'base_text': 'Текст',
            'agent_rationale': 'Сезонный повод: Октоберфест', 'shot_list': 'Краны крупно; бокалы на стойке'})
        assert r.status_code == 200, r.get_json()
        m = r.get_json()['material']
        assert (m['origin'], m['created_by'], m['updated_by'], m['agent_draft']) == (
            'agent', 'anna · агент', 'anna · агент', True)
        assert (m['agent_rationale'], m['shot_list']) == ('Сезонный повод: Октоберфест',
                                                          'Краны крупно; бокалы на стойке')
        pid = c.post(f'/api/content-plan/materials/{m["id"]}/placements', json={
            'channel': 'telegram', 'bars': ['bolshoy'], 'date': '2026-10-09', 'time': '16:00'}).get_json()['created'][0]
        assert c.post('/api/content-plan/approve', json={'placement_ids': [pid]}).get_json()['approved'] == [pid]
        raw = _raw(store, pid)
        assert (raw['approved_by'], raw['updated_by']) == ('anna · агент', 'anna · агент')
        entries = c.get(f'/api/content-plan/materials/{m["id"]}/log').get_json()['entries']
        assert [e['action'] for e in entries] == ['approve', 'add_placement', 'create']
        assert {e['by'] for e in entries} == {'anna · агент'}
        # утверждённое — уже не черновик ИИ
        assert c.get(f'/api/content-plan/materials/{m["id"]}').get_json()['material']['agent_draft'] is False
        # origin в теле запроса — 400: его ставит только сервер
        r = c.post('/api/content-plan/materials', json={'month': MONTH, 'title': 'Подделка', 'origin': 'human'})
        assert r.status_code == 400 and 'origin' in r.get_json()['error']
        r = c.patch(f'/api/content-plan/materials/{m["id"]}', json={'origin': 'human', 'title': 'x'})
        assert r.status_code == 400
    raw_m = store.get_material_raw(m['id'])
    assert (raw_m['origin'], raw_m['title']) == ('agent', 'Черновик агента')     # отказ ничего не поменял
    assert [x['title'] for x in store.month_payload(MONTH)['materials']] == ['Черновик агента']
    with _client(store) as c:
        h = c.post('/api/content-plan/materials', json={'month': MONTH, 'title': 'Руками'}).get_json()['material']
        assert (h['origin'], h['created_by'], h['agent_draft'], h['agent_rationale'], h['shot_list']) == (
            'human', 'anna', False, '', '')
        # человек правит материал агента: origin остаётся, подпись — человека
        body = c.patch(f'/api/content-plan/materials/{m["id"]}', json={'title': 'Поправлено'}).get_json()['material']
        assert (body['origin'], body['updated_by']) == ('agent', 'anna')
    # путь «Сделать материалом» (routes/reviews.py зовёт create_material с current_user())
    made = store.create_material({'month': MONTH, 'title': 'Отзыв гостя — ВО', 'source_review_id': 'r_1'}, AGENT)
    assert (made['origin'], made['created_by']) == ('agent', 'anna · агент')
    try:
        store.create_material({'month': MONTH, 'title': 'x', 'origin': 'agent'}, USER)
        raise AssertionError('origin в полях create_material должен давать ValueError')
    except ValueError:
        pass
    assert (cp.actor_label(AGENT), cp.actor_label(USER), cp.actor_label(None)) == ('anna · агент', 'anna', 'unknown')
    assert cp.is_agent_user({'login': 'x', 'via_mcp': False}) is False and cp.origin_of(None) == 'human'


def test_agent_fields_round_trip_and_limits():
    store = _store()
    m = _material(store)
    pid = _add(store, m['id'])[0]
    store.approve([pid], USER)
    with _client(store) as c:
        url = f'/api/content-plan/materials/{m["id"]}'
        r = c.patch(url, json={'agent_rationale': 'Почему', 'shot_list': 'Что снять'})
        assert r.status_code == 200 and r.get_json()['unapproved'] == []    # не содержание публикации
        assert _raw(store, pid)['status'] == 'approved'
        got = c.get(url).get_json()['material']
        assert (got['agent_rationale'], got['shot_list'], got['origin']) == ('Почему', 'Что снять', 'human')
        assert store.log_for(m['id'])[0]['text'] == 'Изменено: «почему этот пост», «что снять»'
        assert c.patch(url, json={'agent_rationale': 'x' * 2000, 'shot_list': 'y' * 2000}).status_code == 200
        r = c.patch(url, json={'agent_rationale': 'x' * 2001})
        assert r.status_code == 400 and r.get_json()['error'] == '«Почему этот пост» длиннее 2000 знаков'
        r = c.patch(url, json={'shot_list': 'y' * 2001})
        assert r.status_code == 400 and r.get_json()['error'] == '«Что снять» длиннее 2000 знаков'
        r = c.post('/api/content-plan/materials', json={'month': MONTH, 'title': 't', 'agent_rationale': 'x' * 2001})
        assert r.status_code == 400
        assert len(store.get_material_raw(m['id'])['agent_rationale']) == 2000
        # пределы и правило черновика ИИ — в справочниках ответа (для агента и экрана)
        meta = c.get('/api/content-plan').get_json()
        assert meta['field_limits'] == {'title': 200, 'base_text': 10000, 'note': 2000,
                                        'agent_rationale': 2000, 'shot_list': 2000}
        assert [o['key'] for o in meta['origins']] == ['human', 'agent']
        assert meta['agent_draft_rule'] == cp.AGENT_DRAFT_RULE
    assert cp.AGENT_TEXT_MAX == cp.NOTE_MAX == 2000


def test_old_materials_are_human_and_bad_origin_is_503():
    store = _store()
    old = {'version': 1, 'log': [], 'materials': {'m_old': {
        'id': 'm_old', 'month': MONTH, 'title': 'Старый', 'kind': 'fixed', 'base_text': 'x',
        'placements': [], 'media': []}}}
    with open(store.data_file, 'w', encoding='utf-8') as f:
        json.dump(old, f, ensure_ascii=False)
    got = store.get_material('m_old')
    assert (got['origin'], got['agent_rationale'], got['shot_list'], got['agent_draft']) == ('human', '', '', False)
    old['materials']['m_old']['origin'] = 'robot'
    content = json.dumps(old, ensure_ascii=False)
    with open(store.data_file, 'w', encoding='utf-8') as f:
        f.write(content)
    with _client(store) as c:
        r = c.get('/api/content-plan')
        assert r.status_code == 503 and r.get_json()['code'] == 'content_plan_unavailable'
        assert c.post('/api/content-plan/agent-drafts/delete', json={'month': MONTH}).status_code == 503
    with open(store.data_file, encoding='utf-8') as f:
        assert f.read() == content                                              # не перезаписан


def test_copies_take_origin_of_the_actor():
    # повтор: копии — того, кто повторяет; пояснения — вместе с содержанием (всегда)
    store = _store()
    src = store.create_material({'month': MONTH, 'title': 'Пятница', 'planned_date': '2026-10-09',
                                 'base_text': 'Текст', 'agent_rationale': 'Повод', 'shot_list': 'Кадры'}, AGENT)
    _add(store, src['id'], date='2026-10-09')
    by_human = store.repeat(src['id'], [4], MONTH, USER)['created']
    assert len(by_human) == 3
    for mid in by_human:
        raw = store.get_material_raw(mid)
        assert (raw['origin'], raw['created_by'], raw['agent_rationale'], raw['shot_list']) == (
            'human', 'anna', 'Повод', 'Кадры')
    assert store.get_material_raw(src['id'])['origin'] == 'agent'               # источник не меняется
    by_agent = store.repeat(src['id'], [5], MONTH, AGENT)['created']
    assert by_agent and all(store.get_material_raw(x)['origin'] == 'agent' for x in by_agent)

    # копирование месяца: без содержания пояснения очищаются (кроме живых данных)
    store = _store()
    a = store.create_material({'month': MONTH, 'title': 'Агентский', 'planned_date': '2026-10-09',
                               'base_text': 'Текст', 'agent_rationale': 'Повод', 'shot_list': 'Кадры'}, AGENT)
    live = store.create_material({'month': MONTH, 'title': 'Таплист', 'kind': 'live', 'live_source': 'taplist',
                                  'base_text': '{таплист}', 'planned_date': '2026-10-02',
                                  'agent_rationale': 'Живой', 'shot_list': 'Краны'}, USER)
    members = _friday_series(store, title='Серия людей')
    store.copy_month(MONTH, '2026-11', False, USER)
    nov = {m['copied_from']: m for m in store.month_payload('2026-11')['materials']}
    assert (nov[a['id']]['origin'], nov[a['id']]['base_text'], nov[a['id']]['agent_rationale'],
            nov[a['id']]['shot_list']) == ('human', '', '', '')
    assert (nov[live['id']]['agent_rationale'], nov[live['id']]['shot_list']) == ('Живой', 'Краны')
    assert nov[members[0]]['origin'] == 'human'
    store.copy_month(MONTH, '2026-12', True, AGENT)
    dec = [m for m in store.month_payload('2026-12')['materials']]
    assert dec and all(m['origin'] == 'agent' and m['created_by'] == 'anna · агент' for m in dec)
    d = next(m for m in dec if m['copied_from'] == a['id'])
    assert (d['agent_rationale'], d['shot_list'], d['base_text']) == ('Повод', 'Кадры', 'Текст')
    assert all(m['agent_draft'] for m in dec)                                   # все копии — черновики


def test_delete_agent_drafts():
    store = _store()
    ok, shared = store.media.save(PNG, '2026-10-07')
    ok, own = store.media.save(JPEG, '2026-10-07')
    topic = store.create_material({'month': MONTH, 'title': 'Тема агента'}, AGENT)        # без размещений
    draft = store.create_material({'month': MONTH, 'title': 'Черновик агента', 'base_text': 'Текст'}, AGENT)
    store.add_media(draft['id'], own, len(JPEG), 'own.jpg', AGENT)
    store.add_media(draft['id'], shared, len(PNG), 'shared.png', AGENT)
    _add(store, draft['id'])
    p_cancel = _add(store, draft['id'], bars=['ligovskiy'])[0]
    store.placement_action(p_cancel, 'cancel', AGENT)                                    # отменённое не мешает
    kept = {}
    for title, status in (('Утверждённый', 'approved'), ('На паузе', 'paused'), ('Вышедший', 'published'),
                          ('С ошибкой', 'failed')):
        material = store.create_material({'month': MONTH, 'title': title, 'base_text': 'Текст'}, AGENT)
        _add(store, material['id'], bars=['varshavskaya'])
        pid = _add(store, material['id'])[0]
        _set(store, pid, status=status)
        kept[material['id']] = title
    human = _material(store, title='Черновик людей')
    _add(store, human['id'])
    store.add_media(human['id'], shared, len(PNG), 'shared.png', USER)                   # файл общий с людьми
    november = store.create_material({'month': '2026-11', 'title': 'Ноябрьский'}, AGENT)

    view = {m['id']: m for m in store.month_payload(MONTH)['materials']}
    assert (view[topic['id']]['agent_draft'], view[draft['id']]['agent_draft'], view[human['id']]['agent_draft']) == (
        True, True, False)
    assert not any(view[mid]['agent_draft'] for mid in kept)

    with _client(store) as c:
        url = '/api/content-plan/agent-drafts/delete'
        # проверки ввода
        assert c.post(url, json={}).status_code == 400                                   # нет месяца
        assert c.post(url, json={'month': '2026-13'}).status_code == 400
        assert c.post(url, json={'month': MONTH, 'material_ids': topic['id']}).status_code == 400
        assert c.post(url, json={'month': MONTH, 'material_ids': []}).status_code == 400
        r = c.post(url, json={'month': MONTH, 'material_ids': ['m_x'] * (rcp.BULK_MAX + 1)})
        assert r.status_code == 400 and str(rcp.BULK_MAX) in r.get_json()['error']
        # явные id: удаляется только подходящее, остальное — с причиной
        r = c.post(url, json={'month': MONTH, 'material_ids': [topic['id'], human['id'], november['id'], 'm_nope',
                                                               topic['id']]})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body['deleted'] == [topic['id']]
        reasons = {s['id']: s['reason'] for s in body['skipped']}
        assert set(reasons) == {human['id'], november['id'], 'm_nope'}
        assert reasons['m_nope'] == 'материал не найден'
        assert 'создали люди' in reasons[human['id']]
        assert 'ноябрь 2026' in reasons[november['id']]
        # без id: все черновики агента месяца; не черновики — в skipped
        body = c.post(url, json={'month': MONTH}).get_json()
        assert body['deleted'] == [draft['id']]
        assert {s['id'] for s in body['skipped']} == set(kept)
        assert all('уже не черновик' in s['reason'] for s in body['skipped'])
        assert c.post(url, json={'month': MONTH}).get_json()['deleted'] == []
    left = {m['id'] for m in store.month_payload(MONTH)['materials']}
    assert left == set(kept) | {human['id']}
    assert store.get_material_raw(november['id'])['month'] == '2026-11'                # другой месяц не тронут
    # файлы: свой файл черновика ушёл с диска, общий с людьми — остался
    assert not store.media.exists(own) and store.media.exists(shared)
    entry = store.log_for(draft['id'])[0]
    assert (entry['action'], entry['by']) == ('delete', 'anna')
    assert entry['text'] == 'Удалён черновик агента «Черновик агента» (массовое удаление черновиков ИИ)'
    # агент по MCP удаляет свой черновик сам — подпись агента
    again = store.create_material({'month': MONTH, 'title': 'Ещё один'}, AGENT)
    assert store.delete_agent_drafts(MONTH, AGENT) == {
        'deleted': [again['id']], 'skipped': [{'id': mid, 'reason': f'«{title}»: есть утверждённые, вышедшие или '
                                                                    'ошибочные размещения — это уже не черновик'}
                                              for mid, title in sorted(kept.items(), key=lambda kv: (NOW_STR, kv[0]))]}
    assert store.log_for(again['id'])[0]['by'] == 'anna · агент'


def test_approve_preview_origin_filter():
    store = _store()
    human = _material(store, title='Люди')
    _add(store, human['id'])
    agent = store.create_material({'month': MONTH, 'title': 'Агент', 'base_text': 'Текст'}, AGENT)
    _add(store, agent['id'], bars=['ligovskiy'])
    with _client(store) as c:
        url = '/api/content-plan/approve-preview?month=2026-10'
        p = c.get(url).get_json()
        assert {i['title']: i['origin'] for i in p['will_approve']} == {'Люди': 'human', 'Агент': 'agent'}
        assert [i['title'] for i in c.get(url + '&origin=agent').get_json()['will_approve']] == ['Агент']
        assert [i['title'] for i in c.get(url + '&origin=human').get_json()['will_approve']] == ['Люди']
        assert c.get(url + '&origin=').get_json() == p                                  # пусто — без фильтра
        assert c.get(url + '&origin=robot').status_code == 400


def test_page_route_renders_template():
    calls = []
    saved_render = rcp.render_template
    saved_ext = sys.modules.get('extensions')
    sys.modules['extensions'] = types.SimpleNamespace(APP_VERSION='abc123')
    try:
        rcp.render_template = lambda name, **ctx: calls.append((name, ctx)) or 'ok'
        app = Flask('test_content_plan_page')
        app.register_blueprint(content_plan_bp)
        r = app.test_client().get('/content-plan')
        assert r.status_code == 200 and calls == [('content_plan.html', {'app_version': 'abc123'})]
        rcp.render_template = saved_render
        if not os.path.exists(os.path.join(REPO, 'templates', 'content_plan.html')):
            _skip('templates/content_plan.html ещё нет — настоящая отрисовка не проверена')
            return
        from werkzeug.routing import BuildError
        app = Flask('test_content_plan_page_real', template_folder=os.path.join(REPO, 'templates'),
                    static_folder=os.path.join(REPO, 'static'))
        app.register_blueprint(content_plan_bp)
        app.context_processor(lambda: {'current_user': USER})
        try:
            r = app.test_client().get('/content-plan')
        except BuildError as e:
            _skip(f'шаблон ссылается на эндпоинт вне голого приложения: {e}')
            return
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'Контент-план' in html and 'abc123' in html
    finally:
        rcp.render_template = saved_render
        if saved_ext is None:
            sys.modules.pop('extensions', None)
        else:
            sys.modules['extensions'] = saved_ext


def test_draft_mode_agent_edits_only_own_drafts():
    """Коннектор …/draft (mcp_mode='draft'): агент правит только свои черновики.

    Проверка безопасности 2026-09-28: по расписанию агент читает отзывы гостей;
    внедрённая в них «команда» не должна трогать материалы владельца или уже
    утверждённое. В полном режиме и у людей на сайте ограничения нет."""
    store = _store()
    agent_draft = dict(AGENT, mcp_mode='draft')
    agent_full = dict(AGENT, mcp_mode='full')
    owners = _material(store, title='Материал владельца')
    own = store.create_material({'month': MONTH, 'title': 'Черновик агента',
                                 'base_text': 'Текст агента'}, agent_draft)
    assert own['origin'] == 'agent'
    # свой черновик: правка, размещение, правка размещения — можно
    store.update_material(own['id'], {'title': 'Черновик агента 2'}, agent_draft)
    _m, created = store.add_placements(own['id'], {'channel': 'telegram', 'bars': ['bolshoy'],
                                                   'date': '2026-10-09', 'time': '16:00'}, agent_draft)
    store.update_placement(created[0], {'time': '17:00'}, agent_draft)
    # материал владельца — отказ на каждой записи
    owner_pid = _add(store, owners['id'])[0]
    for call in (lambda: store.update_material(owners['id'], {'title': 'x'}, agent_draft),
                 lambda: store.add_placements(owners['id'], {'channel': 'telegram', 'bars': ['bolshoy'],
                                                             'date': '2026-10-09', 'time': '16:00'},
                                              agent_draft),
                 lambda: store.update_placement(owner_pid, {'time': '18:00'}, agent_draft)):
        try:
            call()
        except cp.ContentPlanConflict as e:
            assert 'черновики' in str(e)
        else:
            raise AssertionError('в режиме draft агент изменил материал владельца')
    # свой материал после утверждения владельцем — уже не черновик
    store.approve(created, USER)
    try:
        store.update_placement(created[0], {'time': '19:00'}, agent_draft)
    except cp.ContentPlanConflict:
        pass
    else:
        raise AssertionError('в режиме draft агент перенёс утверждённое размещение')
    # полный режим и человек на сайте — без ограничения
    store.update_material(owners['id'], {'title': 'Полный режим'}, agent_full)
    store.update_material(owners['id'], {'title': 'Человек'}, USER)
    assert store.get_material(owners['id'])['title'] == 'Человек'


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
