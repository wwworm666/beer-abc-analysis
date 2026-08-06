"""
Экспорт расчёта ЗП (/salary) в Google Таблицу — рендерер раскладки в Sheets API.

## Что это

Вторая кнопка экспорта на `/salary`: те же строки и формулы, что в .xlsx, но
записанные прямо в Google Таблицу — бухгалтерия работает в Таблицах (эталон
«Новая таблица (3).xlsx» сам выгружен оттуда). Плюс к .xlsx: Таблицы считают
формулы на сервере, поэтому «пустых формульных ячеек в предпросмотре» здесь
нет в принципе.

Раскладка — общая с .xlsx (`core/salary_layout.py`), так что форматы не
разъезжаются: строка/формула/цвет правится в одном месте.

## Файлы

- `core/salary_layout.py` — что писать (строки, формулы, цвета).
- `core/salary_gsheet.py`  — этот модуль: превращает раскладку в запросы
  Sheets API и выполняет их.
- `routes/salary.py`       — эндпоинт `POST /api/salary/export-gsheet`.

## Один адрес записи, два триггера (правка 2026-08-06)

И кнопка, и ночная задача пишут ОДНУ вкладку «Июль_2026_Автоматическая» в
таблице бухгалтерии `SALARY_SHEET_ID` и переписывают её целиком:

- **Ночная выгрузка в 04:00** — `sync_to_master()` через
  `core/salary_scheduler.py`, payload собирается на сервере, месяц — текущий
  (+ предыдущий до 7 числа).
- **Кнопка «Обновить Google»** — `export_to_gsheet()`: то же самое, но сейчас,
  за месяц, открытый на странице, и по данным этого расчёта.

Ручная вкладка месяца («июль2026») не трогается — в ней бухгалтер ведёт
«мосты», отпуск, доп доход и вычеты, которых приложение не знает. Разделение
вкладок и снимает конфликт.

**Почему кнопка больше не создаёт свой файл.** Создание таблицы
(`POST /v4/spreadsheets`) сервис-аккаунту недоступно — в проде это `403 The
caller does not have permission` (у него нет своего Диска). Владелец нажал
кнопку 2026-08-05 сразу после простановки штрафов и вместо результата получил
500. Запись в расшаренную таблицу работает, ею всё время ходила ночная
выгрузка. `create_new_spreadsheet()` остался фоллбэком для установки без
`SALARY_SHEET_ID` (там же шаринг новых файлов через `SALARY_SHARE_WITH`).

## Как работает

1. Авторизация — сервис-аккаунт Google Cloud (JSON-ключ). API-ключа
   недостаточно: запись в Таблицы требует OAuth-учётки, а сервис-аккаунт —
   единственный вариант без интерактивного входа пользователя.
2. Данные пишутся одним `batchUpdate` из общей раскладки — значения,
   оформление, закрепление шапки и ширины колонок.
3. Скоуп Drive — `drive.file`: сервис-аккаунт видит только то, что создал
   сам. Поэтому таблицу бухгалтерии он читает через Sheets API (она ему
   расшарена), а правами управляет только у собственных новых файлов.

## Переменные окружения

    GOOGLE_SA_JSON   путь к JSON-ключу сервис-аккаунта
                     (по умолчанию /app/secrets/google-sa.json)
    SALARY_SHEET_ID  id таблицы бухгалтерии — цель НОЧНОЙ выгрузки
    SALARY_SHARE_WITH  (опц.) email через запятую: кому шарить новые таблицы
                     кнопки. Задан — доступ по ссылке не включается
    SALARY_SHEET_FOLDER_ID  (опц.) папка Drive для новых таблиц

## Changelog

- 2026-08-06 — кнопка пишет ту же вкладку «..._Автоматическая», что ночная
  выгрузка: создание отдельного файла отвечало 403 (нет прав у сервис-аккаунта).
- 2026-08-01 (2) — кнопка создаёт новую таблицу; ночная выгрузка пишет в
  отдельную вкладку «..._Автоматическая» таблицы бухгалтерии.
- 2026-08-01 — модуль создан (вторая кнопка экспорта, запрос владельца).
"""

import json
import os

from core.salary_layout import (FILL_HEADER, FILL_RED_LABEL, FILL_TOTAL,
                                FIRST_DATA_ROW, FMT_HOURS, FMT_MONEY,
                                FONT_NAME, FONT_SIZE, HEADER_ROW, HEADERS,
                                WIDTH_EMP, WIDTH_LABEL, WIDTH_META, WIDTH_TOTAL,
                                Formula, auto_sheet_title, build_sheet)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive.file']

DEFAULT_KEY_PATH = '/app/secrets/google-sa.json'

# Ширины в Таблицах задаются в ПИКСЕЛЯХ, в Excel — в «символах» шрифта по
# умолчанию. Перевод по формуле Excel: px = width * 7 + 5 (округляем).
_PX_PER_CHAR = 7
_PX_PADDING = 5


class GSheetError(Exception):
    """Ошибка экспорта в Google Таблицу с человекочитаемым текстом."""


class GSheetNotConfigured(GSheetError):
    """Нет ключа сервис-аккаунта или библиотек — интеграция не настроена."""


class MasterSheetNotSet(GSheetError):
    """Не задан SALARY_SHEET_ID — ночной выгрузке некуда писать."""


def _px(width):
    return int(round(width * _PX_PER_CHAR + _PX_PADDING))


def _color(hex_color):
    """'FFF2CC' -> {'red': .., 'green': .., 'blue': ..} (Sheets — доли 0..1)."""
    if not hex_color:
        return None
    h = hex_color.lstrip('#')
    return {'red': int(h[0:2], 16) / 255.0,
            'green': int(h[2:4], 16) / 255.0,
            'blue': int(h[4:6], 16) / 255.0}


def _value(v):
    """Ячейка раскладки -> userEnteredValue Sheets API.

    Формулой становится ТОЛЬКО Formula. Обычная строка уходит в stringValue,
    и Таблицы хранят её текстом даже с ведущим «=» — formula injection через
    имя сотрудника невозможен by design (в отличие от openpyxl, где тип ячейки
    приходится вычислять из содержимого).
    """
    if v is None or v == '':
        return {}
    if isinstance(v, Formula):
        return {'formulaValue': str(v)}
    if isinstance(v, bool):
        return {'stringValue': str(v)}
    if isinstance(v, (int, float)):
        return {'numberValue': v}
    return {'stringValue': str(v)}


def _fmt(pattern):
    """Формат числа -> numberFormat Sheets API (General не задаётся)."""
    if not pattern or pattern == FMT_HOURS:
        return None
    return {'type': 'NUMBER', 'pattern': pattern}


def _cell(value, *, fill=None, bold=False, italic=False, color=None,
          fmt=None, center=False, wrap=False):
    """Одна ячейка: значение + оформление (шрифт эталона везде)."""
    text_format = {'fontFamily': FONT_NAME, 'fontSize': FONT_SIZE,
                   'bold': bold, 'italic': italic}
    if color:
        text_format['foregroundColor'] = _color(color)
    cell_format = {'textFormat': text_format}
    if fill:
        cell_format['backgroundColor'] = _color(fill)
    number_format = _fmt(fmt)
    if number_format:
        cell_format['numberFormat'] = number_format
    if center:
        cell_format['horizontalAlignment'] = 'CENTER'
        cell_format['verticalAlignment'] = 'MIDDLE'
    if wrap:
        cell_format['wrapStrategy'] = 'WRAP'
    return {'userEnteredValue': _value(value), 'userEnteredFormat': cell_format}


def build_grid(sheet):
    """Раскладка -> строки ячеек Sheets API (строка 1 пустая, шапка во 2-й)."""
    n_cols = sheet.total_col
    grid = [{'values': []}]                       # строка 1 — пустая

    header = [_cell(HEADERS[0], italic=True, center=True, wrap=True)]
    header += [_cell(h, bold=True, italic=True, center=True, wrap=True)
               for h in HEADERS[1:]]
    header += [_cell(name, fill=FILL_HEADER, bold=True, center=True, wrap=True)
               for name in sheet.employees]
    header.append(_cell('ИТОГО', fill=FILL_HEADER, bold=True, center=True, wrap=True))
    grid.append({'values': header})

    for r in sheet.rows:
        owner, deadline, checker = r.meta
        # тёмно-красная плашка вычетов — подпись белым
        label_color = 'FFFFFF' if r.label_fill == FILL_RED_LABEL else None
        values = [
            _cell(r.label, fill=r.label_fill, bold=r.label_bold,
                  italic=r.label_italic, color=label_color),
            _cell(owner or None, fill=r.owner_fill or r.meta_fill, center=True),
            _cell(deadline or None, fill=r.meta_fill, italic=True, center=True),
            _cell(checker or None, fill=r.meta_fill, center=True),
            _cell(r.tariff, fill=r.meta_fill, italic=True, fmt=FMT_MONEY, center=True),
        ]
        values += [_cell(r.cells[i] if i < len(r.cells) else None,
                         fill=r.data_fill, fmt=r.fmt)
                   for i in range(sheet.n_emp)]
        values.append(_cell(r.total, fill=FILL_TOTAL, bold=True, fmt=r.fmt))
        grid.append({'values': values[:n_cols]})

    return grid


def build_requests(sheet, sheet_id):
    """Раскладка -> запросы batchUpdate для листа `sheet_id`.

    Чистая функция без сети — на ней держатся тесты (реальный API в CI не
    дёргается).
    """
    grid = build_grid(sheet)
    n_rows = len(grid)
    n_cols = sheet.total_col

    requests = [
        # Полная перезапись значений и оформления диапазона листа
        {'updateCells': {
            'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': n_rows,
                      'startColumnIndex': 0, 'endColumnIndex': n_cols},
            'rows': grid,
            'fields': 'userEnteredValue,userEnteredFormat'}},
        # Шапка и метаданные закреплены — как в .xlsx
        {'updateSheetProperties': {
            'properties': {'sheetId': sheet_id,
                           'gridProperties': {'frozenRowCount': FIRST_DATA_ROW - 1,
                                              'frozenColumnCount': sheet.first_emp_col - 1}},
            'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}},
    ]

    # Ширины колонок: A, метаданные B..E, сотрудники, ИТОГО
    widths = [(0, 1, WIDTH_LABEL)]
    for i, w in enumerate(WIDTH_META):
        widths.append((1 + i, 2 + i, w))
    widths.append((sheet.first_emp_col - 1, sheet.total_col - 1, WIDTH_EMP))
    widths.append((sheet.total_col - 1, sheet.total_col, WIDTH_TOTAL))
    for start, end, width in widths:
        if end <= start:
            continue                              # нет сотрудников — нечего задавать
        requests.append({'updateDimensionProperties': {
            'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
                      'startIndex': start, 'endIndex': end},
            'properties': {'pixelSize': _px(width)},
            'fields': 'pixelSize'}})

    return requests


def _load_credentials():
    """Учётка сервис-аккаунта из JSON-ключа (путь — GOOGLE_SA_JSON)."""
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        raise GSheetNotConfigured(
            'Не установлены библиотеки Google API (google-auth, '
            'google-api-python-client) — пересоберите образ приложения') from e

    path = os.environ.get('GOOGLE_SA_JSON') or DEFAULT_KEY_PATH
    raw = os.environ.get('GOOGLE_SA_JSON_CONTENT')
    if raw:
        try:
            info = json.loads(raw)
        except ValueError as e:
            raise GSheetNotConfigured('GOOGLE_SA_JSON_CONTENT — не валидный JSON') from e
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    if not os.path.exists(path):
        raise GSheetNotConfigured(
            f"Нет ключа сервис-аккаунта ({path}). Экспорт в Google Таблицу не "
            f"настроен — см. docs/guides/google-sheets-export.md")
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def _service():
    try:
        from googleapiclient.discovery import build as build_service
    except ImportError as e:
        raise GSheetNotConfigured(
            'Не установлена библиотека google-api-python-client — '
            'пересоберите образ приложения') from e
    return build_service('sheets', 'v4', credentials=_load_credentials(),
                         cache_discovery=False)


def spreadsheet_url(spreadsheet_id, sheet_id=None):
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return f"{url}#gid={sheet_id}" if sheet_id is not None else url


def export_to_gsheet(payload: dict) -> dict:
    """Кнопка «Обновить Google»: обновить таблицу бухгалтерии ПРЯМО СЕЙЧАС.

    Пишет то же, что ночная выгрузка в 04:00, и в ТУ ЖЕ вкладку
    «Июль_2026_Автоматическая» таблицы `SALARY_SHEET_ID` — но за месяц,
    открытый на странице, и по данным этого расчёта. Одна Google-страница,
    которая обновляется сама ночью и по кнопке при необходимости.

    Раньше кнопка СОЗДАВАЛА новую таблицу и падала с 403 «The caller does not
    have permission»: у сервис-аккаунта нет своего Диска, и создание файла ему
    недоступно (лог прода 2026-08-05). Запись в расшаренную таблицу работает —
    ночная выгрузка ходила этим путём всё время. Создание нового файла осталось
    фоллбэком для установки, где таблица ещё не настроена.

    Возвращает {url, tab, spreadsheet_id}.
    """
    if (os.environ.get('SALARY_SHEET_ID') or '').strip():
        return sync_to_master(payload)
    return create_new_spreadsheet(payload)


def create_new_spreadsheet(payload: dict) -> dict:
    """Создать ОТДЕЛЬНУЮ новую таблицу с расчётом (фоллбэк без SALARY_SHEET_ID).

    Требует, чтобы сервис-аккаунту было куда писать файл: включённый Drive API
    и доступное хранилище. В проде этот путь отвечает 403 — там задан
    SALARY_SHEET_ID и используется запись в таблицу бухгалтерии.
    """
    sheet = build_sheet(payload)
    spreadsheets = _service().spreadsheets()

    try:
        created = spreadsheets.create(body={
            'properties': {'title': f"Расчёт ЗП — {sheet.title}"},
            'sheets': [{'properties': {'title': sheet.title}}],
        }, fields='spreadsheetId,sheets.properties').execute()
    except Exception as e:
        # Типовой отказ: сервис-аккаунту нельзя создавать файлы (нет Диска /
        # выключен Drive API). Правильный путь — писать в расшаренную таблицу
        raise GSheetError(
            'Не удалось создать новую таблицу: у сервис-аккаунта нет прав на '
            'создание файлов. Задайте SALARY_SHEET_ID (id таблицы бухгалтерии, '
            'расшаренной на сервис-аккаунт) — тогда выгрузка пойдёт в неё. '
            f"См. docs/guides/google-sheets-export.md. ({e})") from e
    spreadsheet_id = created['spreadsheetId']
    sheet_id = created['sheets'][0]['properties']['sheetId']

    spreadsheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': build_requests(sheet, sheet_id)}).execute()

    # Файл принадлежит сервис-аккаунту: без выдачи прав владелец его не
    # откроет. Best-effort — таблица уже создана и ссылка валидна.
    _grant_access(spreadsheet_id)
    _move_to_folder(spreadsheet_id)

    return {'url': spreadsheet_url(spreadsheet_id, sheet_id),
            'tab': sheet.title,
            'spreadsheet_id': spreadsheet_id}


def sync_to_master(payload: dict) -> dict:
    """Ночная выгрузка: переписать вкладку «..._Автоматическая» в таблице ЗП.

    Цель — `SALARY_SHEET_ID` (таблица бухгалтерии). Вкладка отдельная от
    ручной («июль2026»), поэтому переписывается целиком без подтверждений:
    ручные строки бухгалтера живут в соседней вкладке и не задеваются.
    """
    sheet = build_sheet(payload)
    sheet.title = auto_sheet_title(payload.get('month') or '')

    spreadsheet_id = (os.environ.get('SALARY_SHEET_ID') or '').strip()
    if not spreadsheet_id:
        raise MasterSheetNotSet(
            'Не задан SALARY_SHEET_ID — ночной выгрузке некуда писать '
            '(см. docs/guides/google-sheets-export.md)')

    spreadsheets = _service().spreadsheets()
    try:
        meta = spreadsheets.get(spreadsheetId=spreadsheet_id,
                                fields='sheets.properties').execute()
    except Exception as e:
        raise GSheetError(
            f"Таблица {spreadsheet_id} недоступна. Проверьте, что она "
            f"расшарена на сервис-аккаунт с правом «Редактор». ({e})") from e

    existing = {s['properties']['title']: s['properties'] for s in meta.get('sheets', [])}
    prop = existing.get(sheet.title)
    if prop:
        sheet_id = prop['sheetId']
        # Лист мог остаться от прошлого месяца с бОльшим числом сотрудников:
        # чистим целиком, иначе справа останутся колонки-призраки
        spreadsheets.values().clear(
            spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'", body={}).execute()
    else:
        added = spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{'addSheet': {'properties': {'title': sheet.title}}}]}
        ).execute()
        sheet_id = added['replies'][0]['addSheet']['properties']['sheetId']

    spreadsheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': build_requests(sheet, sheet_id)}).execute()

    return {'url': spreadsheet_url(spreadsheet_id, sheet_id),
            'tab': sheet.title,
            'spreadsheet_id': spreadsheet_id}


def _drive():
    from googleapiclient.discovery import build as build_service
    return build_service('drive', 'v3', credentials=_load_credentials(),
                         cache_discovery=False)


def _grant_access(spreadsheet_id):
    """Выдать права на новую таблицу.

    `SALARY_SHARE_WITH` задан — шарим на эти адреса (Редактор), иначе доступ
    «всем, у кого есть ссылка» (выбор владельца 2026-08-01: файл создаёт
    сервис-аккаунт, и без прав ссылка открывается только ему).

    Best-effort: таблица уже создана, и неудачная выдача прав не повод валить
    экспорт — ссылку всегда можно расшарить руками.
    """
    emails = [e.strip() for e in (os.environ.get('SALARY_SHARE_WITH') or '').split(',')
              if e.strip()]
    try:
        drive = _drive()
        if emails:
            for email in emails:
                drive.permissions().create(
                    fileId=spreadsheet_id, sendNotificationEmail=False,
                    body={'type': 'user', 'role': 'writer', 'emailAddress': email}
                ).execute()
        else:
            drive.permissions().create(
                fileId=spreadsheet_id,
                body={'type': 'anyone', 'role': 'writer'}).execute()
    except Exception as e:
        print(f"[GSHEET WARNING] права на таблицу {spreadsheet_id} не выданы: {e}")


def _move_to_folder(spreadsheet_id):
    """Перенести новую таблицу в папку SALARY_SHEET_FOLDER_ID (если задана).

    Best-effort: с скоупом drive.file папка видна, только если её создал сам
    сервис-аккаунт, поэтому перенос может не пройти — файл просто останется
    на Диске сервис-аккаунта, ссылка при этом рабочая.
    """
    folder = (os.environ.get('SALARY_SHEET_FOLDER_ID') or '').strip()
    if not folder:
        return
    try:
        _drive().files().update(fileId=spreadsheet_id, addParents=folder,
                                fields='id').execute()
    except Exception as e:
        print(f"[GSHEET WARNING] таблица не перенесена в папку {folder}: {e}")
