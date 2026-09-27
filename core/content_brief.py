"""
Бриф сети для ИИ-агента контент-плана раздела «Гости».

## Что это

Постоянные правила сети, по которым ИИ-агент (Claude по MCP) пишет черновики
контент-плана: что за сеть и бары, каким тоном говорим, какие рубрики и ритм,
о чём не пишем, как соблюдаем ограничения рекламы алкоголя, что и как снимаем,
примеры удачных постов. Агент читает бриф целиком перед каждым черновиком
(GET /api/content-plan/brief). Владелец правит его на странице «Контент-план»:
кнопка «Бриф для агента» открывает выдвижную карточку со всеми полями
(автосохранение, счётчики длины; `?brief=1` в адресе открывает её сразу).

Бриф ничего не публикует и не утверждает: черновики агента появляются в плане
с пометкой «ИИ» и ждут проверки (core/content_plan.py, раздел «ИИ-агент»).

## Файлы

| Файл | Роль |
|------|------|
| `core/content_brief.py` | этот модуль: структура, затравка, проверка, слияние, хранилище |
| `routes/content_plan.py` | GET / PUT `/api/content-plan/brief` (ошибки: 400, 503) |
| `static/js/guest_hub/content_plan.js` | карточка «Бриф для агента» |
| `tests/test_content_brief.py` | тесты (self-runnable) |

Данные: `content_brief.json` на постоянном диске (`core/storage_paths`), рядом
lock-файл `content_brief.json.lock`.

## Структура

    {version: 1,
     sections: {network, tone, rubrics, rhythm, taboo, alcohol_ads_rules,
                photo_rules, notes: str,
                examples: [str],
                bars: {bolshoy|ligovskiy|kremenchugskaya|varshavskaya:
                       {character, audience, hours, kitchen, events, photo_spots: str}}},
     updated_at: 'YYYY-MM-DDTHH:MM' (МСК) | null,
     updated_by: 'anna' | 'anna · агент' (правка через MCP) | null}

Смысл каждого поля (подпись и подсказка) — TEXT_SECTIONS и BAR_FIELDS; тот
же текст уходит в ответе GET (`schema`): его читают и экран, и агент.
Ключи баров — как в core/content_plan.BAR_KEYS (= core/venues_config
PHYSICAL_VENUES); `schema.bars` сопоставляет ключ с названием, адресом и
числом кранов из core/venues_config.

## Пределы длины

Длина = число символов Unicode (`len`), как счётчик в браузере.

| Что | Предел | Почему |
|---|---|---|
| текстовый раздел | 3000 (`SECTION_TEXT_MAX`) | страница правил: длиннее агент выполняет хуже, а владелец не перечитывает |
| пример поста | 4096 (`EXAMPLE_TEXT_MAX` = `TG_TEXT_LIMIT`) | самый длинный пост плана — сообщение Telegram без фото |
| примеров | 10 (`EXAMPLES_MAX`) | образцов хватает, чтобы уловить голос; больше — архив, а не образец |
| поле бара | 1000 (`BAR_FIELD_MAX`) | абзац о баре |
| весь бриф | 40 000 (`BRIEF_TOTAL_MAX`) | агент перечитывает бриф целиком перед каждым черновиком; мост MCP обрезает ответ длиннее 60 000 знаков (core/mcp/bridge.py, RESULT_TEXT_LIMIT) — 40 000 оставляют запас на описание полей (`schema`, ~4 000) и экранирование JSON |

«Весь бриф» = сумма длин всех текстовых разделов, примеров и полей баров
(`brief_total`). Правка, после которой бриф длиннее 40 000 знаков И длиннее,
чем был, — 400; правка, которая бриф сокращает, проходит даже сверх предела
(если предел понизят, бриф можно сокращать по частям). Пределы полей
проверяются только у переданных полей: старое длинное поле не мешает править
соседнее. Пример: бриф 39 990 знаков, в «Тон» дописали 20 → 40 010 > 40 000 и
больше, чем было → 400 «Бриф длиннее 40 000 знаков (стало бы 40 010)».

## Слияние: PUT /api/content-plan/brief {sections: {...}}

- меняются только переданные поля, остальное остаётся как было;
- текстовый раздел и поле бара заменяются целиком; null — пустая строка;
- examples заменяется всем списком; пустые примеры (из одних пробелов)
  отбрасываются, остальные сохраняются как есть;
- bars сливается по барам и полям: {bars: {ligovskiy: {hours: '…'}}} меняет
  только часы Лиговского;
- неизвестный ключ тела, раздел, бар или поле, неверный тип, превышение
  предела — ValueError (400), не сохраняется НИЧЕГО (проверка до записи);
- правка без изменений (те же значения) файл не пишет и updated_at не меняет;
- updated_at / updated_by — при каждой записи; подпись через MCP —
  «<login> · агент» (core/content_plan.actor_label).

Ответ: {brief, stored, total, changed: ['tone', 'bars.ligovskiy.hours', …]}.

## Затравка

Файла нет — действует затравка в памяти (`seed_brief`): раздел «О сети» —
список баров с названием, адресом и числом кранов из core/venues_config,
остальное пусто. На диск затравка попадает вместе с первой правкой (как
стартовый набор core/supplier_directory.py). Ответ GET несёт stored=false,
экран подписывает «ещё не сохранён — показана затравка».

## Хранение

Паттерн core/supplier_directory.py: запись под threading.Lock и файловой
блокировкой (core/json_store.file_lock), строгое перечитывание файла внутри
блокировки, атомарная запись (atomic_write_json). Файл есть, но не читается,
не JSON, неожиданной структуры, с неизвестным разделом, баром, полем или
версией новее этой — ContentBriefUnavailable (API 503) и на чтение, и на
запись; файл НИКОГДА не перезаписывается: иначе одна правка стёрла бы бриф
(или поля, которых эта версия не понимает). Часы подменяемы
(`ContentBriefStore(now_fn=...)`) — тесты детерминированы.

## Что сломается, если менять неправильно

- `_load` на ошибке вернёт затравку вместо исключения — следующая правка
  перезапишет весь бриф затравкой.
- Поднять BRIEF_TOTAL_MAX к 60 000 — ответ GET по MCP начнёт обрезаться, и
  агент прочитает бриф не целиком (без предупреждения в самих правилах).
- Сделать examples слиянием по индексу — удаление примера на экране станет
  невозможным (сервер вернёт удалённый пример обратно).

## Changelog

- 2026-09-27 — модуль создан (MCP-платформа: поддержка агента в контент-плане).
"""

import copy
import json
import os
import threading
from typing import Callable, Dict, List, Optional, Tuple

from core import msk_time
from core.content_plan import BAR_BY_KEY, BAR_KEYS, TG_TEXT_LIMIT, actor_label
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path
from core.venues_config import VENUES

SCHEMA_VERSION = 1
DATA_FILE_NAME = 'content_brief.json'

# ---------------------------------------------------------------------------
# Пределы длины (обоснование — таблица «Пределы длины» в докстроке).
# ---------------------------------------------------------------------------
SECTION_TEXT_MAX = 3000          # текстовый раздел: страница правил
EXAMPLE_TEXT_MAX = TG_TEXT_LIMIT  # пример поста: самый длинный пост плана (4096)
EXAMPLES_MAX = 10                # примеров удачных постов
BAR_FIELD_MAX = 1000             # поле бара: абзац
BRIEF_TOTAL_MAX = 40000          # весь бриф (сумма длин всех строк)
# Только для пояснения на экране: мост MCP обрезает ответ длиннее этого
# (core/mcp/bridge.py, RESULT_TEXT_LIMIT). Модуль моста не импортируется:
# бриф не должен зависеть от MCP-пакета.
MCP_RESULT_LIMIT = 60000

# Текстовые разделы: (ключ, подпись, подсказка). Порядок — порядок хранения.
TEXT_SECTIONS = (
    ('network', 'О сети',
     'Что за сеть и чем отличается: бары, адреса, краны, формат. Затравка — из справочника баров сервиса: '
     'проверьте адреса и допишите.'),
    ('tone', 'Тон и голос',
     'Как говорим с гостями: на «вы» или на «ты», длина фраз, юмор, каких интонаций избегаем.'),
    ('rubrics', 'Рубрики',
     'Постоянные рубрики: название, о чём, площадка, как часто. Например: «Таплист пятницы» — пятница, 18:00, '
     'Telegram каждого бара.'),
    ('rhythm', 'Ритм публикаций',
     'Сколько постов в неделю на каждой площадке, в какие дни и часы, сколько рассылок бота в месяц.'),
    ('taboo', 'Табу',
     'О чём не пишем и каких слов не используем.'),
    ('alcohol_ads_rules', 'Реклама алкоголя',
     'Как соблюдаем ограничения рекламы алкоголя (закон «О рекламе», ст. 21) и правила площадок: чего нельзя '
     'обещать и показывать, какие пометки обязательны.'),
    ('photo_rules', 'Фото и видео',
     'Что и как снимаем: свет, ракурсы, люди в кадре (только с согласия), чего не должно быть в кадре.'),
    ('notes', 'Заметки',
     'Всё остальное, что агенту стоит знать: сезонные поводы, партнёры, поставщики.'),
)
TEXT_KEYS = tuple(key for key, _label, _hint in TEXT_SECTIONS)
TEXT_LABELS = {key: label for key, label, _hint in TEXT_SECTIONS}
TEXT_HINTS = {key: hint for key, _label, hint in TEXT_SECTIONS}

EXAMPLES_LABEL = 'Примеры удачных постов'
EXAMPLES_HINT = 'Тексты, которые агенту стоит брать за образец голоса и формата: по одному посту в поле.'
BARS_LABEL = 'Бары'
BARS_HINT = 'Чем отличается каждый бар: агент пишет и для Telegram-канала конкретного бара.'

# Поля бара: (ключ, подпись, подсказка).
BAR_FIELDS = (
    ('character', 'Характер', 'Атмосфера и отличие от других баров сети.'),
    ('audience', 'Гости', 'Кто приходит и когда: будни, выходные, поводы.'),
    ('hours', 'Часы работы', 'Когда открыт, особые дни.'),
    ('kitchen', 'Кухня', 'Что есть на кухне, фирменные блюда.'),
    ('events', 'События', 'Регулярные события: дегустации, квизы, трансляции.'),
    ('photo_spots', 'Где снимать', 'Места в баре для фото: стена кранов, окно, стойка.'),
)
BAR_FIELD_KEYS = tuple(key for key, _label, _hint in BAR_FIELDS)
BAR_FIELD_LABELS = {key: label for key, label, _hint in BAR_FIELDS}

SECTION_KEYS = TEXT_KEYS + ('examples', 'bars')
# Порядок разделов в карточке «Бриф для агента» (и в schema.sections).
SCREEN_ORDER = ('network', 'tone', 'rubrics', 'rhythm', 'taboo', 'alcohol_ads_rules', 'photo_rules',
                'examples', 'bars', 'notes')
STORED_KEYS = ('version', 'sections', 'updated_at', 'updated_by')


def _num(value: int) -> str:
    """40000 -> '40 000' (неразрывный пробел между тысячами, как GH.fmtNum)."""
    return f'{value:,}'.replace(',', ' ')


PURPOSE = ('Бриф — постоянные правила сети для ИИ-агента контент-плана. Агент читает его целиком перед каждым '
           'черновиком (по MCP) и пишет посты по этим правилам: о сети и барах, нужным тоном и рубриками, в нужном '
           'ритме, без запретных тем, с учётом ограничений рекламы алкоголя и того, что можно снять. Бриф ничего '
           'не публикует и не утверждает: черновики агента появляются в плане с пометкой «ИИ» и ждут вашей '
           'проверки.')
LIMITS_NOTE = (f'Пределы: раздел — до {_num(SECTION_TEXT_MAX)} знаков, пример поста — до {_num(EXAMPLE_TEXT_MAX)} '
               f'(сообщение Telegram без фото), примеров — до {EXAMPLES_MAX}, поле бара — до {_num(BAR_FIELD_MAX)}, '
               f'весь бриф — до {_num(BRIEF_TOTAL_MAX)}. Агент перечитывает бриф перед каждым черновиком: длинные '
               f'правила он выполняет хуже, а ответ MCP длиннее {_num(MCP_RESULT_LIMIT)} знаков обрезается. Правка, '
               'которая удлиняет бриф сверх предела, не сохраняется; сокращать можно всегда.')
MERGE_RULES = (
    'PUT {"sections": {...}} меняет только переданные поля; остальное остаётся как было.',
    'Текстовый раздел и поле бара заменяются целиком; null — пустая строка.',
    'examples заменяется всем списком; пустые примеры (из одних пробелов) отбрасываются.',
    'bars сливается по барам и полям: {"bars": {"ligovskiy": {"hours": "…"}}} меняет только часы Лиговского.',
    'Неизвестный раздел, бар или поле, неверный тип или превышение предела — ошибка 400, не сохраняется ничего.',
)


class ContentBriefUnavailable(RuntimeError):
    """Файл брифа есть, но прочитать его нельзя: писать поверх запрещено (API 503)."""


# ---------------------------------------------------------------------------
# Справочник баров и затравка
# ---------------------------------------------------------------------------

def bars_reference() -> List[dict]:
    """[{key, name, short, address, taps}] в порядке BAR_KEYS: название, адрес и
    число кранов — из core/venues_config (короткое имя — core/content_plan)."""
    out = []
    for key in BAR_KEYS:
        venue = VENUES.get(key) or {}
        bar = BAR_BY_KEY[key]
        out.append({'key': key, 'name': venue.get('name') or bar['name'], 'short': bar['short'],
                    'address': venue.get('address') or '', 'taps': venue.get('taps')})
    return out


def _bar_name(key: str) -> str:
    return (VENUES.get(key) or {}).get('name') or BAR_BY_KEY[key]['name']


def seed_network_text() -> str:
    """Затравка раздела «О сети»: список баров с адресом и числом кранов.

    'Бары сети:\\n— Лиговский — адрес: Лиговский пр., кранов: 12;\\n…' —
    последний пункт с точкой. Пустые адрес или краны опускаются."""
    refs = bars_reference()
    lines = ['Бары сети:']
    for index, ref in enumerate(refs):
        parts = []
        if ref['address']:
            parts.append(f'адрес: {ref["address"]}')
        if ref['taps']:
            parts.append(f'кранов: {ref["taps"]}')
        tail = ' — ' + ', '.join(parts) if parts else ''
        lines.append(f'— {ref["name"]}{tail}' + ('.' if index == len(refs) - 1 else ';'))
    return '\n'.join(lines)


def empty_sections() -> dict:
    """Все разделы пустые: строки '', примеров нет, у каждого бара все поля ''."""
    sections: Dict[str, object] = {key: '' for key in TEXT_KEYS}
    sections['examples'] = []
    sections['bars'] = {key: {field: '' for field in BAR_FIELD_KEYS} for key in BAR_KEYS}
    return sections


def seed_brief() -> dict:
    """Бриф, пока файла нет: «О сети» — из справочника баров, остальное пусто."""
    sections = empty_sections()
    sections['network'] = seed_network_text()
    return {'version': SCHEMA_VERSION, 'sections': sections, 'updated_at': None, 'updated_by': None}


def brief_total(sections: dict) -> int:
    """Длина брифа: сумма len всех текстовых разделов, примеров и полей баров."""
    total = sum(len(sections.get(key) or '') for key in TEXT_KEYS)
    total += sum(len(item or '') for item in sections.get('examples') or [])
    for fields in (sections.get('bars') or {}).values():
        total += sum(len(value or '') for value in fields.values())
    return total


def schema() -> dict:
    """Описание полей для экрана и агента: подписи, подсказки, пределы, бары,
    назначение брифа и правила слияния (один источник текста — этот модуль)."""
    specs = []
    for key in SCREEN_ORDER:
        if key in TEXT_LABELS:
            specs.append({'key': key, 'type': 'text', 'label': TEXT_LABELS[key], 'hint': TEXT_HINTS[key],
                          'max': SECTION_TEXT_MAX})
        elif key == 'examples':
            specs.append({'key': key, 'type': 'list', 'label': EXAMPLES_LABEL, 'hint': EXAMPLES_HINT,
                          'max': EXAMPLE_TEXT_MAX, 'max_items': EXAMPLES_MAX})
        else:
            specs.append({'key': key, 'type': 'bars', 'label': BARS_LABEL, 'hint': BARS_HINT,
                          'max': BAR_FIELD_MAX})
    return {
        'sections': specs,
        'bar_fields': [{'key': key, 'label': label, 'hint': hint, 'max': BAR_FIELD_MAX}
                       for key, label, hint in BAR_FIELDS],
        'bars': bars_reference(),
        'total_max': BRIEF_TOTAL_MAX,
        'purpose': PURPOSE,
        'limits_note': LIMITS_NOTE,
        'merge_rules': list(MERGE_RULES),
    }


# ---------------------------------------------------------------------------
# Проверка файла и правки
# ---------------------------------------------------------------------------

def _broken(text: str) -> ContentBriefUnavailable:
    return ContentBriefUnavailable(f'Файл брифа повреждён: {text}')


def check_stored(data) -> dict:
    """Проверить содержимое файла -> полный бриф (недостающие поля — пустые).

    Любая неожиданность — ContentBriefUnavailable: неизвестный ключ, раздел,
    бар или поле, не строка там, где строка, версия новее SCHEMA_VERSION. Не
    чиним молча: запись поверх стёрла бы то, чего эта версия не понимает."""
    if not isinstance(data, dict) or not isinstance(data.get('sections'), dict):
        raise _broken('неожиданная структура')
    unknown_top = sorted(str(key) for key in data if key not in STORED_KEYS)
    if unknown_top:
        raise _broken('неизвестные поля ' + ', '.join(unknown_top))
    version = data.get('version', SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= SCHEMA_VERSION:
        raise _broken(f'версия {version!r}')
    raw = data['sections']
    unknown = sorted(str(key) for key in raw if key not in SECTION_KEYS)
    if unknown:
        raise _broken('неизвестные разделы ' + ', '.join(unknown))
    sections = empty_sections()
    for key in TEXT_KEYS:
        value = raw.get(key, '')
        if not isinstance(value, str):
            raise _broken(f'раздел {key}')
        sections[key] = value
    examples = raw.get('examples', [])
    if not isinstance(examples, list) or not all(isinstance(item, str) for item in examples):
        raise _broken('примеры')
    sections['examples'] = list(examples)
    bars = raw.get('bars', {})
    if not isinstance(bars, dict):
        raise _broken('бары')
    for bar, fields in bars.items():
        if bar not in BAR_KEYS or not isinstance(fields, dict):
            raise _broken(f'бар {bar}')
        for field, value in fields.items():
            if field not in BAR_FIELD_KEYS or not isinstance(value, str):
                raise _broken(f'поле {field} бара {bar}')
            sections['bars'][bar][field] = value
    for name in ('updated_at', 'updated_by'):
        if data.get(name) is not None and not isinstance(data.get(name), str):
            raise _broken(name)
    return {'version': SCHEMA_VERSION, 'sections': sections, 'updated_at': data.get('updated_at'),
            'updated_by': data.get('updated_by')}


def _text(value, limit: int, label: str) -> str:
    """Строка поля: null -> ''; не строка -> ValueError; длиннее limit -> ValueError."""
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError(f'{label}: нужна строка')
    if len(value) > limit:
        raise ValueError(f'{label} длиннее {_num(limit)} знаков (сейчас {_num(len(value))})')
    return value


def _examples(value) -> List[str]:
    """Список примеров: null -> []; пустые (из пробелов) отбрасываются; каждый
    до EXAMPLE_TEXT_MAX; после отбрасывания — не больше EXAMPLES_MAX."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('Примеры: нужен список строк')
    out = []
    for number, item in enumerate(value, 1):
        if item is None:
            continue
        if not isinstance(item, str):
            raise ValueError(f'Пример {number}: нужна строка')
        if not item.strip():
            continue
        if len(item) > EXAMPLE_TEXT_MAX:
            raise ValueError(f'Пример {number} длиннее {_num(EXAMPLE_TEXT_MAX)} знаков (сейчас {_num(len(item))})')
        out.append(item)
    if len(out) > EXAMPLES_MAX:
        raise ValueError(f'Примеров больше {EXAMPLES_MAX} (передано {len(out)}): оставьте лучшие')
    return out


def _bars(value) -> Dict[str, Dict[str, str]]:
    """{ключ бара: {поле: текст}} -> проверенные переданные поля."""
    if not isinstance(value, dict):
        raise ValueError('Бары: нужен объект {ключ бара: {поле: текст}}')
    out: Dict[str, Dict[str, str]] = {}
    for bar, fields in value.items():
        if bar not in BAR_KEYS:
            raise ValueError(f'Неизвестный бар «{bar}». Бары: {", ".join(BAR_KEYS)}')
        if not isinstance(fields, dict):
            raise ValueError(f'Бар {bar}: нужен объект {{поле: текст}}')
        clean = {}
        for field, text in fields.items():
            if field not in BAR_FIELD_LABELS:
                raise ValueError(f'Неизвестное поле бара «{field}». Поля: {", ".join(BAR_FIELD_KEYS)}')
            clean[field] = _text(text, BAR_FIELD_MAX, f'{_bar_name(bar)} — «{BAR_FIELD_LABELS[field]}»')
        out[bar] = clean
    return out


def clean_patch(body) -> dict:
    """Тело PUT {sections: {...}} -> проверенные переданные разделы.

    ValueError (400) — не объект; ключ тела кроме sections; нет sections;
    неизвестный раздел, бар или поле; неверный тип; превышен предел поля."""
    if not isinstance(body, dict):
        raise ValueError('Нужен JSON-объект вида {"sections": {...}}')
    extra = sorted(str(key) for key in body if key != 'sections')
    if extra:
        raise ValueError('Неизвестные поля запроса: ' + ', '.join(extra) + '. Правки брифа передаются в sections')
    if 'sections' not in body:
        raise ValueError('Нет sections: передайте {"sections": {"раздел": "текст", ...}}')
    sections = body['sections']
    if not isinstance(sections, dict):
        raise ValueError('sections: нужен объект {раздел: значение}')
    patch: Dict[str, object] = {}
    for key, value in sections.items():
        if key in TEXT_LABELS:
            patch[key] = _text(value, SECTION_TEXT_MAX, f'Раздел «{TEXT_LABELS[key]}»')
        elif key == 'examples':
            patch[key] = _examples(value)
        elif key == 'bars':
            patch[key] = _bars(value)
        else:
            raise ValueError(f'Неизвестный раздел брифа «{key}». Разделы: {", ".join(SECTION_KEYS)}')
    return patch


def merge(sections: dict, patch: dict) -> Tuple[dict, List[str]]:
    """Слить проверенную правку с разделами -> (новые разделы, [что изменилось]).

    Пути изменений: 'tone', 'examples', 'bars.ligovskiy.hours'. Значение, равное
    прежнему, изменением не считается."""
    merged = copy.deepcopy(sections)
    changed: List[str] = []
    for key, value in patch.items():
        if key == 'bars':
            for bar, fields in value.items():
                for field, text in fields.items():
                    if merged['bars'][bar][field] != text:
                        merged['bars'][bar][field] = text
                        changed.append(f'bars.{bar}.{field}')
        elif merged[key] != value:
            merged[key] = value
            changed.append(key)
    return merged, changed


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------

class ContentBriefStore:
    """Бриф на диске. now_fn — часы (для тестов)."""

    def __init__(self, data_file: Optional[str] = None, now_fn: Optional[Callable] = None):
        self.data_file = data_file or get_data_path(DATA_FILE_NAME)
        self._now_fn = now_fn or msk_time.now
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'

    def now_str(self) -> str:
        """Текущая минута по Москве: 'YYYY-MM-DDTHH:MM' (как метки контент-плана)."""
        moment = self._now_fn()
        if moment.tzinfo is not None:
            moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
        return moment.strftime('%Y-%m-%dT%H:%M')

    def is_stored(self) -> bool:
        return os.path.exists(self.data_file)

    def _load(self) -> Tuple[dict, bool]:
        """(бриф, есть ли файл). Нет файла — затравка; файл битый — исключение."""
        if not os.path.exists(self.data_file):
            return seed_brief(), False
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f'[CONTENT_BRIEF] cannot read {self.data_file}: {e}')
            raise ContentBriefUnavailable(f'Файл брифа не читается: {e}') from e
        return check_stored(data), True

    def payload(self) -> dict:
        """Ответ GET: {brief, stored, total, schema}."""
        brief, stored = self._load()
        return {'brief': brief, 'stored': stored, 'total': brief_total(brief['sections']), 'schema': schema()}

    def update(self, body, user: Optional[dict]) -> dict:
        """PUT: слить правку (правила — «Слияние» в докстроке).
        -> {brief, stored, total, changed}. ValueError — 400, ContentBriefUnavailable — 503."""
        patch = clean_patch(body)
        with self._lock, file_lock(self._lock_path):
            brief, stored = self._load()
            merged, changed = merge(brief['sections'], patch)
            if changed:
                old_total = brief_total(brief['sections'])
                new_total = brief_total(merged)
                if new_total > BRIEF_TOTAL_MAX and new_total > old_total:
                    raise ValueError(f'Бриф длиннее {_num(BRIEF_TOTAL_MAX)} знаков (стало бы {_num(new_total)}): '
                                     'сократите примеры или разделы — агент читает бриф целиком перед каждым '
                                     'черновиком')
                brief = {'version': SCHEMA_VERSION, 'sections': merged, 'updated_at': self.now_str(),
                         'updated_by': actor_label(user)}
                atomic_write_json(self.data_file, brief)
                stored = True
        return {'brief': brief, 'stored': stored, 'total': brief_total(brief['sections']), 'changed': changed}


_store: Optional[ContentBriefStore] = None
_store_guard = threading.Lock()


def get_content_brief_store(data_file: Optional[str] = None) -> ContentBriefStore:
    """Ленивый синглтон на процесс (файл на томе общий для воркеров). data_file
    (для тестов) заменяет синглтон хранилищем на этом файле."""
    global _store
    with _store_guard:
        if data_file is not None and (_store is None or _store.data_file != data_file):
            _store = ContentBriefStore(data_file)
        elif _store is None:
            _store = ContentBriefStore()
        return _store
