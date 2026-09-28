"""
Эталонные вопросы к ИИ-агенту (tests/mcp_eval_questions.json, scripts/mcp_eval.py): формат файла
и сухой режим. Настоящий прогон (--run) тратит токены владельца и здесь не запускается.

Self-runnable: `py -3 tests/test_mcp_eval.py` (совместимо с pytest).

Что проверяется:
- файл вопросов: версия, по 5–8 вопросов на каждый из четырёх разделов, уникальные id,
  подстановки и путь к числу разбираются, допуск корректный;
- по настоящему реестру: ожидаемые инструменты есть, видны в коннекторе своего раздела и
  разрешены в режиме «Только чтение» (сообщение владельцу — нет), эталон — один из них,
  аргументы эталона проходят схему инструмента;
- сухой режим (по умолчанию): печатает план со всеми вопросами, не ходит в сеть и не
  запускает процессов; кривой файл — код 2 со списком ошибок;
- помощники: путь к числу, число из строки «ОТВЕТ», допуск, подстановки дат, разбор
  stream-json и команда claude -p (режим dontAsk, только коннектор, без сообщения владельцу).
"""

import importlib.util
import io
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

QUESTIONS = os.path.join(HERE, 'mcp_eval_questions.json')


def _script():
    spec = importlib.util.spec_from_file_location('mcp_eval_script', os.path.join(ROOT, 'scripts', 'mcp_eval.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = _script()


def test_questions_file_format():
    data = ev.load_questions(QUESTIONS)
    assert ev.validate(data) == [], ev.validate(data)
    per_domain = {}
    for q in data['questions']:
        per_domain[q['domain']] = per_domain.get(q['domain'], 0) + 1
    assert set(per_domain) == set(ev.DOMAINS), per_domain
    assert all(5 <= n <= 8 for n in per_domain.values()), per_domain


def test_questions_match_real_registry():
    from core.mcp import registry
    registry.use_modules(None)
    tools = {spec.name: spec for spec in registry.all_tools()}
    problems = ev.validate(ev.load_questions(QUESTIONS), tools)
    assert problems == [], problems


def test_validate_catches_broken_files():
    good = ev.load_questions(QUESTIONS)
    broken = json.loads(json.dumps(good))
    broken['questions'][0]['reference']['path'] = 'stats..materials'
    broken['questions'][1]['tolerance'] = {'abs': -1}
    broken['questions'][2]['id'] = broken['questions'][3]['id']
    broken['questions'][4]['question'] = 'Сколько за {next_year}?'
    broken['questions'][5]['reference']['tool'] = 'content_unknown'
    broken['questions'][6]['surprise'] = 1
    text = '\n'.join(ev.validate(broken))
    for needle in ('пустой шаг', 'tolerance', 'id повторяется', 'неизвестные подстановки',
                   'reference.tool должен быть среди expect_tools', 'лишние поля'):
        assert needle in text, (needle, text)
    few = dict(good, questions=[q for q in good['questions'] if q['domain'] != 'staff'][:])
    assert any('раздел staff' in p for p in ev.validate(few))
    from core.mcp import registry
    tools = {spec.name: spec for spec in registry.all_tools()}
    wrong = json.loads(json.dumps(good))
    stocks_q = next(q for q in wrong['questions'] if q['domain'] == 'stocks')
    stocks_q['expect_tools'].append('staff_auth_users')               # чужой раздел
    stocks_q['expect_tools'].append('common_notify_owner')            # не чтение
    stocks_q['reference']['args'] = {'bar_id': 'Лиговский'}
    text = '\n'.join(ev.validate(wrong, tools))
    assert 'не виден в коннекторе /mcp/stocks' in text and 'недоступен в режиме' in text
    assert 'reference.args не проходят схему' in text


def test_dry_run_prints_plan_without_network_or_processes():
    import subprocess
    import urllib.request
    calls = []
    saved = (subprocess.run, urllib.request.urlopen, ev.subprocess.run, ev.urllib.request.urlopen)

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('сухой режим не должен ходить в сеть и запускать процессы')
    subprocess.run = urllib.request.urlopen = forbidden
    ev.subprocess.run = ev.urllib.request.urlopen = forbidden
    try:
        out = io.StringIO()
        code = ev.main([], out=out)
        text = out.getvalue()
        assert code == 0, text
        assert 'Сухой режим' in text and '--run' in text
        for q in ev.load_questions(QUESTIONS)['questions']:
            assert '[' + q['id'] + ']' in text, q['id']
            assert '/mcp/' + q['domain'] + '/read' in text
        assert '{month}' not in text and '{today}' not in text, 'подстановки раскрыты'
        assert 'kmcp_' not in text
        one = io.StringIO()
        assert ev.main(['--domain', 'staff', '--ids', 'staff-taxi-rate'], out=one) == 0
        assert '[staff-taxi-rate]' in one.getvalue() and '[staff-locations]' not in one.getvalue()
        none = io.StringIO()
        assert ev.main(['--ids', 'нет-такого'], out=none) == 2
    finally:
        subprocess.run, urllib.request.urlopen, ev.subprocess.run, ev.urllib.request.urlopen = saved
    assert calls == []


def test_run_without_token_stops_before_any_call():
    import tempfile
    saved_env = os.environ.pop('KULTURA_MCP_TOKEN_TEST_ABSENT', None)
    out = io.StringIO()
    assert ev.main(['--run', '--token-env', 'KULTURA_MCP_TOKEN_TEST_ABSENT'], out=out) == 2
    assert 'Нет токена' in out.getvalue()
    if saved_env is not None:
        os.environ['KULTURA_MCP_TOKEN_TEST_ABSENT'] = saved_env
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, 'q.json')
        with open(bad, 'w', encoding='utf-8') as handle:
            json.dump({'version': 2, 'questions': []}, handle)
        out = io.StringIO()
        assert ev.main(['--questions', bad, '--no-registry'], out=out) == 2
        assert 'Файл вопросов с ошибками' in out.getvalue()


def test_extract_paths():
    data = {'stats': {'materials': 10}, 'orders': [{'x': 1}, {'x': 2}],
            'days': [{'date': '2026-09-27', 'daily_plan': 100.5}, {'date': '2026-09-28', 'daily_plan': 200}],
            'filter': {'matched': '7'}, 'flag': True}
    assert ev.extract(data, 'stats.materials') == 10
    assert ev.extract(data, 'orders|len') == 2
    assert ev.extract(data, 'orders.1.x') == 2
    assert ev.extract(data, 'orders|sum:x') == 3 and ev.extract(data, 'orders|max:x') == 2
    assert ev.extract(data, 'days[date=2026-09-28].daily_plan') == 200
    assert ev.extract(data, 'filter.matched') == 7
    users = [{'is_admin': True, 'name': 'бармен', 'rate': 300}, {'is_admin': False}, {'is_admin': True}]
    assert ev.extract(users, '|len') == 3 and ev.extract(users, '|count:is_admin=true') == 2
    assert ev.extract(users, '[name=бармен].rate') == 300
    for bad in ('stats.nothing', 'orders.5.x', 'flag', 'days[date=2030-01-01].daily_plan'):
        try:
            ev.extract(data, bad)
        except ValueError:
            continue
        raise AssertionError('путь без числа должен давать ValueError: ' + bad)
    for broken in ('', 'a..b', 'a|median:x', 'a|sum', 'a[b].c'):
        try:
            ev.parse_path(broken)
        except ValueError:
            continue
        raise AssertionError('кривой путь принят: ' + repr(broken))


def test_answers_tolerance_and_placeholders():
    assert ev.answer_number('Выручка 1 250 000 руб.\nОТВЕТ: 1 250 000') == 1250000
    assert ev.answer_number('ответ: 3,5') == 3.5
    assert ev.answer_number('ОТВЕТ: 12\nуточнение\nОТВЕТ: 13') == 13, 'последняя строка ОТВЕТ'
    assert ev.answer_number('без строки') is None
    assert ev.numbers_in('Было 12 345,67 руб. и −3 шт., 0.5 л') == [12345.67, -3.0, 0.5]
    assert ev.numbers_in('в 3 барах 12 кранов, выручка 1 250 000') == [3.0, 12.0, 1250000.0]
    assert ev.answer_number('ОТВЕТ: −2,5') == -2.5
    assert ev.within(100.4, 100, {'abs': 0.5}) and not ev.within(101, 100, {'abs': 0.5})
    assert ev.within(1005, 1000, {'rel': 0.005}) and not ev.within(1006, 1000, {'rel': 0.005})
    assert ev.within(7, 7, {'abs': 0})
    values = ev.placeholders(date(2026, 1, 5))                 # понедельник в январе
    assert values['month'] == '2026-01' and values['prev_month'] == '2025-12'
    assert values['prev_month_year'] == 2025 and values['prev_month_num'] == 12
    assert values['month_end'] == '2026-01-31' and values['prev_month_end'] == '2025-12-31'
    assert (values['prev_week_start'], values['prev_week_end']) == ('2025-12-29', '2026-01-04')
    assert values['yesterday'] == '2026-01-04'
    filled = ev.fill({'year': '{year}', 'month': '{month_num}', 'text': 'на {month}', 'x': '{unknown}'}, values)
    assert filled == {'year': 2026, 'month': 1, 'text': 'на 2026-01', 'x': '{unknown}'}


def test_stream_parsing_and_claude_command():
    stream = '\n'.join(json.dumps(event, ensure_ascii=False) for event in (
        {'type': 'system', 'subtype': 'init'},
        {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'mcp__kultura-eval__stocks_taps_statistics'}]}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Считаю'}]}},
        {'type': 'result', 'subtype': 'success', 'result': 'Активно 1 кран.\nОТВЕТ: 1', 'total_cost_usd': 0.04,
         'num_turns': 3},
    )) + '\nне json\n'
    parsed = ev.parse_stream(stream)
    assert parsed['tools'] == ['stocks_taps_statistics'] and parsed['cost_usd'] == 0.04
    assert ev.answer_number(parsed['text']) == 1 and parsed['error'] is None
    cmd = ev.claude_command('claude', 'cfg.json', model='sonnet', budget=0.5)
    assert cmd[:2] == ['claude', '-p']
    assert cmd[cmd.index('--permission-mode') + 1] == 'dontAsk', 'никогда bypassPermissions'
    assert '--strict-mcp-config' in cmd and cmd[cmd.index('--tools') + 1] == ''
    assert cmd[cmd.index('--allowedTools') + 1] == 'mcp__kultura-eval'
    denied = cmd[cmd.index('--disallowedTools') + 1:cmd.index('--no-session-persistence')]
    assert 'mcp__kultura-eval__common_notify_owner' in denied and 'Bash' in denied and 'Write' in denied
    assert cmd[-4:] == ['--model', 'sonnet', '--max-budget-usd', '0.5']
    assert ev.connector_url('https://beerkultura.ru/', 'stocks') == 'https://beerkultura.ru/mcp/stocks/read'
    fresh = {'content': [{'type': 'text', 'text': 'Данные на 14:05 МСК (кэш до 5 минут)'},
                         {'type': 'text', 'text': '{"decide_count": 4}'}], 'isError': False}
    assert ev.result_json(fresh) == {'decide_count': 4}
    for bad in ({'content': [{'type': 'text', 'text': 'ВНИМАНИЕ: ответ обрезан до 60000\n{}'}], 'isError': False},
                {'content': [{'type': 'text', 'text': 'Ошибка HTTP 400: нет бара'}], 'isError': True}):
        try:
            ev.result_json(bad)
        except RuntimeError:
            continue
        raise AssertionError('обрезанный или ошибочный эталон не должен приниматься')


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print('ok   ' + name)
            except Exception as error:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print('FAIL ' + name + ': ' + repr(error))
    sys.exit(1 if failed else 0)
