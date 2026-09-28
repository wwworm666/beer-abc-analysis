"""
Тесты отправки публикаций контент-плана: core/content_publisher.py,
core/content_publisher_scheduler.py, core/content_channels.py, новые маршруты
routes/content_plan.py и multipart-вызов core/open_check_telegram.api_call_files.

Self-runnable: `py -3 tests/test_content_publisher.py` (совместимо с pytest).

В настоящий Telegram не уходит НИЧЕГО: транспорт — FakeTelegram (отвечает как Bot API
и пишет вызовы), подписчики гостевого бота — FakeSubscribers, requests.post в тесте
api_call_files подменён. app.py не импортируется. Данные — временные файлы, часы
хранилищ заморожены (Clock), паузы (темп рассылки, 429) — поддельные.

Что проверяется (контракт 3.2–3.7):
- Telegram: текст (sendMessage без parse_mode), 1 фото / видео (multipart с подписью),
  альбом (sendMediaGroup, подпись у первого), повторное использование file_id;
- живые данные: ок — таплист на момент отправки; стоп-правило — failed без отправки;
  предел длины проверяется до отправки;
- ответы: 429 — один повтор через retry_after (долгий — ошибка), 5xx — failed с текстом
  без повтора, нет ответа — failed «статус неизвестен»;
- идемпотентность: «отправляется» дольше 10 минут — failed без повторной отправки;
  в пределах 10 минут — не трогается; второй проход не шлёт дубль;
- GRACE 120 минут: опоздавшее — failed «время выхода прошло»; повтор (retry) —
  отправка сразу; время раньше подключения площадки — пропуск (ручной хвост);
- Instagram: напоминание (заголовок со ссылкой, текст, альбом) один раз, опоздавшее —
  reminder_late, сбой — reminder_failed без автоповтора;
- бот: частичная рассылка «дошло N из M», 403 -> mark_blocked, retry_failed — только
  неудавшимся, прерванная рассылка не шлёт повторно получившим, отписавшимся не шлёт,
  три обрыва связи подряд — стоп, темп 25/с, пустая аудитория — failed;
- выключатели: главный (ничего не шлётся, skipped все), рассылки бота, нет токена;
- планировщик: не стартует без токена и при CONTENT_PUBLISH=0, один раз, лок занят;
- маршруты: каналы (GET/PUT/check/test, 400/503), publish-now (409-ветки, только
  очередь), аудитория, agent-edits, compact, zip; учёт правок агента (agent_original);
- вид для экрана: «Отправляется», «В очереди», «Напоминание отправлено», «дошло N из M»,
  списки получателей не уходят в API, 409 пока отправляется;
- регрессии независимой проверки 2026-09-28 (раздел в конце, тест на пункт): без
  дублей при сбое связи (safe_resend), 409 на правки во время отправки, время поста у
  Instagram, перенос взводит напоминание, сбой проверки канала, остановка рассылки,
  только администратор, бюджет рассылок, своя долгая отправка не «зависла», UTF-16,
  адреса по роли.
"""

import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import core.content_channels as cc  # noqa: E402
import core.content_plan as cp  # noqa: E402
import core.content_publisher as pub  # noqa: E402
import core.content_publisher_scheduler as sched  # noqa: E402
import routes.content_plan as rcp  # noqa: E402
from routes.content_plan import content_plan_bp  # noqa: E402

USER = {'login': 'anna', 'display_name': 'Анна', 'is_admin': True}          # владелец (администратор)
AGENT = {'login': 'anna', 'display_name': 'Анна', 'is_admin': True, 'via_mcp': True, 'mcp_client': 'Claude',
         'mcp_token_id': 't1'}
BARTENDER = {'login': 'petr', 'display_name': 'Пётр'}                        # обычный аккаунт бара
SETUP = datetime(2026, 10, 7, 11, 0)      # среда: подключение и утверждение
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
MP4 = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 32


# --------------------------------------------------------------------------- подделки

class Clock:
    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment


class FakeTelegram:
    """Поддельный Bot API: отвечает по умолчанию «ок», очереди ответов по методу,
    ответы по чату (рассылка), исключения по чату. Пишет все вызовы."""

    token = 'test-token'

    def __init__(self):
        self.calls = []
        self.queue = {}
        self.per_chat = {}
        self.raise_for = set()
        self.next_id = 500

    def respond(self, method, *responses):
        self.queue.setdefault(method, []).extend(responses)

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _default(self, method, chat, count):
        if method == 'getMe':
            return {'ok': True, 'result': {'id': 42, 'username': 'kult_test_bot'}}
        if method == 'getChat':
            name = str(chat)[1:] if str(chat).startswith('@') else None
            return {'ok': True, 'result': {'id': -1001234, 'type': 'channel', 'title': 'Канал бара',
                                           'username': name}}
        if method == 'getChatMember':
            return {'ok': True, 'result': {'status': 'administrator', 'can_post_messages': True}}
        if method == 'sendMediaGroup':
            result = []
            for _ in range(count):
                mid = self._id()
                result.append({'message_id': mid, 'photo': [{'file_id': 'small'}, {'file_id': f'G{mid}'}]})
            return {'ok': True, 'result': result}
        mid = self._id()
        if method == 'sendPhoto':
            return {'ok': True, 'result': {'message_id': mid, 'photo': [{'file_id': 'small'}, {'file_id': f'P{mid}'}]}}
        if method == 'sendVideo':
            return {'ok': True, 'result': {'message_id': mid, 'video': {'file_id': f'V{mid}'}}}
        return {'ok': True, 'result': {'message_id': mid}}

    def _answer(self, method, chat, count):
        if str(chat) in self.raise_for:
            raise RuntimeError('сбой транспорта')
        if str(chat) in self.per_chat:
            answer = self.per_chat[str(chat)]
            return answer() if callable(answer) else answer
        queued = self.queue.get(method)
        if queued:
            return queued.pop(0)
        return self._default(method, chat, count)

    def call(self, method, payload=None):
        payload = dict(payload or {})
        self.calls.append({'method': method, 'payload': payload, 'files': None})
        media = payload.get('media') if method == 'sendMediaGroup' else None
        return self._answer(method, payload.get('chat_id'), len(media) if isinstance(media, list) else 1)

    def upload(self, method, fields, files):
        self.calls.append({'method': method, 'payload': dict(fields),
                           'files': [(f[0], f[1], len(f[2]), f[3]) for f in files]})
        media = json.loads(fields['media']) if method == 'sendMediaGroup' else None
        return self._answer(method, fields.get('chat_id'), len(media) if media else 1)

    def sends(self):
        return [c for c in self.calls if c['method'].startswith('send')]


class FakeSubscribers:
    """Как core/guest_subscribers (контракт раздела 5): audience_size, recipients,
    mark_blocked, stats."""

    def __init__(self, chats):
        self.chats = list(chats)
        self.blocked = []
        self.unsubscribed = set()
        self.asked = []

    def recipients(self, segment, bar=None):
        self.asked.append((segment, bar))
        return [{'chat_id': c} for c in self.chats if c not in self.unsubscribed and c not in self.blocked]

    def audience_size(self, segment, bar=None):
        return len(self.recipients(segment, bar))

    def mark_blocked(self, chat_id):
        self.blocked.append(chat_id)

    def stats(self):
        return {'total': len(self.chats), 'subscribed': len(self.recipients('bot_all')), 'with_phone': 0,
                'by_bar': {}}


@contextmanager
def _patch(obj, name, value):
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield value
    finally:
        setattr(obj, name, saved)


@contextmanager
def _subscribers(fake):
    with _patch(cc, '_subscribers_module', lambda: fake):
        yield fake


@contextmanager
def _env_vars(**values):
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _tmpdir():
    tmp = tempfile.mkdtemp(prefix='content_publisher_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


class Env:
    """План, настройки каналов и поддельный Telegram во временной папке."""

    def __init__(self, moment=SETUP):
        self.tmp = _tmpdir()
        self.clock = Clock(moment)
        self.store = cp.ContentPlanStore(os.path.join(self.tmp, 'content_plan.json'), now_fn=self.clock)
        self.channels = cc.ChannelsStore(os.path.join(self.tmp, 'content_channels.json'), now_fn=self.clock)
        self.tg = FakeTelegram()
        self.sleeps = []
        self._mono = 0.0

    def at(self, hour, minute, day=7):
        self.clock.moment = datetime(2026, 10, day, hour, minute)
        return self

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self._mono += seconds

    def mono(self):
        return self._mono

    def run(self, transport='fake', guest='same', **kw):
        """Проход отправщика; guest='same' — гостевой бот тот же поддельный транспорт."""
        channel = self.tg if transport == 'fake' else transport
        return pub.publish_due(transport=channel, guest_transport=channel if guest == 'same' else guest,
                               store=self.store, channels=self.channels, sleep=self.sleep, clock=self.mono, **kw)

    def enable(self, bars=('bolshoy',), instagram_chat=None, minutes=None, bot=False, enabled=True):
        patch = {'enabled': enabled, 'telegram': {b: {'chat': '@kult_' + b} for b in bars}}
        if instagram_chat is not None:
            patch['instagram'] = {'reminder_chat': instagram_chat}
            if minutes is not None:
                patch['instagram']['reminder_minutes_before'] = minutes
        if bot:
            patch['bot'] = {'enabled': True}
        self.channels.update(patch, USER)
        for bar in bars:
            result = pub.check_channel(bar, USER, transport=self.tg, channels=self.channels)
            assert result['check']['can_post'], result
        self.tg.calls.clear()

    def material(self, **fields):
        base = {'month': '2026-10', 'title': 'Квиз', 'base_text': 'Сегодня квиз в 20:00'}
        base.update(fields)
        return self.store.create_material(base, USER)

    def placement(self, material_id, channel='telegram', **fields):
        fields['channel'] = channel
        if channel == 'telegram':
            fields.setdefault('bars', ['bolshoy'])
        fields.setdefault('date', '2026-10-07')
        fields.setdefault('time', '12:00')
        _m, created = self.store.add_placements(material_id, fields, USER)
        return created[0]

    def approve(self, *pids):
        result = self.store.approve(list(pids), USER, confirm_bot=True)
        assert result['approved'] == list(pids), result
        return result

    def photo(self, material_id, data=PNG, original='bar.png'):
        ok, name = self.store.media.save(data, '2026-10-07')
        assert ok, name
        self.store.add_media(material_id, name, len(data), original, USER)
        return name

    def raw(self, pid):
        return self.store.get_placement_raw(pid)[1]

    def view(self, pid):
        material, _p = self.store.get_placement_raw(pid)
        return next(p for p in self.store.get_material(material['id'])['placements'] if p['id'] == pid)

    def set(self, pid, **fields):
        with self.store._tx() as (data, _after):
            _m, placement = self.store._placement(data, pid)
            placement.update(fields)

    def log(self, material_id):
        return [e['action'] for e in self.store.log_for(material_id)]


def _post(env, channel='telegram', text='Сегодня квиз в 20:00', time='12:00', **fields):
    """Утверждённое размещение (материал + размещение) -> (material_id, pid)."""
    material = env.material(base_text=text)
    pid = env.placement(material['id'], channel=channel, time=time, **fields)
    env.approve(pid)
    return material['id'], pid


# --------------------------------------------------------------------------- Telegram

def test_text_post_published():
    env = Env()
    env.enable()
    mid, pid = _post(env)
    env.at(11, 59)
    report = env.run()
    assert report['sent'] == 0 and env.tg.sends() == []                      # ещё не время
    env.at(12, 0)
    report = env.run()
    assert (report['sent'], report['failed'], report['enabled']) == (1, 0, True)
    assert env.tg.sends() == [{'method': 'sendMessage', 'files': None, 'payload': {
        'chat_id': '@kult_bolshoy', 'text': 'Сегодня квиз в 20:00', 'disable_web_page_preview': False}}]
    raw = env.raw(pid)
    assert (raw['status'], raw['published_at'], raw['published_by']) == ('published', '2026-10-07T12:00', 'бот')
    assert raw['delivery']['state'] == 'sent' and raw['delivery']['chat'] == '@kult_bolshoy'
    assert raw['delivery']['message_ids'] == [env.tg.next_id]
    view = env.view(pid)
    assert view['post_url'] == f'https://t.me/kult_bolshoy/{env.tg.next_id}'
    assert view['display_state'] == 'published' and view['delivery']['state'] == 'sent'
    assert 'auto_publish' in env.log(mid)
    assert env.run()['sent'] == 0 and len(env.tg.sends()) == 1                # второй проход — без дубля


def test_single_photo_and_video_are_multipart_with_caption():
    env = Env()
    env.enable()
    photo_material = env.material(base_text='Новое меню')
    env.photo(photo_material['id'])
    p_photo = env.placement(photo_material['id'])
    video_material = env.material(title='Видео', base_text='Как наливаем')
    env.photo(video_material['id'], data=MP4, original='clip.mp4')
    p_video = env.placement(video_material['id'], time='12:01')
    env.approve(p_photo, p_video)
    env.at(12, 1)
    assert env.run()['sent'] == 2
    photo, video = env.tg.sends()
    assert photo['method'] == 'sendPhoto' and photo['payload'] == {'chat_id': '@kult_bolshoy', 'caption': 'Новое меню'}
    assert photo['files'][0][0] == 'photo' and photo['files'][0][3] == 'image/png'
    assert photo['files'][0][1].startswith('cp_20261007_')                   # латинское имя, не «bar.png»
    assert video['method'] == 'sendVideo' and video['files'][0][0] == 'video'
    assert video['files'][0][3] == 'video/mp4' and video['payload']['caption'] == 'Как наливаем'
    assert env.raw(p_photo)['status'] == env.raw(p_video)['status'] == 'published'


def test_album_caption_on_first_and_file_id_reused_for_second_bar():
    env = Env()
    env.enable(bars=('bolshoy', 'ligovskiy'))
    material = env.material(base_text='Октоберфест')
    for i in range(3):
        env.photo(material['id'], original=f'p{i}.png')
    _m, created = env.store.add_placements(material['id'], {'channel': 'telegram', 'bars': ['bolshoy', 'ligovskiy'],
                                                            'date': '2026-10-07', 'time': '12:00'}, USER)
    env.approve(*created)
    env.at(12, 0)
    assert env.run()['sent'] == 2
    first, second = env.tg.sends()
    assert first['method'] == 'sendMediaGroup' and [f[0] for f in first['files']] == ['file0', 'file1', 'file2']
    media = json.loads(first['payload']['media'])
    assert [m['media'] for m in media] == ['attach://file0', 'attach://file1', 'attach://file2']
    assert media[0]['caption'] == 'Октоберфест' and 'caption' not in media[1] and 'caption' not in media[2]
    # второй бар — те же файлы по file_id, без повторной загрузки
    assert second['method'] == 'sendMediaGroup' and second['files'] is None
    assert [m['media'] for m in second['payload']['media']] == ['G501', 'G502', 'G503']
    assert second['payload']['media'][0]['caption'] == 'Октоберфест'
    assert len(env.raw(created[0])['delivery']['message_ids']) == 3


def test_live_template_rendered_at_send_and_stop_rule_fails():
    import test_content_plan as tcp
    env = Env()
    env.enable(bars=('varshavskaya', 'ligovskiy'))
    material = env.material(kind='live', live_source='taplist', base_text=tcp.TEMPLATE)
    ok_pid = env.placement(material['id'], bars=['varshavskaya'])
    stop_pid = env.placement(material['id'], bars=['ligovskiy'], time='12:01')
    env.approve(ok_pid, stop_pid)
    with _patch(cp, 'load_live_data', lambda registry=None: (tcp.SNAPSHOT, tcp.REGISTRY)):
        env.at(12, 1)
        report = env.run()
    assert (report['sent'], report['failed']) == (1, 1)
    assert len(env.tg.sends()) == 1                                         # стоп — без отправки
    text = env.tg.sends()[0]['payload']['text']
    assert text.startswith('Сегодня в баре «Варшавская» (7 октября), кранов: 2')
    assert '1. Б — IPA, IPA - American, 6,5%' in text
    stopped = env.raw(stop_pid)
    assert stopped['status'] == 'failed'
    assert stopped['failed_error'].startswith('Публикация остановлена: Кран 4: Нет проверенной связи с Untappd')
    assert env.raw(ok_pid)['approved_snapshot']['text'] == tcp.TEMPLATE        # снимок — шаблон


def test_length_limit_checked_before_send():
    env = Env()
    env.enable()
    material = env.material(base_text='x' * 1500)
    pid = env.placement(material['id'])
    env.approve(pid)
    name = env.photo(material['id'])                                        # снимает утверждение…
    env.set(pid, status='approved', approved_snapshot={'text': 'x' * 1500, 'media': [name]})   # …старые данные
    env.at(12, 0)
    report = env.run()
    assert report['failed'] == 1 and env.tg.sends() == []
    assert env.raw(pid)['failed_error'] == 'Публикация остановлена: текст длиннее 1024 знаков'


def test_429_retry_after_once():
    env = Env()
    env.enable()
    _mid, pid = _post(env)
    env.tg.respond('sendMessage', {'ok': False, 'error_code': 429, 'description': 'Too Many Requests: retry after 3',
                                   'parameters': {'retry_after': 3}})
    env.at(12, 0)
    assert env.run()['sent'] == 1
    assert env.sleeps == [3] and len(env.tg.sends()) == 2 and env.raw(pid)['status'] == 'published'
    # долгий retry_after — не ждём, ошибка
    env2 = Env()
    env2.enable()
    _mid, pid2 = _post(env2)
    env2.tg.respond('sendMessage', {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 3600}})
    env2.at(12, 0)
    assert env2.run()['failed'] == 1 and env2.sleeps == [] and len(env2.tg.sends()) == 1
    assert 'подождать 3600 с' in env2.raw(pid2)['failed_error']
    # 429 дважды — ошибка после одного повтора
    env3 = Env()
    env3.enable()
    _mid, pid3 = _post(env3)
    busy = {'ok': False, 'error_code': 429, 'description': 'Too Many Requests', 'parameters': {'retry_after': 1}}
    env3.tg.respond('sendMessage', busy, dict(busy))
    env3.at(12, 0)
    assert env3.run()['failed'] == 1 and len(env3.tg.sends()) == 2
    assert env3.raw(pid3)['failed_error'].startswith('Telegram отклонил запрос (ошибка 429)')


def test_5xx_failed_with_text_and_no_retry():
    env = Env()
    env.enable()
    mid, pid = _post(env)
    env.tg.respond('sendMessage', {'ok': False, 'error_code': 502, 'description': 'Bad Gateway'})
    env.at(12, 0)
    report = env.run()
    assert report['failed'] == 1 and len(env.tg.sends()) == 1
    raw = env.raw(pid)
    assert raw['status'] == 'failed' and raw['failed_error'] == 'Telegram временно не отвечает (ошибка 502): Bad Gateway'
    assert raw['delivery']['state'] == 'failed' and 'auto_failed' in env.log(mid)
    assert env.view(pid)['display_state'] == 'failed'
    assert env.run()['failed'] == 0 and len(env.tg.sends()) == 1            # failed больше не трогается


def test_known_telegram_errors_are_translated_and_no_answer_is_unknown():
    assert pub.human_error(400, 'Bad Request: chat not found').startswith('канал или чат не найден')
    assert pub.human_error(403, 'Forbidden: bot is not a member of the channel chat').startswith(
        'бот не состоит в канале')
    assert pub.classify(None)[0] == 'network'
    assert pub.classify({'ok': False, 'error_code': 403, 'description': 'bot was blocked by the user'})[0] == 'forbidden'
    env = Env()
    env.enable()
    _mid, pid = _post(env)

    class Silent(FakeTelegram):
        def call(self, method, payload=None):
            self.calls.append({'method': method, 'payload': payload, 'files': None})
            return None

    silent = Silent()
    env.at(12, 0)
    env.run(transport=silent)
    assert env.raw(pid)['failed_error'] == pub.NO_ANSWER_TEXT


# --------------------------------------------------------------------------- идемпотентность, GRACE

def test_stale_sending_fails_without_resend():
    env = Env()
    env.enable()
    mid, pid = _post(env)
    env.set(pid, delivery={'state': 'sending', 'attempt_id': 'a1', 'started_at': '2026-10-07T12:00',
                           'heartbeat_at': '2026-10-07T12:00'})
    env.at(12, 9)
    assert env.run() == {'sent': 0, 'failed': 0, 'skipped': 0, 'details': [], 'enabled': True}
    assert env.raw(pid)['delivery']['state'] == 'sending' and env.tg.sends() == []
    assert env.view(pid)['display_label'] == 'Отправляется'
    env.at(12, 10)                                                          # 10 минут без отметки
    report = env.run()
    assert report['failed'] == 1 and report['details'][0]['result'] == 'stale'
    raw = env.raw(pid)
    assert (raw['status'], raw['failed_error']) == ('failed', pub.STALE_TEXT)
    assert env.tg.sends() == [] and 'auto_failed' in env.log(mid)


def test_claim_blocks_second_sender_and_edits():
    env = Env()
    env.enable()
    _mid, pid = _post(env)
    env.set(pid, delivery={'state': 'sending', 'attempt_id': 'other', 'started_at': '2026-10-07T12:00',
                           'heartbeat_at': '2026-10-07T12:00'})
    env.at(12, 1)
    for call in (lambda: env.store.update_placement(pid, {'time': '13:00'}, USER),
                 lambda: env.store.placement_action(pid, 'pause', USER),
                 lambda: env.store.delete_placement(pid, USER)):
        try:
            call()
            raise AssertionError('правка во время отправки должна давать 409')
        except cp.ContentPlanConflict as e:
            assert str(e) == cp.SENDING_CONFLICT
    try:
        pub.publish_now(pid, USER, store=env.store, channels=env.channels, transport=env.tg)
        raise AssertionError('второй отправщик не должен взять размещение')
    except cp.ContentPlanConflict as e:
        assert str(e) == cp.SENDING_CONFLICT
    assert env.tg.sends() == []


def test_placement_deleted_during_pass_does_not_break_the_pass():
    env = Env()
    env.enable()
    _m1, gone = _post(env)
    _m2, kept = _post(env)
    snapshot = env.store.snapshot_data()                                    # проход прочитал план…
    env.store.delete_placement(gone, USER)                                  # …а размещение удалили
    with _patch(env.store, 'snapshot_data', lambda: snapshot):
        env.at(12, 0)
        report = env.run()
    assert report['sent'] == 1 and env.raw(kept)['status'] == 'published'
    assert any(d['placement_id'] == gone and d['result'] == 'skipped' for d in report['details'])
    assert len(env.tg.sends()) == 1


def test_grace_late_fails_and_retry_sends_now():
    env = Env(datetime(2026, 10, 7, 8, 0))
    env.enable()
    mid, pid = _post(env, time='09:00')
    _mid2, on_edge = _post(env, time='09:01')
    env.at(11, 0)                                                           # 09:00 — ровно 120 минут назад
    report = env.run()
    assert (report['sent'], report['failed']) == (1, 1)
    assert env.raw(pid)['failed_error'] == pub.GRACE_TEXT and env.raw(on_edge)['status'] == 'published'
    assert len(env.tg.sends()) == 1
    # «Повторить» — отправка в ближайшую минуту, хотя время выхода давно прошло
    env.store.placement_action(pid, 'retry', USER)
    view = env.view(pid)
    assert (view['status'], view['display_state'], view['display_label']) == ('approved', 'scheduled',
                                                                                 'В очереди на отправку: уйдёт в течение минуты')
    assert env.store.attention_counts()['overdue'] == 0                    # в очереди — не «время вышло»
    env.at(11, 1)
    assert env.run()['sent'] == 1 and env.raw(pid)['status'] == 'published'
    assert {'auto_failed', 'retry', 'auto_publish'} <= set(env.log(mid))


def test_queued_retry_expires_after_grace():
    """«Повторить» нажали в 09:05, а сервер не работал до 11:05: очередь 2 часа и старше —
    не «отправляется», а снова «время вышло»; отправщик ставит ошибку, а не шлёт с опозданием."""
    env = Env(datetime(2026, 10, 7, 8, 0))
    env.enable()
    _mid, pid = _post(env, time='09:00')
    env.at(9, 5)
    env.set(pid, status='failed')
    env.store.placement_action(pid, 'retry', USER)                        # retry_at 09:05
    env.at(11, 4)
    assert env.view(pid)['display_label'] == 'В очереди на отправку: уйдёт в течение минуты'   # 119 минут
    env.at(11, 5)
    assert env.view(pid)['display_state'] == 'overdue'                     # ровно 2 часа — уже опоздание
    report = env.run()
    assert report['failed'] == 1 and env.tg.sends() == []
    assert env.raw(pid)['failed_error'] == pub.GRACE_TEXT


def test_time_before_connection_is_left_for_manual_marking():
    env = Env(datetime(2026, 10, 7, 10, 0))
    _mid, pid = _post(env, time='11:00')
    env.at(11, 30)
    env.enable()                                                           # подключили после времени выхода
    env.at(11, 31)
    report = env.run()
    assert report['skipped'] == 1 and 'раньше подключения' in report['details'][0]['text']
    assert env.raw(pid)['status'] == 'approved' and env.tg.sends() == []
    assert env.view(pid)['display_state'] == 'overdue'


# --------------------------------------------------------------------------- выключатели

def test_master_switch_off_sends_nothing_and_writes_nothing():
    env = Env()
    env.enable(enabled=False)
    _mid, pid = _post(env)
    env.at(12, 0)
    before = open(env.store.data_file, encoding='utf-8').read()
    report = env.run()
    assert (report['enabled'], report['sent'], report['skipped']) == (False, 0, 1)
    assert report['details'][0]['text'] == 'Отправка выключена владельцем'
    assert env.tg.calls == [] and open(env.store.data_file, encoding='utf-8').read() == before


def test_not_connected_channel_and_no_token_are_skipped():
    env = Env()
    env.enable(bars=('bolshoy',))
    _mid, other = _post(env, bars=['ligovskiy'])
    env.at(12, 0)
    report = env.run()
    assert report['skipped'] == 1 and report['details'][0]['text'] == 'Площадка не подключена: канал не указан'
    assert env.raw(other)['status'] == 'approved' and env.tg.sends() == []
    with _patch(pub, 'default_transport', lambda: None), _patch(pub, 'default_guest_transport', lambda: None):
        report = env.run(transport=None, guest=None)
    assert report['skipped'] == 1 and report['details'][0]['text'] == pub.NO_TOKEN_TEXT


# --------------------------------------------------------------------------- Instagram

def _instagram(env, time='12:00'):
    material = env.material(title='Команда Лиговского', base_text='Знакомьтесь: команда Лиговского')
    env.photo(material['id'])
    pid = env.placement(material['id'], channel='instagram', time=time)
    env.approve(pid)
    return material['id'], pid


def test_instagram_reminder_once_with_header_text_and_album():
    env = Env()
    env.enable(bars=(), instagram_chat='670033096', minutes=30)
    mid, pid = _instagram(env, time='12:30')
    env.at(11, 59)
    assert env.run()['sent'] == 0
    env.at(12, 0)                                                          # 12:30 минус 30 минут
    report = env.run()
    assert report['sent'] == 1 and report['details'][0]['result'] == 'reminded'
    header, body, album = env.tg.sends()
    assert header['method'] == 'sendMessage' and header['payload']['chat_id'] == '670033096'
    assert header['payload']['text'].startswith('Instagram: пора выложить — «Команда Лиговского», 7 октября 12:30')
    assert f'https://beerkultura.ru/content-plan?open={mid}' in header['payload']['text']
    assert body['payload']['text'] == 'Знакомьтесь: команда Лиговского'
    assert album['method'] == 'sendPhoto' and 'caption' not in album['payload']
    raw = env.raw(pid)
    assert raw['status'] == 'approved' and raw['delivery']['state'] == 'reminded'
    assert raw['delivery']['reminded_at'] == '2026-10-07T12:00'
    assert env.view(pid)['display_label'] == 'Напоминание отправлено'
    env.at(12, 31)
    assert env.run()['sent'] == 0 and len(env.tg.sends()) == 3             # напоминание — один раз
    view = env.view(pid)
    assert (view['display_state'], view['display_label']) == ('overdue', 'Напоминание отправлено, выход не отмечен')
    assert 'reminder' in env.log(mid)
    env.store.placement_action(pid, 'mark_published', USER)                # «вышло» отмечает владелец
    assert env.raw(pid)['status'] == 'published'


def test_instagram_reminder_late_and_failed_are_not_repeated():
    env = Env(datetime(2026, 10, 7, 8, 0))
    env.enable(bars=(), instagram_chat='670033096')
    _mid, late = _instagram(env, time='09:00')
    env.at(11, 0)
    report = env.run()
    assert report['skipped'] == 1 and env.tg.sends() == []
    assert env.raw(late)['delivery']['state'] == 'reminder_late'
    assert env.run()['details'] == []                                       # один раз
    env2 = Env()
    env2.enable(bars=(), instagram_chat='670033096')
    _mid, pid = _instagram(env2)
    env2.tg.respond('sendMessage', {'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'})
    env2.at(12, 0)
    assert env2.run()['failed'] == 1
    raw = env2.raw(pid)
    assert raw['status'] == 'approved' and raw['delivery']['state'] == 'reminder_failed'
    assert env2.view(pid)['display_label'].startswith('Напоминание не отправлено: канал или чат не найден')
    env2.at(12, 1)
    assert env2.run()['details'] == [] and len(env2.tg.sends()) == 1        # без автоповтора


# --------------------------------------------------------------------------- бот

def _bot_post(env, segment='bot_all', bar=None, media=False, time='12:00'):
    material = env.material(title='Новости', base_text='Новый сезон кранов')
    if media:
        env.photo(material['id'])
    fields = {'audience': {'segment': segment}, 'time': time}
    if bar:
        fields['bars'] = [bar]
    pid = env.placement(material['id'], channel='bot', **fields)
    env.approve(pid)
    return material['id'], pid


def test_bot_partial_delivery_blocked_and_retry_only_failed():
    env = Env()
    env.enable(bars=(), bot=True)
    subs = FakeSubscribers([101, 102, 103, 104, 105])
    env.tg.per_chat['103'] = {'ok': False, 'error_code': 403, 'description': 'Forbidden: bot was blocked by the user'}
    env.tg.per_chat['104'] = {'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'}
    with _subscribers(subs):
        mid, pid = _bot_post(env)
        env.at(12, 0)
        report = env.run()
        assert report['sent'] == 1 and report['details'][0]['text'] == 'дошло 3 из 5'
        assert [c['payload']['chat_id'] for c in env.tg.sends()] == [101, 102, 103, 104, 105]
        assert subs.blocked == [103]                                        # 403 -> mark_blocked
        raw = env.raw(pid)
        assert raw['status'] == 'published' and raw['delivery']['state'] == 'partial'
        stats = raw['delivery']['stats']
        assert (stats['total'], stats['sent'], stats['failed'], stats['blocked']) == (5, 3, 1, 1)
        assert raw['delivery']['failed_to'] == ['104'] and raw['delivery']['sent_to'] == ['101', '102', '105']
        view = env.view(pid)
        assert view['display_label'] == 'Вышло: дошло 3 из 5'
        assert 'sent_to' not in view['delivery'] and 'recipients' not in view['delivery']   # chat_id не наружу
        assert 'failed_to' not in json.dumps(env.store.month_payload('2026-10'))
        # повтор только неудавшимся
        del env.tg.per_chat['104']
        env.store.placement_action(pid, 'retry_failed', USER)
        assert env.view(pid)['display_label'] == 'Вышло: дошло 3 из 5 · повтор неудавшимся в очереди'
        env.tg.calls.clear()
        env.at(12, 1)
        assert env.run()['sent'] == 1
        assert [c['payload']['chat_id'] for c in env.tg.sends()] == [104]
        raw = env.raw(pid)
        assert raw['delivery']['state'] == 'sent' and raw['delivery']['stats']['sent'] == 4
        assert raw['published_at'] == '2026-10-07T12:00'                   # первая публикация не переписана
        try:
            env.store.placement_action(pid, 'retry_failed', USER)
            raise AssertionError('повторять некому — 409')
        except cp.ContentPlanConflict:
            pass
        assert {'auto_publish', 'retry_failed'} <= set(env.log(mid))


def test_bot_rate_limit_25_per_second_and_media_counts_as_messages():
    env = Env()
    env.enable(bars=(), bot=True)
    with _subscribers(FakeSubscribers(list(range(1, 31)))):
        _bot_post(env)
        env.at(12, 0)
        env.run()
    assert len(env.tg.sends()) == 30 and len(env.sleeps) == 29
    assert abs(sum(env.sleeps) - 29 / 25) < 1e-9                            # 30 сообщений — 1,16 с
    env2 = Env()
    env2.enable(bars=(), bot=True)
    with _subscribers(FakeSubscribers([1, 2, 3])):
        material = env2.material(base_text='Альбом')
        env2.photo(material['id'])
        env2.photo(material['id'])
        pid = env2.placement(material['id'], channel='bot', audience={'segment': 'bot_all'})
        env2.approve(pid)
        env2.at(12, 0)
        env2.run()
    assert env2.sleeps == [2 / 25, 2 / 25]                                  # альбом из 2 файлов — 2 сообщения
    first, second, third = env2.tg.sends()
    assert first['files'] and second['files'] is None and third['files'] is None   # загрузка один раз


def test_bot_interrupted_mailing_is_not_resent_to_recipients():
    env = Env()
    env.enable(bars=(), bot=True)
    subs = FakeSubscribers([1, 2, 3, 4, 5])
    with _subscribers(subs):
        mid, pid = _bot_post(env)
        env.set(pid, delivery={'state': 'sending', 'attempt_id': 'dead', 'started_at': '2026-10-07T12:00',
                               'heartbeat_at': '2026-10-07T12:00', 'recipients': ['1', '2', '3', '4', '5'],
                               'sent_to': ['1', '2'], 'pending': ['3', '4'], 'failed_to': []})
        env.at(12, 10)
        report = env.run()
        assert report['details'][0]['result'] == 'stale' and env.tg.sends() == []
        raw = env.raw(pid)
        assert raw['status'] == 'published' and raw['delivery']['state'] == 'partial'
        assert raw['delivery']['unknown_to'] == ['3', '4'] and raw['delivery']['failed_to'] == ['5']
        assert raw['delivery']['error'] == 'Рассылка прервалась: дошло 2 из 5; у 2 статус неизвестен'
        env.store.placement_action(pid, 'retry_failed', USER)
        env.at(12, 11)
        env.run()
        assert [c['payload']['chat_id'] for c in env.tg.sends()] == [5]     # 1, 2 получили; 3, 4 — не повторяем
        stats = env.raw(pid)['delivery']['stats']
        assert (stats['total'], stats['sent'], stats['unknown'], stats['failed']) == (5, 3, 2, 0)


def test_bot_unsubscribed_are_not_resent_and_network_abort():
    env = Env()
    env.enable(bars=(), bot=True)
    subs = FakeSubscribers([1, 2, 3])
    env.tg.per_chat['2'] = {'ok': False, 'error_code': 400, 'description': 'Bad Request: something'}
    with _subscribers(subs):
        _mid, pid = _bot_post(env)
        env.at(12, 0)
        env.run()
        subs.unsubscribed.add(2)                                           # отписался — повтор ему не шлём
        env.store.placement_action(pid, 'retry_failed', USER)
        env.tg.calls.clear()
        env.at(12, 1)
        env.run()
        assert env.tg.sends() == []
        stats = env.raw(pid)['delivery']['stats']
        assert (stats['sent'], stats['unsubscribed'], stats['failed']) == (2, 1, 0)
    env2 = Env()
    env2.enable(bars=(), bot=True)

    class Down(FakeTelegram):
        def call(self, method, payload=None):
            self.calls.append({'method': method, 'payload': dict(payload or {}), 'files': None})
            return None

    down = Down()
    with _subscribers(FakeSubscribers([1, 2, 3, 4, 5, 6])):
        _mid, pid2 = _bot_post(env2)
        env2.at(12, 0)
        env2.run(transport=down)
    assert len(down.sends()) == pub.NETWORK_ABORT_AFTER                     # три обрыва подряд — стоп
    raw = env2.raw(pid2)
    stats = raw['delivery']['stats']
    # Ответа нет (запрос мог дойти) — статус неизвестен, повтор им не шлётся; до кого
    # очередь не дошла — failed_to (повтор безопасен).
    assert raw['status'] == 'failed' and (stats['unknown'], stats['failed']) == (3, 3)
    assert raw['delivery']['unknown_to'] == ['1', '2', '3'] and raw['delivery']['failed_to'] == ['4', '5', '6']
    assert raw['failed_error'].startswith('Рассылка не дошла ни одному подписчику: не отправлено: нет связи')
    # после ошибки «Повторить» шлёт тем, кому точно не ушло
    env2.store.placement_action(pid2, 'retry', USER)
    with _subscribers(FakeSubscribers([1, 2, 3, 4, 5, 6])):
        env2.at(12, 1)
        env2.run()
    assert [c['payload']['chat_id'] for c in env2.tg.sends()] == [4, 5, 6]
    assert env2.raw(pid2)['status'] == 'published'
    # транспорт знает, что запрос не ушёл (все пути отказали до отправки) — это failed,
    # и «Повторить» доводит всем
    env3 = Env()
    env3.enable(bars=(), bot=True)

    class Refused(Down):
        last_outcome = 'not_sent'

    with _subscribers(FakeSubscribers([1, 2, 3, 4])):
        _mid, pid3 = _bot_post(env3)
        env3.at(12, 0)
        env3.run(transport=Refused())
        raw = env3.raw(pid3)
        assert raw['delivery']['stats']['failed'] == 4 and raw['delivery']['stats']['unknown'] == 0
        env3.store.placement_action(pid3, 'retry', USER)
        env3.at(12, 1)
        env3.run()
    assert len(env3.tg.sends()) == 4 and env3.raw(pid3)['status'] == 'published'


def test_bot_disabled_empty_audience_and_transport_exception():
    env = Env()
    env.enable(bars=())                                                    # рассылки гостям выключены
    with _subscribers(FakeSubscribers([1])):
        _mid, pid = _bot_post(env)
        env.at(12, 0)
        report = env.run()
    assert report['details'][0]['text'] == 'Площадка не подключена: рассылки гостям выключены'
    assert env.tg.sends() == [] and env.raw(pid)['status'] == 'approved'
    env2 = Env()
    env2.enable(bars=(), bot=True)
    with _subscribers(FakeSubscribers([])):
        _mid, pid = _bot_post(env2)
        env2.at(12, 0)
        env2.run()
    assert env2.raw(pid)['status'] == 'failed' and env2.raw(pid)['failed_error'] == pub.EMPTY_AUDIENCE_TEXT
    assert env2.tg.sends() == []
    # сбой транспорта на одном госте: его статус неизвестен (повтор ему не шлётся), остальным — дошло
    env3 = Env()
    env3.enable(bars=(), bot=True)
    env3.tg.raise_for.add('2')
    with _subscribers(FakeSubscribers([1, 2, 3])):
        _mid, pid = _bot_post(env3)
        env3.at(12, 0)
        env3.run()
    raw = env3.raw(pid)
    assert raw['status'] == 'published' and raw['delivery']['state'] == 'sent'
    assert raw['delivery']['unknown_to'] == ['2'] and raw['delivery']['sent_to'] == ['1', '3']
    assert 'статус неизвестен' in raw['delivery']['error'] and raw['delivery']['stats']['unknown'] == 1


def test_guest_mailing_uses_only_guest_bot():
    """Регрессия (проверка 2026-09-28): при отдельном боте контента рассылка гостям шла бы
    им — Telegram ответил бы 403, и каждый подписчик был бы помечен «заблокировал бота».
    Рассылка — только гостевым ботом; посты в каналы — ботом каналов; file_id у ботов свои."""
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='content-token', TELEGRAM_BOT_TOKEN='guest-token'):
        assert cc.channel_bot_token() == ('content-token', 'content')
        assert cc.guest_bot_token() == ('guest-token', 'taplist')
        assert pub.default_transport().token == 'content-token'
        assert pub.default_guest_transport().token == 'guest-token'
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='content-token', TELEGRAM_BOT_TOKEN=None):
        assert cc.guest_bot_token() == (None, None) and pub.default_guest_transport() is None
        settings = dict(cc.default_settings(), enabled=True, bot={'enabled': True, 'signup': False})
        delivery = cc.delivery_state(settings, True, 0, guest_token_present=False)
        assert delivery['bot']['connected'] is False and delivery['bot']['reason'] == cc.GUEST_BOT_MISSING
    env = Env()
    env.enable(bot=True)
    content_bot, guest_bot = FakeTelegram(), FakeTelegram()
    content_bot.next_id, guest_bot.next_id = 1000, 2000
    material = env.material(base_text='Новости недели')
    env.photo(material['id'])
    post = env.placement(material['id'])
    mailing = env.placement(material['id'], channel='bot', audience={'segment': 'bot_all'})
    env.approve(post, mailing)
    subs = FakeSubscribers([7, 8])
    with _subscribers(subs):
        env.at(12, 0)
        report = env.run(transport=content_bot, guest=guest_bot)
    assert report['sent'] == 2 and subs.blocked == []
    assert [c['payload']['chat_id'] for c in content_bot.sends()] == ['@kult_bolshoy']
    assert [c['payload']['chat_id'] for c in guest_bot.sends()] == ['7', 8]
    first, second = guest_bot.sends()
    assert first['files'] and second['files'] is None                   # гостевой бот загрузил сам
    assert second['payload']['photo'].startswith('P2')                   # и шлёт своим file_id
    # гостевого бота нет — рассылка пропущена, пост в канал уходит
    env2 = Env()
    env2.enable(bot=True)
    _mid, post2 = _post(env2)
    _bmid, mailing2 = _bot_post(env2)
    with _subscribers(FakeSubscribers([7])):
        env2.at(12, 0)
        report = env2.run(guest=None)
    assert report['sent'] == 1 and report['skipped'] == 1
    assert next(d for d in report['details'] if d['result'] == 'skipped')['text'] == pub.GUEST_NO_TOKEN_TEXT
    assert env2.raw(mailing2)['status'] == 'approved' and env2.raw(post2)['status'] == 'published'
    try:
        pub.publish_now(mailing2, USER, store=env2.store, channels=env2.channels, transport=env2.tg,
                        guest_transport=None)
        raise AssertionError('рассылка без гостевого бота — 409')
    except cp.ContentPlanConflict as e:
        assert str(e) == pub.GUEST_NO_TOKEN_TEXT
    with _client(env2, guest_token=(None, None)) as c:
        body = c.get('/api/content-plan/channels').get_json()
        assert body['token_source'] == 'taplist' and body['guest_token_source'] is None
        assert body['delivery']['bot']['reason'] == cc.GUEST_BOT_MISSING
        assert body['delivery']['guest_bot_configured'] is False and body['delivery']['bot_configured'] is True


def test_bot_audience_passes_segment_and_bar():
    env = Env()
    env.enable(bars=(), bot=True)
    subs = FakeSubscribers([7])
    with _subscribers(subs):
        _bot_post(env, segment='bot_bar', bar='ligovskiy')
        env.at(12, 0)
        env.run()
    assert subs.asked == [('bot_bar', 'ligovskiy')]


def test_real_guest_subscribers_module():
    """С настоящим core/guest_subscribers.py (временная база): размер аудитории, получатели,
    403 -> отметка «заблокировал» в базе подписчиков. Нет модуля — пропуск."""
    try:
        import core.guest_subscribers as gs
    except ImportError:
        return
    tmp = _tmpdir()
    store = gs.SubscriberStore(os.path.join(tmp, 'guest_subscribers.db'), os.path.join(tmp, 'guests.db'),
                               clock=lambda: datetime(2026, 10, 7, 11, 0))
    previous = gs.set_store(store)
    try:
        for chat in (111, 222, 333):
            store.subscribe(chat, username=f'guest{chat}', first_name='Гость')
        store.set_bars(333, ['ligovskiy'])
        assert cc.audience_size('bot_all') == (3, cc.audience_size('bot_all')[1])
        assert cc.audience_size('bot_bar', 'bolshoy')[0] == 2                # 333 выбрал только Лиговский
        assert cc.subscribers_total() == 3
        assert cc.recipients('bot_all') == [111, 222, 333]
        env = Env()
        env.enable(bars=(), bot=True)
        env.tg.per_chat['222'] = {'ok': False, 'error_code': 403, 'description': 'Forbidden: bot was blocked by the user'}
        _mid, pid = _bot_post(env)
        env.at(12, 0)
        env.run()
        stats = env.raw(pid)['delivery']['stats']
        assert (stats['total'], stats['sent'], stats['blocked']) == (3, 2, 1)
        assert store.stats()['blocked'] == 1 and cc.subscribers_total() == 2
        assert cc.recipients('bot_all') == [111, 333]
    finally:
        gs.set_store(previous)


# --------------------------------------------------------------------------- «Отправить сейчас»

def test_publish_now_rules_and_channels():
    env = Env()
    env.enable(enabled=False, instagram_chat='670033096')
    material = env.material(base_text='Сейчас')
    draft = env.placement(material['id'], time='18:00')
    kwargs = dict(store=env.store, channels=env.channels, transport=env.tg, guest_transport=env.tg)
    try:
        pub.publish_now(draft, USER, **kwargs)
        raise AssertionError('черновик — 409')
    except cp.ContentPlanConflict as e:
        assert 'только утверждённую' in str(e)
    env.approve(draft)
    try:
        pub.publish_now(draft, USER, **kwargs)
        raise AssertionError('выключено — 409')
    except cp.ContentPlanConflict as e:
        assert str(e) == pub.DISABLED_TEXT
    assert env.tg.sends() == []
    env.channels.update({'enabled': True}, USER)
    try:
        pub.publish_now(draft, USER, store=env.store, channels=env.channels, transport=None, guest_transport=env.tg)
        raise AssertionError('нет бота каналов — 409')
    except cp.ContentPlanConflict as e:
        assert str(e) == pub.NO_TOKEN_TEXT
    # «Отправить сейчас» только ставит в очередь (п. 9/10 проверки): отправляет планировщик.
    result = pub.publish_now(draft, USER, **kwargs)                        # 18:00 — сейчас 11:00
    assert result['queued'] is True and result['message'] == 'Уйдёт в течение минуты'
    assert result['placement']['status'] == 'approved' and env.tg.sends() == []
    assert result['placement']['delivery']['state'] == 'queued' and result['placement']['delivery']['send_now']
    assert result['placement']['display_label'] == 'В очереди на отправку: уйдёт в течение минуты'
    assert env.log(material['id'])[0] == 'publish_now'
    env.at(11, 1)
    report = env.run()                                                     # ближайший проход — отправка
    assert report['sent'] == 1 and env.raw(draft)['status'] == 'published' and len(env.tg.sends()) == 1
    assert env.log(material['id'])[:2] == ['auto_publish', 'publish_now']
    other = env.material(base_text='Лиговский')
    lig = env.placement(other['id'], bars=['ligovskiy'], time='18:00')
    env.approve(lig)
    try:
        pub.publish_now(lig, USER, **kwargs)
        raise AssertionError('канал не подключён — 409')
    except cp.ContentPlanConflict as e:
        assert str(e) == 'Площадка не подключена: канал не указан'
    ig_mid, ig = _instagram(env, time='18:00')
    result = pub.publish_now(ig, USER, **kwargs)
    assert result['queued'] is True and result['placement']['status'] == 'approved'
    env.at(11, 2)
    env.run()                                                              # напоминание — сразу, не за N минут
    assert env.raw(ig)['delivery']['state'] == 'reminded' and env.raw(ig)['status'] == 'approved'
    # бот: тоже в очередь; рассылку ведёт планировщик (не поток веб-воркера)
    env.channels.update({'bot': {'enabled': True}}, USER)
    with _subscribers(FakeSubscribers([1, 2])):
        _bmid, bot = _bot_post(env, time='18:00')
        result = pub.publish_now(bot, USER, **kwargs)
        assert result['queued'] is True and env.raw(bot)['delivery']['state'] == 'queued'
        env.at(11, 3)
        env.run()
    assert env.raw(bot)['status'] == 'published' and env.raw(bot)['delivery']['stats']['sent'] == 2
    # CONTENT_PUBLISH=0 — планировщика нет, очередь не разобрать: 409
    other2 = env.material(base_text='Ещё')
    p2 = env.placement(other2['id'], time='18:00')
    env.approve(p2)
    with _env_vars(CONTENT_PUBLISH='0'):
        try:
            pub.publish_now(p2, USER, **kwargs)
            raise AssertionError('CONTENT_PUBLISH=0 — 409')
        except cp.ContentPlanConflict as e:
            assert str(e) == pub.SCHEDULER_OFF_TEXT


# --------------------------------------------------------------------------- маршруты

@contextmanager
def _client(env, user=USER, token=('test-token', 'taplist'), guest_token=None):
    """Голое приложение с content_plan_bp; оба бота — env.tg (guest_token по умолчанию =
    token); токен None — бот не настроен."""
    names = ('_store', 'current_user', '_channels', '_transport', '_guest_transport', '_bot_token',
             '_guest_bot_token', '_audience', '_subscribers_total')
    saved = [(name, getattr(rcp, name)) for name in names]
    guest_token = token if guest_token is None else guest_token
    rcp._store = lambda: env.store
    rcp.current_user = lambda: user
    rcp._channels = lambda: env.channels
    rcp._transport = lambda: env.tg if token[0] else None
    rcp._guest_transport = lambda: env.tg if guest_token[0] else None
    rcp._bot_token = lambda: token
    rcp._guest_bot_token = lambda: guest_token
    rcp._audience = lambda segment, bar: (3 if bar is None else 1, 'тестовые подписчики')
    rcp._subscribers_total = lambda: 3
    try:
        app = Flask('test_content_publisher')
        app.register_blueprint(content_plan_bp)
        yield app.test_client()
    finally:
        for name, value in saved:
            setattr(rcp, name, value)


def test_channels_routes():
    env = Env()
    with _client(env) as c:
        body = c.get('/api/content-plan/channels').get_json()
        assert body['channels']['enabled'] is False and body['token_source'] == 'taplist'
        assert body['delivery']['telegram']['bolshoy'] == {'connected': False, 'chat': '', 'title': '',
                                                           'reason': 'канал не указан'}
        assert body['delivery_connected'] == {'telegram': False, 'instagram': False, 'bot': False}
        assert body['limits'] == {'reminder_minutes_max': 720, 'title_max': 100}
        assert 'bot_identity' not in body['channels'] and body['subscribers_total'] == 3
        r = c.put('/api/content-plan/channels', json={'telegram': {'bolshoy': {'chat': 't.me/kult_vo',
                                                                               'title': ' Культура  ВО '}},
                                                     'instagram': {'reminder_chat': 670033096,
                                                                   'reminder_minutes_before': 30}})
        assert r.status_code == 200
        body = r.get_json()
        assert body['channels']['telegram']['bolshoy']['chat'] == '@kult_vo'
        assert body['channels']['telegram']['bolshoy']['title'] == 'Культура ВО'
        assert body['channels']['instagram']['reminder_chat'] == '670033096'
        assert body['delivery']['telegram']['bolshoy']['reason'] == 'канал не проверен'
        for bad in ({'telegram': {'nevsky': {'chat': '@kult_nv'}}}, {'slack': 1},
                    {'telegram': {'bolshoy': {'chat': 't.me/+AbCdEf'}}},
                    {'telegram': {'bolshoy': {'chat': '@ab'}}},
                    {'instagram': {'reminder_minutes_before': 721}}, {'enabled': 'может'},
                    {'bot': {'enabled': True, 'segment': 'x'}}):
            r = c.put('/api/content-plan/channels', json=bad)
            assert r.status_code == 400, (bad, r.get_json())
        assert c.post('/api/content-plan/channels/check', json={}).status_code == 400
        assert c.post('/api/content-plan/channels/check', json={'bar': 'ligovskiy'}).status_code == 400   # нет канала
        r = c.post('/api/content-plan/channels/check', json={'bar': 'bolshoy'})
        body = r.get_json()
        assert r.status_code == 200 and body['check']['ok'] and body['check']['can_post'] and body['saved']
        assert body['bot_username'] == 'kult_test_bot' and body['check']['chat_username'] == 'kult_vo'
        assert body['channels']['telegram']['bolshoy']['connected_since'] == '2026-10-07T11:00'
        assert body['delivery']['telegram']['bolshoy']['reason'] == 'отправка выключена'
        r = c.put('/api/content-plan/channels', json={'enabled': True})
        assert r.get_json()['delivery']['telegram']['bolshoy']['connected'] is True
        assert r.get_json()['delivery_connected'] == {'telegram': True, 'instagram': True, 'bot': False}
        r = c.post('/api/content-plan/channels/test', json={'bar': 'bolshoy'})
        body = r.get_json()
        assert body['ok'] is True and body['message_id'] and body['chat'] == '@kult_vo'
        assert env.tg.calls[-1]['payload']['text'] == 'Проверка связи с сайтом'
        history = [h['text'] for h in env.channels.load()['history']]
        assert 'Отправка публикаций включена' in history and any(t.startswith('Тестовое сообщение') for t in history)
        # смена адреса стирает проверку
        c.put('/api/content-plan/channels', json={'telegram': {'bolshoy': {'chat': '@kult_vo_new'}}})
        assert env.channels.load()['telegram']['bolshoy']['check'] is None
    with _client(env, token=(None, None)) as c:
        body = c.get('/api/content-plan/channels').get_json()
        assert body['token_source'] is None and body['delivery']['bot']['reason'] == 'рассылки гостям выключены'
        assert body['delivery']['instagram']['reason'] == 'бот не настроен'
        r = c.post('/api/content-plan/channels/test', json={'bar': 'bolshoy'})
        assert r.get_json() == {'ok': False, 'message_id': None, 'error': pub.NO_TOKEN_TEXT, 'chat': '@kult_vo_new'}
        r = c.post('/api/content-plan/channels/check', json={'bar': 'bolshoy'})
        assert r.get_json()['check']['error'] == pub.NO_TOKEN_TEXT and r.get_json()['saved'] is False
    with open(env.channels.data_file, 'w', encoding='utf-8') as f:
        f.write('{битый')
    with _client(env) as c:
        for r in (c.get('/api/content-plan/channels'), c.put('/api/content-plan/channels', json={'enabled': False})):
            assert r.status_code == 503 and r.get_json()['code'] == 'content_channels_unavailable'
    assert open(env.channels.data_file, encoding='utf-8').read() == '{битый'   # не перезаписан


def test_channel_check_errors():
    env = Env()
    env.channels.update({'telegram': {'bolshoy': {'chat': '@kult_vo'}}}, USER)
    env.tg.respond('getChat', {'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'})
    check = pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']
    assert check['ok'] is False and check['error'].startswith('канал или чат не найден')
    env.tg.respond('getChatMember', {'ok': True, 'result': {'status': 'member'}})
    check = pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']
    assert check['ok'] is True and check['can_post'] is False and 'Публикация сообщений' in check['error']
    env.tg.respond('getChatMember', {'ok': True, 'result': {'status': 'left'}})
    check = pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']
    assert check['error'].startswith('Бот не состоит в канале')
    assert cc.telegram_bar_reason(env.channels.load()['telegram']['bolshoy']).startswith('Бот не состоит')
    env.tg.respond('getChatMember', {'ok': True, 'result': {'status': 'administrator', 'can_post_messages': False}})
    assert pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']['can_post'] is False
    env.tg.respond('getChat', {'ok': True, 'result': {'id': -5, 'type': 'supergroup', 'title': 'Группа'}})
    env.tg.respond('getChatMember', {'ok': True, 'result': {'status': 'member'}})
    assert pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']['can_post'] is True


def test_publish_now_route():
    env = Env()
    env.enable()
    material = env.material(base_text='Сейчас')
    pid = env.placement(material['id'], time='18:00')
    with _client(env) as c:
        assert c.post('/api/content-plan/publish-now', json={}).status_code == 400
        assert c.post('/api/content-plan/publish-now', json={'placement_id': 'p_nope'}).status_code == 404
        r = c.post('/api/content-plan/publish-now', json={'placement_id': pid})
        assert r.status_code == 409 and 'только утверждённую' in r.get_json()['error']
        env.approve(pid)
        r = c.post('/api/content-plan/publish-now', json={'placement_id': pid})
        body = r.get_json()
        assert r.status_code == 200 and body['queued'] is True and body['message'] == 'Уйдёт в течение минуты'
        assert body['placement']['status'] == 'approved' and body['material']['id'] == material['id']
        assert env.tg.sends() == []                                         # в запросе ничего не шлётся
        assert env.store.log_for(material['id'])[0]['by'] == 'anna'        # publish_now — кто нажал
    with _client(env, user=AGENT) as c:
        other = env.material(base_text='Ещё')
        pid2 = env.placement(other['id'], time='18:00')
        env.approve(pid2)
        r = c.post('/api/content-plan/publish-now', json={'placement_id': pid2})
        assert r.status_code == 200 and env.store.log_for(other['id'])[0]['by'] == 'anna · агент'


def test_audience_route_and_real_sizes_in_month():
    env = Env()
    with _client(env) as c:
        r = c.get('/api/content-plan/audience?segment=bot_all')
        assert r.get_json() == {'segment': 'bot_all', 'name': 'Все подписчики бота', 'bar': 'all', 'size': 3,
                                'size_note': 'тестовые подписчики', 'subscribers_total': 3}
        assert c.get('/api/content-plan/audience?segment=bot_bar&bar=ligovskiy').get_json()['size'] == 1
        assert c.get('/api/content-plan/audience?segment=vip').status_code == 400
        assert c.get('/api/content-plan/audience?segment=bot_all&bar=nevsky').status_code == 400
    # настоящая обёртка над подписчиками: нет модуля — 0, bot_bar без бара — неизвестно
    with _patch(cc, '_subscribers_module', lambda: None):
        assert cc.audience_size('bot_all') == (0, cc.NO_MODULE_NOTE)
        assert cc.subscribers_total() == 0 and cc.recipients('bot_all') == []
    assert cc.audience_size('bot_bar', None) == (None, cc.NEEDS_BAR_NOTE)
    with _subscribers(FakeSubscribers([1, 2])):
        size, note = cc.audience_size('bot_recent_30')
        assert size == 2 and 'телефоном' in note
        store = cp.ContentPlanStore(os.path.join(_tmpdir(), 'content_plan.json'), now_fn=Clock(SETUP),
                                    audience_fn=cc.audience_size)
        material = store.create_material({'month': '2026-10', 'title': 'Б', 'base_text': 'т'}, USER)
        store.add_placements(material['id'], {'channel': 'bot', 'audience': 'bot_all', 'date': '2026-10-08',
                                              'time': '12:00'}, USER)
        payload = store.month_payload('2026-10')
        assert [a['size'] for a in payload['audiences']] == [2, None, 2, 2]
        assert payload['audiences'][1]['size_by_bar'] == {'bolshoy': 2, 'ligovskiy': 2, 'kremenchugskaya': 2,
                                                          'varshavskaya': 2}
        assert payload['materials'][0]['placements'][0]['audience_info']['size'] == 2
        assert store.approve_preview('2026-10')['bot'][0]['audience']['size'] == 2

    class Broken(FakeSubscribers):
        def audience_size(self, segment, bar=None):
            raise OSError('база недоступна')

    with _subscribers(Broken([])):
        assert cc.audience_size('bot_all') == (None, cc.READ_ERROR_NOTE)


def test_month_payload_delivery_block():
    env = Env()
    env.enable()
    store = cp.ContentPlanStore(env.store.data_file, now_fn=env.clock,
                                delivery_fn=lambda: cc.payload_delivery(env.channels, lambda: 5))
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='x-token', TELEGRAM_BOT_TOKEN=None):
        payload = store.month_payload('2026-10')
    assert payload['delivery']['telegram']['bolshoy']['connected'] is True
    assert payload['delivery']['bot'] == {'connected': False, 'enabled': False, 'signup': False,
                                          'subscribers_total': 5, 'reason': 'рассылки гостям выключены'}
    assert payload['delivery_connected'] == {'telegram': True, 'instagram': False, 'bot': False}
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN=None, TELEGRAM_BOT_TOKEN=None):
        payload = store.month_payload('2026-10')
    assert payload['delivery_connected']['telegram'] is False
    assert payload['delivery']['telegram']['bolshoy']['reason'] == 'бот не настроен'
    with open(env.channels.data_file, 'w', encoding='utf-8') as f:
        f.write('[]')
    payload = store.month_payload('2026-10')                               # битые настройки — план открывается
    assert payload['delivery']['error'].startswith('Файл настроек каналов повреждён')
    assert payload['delivery_connected'] == {'telegram': False, 'instagram': False, 'bot': False}
    plain = env.store.month_payload('2026-10')                              # без delivery_fn — как раньше
    assert plain['delivery_connected'] == cp.DELIVERY_CONNECTED and plain['delivery']['enabled'] is False


def test_compact_view():
    env = Env()
    mid, pid = _post(env)
    env.set(pid, status='failed', failed_error='сеть')
    with _client(env) as c:
        body = c.get('/api/content-plan?month=2026-10&compact=1').get_json()
        assert body['compact'] is True and 'channels' not in body and 'delivery' not in body
        assert body['stats'] == {'materials': 1, 'placements': 1, 'by_state': {'failed': 1}}
        assert body['materials'] == [{'id': mid, 'title': 'Квиз', 'kind': 'fixed', 'month': '2026-10',
                                      'in_month': True, 'date': '2026-10-07', 'origin': 'human',
                                      'agent_draft': False,
                                      'summary': {'label': 'Ошибка отправки: 1', 'state': 'failed'},
                                      'placements': [{'id': pid, 'channel': 'telegram', 'bar': 'bolshoy',
                                                      'date': '2026-10-07', 'time': '12:00',
                                                      'display_state': 'failed'}]}]
        state = c.get('/api/content-plan?state=failed&compact=true').get_json()
        assert state['scope'] == 'state' and state['compact'] is True and len(state['materials']) == 1
        full = c.get('/api/content-plan?month=2026-10&compact=0').get_json()
        assert 'compact' not in full and 'channels' in full
        assert c.get('/api/content-plan?month=2026-10&compact=может').status_code == 400
        assert len(json.dumps(body, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False)) / 4


def test_agent_edits():
    env = Env()
    store = env.store
    kept = store.create_material({'month': '2026-10', 'title': 'Как есть', 'base_text': 'Текст агента'}, AGENT)
    store.add_placements(kept['id'], {'channel': 'telegram', 'bars': ['bolshoy'], 'date': '2026-10-09',
                                      'time': '12:00'}, AGENT)
    edited = store.create_material({'month': '2026-10', 'title': 'Правили', 'base_text': 'Черновик агента'}, AGENT)
    _m, pids = store.add_placements(edited['id'], {'channel': 'telegram', 'bars': ['bolshoy', 'ligovskiy'],
                                                   'date': '2026-10-09', 'time': '12:00'}, AGENT)
    store.update_placement(pids[1], {'text': 'Своя версия агента'}, AGENT)  # агент правит сам — не «правка»
    store.update_material(edited['id'], {'base_text': 'Текст владельца'}, USER)
    removed = store.create_material({'month': '2026-10', 'title': 'Лишнее', 'base_text': 'x'}, AGENT)
    store.delete_material(removed['id'], USER)
    self_removed = store.create_material({'month': '2026-10', 'title': 'Сам убрал', 'base_text': 'x'}, AGENT)
    store.delete_material(self_removed['id'], AGENT)
    human = store.create_material({'month': '2026-10', 'title': 'Человек', 'base_text': 'x'}, USER)
    store.update_material(human['id'], {'base_text': 'y'}, USER)
    raw = store.get_material_raw(edited['id'])
    assert raw['agent_original'] == {'base_text': 'Черновик агента',
                                     'placements': {pids[0]: None, pids[1]: 'Своя версия агента'}}
    assert 'agent_original' not in store.get_material(edited['id'])       # в API не отдаётся
    with _client(env, user=USER) as c:
        body = c.get('/api/content-plan/agent-edits').get_json()
        assert body['months'] == 3 and body['from_month'] == '2026-08'
        assert body['counts'] == {'agent_materials': 2, 'without_original': 0, 'changed': 1, 'unchanged': 1,
                                  'removed': 1}
        item = next(i for i in body['items'] if not i['removed'])
        assert (item['material_id'], item['base_text_changed'], item['changed']) == (edited['id'], True, True)
        assert item['original']['base_text'] == 'Черновик агента'
        rows = {r['id']: r for r in item['current']['placements']}
        assert rows[pids[0]]['text'] == 'Текст владельца' and rows[pids[0]]['changed'] is True
        assert rows[pids[1]]['text'] == 'Своя версия агента' and rows[pids[1]]['changed'] is False
        gone = next(i for i in body['items'] if i['removed'])
        assert (gone['material_id'], gone['title'], gone['removed_by']) == (removed['id'], 'Лишнее', 'anna')
        for bad in ('0', '13', 'abc', '1.5'):
            assert c.get('/api/content-plan/agent-edits?months=' + bad).status_code == 400
        assert c.get('/api/content-plan/agent-edits?months=12').status_code == 200
    # вышедшее: текст — из снимка утверждения; копии агента тоже с версией агента
    env.approve(pids[0])
    env.set(pids[0], status='published')
    store.update_material(edited['id'], {'base_text': 'Правка после выхода'}, USER)
    item = next(i for i in store.agent_edits(1)['items'] if not i['removed'])
    row = next(r for r in item['current']['placements'] if r['id'] == pids[0])
    assert (row['text'], row['text_source']) == ('Текст владельца', 'snapshot')
    copies = store.repeat(kept['id'], [4], '2026-10', AGENT)['created']
    assert copies and store.get_material_raw(copies[0])['agent_original']['base_text'] == 'Текст агента'
    human_copies = store.repeat(human['id'], [4], '2026-10', USER)['created']
    assert store.get_material_raw(human_copies[0])['agent_original'] is None


def test_download_zip():
    import test_content_plan as tcp
    env = Env()
    material = env.material(title='Команда', base_text='Подпись для Instagram')
    env.photo(material['id'], original='Команда бара.png')
    env.photo(material['id'], data=MP4, original='../../evil\\clip.mp4')
    ig = env.placement(material['id'], channel='instagram', time='19:00')
    env.placement(material['id'], bars=['ligovskiy'], time='18:00', text='Свой текст для ТГ')
    cancelled = env.placement(material['id'], bars=['varshavskaya'], time='17:00')
    env.store.placement_action(cancelled, 'cancel', USER)
    live = env.material(title='Таплист', kind='live', live_source='taplist', base_text=tcp.TEMPLATE)
    env.placement(live['id'], bars=['varshavskaya'])
    with _client(env) as c:
        r = c.get(f'/api/content-plan/materials/{material["id"]}/download')
        assert r.status_code == 200 and r.mimetype == 'application/zip'
        assert 'attachment' in r.headers['Content-Disposition']
        names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
        archive = zipfile.ZipFile(io.BytesIO(r.data))
        assert names[:2] == ['files/01_Команда бара.png', 'files/02_clip.mp4']      # без пути
        assert '01_telegram_ligovskiy_2026-10-07_1800.txt' in names
        assert '02_instagram_all_2026-10-07_1900.txt' in names
        assert not any('varshavskaya' in n for n in names)                         # отменённое — нет
        assert archive.read('02_instagram_all_2026-10-07_1900.txt').decode('utf-8') == 'Подпись для Instagram'
        assert archive.read('01_telegram_ligovskiy_2026-10-07_1800.txt').decode('utf-8') == 'Свой текст для ТГ'
        opis = archive.read('opis.txt').decode('utf-8')
        assert 'Материал: «Команда»' in opis and 'Instagram · Сеть · 7 окт 19:00' in opis
        assert 'файлы: files/01_Команда бара.png, files/02_clip.mp4' in opis
        assert c.get('/api/content-plan/materials/m_nope/download').status_code == 404
        with _patch(cp, 'load_live_data', lambda registry=None: (tcp.SNAPSHOT, tcp.REGISTRY)):
            r = c.get(f'/api/content-plan/materials/{live["id"]}/download')
        archive = zipfile.ZipFile(io.BytesIO(r.data))
        text = archive.read('01_telegram_varshavskaya_2026-10-07_1200.txt').decode('utf-8')
        assert text.startswith('Сегодня в баре «Варшавская»') and 'на момент скачивания' in archive.read(
            'opis.txt').decode('utf-8')
    assert ig


# --------------------------------------------------------------------------- вид и правки

def test_to_draft_clears_delivery_and_view_hides_internals():
    env = Env()
    env.enable()
    mid, pid = _post(env)
    env.set(pid, status='failed', failed_error='x', delivery={'state': 'failed', 'error': 'x', 'attempt_id': 'a',
                                                             'sent_to': ['1'], 'recipients': ['1']})
    view = env.view(pid)
    assert set(view['delivery']) == {'state', 'error', 'stats'}             # без attempt_id и списков
    env.store.update_material(mid, {'base_text': 'Новый текст'}, USER)      # содержание -> черновик
    raw = env.raw(pid)
    assert raw['status'] == 'draft' and raw['delivery'] is None


def test_channels_store_rules():
    assert cc.parse_chat('@Kult_VO') == '@Kult_VO' and cc.parse_chat('kult_vo') == '@kult_vo'
    assert cc.parse_chat('https://t.me/kult_vo/') == '@kult_vo' and cc.parse_chat(' -1001234567890 ') == '-1001234567890'
    assert cc.parse_chat(670033096) == '670033096' and cc.parse_chat('') == '' and cc.parse_chat(None) == ''
    for bad in ('@abc', 't.me/joinchat/xyz', 'https://t.me/+AbC', '@kult vo', '@_kult', True, ['@x']):
        try:
            cc.parse_chat(bad)
            raise AssertionError(repr(bad))
        except ValueError:
            pass
    env = Env()
    settings = env.channels.update({'enabled': True, 'bot': {'enabled': True},
                                    'instagram': {'reminder_chat': '670033096'}}, USER)
    assert settings['enabled_at'] == settings['bot']['enabled_at'] == settings['instagram']['since'] == '2026-10-07T11:00'
    env.at(11, 30)
    env.channels.update({'telegram': {'bolshoy': {'chat': '@kult_vo'}}}, USER)
    pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)
    settings = env.channels.load()
    assert cc.since_for(settings, 'telegram', 'bolshoy') == '2026-10-07T11:30'
    assert cc.since_for(settings, 'bot') == '2026-10-07T11:00'
    # повторная успешная проверка не сдвигает момент подключения
    env.at(12, 0)
    pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)
    assert env.channels.load()['telegram']['bolshoy']['connected_since'] == '2026-10-07T11:30'
    # результат проверки для старого адреса не сохраняется
    env.channels.save_check('bolshoy', '@old_name', {'ok': True, 'can_post': True}, USER)
    assert env.channels.load()['telegram']['bolshoy']['check']['chat'] == '@kult_vo'
    # правка без изменений файл не пишет; неизвестные ключи сохраняются
    mtime = os.path.getmtime(env.channels.data_file)
    env.channels.update({'enabled': True}, USER)
    assert os.path.getmtime(env.channels.data_file) == mtime
    data = json.load(open(env.channels.data_file, encoding='utf-8'))
    data['future_key'] = {'x': 1}
    json.dump(data, open(env.channels.data_file, 'w', encoding='utf-8'))
    env.channels.update({'enabled': False}, USER)
    assert json.load(open(env.channels.data_file, encoding='utf-8'))['future_key'] == {'x': 1}
    for broken in ({'version': 99}, {'enabled': 'yes'}, {'telegram': {'bolshoy': 'x'}},
                   {'instagram': {'reminder_minutes_before': 9999}}, []):
        json.dump(broken, open(env.channels.data_file, 'w', encoding='utf-8'))
        try:
            env.channels.load()
            raise AssertionError(repr(broken))
        except cc.ContentChannelsUnavailable:
            pass
    assert cc.bot_username({'bot_identity': {'username': 'b', 'token_hash': cc.token_hash('t1')}}, 't1') == 'b'
    assert cc.bot_username({'bot_identity': {'username': 'b', 'token_hash': cc.token_hash('t1')}}, 't2') is None
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='c', TELEGRAM_BOT_TOKEN='t'):
        assert cc.bot_token() == ('c', 'content')
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN=' ', TELEGRAM_BOT_TOKEN='t'):
        assert cc.bot_token() == ('t', 'taplist')
    with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN=None, TELEGRAM_BOT_TOKEN=None):
        assert cc.bot_token() == (None, None)


def test_bot_signup_switch_and_accessor():
    """bot.signup — кнопки «Подписаться на новости» и «Оставить отзыв» в гостевом боте:
    по умолчанию выключено; bot_signup_enabled читает сохранённый файл (кэш по mtime) и
    на любой сбой отвечает False."""
    env = Env()
    path = env.channels.data_file
    assert cc.bot_signup_enabled(path) is False                            # файла нет
    with _client(env) as c:
        body = c.get('/api/content-plan/channels').get_json()
        assert body['channels']['bot'] == {'enabled': False, 'enabled_at': None, 'signup': False}
        assert body['delivery']['bot']['signup'] is False
        body = c.put('/api/content-plan/channels', json={'bot': {'signup': True}}).get_json()
        assert body['channels']['bot']['signup'] is True and body['channels']['bot']['enabled'] is False
        assert body['delivery']['bot']['signup'] is True
        assert c.put('/api/content-plan/channels', json={'bot': {'signup': 'может'}}).status_code == 400
    assert cc.bot_signup_enabled(path) is True
    assert 'Кнопки «Подписаться на новости» и «Оставить отзыв» в боте включены' in [
        h['text'] for h in env.channels.load()['history']]
    reads = []
    real_check = cc._check_settings
    with _patch(cc, '_check_settings', lambda data: reads.append(1) or real_check(data)):
        assert cc.bot_signup_enabled(path) is True and reads == []         # тот же файл — из кэша
        env.channels.update({'bot': {'signup': False}}, USER)
        assert cc.bot_signup_enabled(path) is False and reads             # файл сменился — перечитан
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{битый json')
    assert cc.bot_signup_enabled(path) is False                            # сбой — кнопок нет
    assert cc.bot_signup_enabled(os.path.join(env.tmp, 'нет_такого.json')) is False


def test_history_capped():
    env = Env()
    for i in range(cc.HISTORY_MAX + 5):
        env.channels.update({'telegram': {'bolshoy': {'title': f'Канал {i}'}}}, USER)
    assert len(env.channels.load()['history']) == cc.HISTORY_MAX


# --------------------------------------------------------------------------- планировщик

def test_scheduler_does_not_start_without_token_or_when_disabled():
    started = []
    lock = os.path.join(_tmpdir(), '.content_publisher.lock')
    with _patch(sched, '_started', False), _patch(sched, '_start_thread', started.append):
        with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN=None, TELEGRAM_BOT_TOKEN=None, CONTENT_PUBLISH=None):
            assert sched.start_scheduler(lock_path=lock) is False
        with _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='fake', TELEGRAM_BOT_TOKEN=None, CONTENT_PUBLISH='0'):
            assert sched.start_scheduler(lock_path=lock) is False
    assert started == []


def test_scheduler_starts_once_and_respects_lock():
    import portalocker
    started = []
    lock = os.path.join(_tmpdir(), '.content_publisher.lock')
    with _patch(sched, '_started', False), _patch(sched, '_lock_handle', None), \
            _patch(sched, '_start_thread', started.append), \
            _env_vars(TELEGRAM_CONTENT_BOT_TOKEN='fake', TELEGRAM_BOT_TOKEN=None, CONTENT_PUBLISH=None):
        holder = open(lock, 'a')
        portalocker.lock(holder, portalocker.LOCK_EX | portalocker.LOCK_NB)  # «другой воркер»
        try:
            assert sched.start_scheduler(lock_path=lock) is False and started == []
        finally:
            portalocker.unlock(holder)
            holder.close()
        assert sched.start_scheduler(lock_path=lock) is True
        assert sched.start_scheduler(lock_path=lock) is True                # идемпотентно
        assert started == [sched._loop]
        sched._lock_handle.close()
    assert sched.seconds_to_next_tick(datetime(2026, 10, 7, 12, 0, 30)) == 31
    assert sched.seconds_to_next_tick(datetime(2026, 10, 7, 12, 0, 59, 500000)) == 1.5


# --------------------------------------------------------------------------- транспорт multipart

def test_api_call_files_multipart_and_connect_retry():
    import requests
    import core.open_check_telegram as oct_
    calls = []

    class Resp:
        def json(self):
            return {'ok': True, 'result': {'message_id': 1}}

    attempts = {'n': 0}

    def fake_post(url, data=None, files=None, timeout=None, **kw):
        attempts['n'] += 1
        calls.append({'url': url, 'data': data, 'files': files, 'timeout': timeout, 'json': kw.get('json')})
        if attempts['n'] == 1:
            raise requests.exceptions.ConnectTimeout('ТСПУ')
        return Resp()

    saved_dead = oct_._primary_dead_until
    with _patch(oct_.requests, 'post', fake_post):
        oct_._primary_dead_until = 0.0
        try:
            data = oct_.api_call_files('sendPhoto', {'chat_id': '@kult_vo', 'caption': 'Подпись'},
                                       [('photo', 'cp_1.png', b'PNGDATA', 'image/png')], token='TKN')
        finally:
            oct_._primary_dead_until = saved_dead
    assert data == {'ok': True, 'result': {'message_id': 1}}
    assert len(calls) == 2                                                  # обрыв соединения — повтор
    assert calls[1]['url'].endswith('/botTKN/sendPhoto') and calls[1]['json'] is None
    assert calls[1]['data'] == {'chat_id': '@kult_vo', 'caption': 'Подпись'}
    assert calls[1]['files'] == [('photo', ('cp_1.png', b'PNGDATA', 'image/png'))]
    assert calls[1]['timeout'] == (oct_.CONNECT_TIMEOUT, oct_.FILES_READ_TIMEOUT)
    # основной путь мёртв — запасной IP с тем же телом
    via_ip = []
    with _patch(oct_, '_iter_candidate_ips', lambda: iter(['149.154.167.220'])), \
            _patch(oct_, '_post_files_via_ip', lambda ip, method, token, fields, files, timeout: via_ip.append(
                (ip, method, fields, files)) or {'ok': True, 'result': {'message_id': 2}}):
        saved_ip = oct_._working_ip
        oct_._primary_dead_until = 10 ** 12
        try:
            data = oct_.api_call_files('sendVideo', {'chat_id': '1'}, [('video', 'a.mp4', b'V', 'video/mp4')],
                                       token='TKN')
        finally:
            oct_._primary_dead_until = saved_dead
            oct_._working_ip = saved_ip
    assert data['result']['message_id'] == 2
    assert via_ip == [('149.154.167.220', 'sendVideo', {'chat_id': '1'}, [('video', 'a.mp4', b'V', 'video/mp4')])]
    assert oct_._files_arg([('f', 'n', b'x', 'm')]) == [('f', ('n', b'x', 'm'))]


def test_py310_fstrings():
    """CI гоняет 3.10: внутри f-строки нельзя повторять её кавычку, ставить \\ и комментарий."""
    import tokenize
    start = getattr(tokenize, 'FSTRING_START', None)
    if start is None:
        return
    for rel in ('core/content_publisher.py', 'core/content_publisher_scheduler.py', 'core/content_channels.py',
                'core/content_plan.py', 'routes/content_plan.py', 'core/open_check_telegram.py'):
        src = open(os.path.join(REPO, rel), encoding='utf-8').read()
        stack = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == start:
                quote = tok.string[len(tok.string.rstrip('\'"')):]
                assert not (stack and quote[0] in stack[-1]), rel + ':' + str(tok.start[0])
                stack.append(quote)
            elif tok.type == tokenize.FSTRING_END:
                stack.pop()
            elif stack and tok.type == tokenize.STRING:
                body = tok.string.lstrip('rRbBuU')
                assert body[0] not in stack[-1] and '\\' not in tok.string, rel + ':' + str(tok.start[0])
            elif stack:
                assert tok.type != tokenize.COMMENT, rel + ':' + str(tok.start[0])


# --------------------------------------------------------------------------- проверка 2026-09-28
# Регрессии по 13 пунктам независимой проверки автоотправки (по тесту на пункт; номер
# пункта — в докстроке теста).

class HookTelegram(FakeTelegram):
    """FakeTelegram, который перед ответом на send* вызывает hook(method, chat):
    «владелец нажал кнопку, пока идёт отправка»."""

    def __init__(self, hook=None):
        super().__init__()
        self.hook = hook

    def _answer(self, method, chat, count):
        if self.hook and method.startswith('send'):
            self.hook(method, chat)
        return super()._answer(method, chat, count)


def _per_chat(tg):
    return Counter(str(c['payload'].get('chat_id')) for c in tg.sends())


def test_safe_resend_never_resends_what_may_have_arrived():
    """П. 1 (HIGH). После ReadTimeout, обрыва посреди соединения или ответа не-JSON запрос
    мог дойти: с safe_resend=True транспорт НЕ шлёт его запасным путём (было: 2–4 копии
    поста в канале), а возвращает None и outcome 'unknown'. Запасной путь — только если
    ошибка доказывает «не ушло» (ConnectTimeout, NewConnectionError, SSLError); все пути
    отказали — 'not_sent'. Без ключа (прежние вызовы) — как раньше."""
    import requests
    import urllib3
    import core.open_check_telegram as oct_
    primary, fallback = [], []

    class NotJson:
        def json(self):
            raise ValueError('<html>502 Bad Gateway</html>')

    def refused():
        cause = urllib3.exceptions.NewConnectionError(None, 'Failed to establish a new connection: refused')
        return requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(None, '/bot', reason=cause))

    def call(kind, primary_error=None, primary_resp=None, fallback_errors=(), **kw):
        primary.clear()
        fallback.clear()
        errors = list(fallback_errors)

        def fake_post(url, **_kw):
            primary.append(url)
            if primary_error is not None:
                raise primary_error
            return primary_resp

        def via_ip(ip, *_args):
            fallback.append(ip)
            if errors:
                raise errors.pop(0)
            return {'ok': True, 'result': {'message_id': 8}}

        outcome = []
        saved = (oct_._primary_dead_until, oct_._working_ip)
        oct_._primary_dead_until, oct_._working_ip = 0.0, None
        try:
            with _patch(oct_.requests, 'post', fake_post), \
                    _patch(oct_, '_iter_candidate_ips', lambda: iter(['149.154.167.220', '149.154.166.110'])), \
                    _patch(oct_, '_post_via_ip', via_ip), _patch(oct_, '_post_files_via_ip', via_ip):
                if kind == 'files':
                    result = oct_.api_call_files('sendPhoto', {'chat_id': '@kult_vo'},
                                                 [('photo', 'a.png', b'P', 'image/png')], token='TKN',
                                                 outcome=outcome, **kw)
                else:
                    result = oct_.api_call('sendMessage', {'chat_id': '@kult_vo', 'text': 'Пост'}, token='TKN',
                                           outcome=outcome, **kw)
        finally:
            oct_._primary_dead_until, oct_._working_ip = saved
        return result, outcome

    read_timeout = requests.exceptions.ReadTimeout('Read timed out. (read timeout=20)')
    for kind in ('json', 'files'):
        result, outcome = call(kind, primary_error=read_timeout, safe_resend=True)
        assert (result, outcome, len(primary), fallback) == (None, ['unknown'], 1, []), kind   # одна доставка
    for error in (requests.exceptions.ConnectionError(ConnectionResetError('Connection aborted')),
                  requests.exceptions.ChunkedEncodingError('обрыв посреди ответа')):
        result, outcome = call('json', primary_error=error, safe_resend=True)
        assert (result, outcome, fallback) == (None, ['unknown'], []), repr(error)
    result, outcome = call('files', primary_resp=NotJson(), safe_resend=True)          # страница 5xx прокси
    assert (result, outcome, fallback) == (None, ['unknown'], [])
    # запрос точно не ушёл — запасной путь
    for error in (requests.exceptions.ConnectTimeout('ТСПУ'), refused(), requests.exceptions.SSLError('handshake')):
        result, outcome = call('json', primary_error=error, safe_resend=True)
        assert result['result']['message_id'] == 8 and fallback == ['149.154.167.220'] and outcome == [], repr(error)
    # на запасном адресе ответа нет — дальше не идём
    result, outcome = call('files', primary_error=requests.exceptions.ConnectTimeout('x'),
                           fallback_errors=[read_timeout], safe_resend=True)
    assert (result, outcome, fallback) == (None, ['unknown'], ['149.154.167.220'])
    # все пути отказали до отправки — 'not_sent' (повтор безопасен)
    connect = requests.exceptions.ConnectTimeout('x')
    result, outcome = call('json', primary_error=connect, fallback_errors=[connect] * 4, safe_resend=True)
    assert result is None and outcome == ['not_sent'] and set(fallback) == {'149.154.167.220', '149.154.166.110'}
    # без ключа — прежнее поведение (open-check, таплист-бот): любой сбой -> запасной путь
    result, outcome = call('json', primary_error=read_timeout)
    assert result['result']['message_id'] == 8 and fallback == ['149.154.167.220'] and outcome == []
    # транспорт публикаций передаёт ключ для send* и сообщает last_outcome
    seen = []

    def fake_api_call(method, payload=None, timeout=8, *, token=None, safe_resend=False, outcome=None):
        seen.append((method, safe_resend))
        outcome.append('unknown')
        return None

    def fake_files(method, fields=None, files=None, timeout=0, *, token=None, safe_resend=False, outcome=None):
        seen.append((method, safe_resend))
        outcome.append('not_sent')
        return None

    with _patch(oct_, 'api_call', fake_api_call), _patch(oct_, 'api_call_files', fake_files):
        transport = pub.TelegramTransport('TKN')
        assert transport.call('sendMessage', {'chat_id': 1}) is None and transport.last_outcome == 'unknown'
        assert pub.classify(None, transport)[0] == 'network'
        transport.call('getChat', {'chat_id': '@kult_vo'})
        assert transport.upload('sendPhoto', {'chat_id': 1}, []) is None and transport.last_outcome == 'not_sent'
        assert pub.classify(None, transport) == ('not_sent', None, pub.NOT_SENT_TEXT)
    assert seen == [('sendMessage', True), ('getChat', False), ('sendPhoto', True)]
    # сквозь отправщик: ReadTimeout на основном пути — пост в канале один, ошибка «статус неизвестен»
    env = Env()
    env.enable()
    _mid, pid = _post(env)
    env.at(12, 0)

    def post_timeout(url, **_kw):
        primary.append(url)
        raise read_timeout

    primary.clear()
    fallback.clear()
    saved = (oct_._primary_dead_until, oct_._working_ip)
    oct_._primary_dead_until = 0.0
    try:
        with _patch(oct_.requests, 'post', post_timeout), \
                _patch(oct_, '_iter_candidate_ips', lambda: iter(['149.154.167.220'])), \
                _patch(oct_, '_post_via_ip', lambda ip, *a: fallback.append(ip) or {'ok': True, 'result': {}}):
            env.run(transport=pub.TelegramTransport('TKN'))
    finally:
        oct_._primary_dead_until, oct_._working_ip = saved
    assert len(primary) == 1 and fallback == []
    assert env.raw(pid)['status'] == 'failed' and env.raw(pid)['failed_error'] == pub.NO_ANSWER_TEXT


def test_edits_during_sending_get_409_and_lost_attempt_is_logged():
    """П. 2 (HIGH). Правка текста, файлов, сдвиг материала и правка размещения во время
    отправки — 409 (было: размещение уходило в черновик, delivery стирался, после
    повторного утверждения гости получали рассылку дважды; фото во время поста — пост в
    канале, а в плане черновик). Попытку всё же потеряли — строка в журнал материала."""
    env = Env()
    env.enable(bars=(), bot=True)
    tg = HookTelegram()
    subs = FakeSubscribers(list(range(1, 61)))
    ok, new_file = env.store.media.save(PNG + b'new', '2026-10-07')
    assert ok
    attempts = []
    with _subscribers(subs):
        material = env.material(title='Октоберфест', base_text='Скидка 20% в субботу')
        mid = material['id']
        photo = env.photo(mid)
        pid = env.placement(mid, channel='bot', audience={'segment': 'bot_all'})
        env.approve(pid)

        def hook(method, chat):
            if str(chat) != '30' or attempts:
                return
            for name, change in (
                    ('update_material', lambda: env.store.update_material(mid, {'base_text': 'Скидка 25%'}, USER)),
                    ('add_media', lambda: env.store.add_media(mid, new_file, len(PNG), 'new.png', USER)),
                    ('remove_media', lambda: env.store.remove_media(mid, photo, USER)),
                    ('shift', lambda: env.store.shift(mid, 1, USER)),
                    ('update_placement', lambda: env.store.update_placement(pid, {'time': '13:00'}, USER))):
                try:
                    change()
                    attempts.append((name, 'принято'))
                except cp.ContentPlanConflict as e:
                    attempts.append((name, str(e)))

        tg.hook = hook
        env.at(12, 0)
        report = env.run(transport=tg)
    assert attempts == [(name, cp.SENDING_CONFLICT) for name in
                        ('update_material', 'add_media', 'remove_media', 'shift', 'update_placement')]
    assert report['details'][0]['text'] == 'дошло 60 из 60'
    assert max(_per_chat(tg).values()) == 1 and len(tg.sends()) == 60      # никому дважды
    raw_material = env.store.get_material_raw(mid)
    assert raw_material['base_text'] == 'Скидка 20% в субботу' and [m['name'] for m in raw_material['media']] == [photo]
    assert env.raw(pid)['status'] == 'published' and env.raw(pid)['date'] == '2026-10-07'
    # попытку потеряли (размещение изменили в обход защиты) — итог в журнал
    env2 = Env()
    env2.enable()
    tg2 = HookTelegram()
    mid2, pid2 = _post(env2)
    tg2.hook = lambda method, chat: env2.set(pid2, delivery=dict(env2.raw(pid2)['delivery'], attempt_id='чужая'))
    env2.at(12, 0)
    env2.run(transport=tg2)
    entry = env2.store.log_for(mid2)[0]
    assert len(tg2.sends()) == 1 and entry['action'] == 'auto_failed' and entry['by'] == pub.PUBLISHED_BY
    assert entry['text'].startswith('Пост вышел в канале @kult_bolshoy (сообщение 501), но размещение изменили')
    env3 = Env()
    env3.enable(bars=(), bot=True)
    tg3 = HookTelegram()
    with _subscribers(FakeSubscribers(list(range(1, 61)))):
        mid3, pid3 = _bot_post(env3)
        tg3.hook = lambda method, chat: str(chat) == '30' and env3.set(
            pid3, delivery=dict(env3.raw(pid3)['delivery'], attempt_id='чужая'))
        env3.at(12, 0)
        env3.run(transport=tg3)
    assert len(tg3.sends()) == 50                                         # после потери — ни одной пачки
    assert 'Рассылка остановлена: размещение изменили; дошло 50' in env3.store.log_for(mid3)[0]['text']


def test_instagram_reminder_counts_late_and_since_from_post_time():
    """П. 3. «Опоздало» и «раньше подключения» считаются от времени ПОСТА, а не
    напоминания: пост на 16:00, утверждённый в 11:00 при «напоминать за 720 минут»
    (напоминание — 04:00), раньше оставался без напоминания; теперь оно уходит сразу,
    один раз. Так же — пост на 12:00, утверждённый в 11:00 при «за 180 минут»."""
    env = Env()
    env.enable(bars=(), instagram_chat='670033096', minutes=720)
    _mid, pid = _instagram(env, time='16:00')
    env.at(11, 1)
    report = env.run()
    assert report['sent'] == 1 and report['details'][0]['result'] == 'reminded'
    delivery = env.raw(pid)['delivery']
    assert delivery['state'] == 'reminded' and delivery['reminded_for'] == '2026-10-07T16:00'
    env.at(11, 2)
    assert env.run()['details'] == [] and len(env.tg.sends()) == 3          # один раз
    env2 = Env(datetime(2026, 10, 7, 8, 0))
    env2.enable(bars=(), instagram_chat='670033096', minutes=180)
    env2.at(11, 0)
    _mid, pid2 = _instagram(env2, time='12:00')                            # напоминание — 09:00, уже прошло
    assert env2.run()['details'][0]['result'] == 'reminded'
    # а сам пост давно прошёл (больше 2 часов) — напоминание не шлётся
    env3 = Env(datetime(2026, 10, 7, 8, 0))
    env3.enable(bars=(), instagram_chat='670033096', minutes=30)
    _mid, late = _instagram(env3, time='08:30')
    env3.at(10, 30)
    assert env3.run()['skipped'] == 1 and env3.tg.sends() == []
    assert env3.raw(late)['delivery']['state'] == 'reminder_late'


def test_instagram_reschedule_rearms_reminder():
    """П. 4. Пост Instagram перенесли после напоминания — напоминание взводится заново
    для нового времени (delivery.reminded_for — время поста, для которого оно было).
    Было: reminded навсегда, в новый день напоминания нет, а подпись «Напоминание
    отправлено» вводит в заблуждение."""
    env = Env(datetime(2026, 10, 7, 9, 0))
    env.enable(bars=(), instagram_chat='670033096')
    mid, pid = _instagram(env, time='16:00')
    env.at(16, 0)
    env.run()
    assert len(env.tg.sends()) == 3 and env.raw(pid)['delivery']['reminded_for'] == '2026-10-07T16:00'
    env.at(16, 30)
    env.store.update_placement(pid, {'date': '2026-10-08', 'time': '12:00'}, USER)
    assert env.raw(pid)['status'] == 'approved' and not cp.reminder_is_current(env.raw(pid))
    assert env.view(pid)['display_label'] is None or 'Напоминание' not in env.view(pid)['display_label']
    env.at(12, 0, day=8)
    report = env.run()
    assert report['details'][0]['result'] == 'reminded' and len(env.tg.sends()) == 6
    assert env.raw(pid)['delivery']['reminded_for'] == '2026-10-08T12:00'
    assert env.view(pid)['display_label'] == 'Напоминание отправлено'
    assert env.run()['details'] == []                                       # для нового времени — один раз
    # сдвиг материала на день — тоже новое время поста
    env.at(13, 0, day=8)
    env.store.shift(mid, 1, USER)
    assert env.raw(pid)['date'] == '2026-10-09' and not cp.reminder_is_current(env.raw(pid))


def test_check_blip_keeps_channel_connected():
    """П. 5. Сбой связи при «Проверить» (нет ответа, 429, 5xx) не сохраняется:
    saved=false, прежняя проверка и момент подключения остаются (было: рабочий канал
    выключался, а после повторной проверки connected_since = сейчас, и пост, время
    которого уже было, «раньше подключения» не уходил никогда). Повторная успешная
    проверка того же адреса момент подключения не сдвигает."""
    env = Env()
    env.enable()                                                            # 11:00: проверен, подключён
    _mid, pid = _post(env, time='12:30')
    before = env.channels.load()['telegram']['bolshoy']
    assert before['connected_since'] == '2026-10-07T11:00'
    env.at(12, 0)
    for method, answer in (('getMe', None),
                           ('getChat', {'ok': False, 'error_code': 502, 'description': 'Bad Gateway'}),
                           ('getChatMember', {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 5}})):
        env.tg.respond(method, answer)
        result = pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)
        assert result['saved'] is False and result['check']['transient'] is True, method
        assert result['check']['can_post'] is False and result['check']['error'], method
    after = env.channels.load()['telegram']['bolshoy']
    assert after['check'] == before['check'] and after['connected_since'] == '2026-10-07T11:00'
    assert pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)['check']['can_post']
    assert env.channels.load()['telegram']['bolshoy']['connected_since'] == '2026-10-07T11:00'   # не сдвинут
    with _client(env) as c:
        env.tg.respond('getMe', None)
        body = c.post('/api/content-plan/channels/check', json={'bar': 'bolshoy'}).get_json()
        assert body['saved'] is False and body['check']['error'] == pub.CHECK_NO_ANSWER_TEXT
        assert body['channels']['telegram']['bolshoy']['check']['can_post'] is True
    env.tg.calls.clear()
    env.at(12, 30)
    assert env.run()['sent'] == 1 and env.raw(pid)['status'] == 'published'   # пост ушёл вовремя


def test_running_mailing_can_be_stopped():
    """П. 6. Идущую рассылку останавливают выключатели (настройки перечитываются перед
    каждой пачкой), пауза и отмена (флаг stop_requested; отвечают «остановится после
    текущей пачки», а не 409). Не получившие — в failed_to: «Повторить неудавшимся»
    доведёт позже; получившим повторно не уходит. Было: выключили всё на 11-м из 200 —
    ушло ещё 189."""
    for patch, reason in (({'enabled': False}, 'отправка публикаций выключена'),
                          ({'bot': {'enabled': False}}, 'рассылки гостям выключены')):
        env = Env()
        env.enable(bars=(), bot=True)
        tg = HookTelegram()
        tg.hook = lambda method, chat, env=env, patch=patch: str(chat) == '10' and env.channels.update(patch, USER)
        with _subscribers(FakeSubscribers(list(range(1, 61)))):
            mid, pid = _bot_post(env)
            env.at(12, 0)
            report = env.run(transport=tg)
            assert len(tg.sends()) == 25, reason                            # дошли до конца пачки — и стоп
            raw = env.raw(pid)
            assert raw['status'] == 'published' and raw['delivery']['state'] == 'partial', reason
            assert raw['delivery']['error'] == f'Рассылка остановлена ({reason}): дошло 25 из 60'
            assert len(raw['delivery']['failed_to']) == 35 and raw['delivery']['stats']['failed'] == 35
            assert report['details'][0]['text'] == f'остановлена ({reason}): дошло 25 из 60'
            env.channels.update({'enabled': True, 'bot': {'enabled': True}}, USER)
            env.store.placement_action(pid, 'retry_failed', USER)
            env.at(12, 1)
            env.run(transport=tg)
        assert len(tg.sends()) == 60 and max(_per_chat(tg).values()) == 1, reason
        assert env.raw(pid)['delivery']['state'] == 'sent'
    # пауза во время рассылки: флаг, подпись, остановка после текущей пачки
    env = Env()
    env.enable(bars=(), bot=True)
    tg = HookTelegram()
    answers = []
    with _subscribers(FakeSubscribers(list(range(1, 61)))):
        mid, pid = _bot_post(env)
        tg.hook = lambda method, chat: str(chat) == '30' and answers.append(
            env.store.placement_action(pid, 'pause', USER))
        env.at(12, 0)
        env.run(transport=tg)
    view = next(p for p in answers[0]['placements'] if p['id'] == pid)
    assert view['delivery']['stop_requested']['action'] == 'pause'
    assert view['display_label'] == 'Рассылка идёт: дошло 25 из 60 · остановится после текущей пачки'
    assert len(tg.sends()) == 50                                          # пачка 26–50 дошла, дальше — нет
    raw = env.raw(pid)
    assert raw['status'] == 'published' and raw['delivery'].get('stop_requested') is None
    assert raw['delivery']['error'] == 'Рассылка остановлена (поставлена на паузу): дошло 50 из 60'
    assert 'pause' in env.log(mid)
    # маршрут: ответ с notice
    env2 = Env()
    env2.enable(bars=(), bot=True)
    _mid2, pid2 = _bot_post(env2)
    env2.at(12, 1)
    env2.set(pid2, delivery={'state': 'sending', 'attempt_id': 'a', 'started_at': '2026-10-07T12:00',
                             'heartbeat_at': '2026-10-07T12:01', 'recipients': ['1', '2'], 'sent_to': ['1']})
    with _client(env2) as c:
        body = c.post(f'/api/content-plan/placements/{pid2}/action', json={'action': 'cancel'}).get_json()
    assert body['notice'].startswith('Рассылка остановится после текущей пачки')
    assert env2.raw(pid2)['delivery']['stop_requested']['action'] == 'cancel'
    # рассылка ждёт продолжения (кому-то уже дошло) — отмена останавливает сразу
    env3 = Env()
    env3.enable(bars=(), bot=True)
    with _subscribers(FakeSubscribers(list(range(1, 61)))), _patch(pub, 'MAILING_BUDGET_SEC', 1):
        mid3, pid3 = _bot_post(env3)
        env3.at(12, 0)
        env3.run()
        first = len(env3.tg.sends())
        assert 0 < first < 60 and env3.raw(pid3)['delivery']['continuation'] is True
        env3.store.placement_action(pid3, 'cancel', USER)
        raw = env3.raw(pid3)
        assert raw['status'] == 'published' and raw['delivery']['state'] == 'partial'
        assert raw['delivery']['error'] == f'Рассылка остановлена (отменена): дошло {first} из 60'
        env3.at(12, 1)
        env3.run()
    assert len(env3.tg.sends()) == first                                    # больше не шлёт
    # выключили и включили снова между проходами (даже в ту же минуту) — стоп
    env4 = Env()
    env4.enable(bars=(), bot=True)
    with _subscribers(FakeSubscribers(list(range(1, 61)))), _patch(pub, 'MAILING_BUDGET_SEC', 1):
        _mid4, pid4 = _bot_post(env4)
        env4.at(12, 0)
        env4.run()
        first = len(env4.tg.sends())
        env4.channels.update({'bot': {'enabled': False}}, USER)
        env4.channels.update({'bot': {'enabled': True}}, USER)
        env4.at(12, 1)
        env4.run()
    assert len(env4.tg.sends()) == first
    assert env4.raw(pid4)['delivery']['error'] == (f'Рассылка остановлена (отправку выключали во время '
                                                   f'рассылки): дошло {first} из 60')


def test_admin_only_routes():
    """П. 7. Всё, что может выпустить публикацию наружу, — только администратор: PUT
    каналов, проверка, тест, «Отправить сейчас», утверждение, retry / retry_failed /
    resume размещения, снятие паузы по бару. Остальным — 403 admin_required и ничего не
    меняется. Чтение (каналы, аудитория, zip) и остановка (пауза) — всем."""
    env = Env()
    env.enable()
    mid, approved = _post(env, time='18:00')
    draft = env.placement(env.material(base_text='Черновик')['id'], time='18:00')
    _m, failed = _post(env, time='19:00')
    env.set(failed, status='failed', failed_error='x')
    _m, paused = _post(env, time='20:00')
    env.store.placement_action(paused, 'pause', USER)
    _m, mailing = _bot_post(env, time='18:00')
    env.set(mailing, status='published', delivery={'state': 'partial', 'recipients': ['1', '2'], 'sent_to': ['1'],
                                                   'failed_to': ['2']})
    forbidden = (
        ('put', '/api/content-plan/channels', {'enabled': False}),
        ('post', '/api/content-plan/channels/check', {'bar': 'bolshoy'}),
        ('post', '/api/content-plan/channels/test', {'bar': 'bolshoy'}),
        ('post', '/api/content-plan/publish-now', {'placement_id': approved}),
        ('post', '/api/content-plan/approve', {'placement_ids': [draft]}),
        ('post', f'/api/content-plan/placements/{failed}/action', {'action': 'retry'}),
        ('post', f'/api/content-plan/placements/{mailing}/action', {'action': 'retry_failed'}),
        ('post', f'/api/content-plan/placements/{paused}/action', {'action': 'resume'}),
        ('post', '/api/content-plan/bulk-pause', {'bar': 'all', 'action': 'resume'}),
    )
    plan_before = open(env.store.data_file, encoding='utf-8').read()
    channels_before = open(env.channels.data_file, encoding='utf-8').read()
    with _client(env, user=BARTENDER) as c:
        for method, url, body in forbidden:
            r = getattr(c, method)(url, json=body)
            assert r.status_code == 403, (url, body, r.status_code)
            assert r.get_json()['code'] == 'admin_required' and r.get_json()['error'].startswith(
                'Только администратор может'), url
        assert open(env.store.data_file, encoding='utf-8').read() == plan_before
        assert open(env.channels.data_file, encoding='utf-8').read() == channels_before
        assert env.tg.calls == []
        assert c.get('/api/content-plan/channels').status_code == 200
        assert c.get('/api/content-plan/audience?segment=bot_all').status_code == 200
        assert c.get(f'/api/content-plan/materials/{mid}/download').status_code == 200
        assert c.post(f'/api/content-plan/placements/{approved}/action', json={'action': 'pause'}).status_code == 200
        assert c.post('/api/content-plan/bulk-pause', json={'bar': 'all', 'action': 'pause'}).status_code == 200
    with _client(env, user=USER) as c:                                     # администратор проходит проверку
        for method, url, body in forbidden:
            assert getattr(c, method)(url, json=body).status_code != 403, url


def test_mailing_budget_continuation_and_posts_first():
    """П. 8. Большая рассылка не держит остальные посты: в проходе сначала посты каналов
    и напоминания, рассылки — с бюджетом времени (MAILING_BUDGET_SEC); не уложилась —
    прогресс сохранён, продолжение в следующем проходе без дублей (по sent_to). 429 в
    рассылке не ждётся — продолжение в следующем проходе."""
    env = Env()
    env.enable(bot=True)
    with _subscribers(FakeSubscribers(list(range(1, 81)))), _patch(pub, 'MAILING_BUDGET_SEC', 1):
        bot_mid, mailing = _bot_post(env, time='12:00')
        _m, post = _post(env, time='12:00')
        _m, later = _post(env, time='12:01')
        env.at(12, 0)
        report = env.run()
        first = env.tg.sends()
        assert first[0]['payload']['chat_id'] == '@kult_bolshoy'            # пост канала — первым
        raw = env.raw(mailing)
        assert raw['status'] == 'approved' and raw['delivery']['state'] == 'queued'
        assert raw['delivery']['continuation'] is True
        sent = raw['delivery']['stats']['sent']
        assert 0 < sent < 80 and len(first) == sent + 1
        assert next(d for d in report['details'] if d['placement_id'] == mailing)['result'] == 'queued'
        assert env.view(mailing)['display_label'] == (f'Рассылка идёт: дошло {sent} из 80, '
                                                      'продолжится в течение минуты')
        assert 'delivery_progress' in env.log(bot_mid)
        env.at(12, 1)
        env.run()
        second = env.tg.sends()[len(first):]
        assert second[0]['payload']['chat_id'] == '@kult_bolshoy'           # пост 12:01 — вовремя, до рассылки
        assert env.raw(later)['published_at'] == '2026-10-07T12:01'
        for minute in range(2, 10):
            if env.raw(mailing)['status'] == 'published':
                break
            env.at(12, minute)
            env.run()
    raw = env.raw(mailing)
    assert raw['status'] == 'published' and raw['delivery']['state'] == 'sent'
    assert raw['delivery']['stats']['sent'] == 80 and raw['delivery'].get('continuation') is None
    counts = _per_chat(env.tg)
    assert counts['@kult_bolshoy'] == 2 and all(counts[str(i)] == 1 for i in range(1, 81))   # без дублей
    assert env.raw(post)['published_at'] == '2026-10-07T12:00'
    # 429 в рассылке: не ждём (поток не держим), продолжаем в следующем проходе
    env2 = Env()
    env2.enable(bars=(), bot=True)
    hits = []

    def busy():
        hits.append(1)
        if len(hits) == 1:
            return {'ok': False, 'error_code': 429, 'description': 'Too Many Requests', 'parameters': {'retry_after': 30}}
        return {'ok': True, 'result': {'message_id': 9}}

    env2.tg.per_chat['5'] = busy
    with _subscribers(FakeSubscribers(list(range(1, 11)))):
        _m, mailing2 = _bot_post(env2)
        env2.at(12, 0)
        env2.run()
        assert 30 not in env2.sleeps
        raw = env2.raw(mailing2)
        assert raw['delivery']['continuation'] is True and raw['delivery']['stats']['sent'] == 4
        env2.at(12, 1)
        env2.run()
    counts = _per_chat(env2.tg)
    assert counts['5'] == 2 and all(counts[str(i)] == 1 for i in range(1, 11) if i != 5)
    assert env2.raw(mailing2)['status'] == 'published' and env2.raw(mailing2)['delivery']['stats']['sent'] == 10


def test_scheduler_does_not_count_own_long_send_as_stale():
    """П. 9 и 10. «Отправить сейчас» только ставит в очередь (поток в веб-воркере убран),
    отправляет планировщик — один на сервер; свою долгую отправку он зависшей не считает
    (_ACTIVE_ATTEMPTS). Было: загрузка дольше 10 минут признавалась зависшей, «Повторить»
    давало дубль."""
    assert not hasattr(rcp, '_spawn')
    env = Env()
    env.enable()
    _mid, pid = _post(env)
    nested = []
    tg = HookTelegram()

    def slow_upload(method, chat):
        if nested:
            return
        env.clock.moment = datetime(2026, 10, 7, 12, 15)                   # загрузка идёт 15 минут
        nested.append(env.run(transport=tg))                               # следующий проход того же процесса

    tg.hook = slow_upload
    env.at(12, 0)
    report = env.run(transport=tg)
    assert nested[0]['details'] == [] and report['sent'] == 1
    assert env.raw(pid)['status'] == 'published' and len(tg.sends()) == 1
    assert pub._ACTIVE_ATTEMPTS == set()                                    # попытка снята после отправки
    # процесс, который умер посреди отправки (попытки нет в _ACTIVE_ATTEMPTS), — по-прежнему «зависла»
    _mid, dead = _post(env, time='12:15')
    env.set(dead, delivery={'state': 'sending', 'attempt_id': 'dead', 'started_at': '2026-10-07T12:15',
                            'heartbeat_at': '2026-10-07T12:15'})
    env.at(12, 25)
    assert env.run()['details'][0]['result'] == 'stale'


def test_length_counts_utf16_units():
    """П. 12. Длина для Telegram и бота — в единицах UTF-16 (символ вне основной
    плоскости, например эмодзи, — 2): в проверке готовности, в render_live и в
    отправителе. Instagram — в символах. Было: 4000 букв + 60 эмодзи проходили проверку
    (len 4060), а Telegram отклонял (4120)."""
    wide = '\U00020000'                                                     # вне основной плоскости, 2 единицы
    assert cp.text_units('a' + wide, 'telegram') == 3 and cp.text_units('a' + wide, 'bot') == 3
    assert cp.text_units('a' + wide, 'instagram') == 2 and cp.text_units(None) == 0
    env = Env()
    material = env.material(base_text='x' * 4000 + wide * 60)
    tg_pid = env.placement(material['id'])
    ig_pid = env.placement(env.material(base_text=wide * 2150)['id'], channel='instagram')
    assert 'text_too_long' in [m['code'] for m in env.view(tg_pid)['missing']]
    assert 'text_too_long' not in [m['code'] for m in env.view(ig_pid)['missing']]
    live = cp.render_live(None, None, 'x' * 4000 + wide * 60, channel='telegram')
    assert live['length'] == 4120 and 'text_too_long' in [p['code'] for p in live['problems']]
    assert 'эмодзи считается за 2 знака' in live['limit_note']
    assert cp.render_live(None, None, wide * 2150, channel='instagram')['length'] == 2150
    # отправитель: подпись к фото 1000 букв + 20 широких символов = 1040 > 1024
    env.enable()
    name = env.photo(material['id'])
    env.set(tg_pid, status='approved', approved_snapshot={'text': 'x' * 1000 + wide * 20, 'media': [name]})
    env.at(12, 0)
    assert env.run()['failed'] == 1 and env.tg.sends() == []
    assert env.raw(tg_pid)['failed_error'] == 'Публикация остановлена: текст длиннее 1024 знаков'


def test_address_roles_private_chat_and_reminder_conflict():
    """П. 13. Адреса по роли: канал бара — только канал или группа (личный чат
    отклоняется при проверке и не считается «можно публиковать»; положительный id —
    400); чат напоминаний Instagram не может совпадать с каналом бара (иначе служебная
    заметка уйдёт подписчикам канала): правка — 400, совпадение, появившееся после
    проверки канала, — площадка не подключена, отправщик не шлёт."""
    env = Env()
    env.channels.update({'enabled': True, 'telegram': {'bolshoy': {'chat': '@kult_owner'}}}, USER)
    env.tg.respond('getChat', {'ok': True, 'result': {'id': 670033096, 'type': 'private', 'first_name': 'Анна',
                                                      'username': 'kult_owner'}})
    result = pub.check_channel('bolshoy', USER, transport=env.tg, channels=env.channels)
    check = result['check']
    assert result['saved'] and check['ok'] and check['can_post'] is False and check['error'] == pub.PRIVATE_CHAT_TEXT
    assert 'getChatMember' not in [c['method'] for c in env.tg.calls]
    assert cc.telegram_bar_reason(env.channels.load()['telegram']['bolshoy']) == pub.PRIVATE_CHAT_TEXT
    _mid, pid = _post(env)
    env.tg.calls.clear()
    env.at(12, 0)
    report = env.run()
    assert report['skipped'] == 1 and env.tg.sends() == [] and env.raw(pid)['status'] == 'approved'
    try:
        env.channels.update({'telegram': {'bolshoy': {'chat': '670033096'}}}, USER)
        raise AssertionError('положительный id канала бара — ошибка')
    except ValueError as e:
        assert 'личный чат' in str(e)
    with _client(env) as c:
        r = c.put('/api/content-plan/channels', json={'telegram': {'ligovskiy': {'chat': 670033096}}})
        assert r.status_code == 400
    # чат напоминаний = канал бара: по адресу, по @имени в любом регистре, по id из проверки
    env2 = Env()
    env2.enable()                                                          # @kult_bolshoy, id -1001234
    for chat in ('@KULT_BOLSHOY', 't.me/kult_bolshoy', '-1001234'):
        try:
            env2.channels.update({'instagram': {'reminder_chat': chat}}, USER)
            raise AssertionError(chat)
        except ValueError as e:
            assert 'совпадает с каналом бара' in str(e), chat
    assert not env2.channels.load()['instagram']['reminder_chat']
    with _client(env2) as c:
        r = c.put('/api/content-plan/channels', json={'instagram': {'reminder_chat': '@kult_bolshoy'}})
        assert r.status_code == 400 and 'совпадает с каналом бара' in r.get_json()['error']
    # совпадение появилось после проверки канала (Telegram вернул тот же id)
    env3 = Env()
    env3.channels.update({'enabled': True, 'instagram': {'reminder_chat': '-1001234'},
                          'telegram': {'bolshoy': {'chat': '@kult_bolshoy'}}}, USER)
    pub.check_channel('bolshoy', USER, transport=env3.tg, channels=env3.channels)
    settings = env3.channels.load()
    assert cc.reminder_conflict(settings) == 'bolshoy'
    env3.channels.update({'instagram': {'reminder_minutes_before': 15}}, USER)   # прежнее совпадение правку не блокирует
    state = cc.delivery_state(settings, True, 0, guest_token_present=True)
    assert state['instagram']['connected'] is False
    assert state['instagram']['reason'].startswith('чат для напоминаний совпадает с каналом бара')
    _mid, ig = _instagram(env3)
    env3.tg.calls.clear()
    env3.at(12, 0)
    report = env3.run()
    assert report['skipped'] == 1 and env3.tg.sends() == []
    assert report['details'][0]['text'].startswith('Площадка не подключена: чат для напоминаний совпадает')
    # и сам отправитель напоминания не шлёт (совпадение появилось посреди прохода)
    run = pub._Run(env3.store, env3.channels, env3.channels.load(), env3.tg, env3.clock.moment)
    material, placement = pub._claim(run, ig, 'a1')
    pub._send(run, material, placement, 'a1', None, pub._new_report())
    assert env3.tg.sends() == [] and env3.raw(ig)['delivery']['state'] == 'reminder_failed'
    assert 'совпадает с каналом бара' in env3.raw(ig)['delivery']['error']


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
