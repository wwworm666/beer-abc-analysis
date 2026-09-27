"""Проверка аргументов MCP-инструмента по его JSON Schema (минимальное подмножество).

Зачем свой валидатор, а не пакет jsonschema: в requirements.txt его нет, а нужен
малый и предсказуемый набор правил с РУССКИМИ сообщениями, которые называют поле.
Агент читает текст ошибки и сам исправляет вызов — поэтому сообщение должно
говорить «что не так и где», а не «ValidationError at $.items[2]».

Поддержанные ключевые слова (всё, что пишут описания инструментов в tools/*.py):
    type                 строка или список типов; integer / number / boolean различаются
                         (в Python bool — подкласс int: True НЕ проходит как integer)
    enum, const
    properties, required, additionalProperties (false или схема)
    items, minItems, maxItems, uniqueItems
    minimum, maximum, exclusiveMinimum, exclusiveMaximum
    minLength, maxLength, pattern (re.search, как в JSON Schema — без неявных якорей)
    format: 'date' (YYYY-MM-DD, реальная дата) и 'date-time' (ISO 8601); прочие
            форматы — только подсказка, не проверяются
    anyOf, oneOf, allOf
Не поддержаны и молча игнорируются: $ref, if/then/else, patternProperties,
prefixItems, dependent*. Описания инструментов их не используют.

Правила:
- integer: целое число; 5.0 из JSON (число с нулевой дробной частью) тоже целое —
  так считает JSON Schema 2020-12. normalize() превращает такие значения в int,
  чтобы маршрут получил 5, а не 5.0.
- number: любое конечное число, кроме bool. NaN и бесконечность не проходят.
- Сообщений не больше MAX_ERRORS: длинная простыня мешает агенту, а после
  исправления первых ошибок остальные всё равно проверятся заново.

Путь поля в сообщениях: «bar_id», «items[2].qty»; ошибки самого объекта
аргументов — «аргументы».
"""
import json
import math
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

MAX_ERRORS = 10              # сколько ошибок показать агенту за один вызов
DESCRIPTION_HINT_CHARS = 140  # сколько символов описания поля добавить к ошибке формата
VALUE_PREVIEW_CHARS = 60      # как длинно цитировать ошибочное значение

_TYPE_NAMES = {
    'object': 'объект',
    'array': 'список',
    'string': 'строка',
    'integer': 'целое число',
    'number': 'число',
    'boolean': 'логическое значение true/false',
    'null': 'null',
}

# «Получено …»: название без пояснения в скобках (в «ожидается» оно нужнее).
_GOT_NAMES = dict(_TYPE_NAMES, boolean='логическое значение')

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def json_type(value: Any) -> str:
    """Имя JSON-типа значения (для сообщения «получено …»)."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, (list, tuple)):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    return type(value).__name__


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value) and value.is_integer()


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def matches_type(value: Any, type_name: str) -> bool:
    """Подходит ли значение под один JSON-тип."""
    if type_name == 'null':
        return value is None
    if type_name == 'boolean':
        return isinstance(value, bool)
    if type_name == 'integer':
        return _is_integer(value)
    if type_name == 'number':
        return _is_number(value)
    if type_name == 'string':
        return isinstance(value, str)
    if type_name == 'array':
        return isinstance(value, (list, tuple))
    if type_name == 'object':
        return isinstance(value, dict)
    return True   # неизвестный тип ловит spec.validate_tool_spec, здесь не мешаем


def _preview(value: Any) -> str:
    """Короткая цитата значения в JSON-записи (true, null, 5), строки — в ёлочках."""
    if isinstance(value, str):
        text = '«' + value + '»'
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(value)
    if len(text) > VALUE_PREVIEW_CHARS:
        text = text[:VALUE_PREVIEW_CHARS - 1] + '…'
    return text


def _where(path: str) -> str:
    return 'Поле «' + path + '»' if path else 'Аргументы'


def _join(path: str, key: str) -> str:
    return key if not path else path + '.' + key


def _hint(schema: dict) -> str:
    desc = (schema.get('description') or '').strip()
    if not desc:
        return ''
    if len(desc) > DESCRIPTION_HINT_CHARS:
        desc = desc[:DESCRIPTION_HINT_CHARS - 1] + '…'
    return ' (описание поля: ' + desc + ')'


def _valid_date_time(text: str) -> bool:
    candidate = text[:-1] + '+00:00' if text.endswith('Z') else text
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return 'T' in candidate or ' ' in candidate


def check(schema: Any, value: Any, path: str = '') -> List[str]:
    """Все ошибки значения относительно схемы (пустой список — значение подходит)."""
    errors: List[str] = []
    _check(schema, value, path, errors)
    return errors[:MAX_ERRORS]


def _check(schema: Any, value: Any, path: str, errors: List[str]) -> None:
    if len(errors) >= MAX_ERRORS or not isinstance(schema, dict):
        return

    types = schema.get('type')
    if types is not None:
        wanted = types if isinstance(types, list) else [types]
        if not any(matches_type(value, t) for t in wanted):
            names = ' или '.join(_TYPE_NAMES.get(t, str(t)) for t in wanted)
            got = _GOT_NAMES.get(json_type(value), json_type(value))
            if value is not None:
                got += ' ' + _preview(value)
            errors.append(f'{_where(path)}: ожидается {names}, получено {got}')
            return   # дальнейшие проверки для чужого типа бессмысленны

    if 'const' in schema and value != schema['const']:
        errors.append(f'{_where(path)}: допустимо только значение {_preview(schema["const"])}, '
                      f'получено {_preview(value)}')
    if 'enum' in schema and isinstance(schema['enum'], list):
        allowed = schema['enum']
        if not any(value == a and type(value) is type(a) or (_is_number(value) and _is_number(a) and value == a)
                   for a in allowed):
            listed = ', '.join(_preview(a) for a in allowed[:30])
            more = ' …' if len(allowed) > 30 else ''
            errors.append(f'{_where(path)}: значение {_preview(value)} не из списка допустимых: {listed}{more}')

    if _is_number(value):
        _check_number(schema, value, path, errors)
    if isinstance(value, str):
        _check_string(schema, value, path, errors)
    if isinstance(value, (list, tuple)):
        _check_array(schema, list(value), path, errors)
    if isinstance(value, dict):
        _check_object(schema, value, path, errors)

    for key in ('anyOf', 'oneOf'):
        variants = schema.get(key)
        if isinstance(variants, list) and variants:
            fits = sum(1 for sub in variants if not check(sub, value, path))
            if fits == 0:
                errors.append(f'{_where(path)}: значение не подходит ни под один из допустимых вариантов')
            elif key == 'oneOf' and fits > 1:
                errors.append(f'{_where(path)}: значение подходит сразу под несколько вариантов — уточните')
    variants = schema.get('allOf')
    if isinstance(variants, list):
        for sub in variants:
            _check(sub, value, path, errors)


def _check_number(schema: dict, value, path: str, errors: List[str]) -> None:
    if 'minimum' in schema and _is_number(schema['minimum']) and value < schema['minimum']:
        errors.append(f'{_where(path)}: значение {value} меньше минимума {schema["minimum"]}')
    if 'maximum' in schema and _is_number(schema['maximum']) and value > schema['maximum']:
        errors.append(f'{_where(path)}: значение {value} больше максимума {schema["maximum"]}')
    low = schema.get('exclusiveMinimum')
    if _is_number(low) and value <= low:
        errors.append(f'{_where(path)}: значение {value} должно быть больше {low}')
    high = schema.get('exclusiveMaximum')
    if _is_number(high) and value >= high:
        errors.append(f'{_where(path)}: значение {value} должно быть меньше {high}')


def _check_string(schema: dict, value: str, path: str, errors: List[str]) -> None:
    min_len = schema.get('minLength')
    if _is_integer(min_len) and len(value) < min_len:
        if min_len == 1 and not value:
            errors.append(f'{_where(path)}: пустая строка, нужно значение')
        else:
            errors.append(f'{_where(path)}: строка короче {int(min_len)} симв. (сейчас {len(value)})')
    max_len = schema.get('maxLength')
    if _is_integer(max_len) and len(value) > max_len:
        errors.append(f'{_where(path)}: строка длиннее {int(max_len)} симв. (сейчас {len(value)})')
    pattern = schema.get('pattern')
    if isinstance(pattern, str):
        try:
            ok = re.search(pattern, value) is not None
        except re.error:
            ok = True   # битый шаблон — дефект описания, его ловят тесты описаний
        if not ok:
            errors.append(f'{_where(path)}: значение {_preview(value)} не подходит под шаблон '
                          f'{pattern}{_hint(schema)}')
    fmt = schema.get('format')
    if fmt == 'date':
        valid = bool(_DATE_RE.match(value))
        if valid:
            try:
                date.fromisoformat(value)
            except ValueError:
                valid = False
        if not valid:
            errors.append(f'{_where(path)}: ожидается дата в формате YYYY-MM-DD, получено {_preview(value)}')
    elif fmt == 'date-time' and not _valid_date_time(value):
        errors.append(f'{_where(path)}: ожидается дата и время ISO 8601 (YYYY-MM-DDTHH:MM:SS), '
                      f'получено {_preview(value)}')


def _check_array(schema: dict, value: list, path: str, errors: List[str]) -> None:
    min_items = schema.get('minItems')
    if _is_integer(min_items) and len(value) < min_items:
        errors.append(f'{_where(path)}: нужно хотя бы {int(min_items)} элем. (сейчас {len(value)})')
    max_items = schema.get('maxItems')
    if _is_integer(max_items) and len(value) > max_items:
        errors.append(f'{_where(path)}: не больше {int(max_items)} элем. (сейчас {len(value)})')
    if schema.get('uniqueItems') is True:
        seen = []
        for item in value:
            if item in seen:
                errors.append(f'{_where(path)}: элементы должны быть уникальными, повтор {_preview(item)}')
                break
            seen.append(item)
    items = schema.get('items')
    if isinstance(items, dict):
        for index, item in enumerate(value):
            if len(errors) >= MAX_ERRORS:
                return
            _check(items, item, f'{path}[{index}]' if path else f'[{index}]', errors)


def _check_object(schema: dict, value: dict, path: str, errors: List[str]) -> None:
    props = schema.get('properties') if isinstance(schema.get('properties'), dict) else {}
    for name in schema.get('required') or []:
        if name not in value:
            hint = _hint(props.get(name) or {})
            errors.append(f'Не хватает обязательного поля «{_join(path, name)}»{hint}')
    extra = schema.get('additionalProperties', True)
    for key in value:
        if key in props:
            continue
        if extra is False:
            allowed = ', '.join(sorted(props)) or 'нет параметров'
            errors.append(f'Лишнее поле «{_join(path, key)}»: такого параметра нет. Допустимые: {allowed}')
        elif isinstance(extra, dict):
            _check(extra, value[key], _join(path, key), errors)
    for key, sub in props.items():
        if key in value:
            _check(sub, value[key], _join(path, key), errors)


def validate_arguments(schema: dict, args: Any, tool_name: str = '') -> Optional[str]:
    """Проверить аргументы вызова. None — всё хорошо, иначе готовый русский текст для агента."""
    if args is None:
        args = {}
    errors = check(schema, args)
    if not errors:
        return None
    head = f'Аргументы инструмента {tool_name} не прошли проверку:' if tool_name else \
        'Аргументы не прошли проверку:'
    lines = [head] + ['- ' + e for e in errors[:MAX_ERRORS]]
    if len(errors) >= MAX_ERRORS:
        lines.append(f'- … показаны первые {MAX_ERRORS} ошибок')
    lines.append('Исправьте аргументы по inputSchema инструмента и повторите вызов.')
    return '\n'.join(lines)


def normalize(schema: Any, value: Any) -> Any:
    """Копия значения, где целые из JSON вида 5.0 стали int там, где схема ждёт integer.

    Вызывать после успешной check(): для неподходящих значений ничего не меняет.
    """
    if not isinstance(schema, dict):
        return value
    types = schema.get('type')
    wanted = types if isinstance(types, list) else ([types] if types else [])
    if isinstance(value, float) and 'integer' in wanted and 'number' not in wanted and _is_integer(value):
        return int(value)
    if isinstance(value, dict):
        props = schema.get('properties') if isinstance(schema.get('properties'), dict) else {}
        extra = schema.get('additionalProperties')
        out: Dict[str, Any] = {}
        for key, item in value.items():
            sub = props.get(key, extra if isinstance(extra, dict) else None)
            out[key] = normalize(sub, item)
        return out
    if isinstance(value, list):
        items = schema.get('items')
        return [normalize(items, item) for item in value]
    return value
