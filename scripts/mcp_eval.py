"""Эталонный прогон ИИ-агента через MCP: вопрос -> claude -p -> число в ответе против числа из API.

## Что это

Проверка, что агент с коннектором «Культуры» в режиме «Только чтение» отвечает на типовые
вопросы владельца тем же числом, что показывает сайт. Вопросы — tests/mcp_eval_questions.json
(по 5–8 на раздел: content, stocks, analytics, staff). У каждого вопроса:
    question      текст вопроса (можно с подстановками {month}, {today} ... — список в JSON);
    expect_tools  какие инструменты агент должен вызвать (хотя бы один из списка);
    reference     {tool, args, path} — эталон: тот же инструмент MCP, что у агента, и путь к
                  числу в его JSON-ответе;
    tolerance     допуск: {"abs": 0} — точно, {"rel": 0.005} — 0,5 %, можно оба (берётся больший);
    unit          единица для отчёта.

## Как запускать

    py -3 scripts/mcp_eval.py                     сухой режим (по умолчанию): план, ничего не отправляет
    py -3 scripts/mcp_eval.py --domain stocks     только один раздел (можно несколько --domain)
    py -3 scripts/mcp_eval.py --run               настоящий прогон: ТРАТИТ ТОКЕНЫ подписки владельца
         [--url https://beerkultura.ru] [--token-env KULTURA_MCP_TOKEN] [--ids id1,id2]
         [--model sonnet] [--max-budget-usd 0.5] [--timeout 300] [--json-out результат.json]

Токен — статический токен MCP (kmcp_…) с нужными разделами из переменной окружения
(по умолчанию KULTURA_MCP_TOKEN); выпускает владелец на /admin/mcp. Скрипт сам добавляет
к адресу режим /read: даже токен с полным доступом работает здесь только на чтение.

## Как работает --run (для каждого вопроса)

1. Эталон: JSON-RPC tools/call (эпоха 2025-11-25, без рукопожатия) к <url>/mcp/<раздел>/read
   тем же токеном — инструмент reference.tool с reference.args. Из текстовых блоков берётся
   JSON (строка «Данные на …» и предупреждение об обрезании пропускаются); обрезанный ответ
   эталоном не считается — вопрос помечается «эталон обрезан». Тяжёлые инструменты мост
   кэширует на 5 минут, поэтому агент, спросивший то же самое, получит те же данные.
2. Агент: `claude -p` с одним сервером MCP (временный файл конфигурации с токеном; удаляется
   после вызова), --strict-mcp-config, --permission-mode dontAsk (явно: у проекта в
   .claude/settings.local.json стоит bypassPermissions), --tools "" (встроенные инструменты
   выключены), --allowedTools mcp__kultura-eval, --disallowedTools для сообщения владельцу
   (common_notify_owner) и на всякий случай Bash/Edit/Write/…, --no-session-persistence,
   рабочая папка — временная пустая (проектные настройки не подхватываются). Вопрос идёт
   через stdin: вариативный --allowedTools иначе проглотил бы его как имя инструмента.
   Вывод — stream-json: из него берутся вызванные инструменты, итоговый текст и стоимость.
3. Сверка: число из строки «ОТВЕТ: <число>» (агента просят закончить ею); если её нет —
   любое число текста в пределах допуска (так и помечается). Вопрос пройден, если число в
   допуске И вызван хотя бы один из expect_tools.

## Путь к числу (reference.path)

    stats.materials                ключи через точку
    items.0.recommended            индекс списка
    days[date={today}].daily_plan  первый элемент списка, у которого поле равно значению
    [name=бармен].rate_per_hour    то же на корневом списке
    orders|len  |len               длина списка (или объекта) — в конце после «|»
    |count:is_admin=true           сколько элементов с полем, равным значению (true/1 — JSON)
    |sum:line_sum  |max:x  |min:x  сумма, максимум, минимум поля по списку
Значение после «=» разбирается как JSON (true, 1, null), иначе — строка.

## Безопасность

- Без --run скрипт не ходит в сеть и не запускает процессов (это проверяет тест).
- Только режим /read; сообщение владельцу агенту запрещено флагом клиента.
- Токен не печатается и не пишется в отчёт; файл конфигурации MCP живёт только на время вызова.

## Файлы

    scripts/mcp_eval.py             этот скрипт
    tests/mcp_eval_questions.json   вопросы
    tests/test_mcp_eval.py          тест формата файла и сухого режима (без сети)
    docs/mcp.md, раздел «Эталонные вопросы» — описание для владельца

## Changelog

- 2026-09-28 — создан: 28 вопросов по четырём разделам, сухой режим по умолчанию.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS_FILE = os.path.join(REPO, 'tests', 'mcp_eval_questions.json')
DOMAINS = ('content', 'stocks', 'analytics', 'staff')
QUESTIONS_PER_DOMAIN = (5, 8)            # сколько вопросов на раздел держит файл
SERVER_NAME = 'kultura-eval'             # имя сервера MCP в конфигурации claude -p
PROTOCOL_VERSION = '2025-11-25'          # эпоха без рукопожатия: tools/call сразу
DEFAULT_URL = 'https://beerkultura.ru'
DEFAULT_TOKEN_ENV = 'KULTURA_MCP_TOKEN'
DEFAULT_TIMEOUT_S = 300                  # на один вопрос: тяжёлый отчёт iiko + рассуждения
MSK = timezone(timedelta(hours=3))       # Москва без перехода на летнее время с 2014 года
# Число в строке «ОТВЕТ: …»: пробелы внутри допустимы (1 250 000), но не перевод строки.
ANSWER_RE = re.compile('ОТВЕТ[ \\t]*:[ \\t]*([-\u2212]?\\d[\\d \\t\u00a0\u202f]*(?:[.,]\\d+)?)', re.IGNORECASE)
# Число в свободном тексте: группы тысяч через пробел (обычный, неразрывный, узкий) — только
# по три цифры («12 345,67»), иначе «в 3 барах 12 кранов» склеилось бы в 312. Минус — «-» или «−».
NUMBER_RE = re.compile('[-\u2212]?(?:\\d{1,3}(?:[ \u00a0\u202f]\\d{3})+|\\d+)(?:[.,]\\d+)?')
PLACEHOLDER_RE = re.compile(r'\{([a-z_]+)\}')
FRESHNESS_PREFIX = 'Данные на '
TRUNCATED_PREFIX = 'ВНИМАНИЕ: ответ обрезан'
# Встроенные инструменты клиента, которые агенту эталона не нужны ни при каких условиях.
DISALLOWED_BUILTINS = ('Bash', 'PowerShell', 'Edit', 'Write', 'NotebookEdit', 'WebFetch', 'WebSearch',
                       'Agent', 'Task')

PROMPT_TEMPLATE = (
    'Ты — ИИ-агент сети баров «Культура» с доступом к её сервису через MCP (сервер {server}, режим '
    '«Только чтение»). Ответь на вопрос владельца по данным сервиса: вызови нужные инструменты, '
    'не угадывай. Сегодня по Москве {today}.\n\n'
    'Вопрос: {question}\n\n'
    'Ответь коротко. Последней строкой напиши ровно «ОТВЕТ: <число>» — одно число без единиц '
    'измерения и без пробелов внутри, дробную часть через точку.'
)


# ------------------------------------------------------------------ подстановки дат

def placeholders(today: Optional[date] = None) -> Dict[str, Any]:
    """Значения подстановок на дату today (по умолчанию — сегодня по Москве)."""
    today = today or datetime.now(MSK).date()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    return {
        'today': today.isoformat(),
        'yesterday': (today - timedelta(days=1)).isoformat(),
        'year': today.year,
        'month': today.strftime('%Y-%m'),
        'month_num': today.month,
        'month_start': month_start.isoformat(),
        'month_end': (next_month - timedelta(days=1)).isoformat(),
        'prev_month': prev_month_start.strftime('%Y-%m'),
        'prev_month_year': prev_month_start.year,
        'prev_month_num': prev_month_start.month,
        'prev_month_start': prev_month_start.isoformat(),
        'prev_month_end': prev_month_end.isoformat(),
        'prev_week_start': (week_start - timedelta(days=7)).isoformat(),
        'prev_week_end': (week_start - timedelta(days=1)).isoformat(),
    }


def fill(value: Any, values: Dict[str, Any]) -> Any:
    """Подставить {имя} в строки (рекурсивно). Строка ровно «{year}» -> целое, если значение целое."""
    if isinstance(value, dict):
        return {k: fill(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, values) for v in value]
    if not isinstance(value, str):
        return value
    whole = PLACEHOLDER_RE.fullmatch(value)
    if whole and whole.group(1) in values:
        return values[whole.group(1)]
    return PLACEHOLDER_RE.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), value)


# ------------------------------------------------------------------ путь к числу

def _literal(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


_SELECTOR_RE = re.compile(r'^([^\[\]]*)\[([^=\]]+)=([^\]]*)\]$')


def parse_path(path: str) -> Tuple[List[Any], Optional[Tuple[str, str]]]:
    """reference.path -> (шаги, операция). Шаг: ('key', k) | ('index', n) | ('find', поле, значение).

    Ошибка синтаксиса — ValueError (её ловит проверка файла вопросов).
    """
    if not isinstance(path, str):
        raise ValueError('path должен быть строкой')
    body, _, op_text = path.partition('|')
    steps: List[Any] = []
    for part in [p for p in body.split('.')] if body else []:
        if not part:
            raise ValueError('пустой шаг пути в «' + path + '»')
        match = _SELECTOR_RE.match(part)
        if match:
            if match.group(1):
                steps.append(('key', match.group(1)))
            steps.append(('find', match.group(2).strip(), _literal(match.group(3).strip())))
        elif '[' in part or ']' in part:
            raise ValueError('кривой выбор [поле=значение] в «' + path + '»')
        elif part.isdigit():
            steps.append(('index', int(part)))
        else:
            steps.append(('key', part))
    op = None
    if op_text:
        name, _, arg = op_text.partition(':')
        if name not in ('len', 'count', 'sum', 'max', 'min'):
            raise ValueError('неизвестная операция «' + name + '» в «' + path + '»')
        if name in ('sum', 'max', 'min') and not arg:
            raise ValueError('операции ' + name + ' нужно поле: |' + name + ':<поле>')
        if name == 'count' and arg and '=' not in arg:
            raise ValueError('|count:<поле>=<значение>')
        op = (name, arg)
    if not steps and op is None:
        raise ValueError('пустой путь')
    return steps, op


def extract(data: Any, path: str) -> float:
    """Число из JSON по пути (правила — докстрока модуля). Нет числа — ValueError с объяснением."""
    steps, op = parse_path(path)
    node = data
    for step in steps:
        if step[0] == 'key':
            if not isinstance(node, dict) or step[1] not in node:
                raise ValueError('нет ключа «' + str(step[1]) + '»')
            node = node[step[1]]
        elif step[0] == 'index':
            if not isinstance(node, list) or step[1] >= len(node):
                raise ValueError('нет элемента [' + str(step[1]) + ']')
            node = node[step[1]]
        else:
            if not isinstance(node, list):
                raise ValueError('выбор [' + step[1] + '=…] не по списку')
            found = [item for item in node if isinstance(item, dict) and item.get(step[1]) == step[2]]
            if not found:
                raise ValueError('нет элемента с ' + step[1] + '=' + json.dumps(step[2], ensure_ascii=False))
            node = found[0]
    if op is not None:
        name, arg = op
        items = list(node.values()) if isinstance(node, dict) else node
        if not isinstance(items, list):
            raise ValueError('операция |' + name + ' не по списку')
        if name == 'len' or (name == 'count' and not arg):
            return float(len(items))
        if name == 'count':
            field, _, raw = arg.partition('=')
            want = _literal(raw)
            return float(sum(1 for item in items if isinstance(item, dict) and item.get(field) == want))
        values = [item.get(arg) for item in items if isinstance(item, dict)]
        numbers = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if name == 'sum':
            return float(sum(numbers))
        if not numbers:
            raise ValueError('нет чисел в поле «' + arg + '»')
        return max(numbers) if name == 'max' else min(numbers)
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        if isinstance(node, str):
            try:
                return float(node.replace(',', '.'))
            except ValueError:
                pass
        raise ValueError('по пути не число: ' + json.dumps(node, ensure_ascii=False)[:80])
    return float(node)


# ------------------------------------------------------------------ числа в ответе агента

def _to_float(text: str) -> Optional[float]:
    clean = re.sub('[\\s  ]', '', text).replace(',', '.').replace('−', '-')
    try:
        return float(clean)
    except ValueError:
        return None


def answer_number(text: str) -> Optional[float]:
    """Число из последней строки «ОТВЕТ: …» (None — строки нет)."""
    matches = ANSWER_RE.findall(text or '')
    return _to_float(matches[-1]) if matches else None


def numbers_in(text: str) -> List[float]:
    """Все числа текста: «12 345,67», «12345.67», «-3» (пробел-разделитель тысяч — обычный и узкий)."""
    out = []
    for raw in NUMBER_RE.findall(text or ''):
        value = _to_float(raw)
        if value is not None:
            out.append(value)
    return out


def within(value: float, reference: float, tolerance: Dict[str, Any]) -> bool:
    allowed = max(float(tolerance.get('abs', 0) or 0), float(tolerance.get('rel', 0) or 0) * abs(reference))
    return abs(value - reference) <= allowed + 1e-9


# ------------------------------------------------------------------ файл вопросов

def load_questions(path: str = QUESTIONS_FILE) -> Dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def validate(data: Any, tools: Optional[Dict[str, Any]] = None) -> List[str]:
    """Ошибки файла вопросов (пустой список — всё в порядке).

    tools — {имя: ToolSpec} настоящего реестра (core.mcp.registry): тогда проверяется ещё, что
    инструменты есть, видны в коннекторе раздела, разрешены в режиме read и аргументы эталона
    проходят схему. Без tools — только формат.
    """
    errors: List[str] = []
    if not isinstance(data, dict) or data.get('version') != 1:
        return ['файл: нужен объект с version = 1']
    questions = data.get('questions')
    if not isinstance(questions, list) or not questions:
        return ['файл: questions — непустой список']
    seen = set()
    per_domain = {d: 0 for d in DOMAINS}
    sample = placeholders(date(2026, 9, 28))
    for index, q in enumerate(questions):
        where = 'вопрос ' + str(index + 1)
        if not isinstance(q, dict):
            errors.append(where + ': не объект')
            continue
        qid = q.get('id')
        where = 'вопрос ' + str(qid or index + 1)
        if not isinstance(qid, str) or not re.fullmatch(r'[a-z0-9-]{3,64}', qid):
            errors.append(where + ': id — латиница, цифры и «-», 3..64')
        elif qid in seen:
            errors.append(where + ': id повторяется')
        seen.add(qid)
        extra = set(q) - {'id', 'domain', 'question', 'expect_tools', 'reference', 'tolerance', 'unit'}
        if extra:
            errors.append(where + ': лишние поля ' + ', '.join(sorted(extra)))
        domain = q.get('domain')
        if domain not in DOMAINS:
            errors.append(where + ': domain — один из ' + ', '.join(DOMAINS))
        else:
            per_domain[domain] += 1
        text = q.get('question')
        if not isinstance(text, str) or len(text.strip()) < 10:
            errors.append(where + ': question — текст вопроса')
        else:
            unknown = set(PLACEHOLDER_RE.findall(text)) - set(sample)
            if unknown:
                errors.append(where + ': неизвестные подстановки ' + ', '.join(sorted(unknown)))
        expect = q.get('expect_tools')
        if not isinstance(expect, list) or not expect or not all(isinstance(t, str) for t in expect):
            errors.append(where + ': expect_tools — непустой список имён инструментов')
            expect = []
        ref = q.get('reference')
        if not isinstance(ref, dict) or set(ref) != {'tool', 'args', 'path'}:
            errors.append(where + ': reference — {tool, args, path}')
            ref = None
        elif not isinstance(ref.get('args'), dict):
            errors.append(where + ': reference.args — объект')
            ref = None
        else:
            try:
                parse_path(fill(ref['path'], sample))
            except ValueError as error:
                errors.append(where + ': reference.path: ' + str(error))
            if ref['tool'] not in expect:
                errors.append(where + ': reference.tool должен быть среди expect_tools')
        tol = q.get('tolerance')
        if (not isinstance(tol, dict) or not tol or set(tol) - {'abs', 'rel'}
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in tol.values())):
            errors.append(where + ': tolerance — {"abs": ≥0} и/или {"rel": ≥0}')
        if not isinstance(q.get('unit'), str) or not q.get('unit').strip():
            errors.append(where + ': unit — единица для отчёта')
        if tools is not None and domain in DOMAINS:
            errors.extend(_check_tools(where, domain, expect, ref, tools, sample))
    low, high = QUESTIONS_PER_DOMAIN
    for domain, count in per_domain.items():
        if not low <= count <= high:
            errors.append('раздел ' + domain + ': вопросов ' + str(count) + ', нужно ' + str(low) + '..' + str(high))
    return errors


def _check_tools(where: str, domain: str, expect: List[str], ref: Optional[Dict[str, Any]],
                 tools: Dict[str, Any], sample: Dict[str, Any]) -> List[str]:
    """Инструменты вопроса есть, видны в коннекторе раздела и разрешены в режиме read."""
    from core.mcp import schema_check
    from core.mcp.spec import allowed_in_mode
    errors = []
    for name in expect:
        spec = tools.get(name)
        if spec is None:
            errors.append(where + ': нет инструмента ' + name)
            continue
        visible = spec.domain in (domain, 'common') or domain in spec.also_in
        if not visible:
            errors.append(where + ': ' + name + ' не виден в коннекторе /mcp/' + domain)
        if not allowed_in_mode(spec, 'read') or spec.owner_notice:
            errors.append(where + ': ' + name + ' недоступен в режиме «Только чтение»')
    if ref is not None and ref.get('tool') in tools:
        spec = tools[ref['tool']]
        problem = schema_check.validate_arguments(spec.input_schema, fill(ref['args'], sample), spec.name)
        if problem:
            errors.append(where + ': reference.args не проходят схему: ' + problem)
    return errors


def registry_tools() -> Dict[str, Any]:
    """{имя: ToolSpec} настоящего реестра (только описания; маршруты и app.py не трогаются)."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from core.mcp import registry
    return {spec.name: spec for spec in registry.all_tools()}


# ------------------------------------------------------------------ план (сухой режим)

def select(data: Dict[str, Any], domains: Optional[List[str]] = None,
           ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    out = []
    for q in data['questions']:
        if domains and q['domain'] not in domains:
            continue
        if ids and q['id'] not in ids:
            continue
        out.append(q)
    return out


def connector_url(base: str, domain: str) -> str:
    return base.rstrip('/') + '/mcp/' + domain + '/read'


def claude_command(claude: str, config_path: str, model: Optional[str] = None,
                   budget: Optional[float] = None) -> List[str]:
    """Команда claude -p для одного вопроса (правила — докстрока модуля, «Как работает --run»)."""
    cmd = [claude, '-p', '--output-format', 'stream-json', '--verbose',
           '--permission-mode', 'dontAsk',
           '--strict-mcp-config', '--mcp-config', config_path,
           '--tools', '',
           '--allowedTools', 'mcp__' + SERVER_NAME,
           '--disallowedTools', 'mcp__' + SERVER_NAME + '__common_notify_owner', *DISALLOWED_BUILTINS,
           '--no-session-persistence']
    if model:
        cmd += ['--model', model]
    if budget:
        cmd += ['--max-budget-usd', str(budget)]
    return cmd


def print_plan(questions: List[Dict[str, Any]], values: Dict[str, Any], base: str, heavy: Dict[str, bool],
               out=None) -> None:
    out = out or sys.stdout
    write = lambda text='': out.write(text + '\n')  # noqa: E731
    write('Сухой режим: план эталонного прогона (ничего не отправлено, сеть и claude не вызывались).')
    write('Дата подстановок: ' + str(values['today']) + ' (Москва). Вопросов: ' + str(len(questions)) + '.')
    write('')
    for q in questions:
        ref = q['reference']
        tol = ', '.join(k + '=' + str(v) for k, v in sorted(q['tolerance'].items()))
        write('[' + q['id'] + '] ' + q['domain'] + ' -> ' + connector_url(base, q['domain']))
        write('  вопрос:   ' + fill(q['question'], values))
        write('  агент:    должен вызвать одно из: ' + ', '.join(q['expect_tools']))
        write('  эталон:   ' + ref['tool'] + ' ' + json.dumps(fill(ref['args'], values), ensure_ascii=False)
              + ' -> ' + fill(ref['path'], values) + ' (' + q['unit'] + '; допуск ' + tol + ')'
              + (' [тяжёлый: iiko]' if heavy.get(ref['tool']) else ''))
    counts = {}
    for q in questions:
        counts[q['domain']] = counts.get(q['domain'], 0) + 1
    write('')
    write('По разделам: ' + ', '.join(d + ' ' + str(n) for d, n in sorted(counts.items())) + '.')
    write('Команда агента на вопрос (токен — во временном файле конфигурации, не в команде):')
    write('  ' + ' '.join(repr(part) if part == '' else part
                          for part in claude_command('claude', '<временный mcp.json>', None, None)) + ' < вопрос')
    write('')
    write('Настоящий прогон: --run (тратит токены подписки владельца; нужен токен в '
          + DEFAULT_TOKEN_ENV + ').')


# ------------------------------------------------------------------ настоящий прогон

def mcp_call(base: str, domain: str, token: str, tool: str, args: Dict[str, Any],
             timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """tools/call к коннектору раздела в режиме read. Возвращает result JSON-RPC."""
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': tool, 'arguments': args}}).encode('utf-8')
    request = urllib.request.Request(connector_url(base, domain), data=body, method='POST', headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'application/json',
        'MCP-Protocol-Version': PROTOCOL_VERSION, 'User-Agent': 'kultura-mcp-eval/1'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if 'error' in payload:
        raise RuntimeError('JSON-RPC ' + str(payload['error'].get('code')) + ': ' + str(payload['error'].get('message')))
    return payload['result']


def result_json(result: Dict[str, Any]) -> Any:
    """JSON из результата инструмента: строка свежести пропускается, обрезанный ответ — ошибка."""
    if result.get('isError'):
        texts = [b.get('text') or '' for b in result.get('content') or [] if b.get('type') == 'text']
        raise RuntimeError('инструмент ответил ошибкой: ' + ' '.join(texts)[:300])
    for block in result.get('content') or []:
        text = block.get('text') if block.get('type') == 'text' else None
        if not text or text.startswith(FRESHNESS_PREFIX):
            continue
        if text.startswith(TRUNCATED_PREFIX):
            raise RuntimeError('эталон обрезан мостом (ответ больше 60 000 символов): сузьте аргументы')
        return json.loads(text)
    raise RuntimeError('в ответе нет JSON')


def parse_stream(stdout: str) -> Dict[str, Any]:
    """stream-json claude -p -> {tools: [имена без префикса], text, cost_usd, turns, error}."""
    tools: List[str] = []
    text, cost, turns, error = '', None, None, None
    prefix = 'mcp__' + SERVER_NAME + '__'
    for line in (stdout or '').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'assistant':
            for block in (event.get('message') or {}).get('content') or []:
                if block.get('type') == 'tool_use':
                    name = str(block.get('name') or '')
                    tools.append(name[len(prefix):] if name.startswith(prefix) else name)
        elif event.get('type') == 'result':
            text = str(event.get('result') or '')
            cost = event.get('total_cost_usd')
            turns = event.get('num_turns')
            if event.get('is_error') or event.get('subtype') not in (None, 'success'):
                error = str(event.get('subtype') or 'ошибка')
    return {'tools': tools, 'text': text, 'cost_usd': cost, 'turns': turns, 'error': error}


def run_question(q: Dict[str, Any], values: Dict[str, Any], base: str, token: str, claude: str,
                 model: Optional[str], budget: Optional[float], timeout: float) -> Dict[str, Any]:
    ref = q['reference']
    report: Dict[str, Any] = {'id': q['id'], 'domain': q['domain'], 'question': fill(q['question'], values),
                              'unit': q['unit'], 'passed': False}
    try:
        data = result_json(mcp_call(base, q['domain'], token, ref['tool'], fill(ref['args'], values), timeout))
        report['reference'] = extract(data, fill(ref['path'], values))
    except (RuntimeError, ValueError, OSError, urllib.error.URLError) as error:
        report['error'] = 'эталон: ' + str(error)
        return report
    workdir = tempfile.mkdtemp(prefix='mcp_eval_')
    config_path = os.path.join(workdir, 'mcp.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as handle:
            json.dump({'mcpServers': {SERVER_NAME: {'type': 'http', 'url': connector_url(base, q['domain']),
                                                    'headers': {'Authorization': 'Bearer ' + token}}}}, handle)
        prompt = PROMPT_TEMPLATE.format(server=SERVER_NAME, today=values['today'], question=report['question'])
        started = time.monotonic()
        done = subprocess.run(claude_command(claude, config_path, model, budget), input=prompt,
                              capture_output=True, text=True, encoding='utf-8', timeout=timeout, cwd=workdir)
        report['duration_s'] = round(time.monotonic() - started, 1)
    except (OSError, subprocess.SubprocessError) as error:
        report['error'] = 'claude: ' + type(error).__name__ + ': ' + str(error)[:200]
        return report
    finally:
        shutil.rmtree(workdir, ignore_errors=True)        # файл с токеном не живёт дольше вызова
    stream = parse_stream(done.stdout)
    report.update(tools=stream['tools'], cost_usd=stream['cost_usd'], turns=stream['turns'],
                  answer_text=stream['text'][-600:])
    if done.returncode != 0 and not stream['text']:
        report['error'] = 'claude вышел с кодом ' + str(done.returncode) + ': ' + (done.stderr or '')[-300:]
        return report
    if stream['error']:
        report['error'] = 'claude: ' + stream['error']
    answer = answer_number(stream['text'])
    report['answer'] = answer
    report['answer_source'] = 'строка ОТВЕТ' if answer is not None else 'число в тексте'
    if answer is not None:
        number_ok = within(answer, report['reference'], q['tolerance'])
    else:
        number_ok = any(within(v, report['reference'], q['tolerance']) for v in numbers_in(stream['text']))
    tools_ok = any(name in stream['tools'] for name in q['expect_tools'])
    report.update(number_ok=number_ok, tools_ok=tools_ok, passed=number_ok and tools_ok)
    return report


def print_report(reports: List[Dict[str, Any]], out=None) -> None:
    out = out or sys.stdout
    write = lambda text='': out.write(text + '\n')  # noqa: E731
    for r in reports:
        mark = 'ОК  ' if r.get('passed') else 'НЕТ '
        line = mark + r['id'] + ': эталон ' + str(r.get('reference')) + ', ответ ' + str(r.get('answer'))
        if r.get('answer_source') == 'число в тексте':
            line += ' (строки ОТВЕТ нет)'
        if 'tools_ok' in r and not r['tools_ok']:
            line += '; не вызван ожидаемый инструмент (вызваны: ' + (', '.join(r.get('tools') or []) or 'ничего') + ')'
        if r.get('error'):
            line += '; ' + r['error']
        write(line)
    passed = sum(1 for r in reports if r.get('passed'))
    cost = sum(float(r.get('cost_usd') or 0) for r in reports)
    write('')
    write('Итого: ' + str(passed) + ' из ' + str(len(reports)) + ' вопросов; стоимость по данным claude — $'
          + format(cost, '.2f') + '.')


# ------------------------------------------------------------------ точка входа

def main(argv: Optional[List[str]] = None, out=None) -> int:
    parser = argparse.ArgumentParser(description='Эталонные вопросы к ИИ-агенту через MCP (docs/mcp.md).')
    parser.add_argument('--run', action='store_true', help='настоящий прогон через claude -p (тратит токены)')
    parser.add_argument('--questions', default=QUESTIONS_FILE, help='файл вопросов')
    parser.add_argument('--domain', action='append', choices=DOMAINS, help='только этот раздел (можно повторять)')
    parser.add_argument('--ids', default='', help='только эти вопросы, через запятую')
    parser.add_argument('--url', default=DEFAULT_URL, help='адрес сайта')
    parser.add_argument('--token-env', default=DEFAULT_TOKEN_ENV, help='переменная окружения с токеном kmcp_…')
    parser.add_argument('--claude', default='claude', help='исполняемый файл Claude Code')
    parser.add_argument('--model', default=None, help='модель для claude -p (по умолчанию — из настроек)')
    parser.add_argument('--max-budget-usd', type=float, default=None, help='предел стоимости одного вопроса')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_S, help='секунд на вопрос')
    parser.add_argument('--json-out', default=None, help='записать отчёт JSON в файл')
    parser.add_argument('--no-registry', action='store_true',
                        help='не сверять инструменты с реестром проекта (только формат файла)')
    args = parser.parse_args(argv)
    out = out or sys.stdout

    data = load_questions(args.questions)
    tools = None if args.no_registry else registry_tools()
    problems = validate(data, tools)
    if problems:
        out.write('Файл вопросов с ошибками:\n' + '\n'.join('  - ' + p for p in problems) + '\n')
        return 2
    ids = [i.strip() for i in args.ids.split(',') if i.strip()]
    questions = select(data, args.domain, ids)
    if not questions:
        out.write('Под фильтры не попал ни один вопрос.\n')
        return 2
    values = placeholders()
    heavy = {name: bool(getattr(spec, 'heavy', False)) for name, spec in (tools or {}).items()}
    if not args.run:
        print_plan(questions, values, args.url, heavy, out)
        return 0

    token = os.environ.get(args.token_env, '').strip()
    if not token:
        out.write('Нет токена: задайте переменную окружения ' + args.token_env + ' (токен kmcp_… с /admin/mcp).\n')
        return 2
    claude = shutil.which(args.claude) or args.claude
    reports = []
    for q in questions:
        out.write('... ' + q['id'] + '\n')
        out.flush()
        reports.append(run_question(q, values, args.url, token, claude, args.model, args.max_budget_usd,
                                    args.timeout))
    print_report(reports, out)
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as handle:
            json.dump({'at': datetime.now(MSK).isoformat(timespec='seconds'), 'url': args.url,
                       'reports': reports}, handle, ensure_ascii=False, indent=2)
    return 0 if all(r.get('passed') for r in reports) else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
