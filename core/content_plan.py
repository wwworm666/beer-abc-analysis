"""
Контент-план раздела «Гости»: материалы, размещения, готовность, утверждение.

## Что это

План публикаций и рассылок на месяц. МАТЕРИАЛ — это тема/пост (название, текст,
фото). РАЗМЕЩЕНИЕ — выход этого материала в конкретную площадку (Telegram-канал
бара, Instagram сети, рассылка бота) в конкретный день и час. У одного материала
может быть много размещений: «Октоберфест» — в четыре Telegram-канала баров и в
Instagram сети.

Этап «только интерфейс» (2026-09-26): НИЧЕГО никуда не отправляется. Хранение,
статусы, проверки, предпросмотр, утверждение и журнал — настоящие. Отправка не
подключена (`DELIVERY_CONNECTED` — все False), поэтому «вышло» отмечают вручную.

## Файлы

| Файл | Роль |
|------|------|
| `core/content_plan.py` | этот модуль: модель, правила, операции, живые данные |
| `core/content_media.py` | файлы фото/видео на диске |
| `core/content_brief.py` | бриф сети для ИИ-агента (правила, по которым он пишет черновики) |
| `routes/content_plan.py` | HTTP API и страница `/content-plan` (и бриф: `/api/content-plan/brief`) |
| `tests/test_content_plan.py` | тесты (self-runnable) |

Данные: `content_plan.json` на постоянном диске (`core/storage_paths`):
`{version: 1, materials: {id: M}, log: [...]}`.

## Площадки (CHANNELS) — лимиты это факты платформ

| key | бар | текст | фото/видео |
|-----|-----|-------|------------|
| telegram | обязателен конкретный бар (у каждого бара свой канал) | 4096 без медиа; 1024 — подпись, если есть медиа | до 10 (медиагруппа), по умолчанию не обязательны |
| instagram | 'all' (один аккаунт сети), можно конкретный бар | 2200 (подпись) | 1..10, хотя бы одно ОБЯЗАТЕЛЬНО |
| bot | 'all' или бар (охват аудитории) | как telegram | как telegram |

Источники чисел: Telegram Bot API — sendMessage до 4096 символов, подпись к
медиа (caption) до 1024, sendMediaGroup до 10 файлов; Instagram — подпись до
2200 знаков, карусель до 10 файлов. Длина = число символов Unicode (`len`);
для кириллицы и латиницы совпадает со счётчиком в браузере.

## Статусы размещения (хранятся)

draft (черновик) → approved (утверждено, ждёт времени) ⇄ paused (утверждено, но
остановлено) → published (вышло; пока отмечается вручную). failed — ошибка
отправки (зарезервировано для будущей отправки). cancelled — отменено, остаётся
для истории.

Переходы (`ACTIONS`), любой другой — 409:
- pause: approved → paused; resume: paused → approved (400, если время выхода прошло);
- unapprove: approved|paused → draft; mark_published: approved|paused|failed → published;
- cancel: draft|approved|paused|failed → cancelled; restore: cancelled → draft;
- retry: failed → approved.

## Готовность (вычисляется при чтении, не хранится)

Проверяется только у черновика (у остальных статусов missing = []).
effective_text = placement.text, если он не null, иначе material.base_text.
effective_media = placement.media (только имена, которые ещё есть у материала),
если не null, иначе все файлы материала. Коды по порядку:

1. no_live_source «не выбран источник данных» — материал с актуальными данными без источника;
2. no_text «нет текста» (готовая публикация, текст пустой) / no_template «нет шаблона»
   (актуальные данные, шаблон пустой);
3. bad_placeholder «неизвестная подстановка {x}» — в шаблоне {…} не из списка
   `PLACEHOLDERS` (по одной строке на каждую неизвестную подстановку);
4. no_media «нет фото» — Instagram без медиа, либо у материала отмечено «Нужно фото»;
5. too_many_media «больше 10 файлов»;
6. text_too_long «текст длиннее N знаков» — только у готовой публикации:
   N = 1024 (подпись), если у Telegram/бота есть медиа, иначе 4096; Instagram 2200.
   Длину шаблона с актуальными данными проверяет предпросмотр (подставленный
   таплист заранее неизвестен);
7. no_bar «не выбран бар» — Telegram с баром 'all'; бот с аудиторией «Подписчики,
   выбравшие бар» и баром 'all'; материал с актуальными данными на любой
   площадке с 'all' — текст «для таплиста выберите бар»;
8. no_audience «не выбрана аудитория» — бот без аудитории;
9. no_date «нет даты», no_time «нет времени»;
10. in_past «время выхода уже прошло» — дата+время раньше текущей минуты по Москве.

ready = статус draft и список пуст. Сравнение времени — с точностью до минуты:
публикация на 16:00 «в прошлом» с 16:01.

## Состояние для экрана (display_state)

draft + чего-то не хватает → incomplete «Не хватает: …»; draft + готово → ready
«Готово к утверждению»; approved и время ещё впереди → scheduled «Запланировано»;
approved и время прошло → overdue «Время вышло, выход не отмечен» (пока отправка
не подключена, это напоминание отметить выход вручную); paused «На паузе»;
published «Вышло»; failed «Ошибка отправки»; cancelled «Отменено».
Край: approved без даты/времени (старые данные) считается scheduled.

У материала с актуальными данными (kind 'live') утверждён ШАБЛОН, а таплист
подставится в момент выхода, поэтому scheduled подписывается «Шаблон утверждён,
данные — при выходе» (`LIVE_SCHEDULED_LABEL`); display_state остаётся scheduled.

Цвет на экране выбирается по display_state, а не по tone: tone у scheduled и
published одинаковый (success), но это разные состояния («в очереди» и «вышло»).

## Что показывается у размещения (effective_text / effective_media)

- published и failed со снимком утверждения (approved_snapshot) — текст и файлы
  ИЗ СНИМКА: это то, что ушло (или уходило) в площадку; content_source =
  'snapshot'. Правка общего текста или удаление файла после выхода их не меняют.
- все остальные — текущие данные материала (content_source = 'current').
  У approved/paused текущее и снимок совпадают всегда: любое изменение
  содержания снимает утверждение (см. «Правила редактирования»).
- media_items = [{name, kind, url, original_name}] для effective_media. kind — по
  расширению имени, url — маршрут раздачи файлов, поэтому ссылка работает и для
  файла, которого у материала уже нет (он остался только в снимке; с диска такой
  файл не удаляется, см. `_media_referenced`). original_name — null, если файла
  у материала уже нет.
- У вышедшего материала с актуальными данными снимок хранит ШАБЛОН, а не
  подставленный таплист: предпросмотр такого размещения строится по данным на
  сейчас, а не на момент выхода.

## Сводка материала (summary) — правила, первое совпадение

Отменённые размещения не учитываются, кроме случая «отменены все».
total = число неотменённых размещений, ready = из них готовых, counts — по всем;
rule — номер сработавшего правила, state — какое состояние оно описывает
(display_state или 'empty' для правила 1): по нему экран выбирает цвет.

1. размещений нет → «Только тема» (muted);
2. все отменены → «Отменено» (muted);
3. есть ошибка отправки → «Ошибка отправки: N» (danger);
4. есть незаполненные → «Не хватает: …» (warning). Одно неотменённое размещение —
   недостающее через запятую, без повторов, по порядку: «Не хватает: нет фото,
   нет времени». Размещений больше одного — у каждой причины указано, ГДЕ её не
   хватает (площадка и бар), одинаковые причины собраны вместе, группы через «; »:
   «Не хватает: нет фото — IG Сеть, TG Лиг; нет времени — TG Вар». Если причины
   не хватает во всех неотменённых размещениях — «— везде». Разбивка для
   подсказки — summary.missing [{code, text, where, everywhere}];
5. есть просроченные → «Время вышло: N» (warning);
6. есть готовые → «Готово к утверждению» (accent); если есть и запланированные —
   «Готово к утверждению: N из M», M = total;
7. все вышли → «Вышло» (success);
8. часть вышла, остальные запланированы или на паузе → «Вышло: N из M» (success),
   N — вышедших, M = total;
9. есть на паузе → «На паузе: N» (muted);
10. иначе (все запланированы) → «Запланировано» (success); у материала с
    актуальными данными — «Шаблон утверждён, данные — при выходе».

Дата материала = самая ранняя дата неотменённых размещений, иначе дата темы
(planned_date), иначе нет.

## Вид «по всем месяцам» (state_payload)

Ссылки полосы внимания «Время вышло» и «Ошибки отправки» считают размещения за
ЛЮБОЙ месяц (отправка не подключена — просроченное копится через границу
месяца). Поэтому GET /api/content-plan?state=overdue|failed БЕЗ month отдаёт все
материалы любого месяца, у которых есть размещение в этом состоянии (тот же
вид ответа, что у месяца, плюс scope='state' и state; in_month у всех true,
stats — по этим материалам). С month — обычный месяц (фильтр ?state= — на
экране). Состояния — `CROSS_MONTH_STATES`.

## Правила редактирования

- Изменилось СОДЕРЖАНИЕ утверждённого/стоящего на паузе размещения (канал, бар,
  аудитория, итоговый текст, итоговые медиа, тип материала или источник) →
  размещение возвращается в черновик, утверждение снимается, в журнале
  unapprove_auto, ответ несёт unapproved: [id]. Сравнивается «подпись
  содержания» до и после правки, поэтому правка общего текста НЕ трогает
  размещения со своей версией текста. То же правило применяется к failed
  (иначе повтор отправки ушёл бы со старым снимком при новом тексте).
- Перенос даты/времени сохраняет утверждение; новое время в прошлом у
  утверждённого/на паузе → 400 «Нельзя перенести утверждённую публикацию в прошлое»;
  стереть дату или время у утверждённого нельзя (сначала снять утверждение).
- Вышедшее/отменённое размещение не редактируется (400).
- Название, заметка, дата темы и «Нужно фото» — не содержание (галочка влияет
  только на готовность).
- Удалить материал с вышедшими размещениями нельзя (409).
- Удаление файла убирает его из подборок размещений материала, КРОМЕ вышедших и
  отменённых: они только для чтения, их подборка — история. С диска файл
  удаляется, только когда на него не ссылается ни один материал и ни один
  снимок утверждения (повтор и копирование делят файлы).

## Операции

- approve: утверждаются только готовые черновики, остальные — в skipped с
  причинами; если среди запрошенных есть рассылка бота, нужен confirm_bot=true,
  иначе 400 и ничего не утверждается. Снимок {text, media} на момент утверждения.
- bulk_pause: бар 'all' — вся сеть; бар X — только размещения с bar == X
  (размещения сети 'all' пауза одного бара НЕ трогает: общий Instagram не должен
  останавливаться из-за одного бара). Трогаются только публикации с временем
  впереди; снятие паузы пропускает прошедшие и сообщает о них.
- shift: сдвиг на -60..60 дней (не 0) всех невышедших и неотменённых размещений
  и даты темы; если утверждённое окажется в прошлом — 400, ничего не меняется.
  60 дней — два месяца: дальше это уже планирование другого месяца.
- repeat: копии материала на каждый выбранный день недели месяца, не раньше
  сегодняшнего дня и не на занятые серией даты. Источник и копии — одна серия.
- copy_month (подробно — `copy_month()` и `COPY_RULES`):
  * обычный материал: ОПОРНАЯ дата (`copy_anchor`: дата темы; нет её — самая
    ранняя дата неотменённого размещения внутри месяца-источника; нет и
    таких — самая ранняя дата неотменённого размещения) переносится по правилу
    «n-й день недели месяца», а ВСЕ остальные даты материала сдвигаются на то же
    число дней. Сдвиг кратен 7 (день недели сохраняется), поэтому у каждой даты
    сохраняется и день недели, и порядок, и интервал: анонс во вторник остаётся
    за 4 дня до события в субботу. Переносить каждую дату отдельно нельзя: даты
    одного материала из разных «недель месяца» (1–7, 8–14, …) расходятся, и анонс
    оказывается после события. Дата, ушедшая за месяц назначения, остаётся (это
    честный сдвиг), о ней — заметка. Опора — дата темы, а не самая ранняя дата:
    дата темы задаёт месяц материала (month := месяц planned_date), и только так
    копия гарантированно остаётся в месяце назначения;
  * серия (материалы с общим series.id): перегенерируется на каждый день её
    дней недели в новом месяце. Набор размещений копии — ОБЪЕДИНЕНИЕ
    неотменённых размещений всех дней серии без повторов по (площадка, бар,
    аудитория, время): разовая отмена одного бара в один день не должна пропасть
    из всего следующего месяца. Текст и файлы — из самого раннего дня серии, где
    есть неотменённое размещение. Если дни серии различались (набор размещений,
    время, тексты/файлы) — заметка.

## Живые данные (render_live)

Шаблон с подстановками {бар}, {дата}, {таплист}, {кранов}. Строка таплиста:
«{кран}. {пивоварня} — {название}, {стиль}, {крепость}%» (пустые части
опускаются; крепость — округление до 0,01 по правилу half-up, без хвостовых
нулей, десятичная запятая: 5.0 → «5», 6.5 → «6,5»; 0 и пусто — не пишется).
Публикация будет остановлена, если: бар не выбран; на кранах нет активных
позиций; у крана нет проверенной связи с Untappd; есть неизвестная подстановка;
итоговый текст длиннее предела площадки.

Предел площадки (`text_limit_for`) — тот же, что у готовой публикации: если
передана площадка (channel), то Telegram и бот — 1024 (подпись), когда у
размещения есть фото/видео (has_media), и 4096 без них; Instagram — 2200.
Площадка не передана — 4096 (общая проверка шаблона «на текущих данных»).
Готовность черновика длину живого материала НЕ проверяет: подставленный
таплист заранее неизвестен, его длина видна только в предпросмотре.

## Время

Всё по Москве (`core/msk_time`); в файле — наивные строки: дата 'YYYY-MM-DD',
время 'HH:MM', метки 'YYYY-MM-DDTHH:MM'. День недели: 0 = понедельник.
Часы магазина подменяемы (`ContentPlanStore(now_fn=...)`) — тесты детерминированы.

## Хранение

Как `core/supplier_directory.py`: запись под threading.Lock + файловой
блокировкой, строгое перечтение, атомарная запись. Файла нет → пустой план.
Файл есть, но не читается или повреждён → ContentPlanUnavailable (API 503),
и файл НИКОГДА не перезаписывается. Журнал хранит последние 5000 записей
(≈ год активной работы четырёх баров; больше — разбухание файла).

## ИИ-агент: происхождение, пояснения, подпись (MCP, 2026-09-27)

Агент на стороне Claude работает с планом по MCP: мост (core/mcp/bridge.py)
исполняет те же маршруты от имени владельца и кладёт в пользователя
'via_mcp': True (`is_agent_user`). Клиент это поле не присылает и подделать
через тело запроса не может.

- origin материала: 'agent', если материал создан через MCP, иначе 'human'
  (`origin_of`). Ставится сервером ПРИ СОЗДАНИИ записи и больше не меняется:
  origin в POST/PATCH — 400 (`_reject_origin`). Старые материалы без поля
  читаются как 'human'. Значение вне ('human', 'agent') в файле — файл
  повреждён (503): неизвестное значение не перезаписываем.
- Копии (повтор по дням недели, копирование месяца) — НОВЫЕ записи, их
  origin — по тому, кто выполнил действие: человек скопировал материал
  агента — копии 'human'; агент скопировал месяц — копии 'agent'. Источник
  не меняется. Так «Удалить черновики ИИ» трогает только то, что агент сделал
  сам.
- agent_rationale «Почему этот пост» и shot_list «Что снять» — строки до
  AGENT_TEXT_MAX (2000) знаков, как заметка: это пояснение к посту и список
  кадров, не текст публикации. Принимаются в POST/PATCH материалов и в
  create_material; правка их не снимает утверждение (не содержание). У копий
  они сохраняются только вместе с содержанием (тот же флаг keep, что у
  текста и файлов: повтор — всегда; копирование месяца — при with_content
  или у материала с актуальными данными), иначе пустые.
- Подпись автора (`actor_label`): действие через MCP подписывается
  «<login> · агент» — в журнале (by) и в полях *_by (created_by, updated_by,
  approved_by, published_by, uploaded_by).
- Черновик ИИ (`is_agent_draft`, поле agent_draft в ответе): origin 'agent'
  и все размещения — draft или cancelled (размещений нет — тоже черновик).
  `delete_agent_drafts(month)` удаляет черновики ИИ плана месяца (month
  материала == month) одной записью; остальные материалы агента — в skipped с
  причиной. Материалы людей и утверждённое не трогаются никогда.
- approve_preview(origin=...) — окно «Утвердить готовые» под фильтром
  «Только от ИИ»; в каждой строке — origin материала.

## Changelog

- 2026-09-26 — модуль создан (этап «только интерфейс», без отправки).
- 2026-09-27 — правки по ревью: вид «по всем месяцам» для «Время вышло» /
  «Ошибки отправки»; вышедшее размещение показывает снимок (content_source,
  media_items), удаление файла не трогает вышедшие/отменённые; предел длины
  живых данных по площадке; подписи «Шаблон утверждён…», «Вышло: N из M»,
  «Не хватает: … — где»; kind в предпросмотре утверждения; copy_month —
  опорная дата со сдвигом (порядок размещений сохраняется) и объединение
  размещений серии.
- 2026-09-27 (MCP) — поддержка ИИ-агента: origin материала (ставит сервер по
  via_mcp), agent_rationale и shot_list, подпись «<login> · агент», флаг
  agent_draft и delete_agent_drafts, фильтр origin в approve_preview. Бриф
  сети для агента — отдельный модуль core/content_brief.py.
"""

import copy
import json
import os
import re
import secrets
import threading
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Dict, List, Optional, Tuple

from core import content_media, msk_time
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path

SCHEMA_VERSION = 1
DATA_FILE_NAME = 'content_plan.json'

# ---------------------------------------------------------------------------
# Бары (ключи как в core/venues_config.PHYSICAL_VENUES), порядок отображения.
# ---------------------------------------------------------------------------
BARS = (
    {'key': 'bolshoy', 'name': 'Большой пр. В.О', 'short': 'ВО'},
    {'key': 'ligovskiy', 'name': 'Лиговский', 'short': 'Лиг'},
    {'key': 'kremenchugskaya', 'name': 'Кременчугская', 'short': 'Крем'},
    {'key': 'varshavskaya', 'name': 'Варшавская', 'short': 'Вар'},
)
BAR_KEYS = tuple(b['key'] for b in BARS)
BAR_BY_KEY = {b['key']: b for b in BARS}
BAR_ALL = 'all'                 # размещение на всю сеть (например, единый Instagram)
BAR_ALL_NAME = 'Вся сеть'
BAR_ALL_SHORT = 'Сеть'
# Ключ бара → id бара в таплисте (core/taplist.BAR_NAMES).
TAPLIST_BAR_IDS = {'bolshoy': 'bar1', 'ligovskiy': 'bar2',
                   'kremenchugskaya': 'bar3', 'varshavskaya': 'bar4'}

# ---------------------------------------------------------------------------
# Площадки. Числа — факты платформ (см. докстроку модуля).
# ---------------------------------------------------------------------------
TG_TEXT_LIMIT = 4096        # Telegram Bot API: sendMessage, текст до 4096 символов
TG_CAPTION_LIMIT = 1024     # Telegram Bot API: подпись к фото/видео/медиагруппе до 1024
TG_MEDIA_MAX = 10           # Telegram Bot API: sendMediaGroup до 10 файлов
IG_CAPTION_LIMIT = 2200     # Instagram: подпись к публикации до 2200 знаков
IG_MEDIA_MAX = 10           # Instagram: карусель до 10 файлов

CHANNELS = {
    'telegram': {'key': 'telegram', 'name': 'Telegram', 'short': 'TG', 'bar_rule': 'required',
                 'text_limit': TG_TEXT_LIMIT, 'caption_limit': TG_CAPTION_LIMIT,
                 'media_max': TG_MEDIA_MAX, 'media_required': False},
    'instagram': {'key': 'instagram', 'name': 'Instagram', 'short': 'IG', 'bar_rule': 'network',
                  'text_limit': IG_CAPTION_LIMIT, 'caption_limit': IG_CAPTION_LIMIT,
                  'media_max': IG_MEDIA_MAX, 'media_required': True},
    'bot': {'key': 'bot', 'name': 'Бот', 'short': 'Бот', 'bar_rule': 'optional',
            'text_limit': TG_TEXT_LIMIT, 'caption_limit': TG_CAPTION_LIMIT,
            'media_max': TG_MEDIA_MAX, 'media_required': False},
}
CHANNEL_ORDER = ('telegram', 'instagram', 'bot')
# Отправка не реализована ни в одну площадку (этап «только интерфейс»).
DELIVERY_CONNECTED = {'telegram': False, 'instagram': False, 'bot': False}

# Сегменты аудитории рассылки бота. Размер неизвестен, пока бот не подключён.
AUDIENCES = (
    {'key': 'bot_all', 'name': 'Все подписчики бота', 'needs_bar': False},
    {'key': 'bot_bar', 'name': 'Подписчики, выбравшие бар', 'needs_bar': True},
    {'key': 'bot_recent_30', 'name': 'Были в баре за последние 30 дней', 'needs_bar': False},
    {'key': 'bot_lapsed_60', 'name': 'Не были 60 дней и дольше', 'needs_bar': False},
)
AUDIENCE_BY_KEY = {a['key']: a for a in AUDIENCES}
AUDIENCE_SIZE_NOTE = 'Бот не подключён: размер аудитории появится после интеграции'

# Живые данные: единственный источник — таплист бара.
PLACEHOLDERS = ('{бар}', '{дата}', '{таплист}', '{кранов}')
LIVE_SOURCES = {
    'taplist': {
        'key': 'taplist', 'name': 'Таплист бара',
        'placeholders': [
            {'token': '{бар}', 'hint': 'полное название бара'},
            {'token': '{дата}', 'hint': 'дата выхода, например «9 октября»'},
            {'token': '{таплист}', 'hint': 'список кранов: номер, пивоварня, название, стиль, крепость'},
            {'token': '{кранов}', 'hint': 'число активных кранов'},
        ],
    },
}

KINDS = ('fixed', 'live')
STATUSES = ('draft', 'approved', 'paused', 'published', 'failed', 'cancelled')
STATUS_NAMES = {'draft': 'черновик', 'approved': 'утверждено', 'paused': 'на паузе',
                'published': 'вышло', 'failed': 'ошибка отправки', 'cancelled': 'отменено'}
# Состояния, которые снимаются в черновик при изменении содержания.
UNAPPROVE_ON_CONTENT = ('approved', 'paused', 'failed')

DISPLAY_STATES = ('incomplete', 'ready', 'scheduled', 'overdue', 'paused',
                  'published', 'failed', 'cancelled')
DISPLAY_LABELS = {
    'ready': 'Готово к утверждению',
    'scheduled': 'Запланировано',
    'overdue': 'Время вышло, выход не отмечен',
    'paused': 'На паузе',
    'published': 'Вышло',
    'failed': 'Ошибка отправки',
    'cancelled': 'Отменено',
}
DISPLAY_TONES = {'incomplete': 'warning', 'ready': 'accent', 'scheduled': 'success',
                 'overdue': 'warning', 'paused': 'muted', 'published': 'success',
                 'failed': 'danger', 'cancelled': 'muted'}
# Подпись scheduled у материала с актуальными данными: утверждён шаблон, а данные
# (таплист) подставятся в момент выхода — это не «замороженный» пост.
LIVE_SCHEDULED_LABEL = 'Шаблон утверждён, данные — при выходе'
# Статусы, у которых экран показывает снимок утверждения, а не текущие данные:
# снимок — это то, что ушло (published) или уходило (failed) в площадку.
SNAPSHOT_STATUSES = ('published', 'failed')
# Состояния, для которых есть вид «по всем месяцам» (ссылки полосы внимания:
# счётчики «Время вышло» и «Ошибки отправки» считают любой месяц).
CROSS_MONTH_STATES = ('overdue', 'failed')

SUMMARY_RULES = (
    'Отменённые размещения не учитываются, кроме случая «отменены все». Первое совпадение:',
    '1. Размещений нет — «Только тема».',
    '2. Все размещения отменены — «Отменено».',
    '3. Есть ошибка отправки — «Ошибка отправки: N».',
    '4. Чего-то не хватает — «Не хватает: …»: всё недостающее без повторов; если размещений '
    'несколько — у каждой причины сказано, где её не хватает («нет фото — IG Сеть»; «везде» — во всех).',
    '5. Время вышло, а выход не отмечен — «Время вышло: N».',
    '6. Есть готовые — «Готово к утверждению» (если часть уже запланирована — «N из M»).',
    '7. Все вышли — «Вышло».',
    '8. Часть вышла, остальные запланированы или на паузе — «Вышло: N из M».',
    '9. Есть на паузе — «На паузе: N».',
    '10. Иначе (все запланированы) — «Запланировано»; у материала с актуальными данными — '
    '«Шаблон утверждён, данные — при выходе».',
)
# Как copy_month переносит даты — для подсказки в окне «Скопировать месяц».
COPY_RULES = (
    'Опорная дата материала — дата темы; если её нет — самая ранняя дата размещения в месяце-источнике.',
    'Опорная дата переносится на тот же день недели с тем же номером в месяце: вторая пятница → '
    'вторая пятница. Если такого дня нет (пятая пятница) — на последний такой день месяца.',
    'Остальные даты материала сдвигаются на столько же дней: дни недели, порядок и интервалы '
    'размещений сохраняются (анонс остаётся до события). Дата, ушедшая за месяц, остаётся — о ней заметка.',
    'Серии повторов создаются заново на каждый их день недели. Размещения копии — все размещения '
    'дней серии (разовая отмена в один день не переносится на весь месяц); текст и фото — из самого '
    'раннего дня серии. Если дни различались — заметка.',
    'Материалы без даты копируются без даты. Отменённые размещения не копируются.',
    'Все копии — черновики: ничего не утверждается и не публикуется.',
)
READINESS_RULES = (
    'Готовность проверяется только у черновика.',
    'Текст: свой текст размещения, если задан, иначе общий текст материала.',
    'Telegram и бот: до 4096 знаков без фото, до 1024 с фото; до 10 файлов.',
    'Instagram: до 2200 знаков, от 1 до 10 файлов.',
    'Telegram — конкретный бар; бот — аудитория; таплист — конкретный бар.',
    'Нужны дата и время, и время выхода ещё не прошло.',
)

# ---------------------------------------------------------------------------
# Лимиты хранения (не платформенные: защита от опечаток и разбухания файла).
# ---------------------------------------------------------------------------
TITLE_MAX = 200             # название — строка в таблице, не текст поста
TEXT_MAX = 10000            # общий/свой текст: > 4096 (самый длинный пост) с запасом на черновик
NOTE_MAX = 2000             # внутренняя заметка
ORIGINAL_NAME_MAX = 200     # исходное имя загруженного файла (только для подписи)
SOURCE_REVIEW_ID_MAX = 64   # id отзыва (r_ + 12 hex), запас на будущий формат
MATERIAL_MEDIA_MAX = 20     # файлов у материала: 2 x максимум площадки (10), чтобы
                            # держать разные подборки для разных размещений
LOG_MAX = 5000              # записей журнала (см. «Хранение» в докстроке)
SHIFT_DAYS_MAX = 60         # сдвиг материала, дней в каждую сторону
YEAR_MIN, YEAR_MAX = 2020, 2100

# ---------------------------------------------------------------------------
# ИИ-агент (MCP): происхождение материала и его пояснения (см. докстроку).
# ---------------------------------------------------------------------------
ORIGIN_HUMAN = 'human'
ORIGIN_AGENT = 'agent'
ORIGINS = (ORIGIN_HUMAN, ORIGIN_AGENT)
ORIGIN_NAMES = {ORIGIN_HUMAN: 'люди', ORIGIN_AGENT: 'ИИ-агент'}
# Подпись действия через MCP: «anna · агент» (журнал и поля *_by).
AGENT_SUFFIX = ' · агент'
# «Почему этот пост» и «Что снять»: предел как у заметки (NOTE_MAX = 2000) —
# абзац пояснения или список кадров, который владелец прочтёт при проверке
# черновика; длиннее — это уже второй текст поста, а не пояснение к нему.
AGENT_TEXT_MAX = 2000
# Черновик агента («Удалить черновики ИИ»): ни одно размещение не ушло
# дальше черновика; отменённые не мешают.
AGENT_DRAFT_STATUSES = ('draft', 'cancelled')
AGENT_DRAFT_RULE = ('Черновик ИИ — материал, который создал агент через MCP, если ни одно его размещение '
                    'не утверждено, не стоит на паузе, не вышло и не с ошибкой отправки: все размещения — '
                    'черновики или отменены (или размещений нет). Материалы людей и утверждённое не удаляются.')

MEDIA_URL_PREFIX = '/api/content-plan/media/'

MONTHS_GEN = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
              'августа', 'сентября', 'октября', 'ноября', 'декабря')
MONTHS_SHORT = ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')
MONTHS_NOM = ('январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль',
              'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь')
WEEKDAY_SHORT = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
WEEKDAY_NAMES = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')
# Окончание порядкового числительного по роду названия дня: «5-й понедельник»,
# «5-я пятница», «5-е воскресенье».
WEEKDAY_ORDINAL_SUFFIX = ('й', 'й', 'я', 'й', 'я', 'я', 'е')

ACTIONS = {
    # action: (из каких статусов, в какой)
    'pause': (('approved',), 'paused'),
    'resume': (('paused',), 'approved'),
    'unapprove': (('approved', 'paused'), 'draft'),
    'mark_published': (('approved', 'paused', 'failed'), 'published'),
    'cancel': (('draft', 'approved', 'paused', 'failed'), 'cancelled'),
    'restore': (('cancelled',), 'draft'),
    'retry': (('failed',), 'approved'),
}
ACTION_CONFLICT = {
    'pause': 'На паузу ставится только утверждённая публикация',
    'resume': 'Снять с паузы можно только публикацию на паузе',
    'unapprove': 'Снять утверждение можно только с утверждённой публикации',
    'mark_published': 'Отметить вышедшей можно только утверждённую публикацию',
    'cancel': 'Отменить можно только невышедшее и неотменённое размещение',
    'restore': 'Вернуть можно только отменённое размещение',
    'retry': 'Повторить отправку можно только после ошибки отправки',
}
ACTION_LOG = {
    'pause': 'Пауза', 'resume': 'Пауза снята', 'unapprove': 'Утверждение снято',
    'mark_published': 'Отмечено вышедшим', 'cancel': 'Отменено',
    'restore': 'Возвращено в черновики', 'retry': 'Повтор отправки',
}

# Конец строки — \Z, а не $: `$` пропускает завершающий перевод строки.
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\Z')
_MONTH_RE = re.compile(r'^(\d{4})-(\d{2})\Z')
_TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})\Z')
_TOKEN_RE = re.compile(r'\{[^{}\n]*\}')
_WS = re.compile(r'\s+')
_TRUE_WORDS = {'1', 'true', 'yes', 'on', 'да'}
_FALSE_WORDS = {'', '0', 'false', 'no', 'off', 'нет', 'none', 'null'}


class ContentPlanUnavailable(RuntimeError):
    """Файл контент-плана есть, но прочитать его нельзя: писать поверх запрещено."""


class ContentPlanNotFound(LookupError):
    """Материал, размещение или файл не найдены (API 404)."""

    def __str__(self):
        return self.args[0] if self.args else 'Не найдено'


class ContentPlanConflict(Exception):
    """Операция противоречит состоянию (API 409)."""

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra


# ---------------------------------------------------------------------------
# Разбор входа
# ---------------------------------------------------------------------------

def is_agent_user(user: Optional[dict]) -> bool:
    """Действие пришло через MCP: мост core/mcp/bridge.py кладёт в копию
    пользователя 'via_mcp': True (поле 'login' при этом прежнее). Клиент это
    поле не присылает: признак берётся только из current_user() сервера."""
    return bool(user and user.get('via_mcp'))


def actor_label(user: Optional[dict]) -> str:
    """Подпись автора действия для журнала (by) и полей *_by.

    login (иначе display_name, иначе 'unknown'); действие через MCP —
    «<login> · агент» (AGENT_SUFFIX): в истории видно, что правку сделал агент
    от имени владельца, а не владелец руками."""
    if not user:
        return 'unknown'
    name = user.get('login') or user.get('display_name') or 'unknown'
    return name + AGENT_SUFFIX if is_agent_user(user) else name


def origin_of(user: Optional[dict]) -> str:
    """origin новой записи материала: 'agent' через MCP, иначе 'human'."""
    return ORIGIN_AGENT if is_agent_user(user) else ORIGIN_HUMAN


# Прежнее имя внутри модуля: все операции подписываются через него.
_login = actor_label


def _new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(6)


def parse_month(value, field: str = 'Месяц') -> str:
    text = str(value or '').strip()
    match = _MONTH_RE.match(text)
    if not match:
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ')
    year, month = int(match.group(1)), int(match.group(2))
    if not YEAR_MIN <= year <= YEAR_MAX or not 1 <= month <= 12:
        raise ValueError(f'{field}: год {YEAR_MIN}–{YEAR_MAX}, месяц 01–12')
    return text


def parse_date(value, field: str = 'Дата') -> Optional[str]:
    """'YYYY-MM-DD' или None для пустого значения."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    if not _DATE_RE.match(text):
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ-ДД')
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise ValueError(f'{field}: такой даты нет') from None
    if not YEAR_MIN <= day.year <= YEAR_MAX:
        raise ValueError(f'{field}: год {YEAR_MIN}–{YEAR_MAX}')
    return text


def parse_time(value, field: str = 'Время') -> Optional[str]:
    """'HH:MM' (00:00–23:59) или None; '9:05' нормализуется в '09:05'."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    match = _TIME_RE.match(str(value).strip())
    if not match:
        raise ValueError(f'{field}: нужен формат ЧЧ:ММ')
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f'{field}: от 00:00 до 23:59')
    return f'{hour:02d}:{minute:02d}'


def parse_bool(value, field: str = 'Флаг') -> bool:
    """Флаг из JSON или формы: строки 'false'/'нет'/'0' — ложь, а не bool('false')."""
    if isinstance(value, str):
        word = value.strip().casefold()
        if word in _FALSE_WORDS:
            return False
        if word in _TRUE_WORDS:
            return True
        raise ValueError(f'{field}: нужно да/нет')
    return bool(value)


def parse_weekdays(value) -> List[int]:
    if not isinstance(value, (list, tuple)):
        raise ValueError('Дни недели: нужен список чисел 0..6 (0 = понедельник)')
    days = set()
    for item in value:
        if isinstance(item, bool):
            raise ValueError('Дни недели: нужен список чисел 0..6 (0 = понедельник)')
        try:
            number = int(item)
        except (TypeError, ValueError):
            raise ValueError('Дни недели: нужен список чисел 0..6 (0 = понедельник)') from None
        if not 0 <= number <= 6:
            raise ValueError('Дни недели: нужен список чисел 0..6 (0 = понедельник)')
        days.add(number)
    if not days:
        raise ValueError('Выберите хотя бы один день недели')
    return sorted(days)


def parse_days(value) -> int:
    """Сдвиг в днях: целое -60..60, не 0."""
    text = f'Сдвиг: целое число дней от -{SHIFT_DAYS_MAX} до {SHIFT_DAYS_MAX}, кроме 0'
    if isinstance(value, bool) or value is None or value == '':
        raise ValueError(text)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(text) from None
    if number != number or number in (float('inf'), float('-inf')) or number != int(number):
        raise ValueError(text)
    number = int(number)
    if number == 0 or abs(number) > SHIFT_DAYS_MAX:
        raise ValueError(text)
    return number


def parse_bar(value, field: str = 'Бар') -> str:
    text = str(value or '').strip()
    if text != BAR_ALL and text not in BAR_KEYS:
        raise ValueError(f'{field}: неизвестный бар «{text}»')
    return text


def parse_audience(value) -> Optional[dict]:
    """{segment} или None. Принимается и строка-ключ сегмента."""
    if value is None or value == '':
        return None
    if isinstance(value, str):
        segment = value.strip()
    elif isinstance(value, dict):
        segment = str(value.get('segment') or '').strip()
    else:
        raise ValueError('Аудитория: нужен сегмент рассылки')
    if not segment:
        return None
    if segment not in AUDIENCE_BY_KEY:
        raise ValueError(f'Неизвестная аудитория «{segment}»')
    return {'segment': segment}


def _norm_filter_bar(value) -> Optional[str]:
    """Фильтр по бару для чтения: '', None и 'all' — без фильтра."""
    text = str(value or '').strip()
    if not text or text == BAR_ALL:
        return None
    return text


# ---------------------------------------------------------------------------
# Даты
# ---------------------------------------------------------------------------

def _naive_msk(moment: datetime) -> datetime:
    if moment.tzinfo is not None:
        moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
    return moment


def fmt_stamp(moment: datetime) -> str:
    """'YYYY-MM-DDTHH:MM' — формат всех меток времени плана."""
    return moment.strftime('%Y-%m-%dT%H:%M')


def fmt_date_ru(value) -> str:
    """'2026-10-09' → '9 октября'."""
    day = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f'{day.day} {MONTHS_GEN[day.month - 1]}'


def fmt_date_short(value) -> str:
    """'2026-10-09' → '9 окт'."""
    day = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f'{day.day} {MONTHS_SHORT[day.month - 1]}'


def month_label(month: str) -> str:
    return f'{MONTHS_NOM[int(month[5:7]) - 1]} {month[:4]}'


def month_days(month: str) -> List[date]:
    year, mon = int(month[:4]), int(month[5:7])
    return [date(year, mon, d) for d in range(1, monthrange(year, mon)[1] + 1)]


def add_months(month: str, count: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + count
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def months_between(start: str, end: str) -> int:
    return (int(end[:4]) * 12 + int(end[5:7])) - (int(start[:4]) * 12 + int(start[5:7]))


def map_nth_weekday(day_iso: str, month_offset: int) -> Tuple[str, Optional[Tuple[int, int]]]:
    """Перенести дату на month_offset месяцев по правилу «n-й день недели месяца».

    n = (день - 1) // 7 + 1 (1..5) — какой по счёту это день недели в месяце.
    В целевом месяце берётся тот же день недели с тем же номером n; если n-го
    нет (5-я пятница в месяце с четырьмя пятницами) — последний такой день.
    -> (новая дата, (n, день недели) если пришлось взять последний, иначе None).
    """
    day = date.fromisoformat(day_iso)
    target = add_months(day_iso[:7], month_offset)
    weekday = day.weekday()
    nth = (day.day - 1) // 7 + 1
    same = [d for d in month_days(target) if d.weekday() == weekday]
    if nth <= len(same):
        return same[nth - 1].isoformat(), None
    return same[-1].isoformat(), (nth, weekday)


# ---------------------------------------------------------------------------
# Вычисления (чистые функции)
# ---------------------------------------------------------------------------

def effective_text(material: dict, placement: dict) -> str:
    text = placement.get('text')
    return text if text is not None else (material.get('base_text') or '')


def effective_media(material: dict, placement: dict) -> List[str]:
    names = [item['name'] for item in material.get('media') or []]
    chosen = placement.get('media')
    if chosen is None:
        return names
    have = set(names)
    result = []
    for name in chosen:
        if name in have and name not in result:
            result.append(name)
    return result


def placement_datetime(placement: dict) -> Optional[str]:
    if placement.get('date') and placement.get('time'):
        return f"{placement['date']}T{placement['time']}"
    return None


def unknown_placeholders(text: str) -> List[str]:
    """Подстановки {…}, которых нет в PLACEHOLDERS, без повторов, по порядку."""
    found = []
    for token in _TOKEN_RE.findall(text or ''):
        if token not in PLACEHOLDERS and token not in found:
            found.append(token)
    return found


def text_limit_for(channel: str, has_media: bool) -> int:
    spec = CHANNELS[channel]
    return spec['caption_limit'] if has_media else spec['text_limit']


def limit_note_for(channel: Optional[str], has_media: bool) -> str:
    """Откуда взят предел длины — для подсказки у счётчика знаков."""
    if not channel:
        return f'Площадка не выбрана: проверка по пределу сообщения Telegram — {TG_TEXT_LIMIT} знаков'
    spec = CHANNELS[channel]
    if spec['caption_limit'] == spec['text_limit']:
        return f'{spec["name"]}: подпись до {spec["text_limit"]} знаков'
    if has_media:
        return f'{spec["name"]}, с фото или видео: подпись до {spec["caption_limit"]} знаков'
    return f'{spec["name"]}, без фото: сообщение до {spec["text_limit"]} знаков'


def _segment(placement: dict) -> Optional[str]:
    return (placement.get('audience') or {}).get('segment')


def readiness(material: dict, placement: dict, now_str: str) -> List[dict]:
    """Чего не хватает черновику до утверждения (см. «Готовность» в докстроке)."""
    if placement.get('status') != 'draft':
        return []
    missing: List[dict] = []

    def add(code, text):
        missing.append({'code': code, 'text': text})

    channel = placement.get('channel')
    spec = CHANNELS[channel]
    live = material.get('kind') == 'live'
    text = effective_text(material, placement)
    media = effective_media(material, placement)

    if live and not material.get('live_source'):
        add('no_live_source', 'не выбран источник данных')
    if not text.strip():
        if live:
            add('no_template', 'нет шаблона')
        else:
            add('no_text', 'нет текста')
    if live:
        for token in unknown_placeholders(text):
            add('bad_placeholder', f'неизвестная подстановка {token}')
    if not media and (spec['media_required'] or material.get('media_required')):
        add('no_media', 'нет фото')
    if len(media) > spec['media_max']:
        add('too_many_media', f'больше {spec["media_max"]} файлов')
    if not live:
        limit = text_limit_for(channel, bool(media))
        if len(text) > limit:
            add('text_too_long', f'текст длиннее {limit} знаков')
    if placement.get('bar') == BAR_ALL:
        if live:
            add('no_bar', 'для таплиста выберите бар')
        elif channel == 'telegram' or (channel == 'bot' and _segment(placement) == 'bot_bar'):
            add('no_bar', 'не выбран бар')
    if channel == 'bot' and not _segment(placement):
        add('no_audience', 'не выбрана аудитория')
    if not placement.get('date'):
        add('no_date', 'нет даты')
    if not placement.get('time'):
        add('no_time', 'нет времени')
    moment = placement_datetime(placement)
    if moment and moment < now_str:
        add('in_past', 'время выхода уже прошло')
    return missing


def display_state(material: dict, placement: dict, now_str: str) -> Tuple[str, List[dict]]:
    """-> (display_state, missing)."""
    status = placement.get('status')
    if status == 'draft':
        missing = readiness(material, placement, now_str)
        return ('incomplete' if missing else 'ready'), missing
    if status == 'approved':
        moment = placement_datetime(placement)
        return ('overdue' if moment and moment < now_str else 'scheduled'), []
    return status, []


def display_label(state: str, missing: List[dict], live: bool = False) -> str:
    """Подпись состояния. live — материал с актуальными данными: его scheduled —
    утверждённый шаблон, а не готовый пост (`LIVE_SCHEDULED_LABEL`)."""
    if state == 'incomplete':
        return 'Не хватает: ' + ', '.join(item['text'] for item in missing)
    if state == 'scheduled' and live:
        return LIVE_SCHEDULED_LABEL
    return DISPLAY_LABELS[state]


def placement_content(material: dict, placement: dict) -> Tuple[str, List[str], str]:
    """Что показать как текст и файлы размещения -> (text, media, content_source).

    published/failed со снимком утверждения — снимок ('snapshot'): это то, что
    ушло в площадку, и правка материала после выхода его не меняет. Иначе —
    текущие effective_text/effective_media ('current'). Имена из снимка
    проверяются формой (content_media.is_valid_name): по ним строится URL.
    """
    snapshot = placement.get('approved_snapshot')
    if placement.get('status') in SNAPSHOT_STATUSES and isinstance(snapshot, dict):
        names: List[str] = []
        for name in snapshot.get('media') or []:
            if content_media.is_valid_name(name) and name not in names:
                names.append(name)
        text = snapshot.get('text')
        return ('' if text is None else str(text)), names, 'snapshot'
    return effective_text(material, placement), effective_media(material, placement), 'current'


def media_items(material: dict, names: List[str]) -> List[dict]:
    """[{name, kind, url, original_name}] для списка имён файлов.

    Не ищет файл в material.media: вышедшее размещение может ссылаться на файл,
    которого у материала уже нет (он остался только в снимке). kind — по
    расширению имени, url — маршрут раздачи; original_name — из материала или
    null. Диск не читается: файл из снимка не удаляется (`_media_referenced`)."""
    known = {item['name']: item for item in material.get('media') or []}
    return [{'name': name, 'kind': content_media.kind_of(name), 'url': MEDIA_URL_PREFIX + name,
             'original_name': (known.get(name) or {}).get('original_name')}
            for name in names]


def placement_place(placement: dict) -> str:
    """Где выходит размещение, коротко: 'TG Вар', 'IG Сеть', 'Бот Сеть'."""
    channel = CHANNELS.get(placement.get('channel'), {}).get('short', placement.get('channel'))
    bar = placement.get('bar')
    bar_short = BAR_ALL_SHORT if bar == BAR_ALL else BAR_BY_KEY.get(bar, {}).get('short', bar)
    return f'{channel} {bar_short}'


def audience_info(placement: dict) -> Optional[dict]:
    if placement.get('channel') != 'bot':
        return None
    segment = _segment(placement)
    spec = AUDIENCE_BY_KEY.get(segment)
    if not spec:
        return None
    return {'segment': segment, 'name': spec['name'], 'needs_bar': spec['needs_bar'],
            'size': None, 'size_note': AUDIENCE_SIZE_NOTE}


def material_date(material: dict) -> Optional[str]:
    dates = [p['date'] for p in material.get('placements') or []
             if p.get('status') != 'cancelled' and p.get('date')]
    if dates:
        return min(dates)
    return material.get('planned_date') or None


def is_agent_draft(material: dict) -> bool:
    """Черновик ИИ (`AGENT_DRAFT_RULE`): origin 'agent' и все размещения —
    draft или cancelled. Материал без размещений (тема) — тоже черновик."""
    return (material.get('origin') == ORIGIN_AGENT
            and all(p.get('status') in AGENT_DRAFT_STATUSES for p in material.get('placements') or []))


def guard_draft_mode(user: Optional[dict], material: dict) -> None:
    """Режим «чтение и черновики» (MCP-коннектор …/draft, core/mcp/spec.MODES):
    агент меняет только СВОИ черновики — материал origin 'agent', все размещения
    draft или cancelled (is_agent_draft). Иначе 409.
    
    Зачем: по расписанию агент читает отзывы гостей и описания пива; «команда»,
    внедрённая в такой текст, не должна переносить, менять или снимать утверждение
    с публикаций владельца. Режим ставит мост (core/mcp/bridge.py, поле mcp_mode
    пользователя); у людей на сайте его нет, для них правило не действует."""
    if (user or {}).get('mcp_mode') == 'draft' and not is_agent_draft(material):
        raise ContentPlanConflict(
            'В режиме «чтение и черновики» агент меняет только свои черновики: этот материал '
            'создан не агентом или в нём уже есть утверждённые размещения.')


def _missing_breakdown(active: list) -> List[dict]:
    """Недостающее по всем незаполненным размещениям: [{code, text, where,
    everywhere}] — причины в порядке появления (порядок размещений, затем порядок
    кодов готовности), where — места без повторов в порядке размещений,
    everywhere — причины не хватает во всех неотменённых размещениях."""
    order: List[dict] = []
    by_text: Dict[str, dict] = {}
    for state, missing, place in active:
        if state != 'incomplete':
            continue
        for item in missing:
            entry = by_text.get(item['text'])
            if entry is None:
                entry = {'code': item.get('code'), 'text': item['text'], 'where': [], 'hits': 0}
                by_text[item['text']] = entry
                order.append(entry)
            entry['hits'] += 1
            if place is not None and place not in entry['where']:
                entry['where'].append(place)
    total = len(active)
    return [{'code': e['code'], 'text': e['text'], 'where': e['where'],
             'everywhere': e['hits'] == total} for e in order]


def _missing_label(breakdown: List[dict], total: int, attributed: bool) -> str:
    """Подпись правила 4. Одно размещение (или места неизвестны) — «нет фото,
    нет времени»; несколько — «нет фото — IG Сеть, TG Лиг; нет времени — везде»."""
    if total <= 1 or not attributed:
        return 'Не хватает: ' + ', '.join(e['text'] for e in breakdown)
    parts = [f'{e["text"]} — ' + ('везде' if e['everywhere'] else ', '.join(e['where']))
             for e in breakdown]
    return 'Не хватает: ' + '; '.join(parts)


def material_summary(states: list, live: bool = False) -> dict:
    """Сводка материала по состояниям его размещений (правила — в докстроке).

    states — [(display_state, missing)] или [(display_state, missing, place)],
    place — где выходит размещение ('TG Вар', `placement_place`): по нему
    правило 4 говорит, где чего не хватает. Без place подпись правила 4 — без
    мест (прежний вид). live — материал с актуальными данными (правило 10).
    """
    rows = [(item[0], item[1], item[2] if len(item) > 2 else None) for item in states]
    counts: Dict[str, int] = {}
    for state, _missing, _place in rows:
        counts[state] = counts.get(state, 0) + 1
    active = [row for row in rows if row[0] != 'cancelled']
    n_ready = sum(1 for row in active if row[0] == 'ready')
    breakdown = _missing_breakdown(active)
    base = {'total': len(active), 'ready': n_ready, 'counts': counts, 'missing': breakdown}

    def result(rule, state, label, tone):
        return dict(base, rule=rule, state=state, label=label, tone=tone)

    def count(name):
        return sum(1 for row in active if row[0] == name)

    if not rows:
        return result(1, 'empty', 'Только тема', 'muted')
    if not active:
        return result(2, 'cancelled', 'Отменено', 'muted')
    if count('failed'):
        return result(3, 'failed', f'Ошибка отправки: {count("failed")}', 'danger')
    if count('incomplete'):
        attributed = all(row[2] is not None for row in active)
        return result(4, 'incomplete', _missing_label(breakdown, len(active), attributed), 'warning')
    if count('overdue'):
        return result(5, 'overdue', f'Время вышло: {count("overdue")}', 'warning')
    if n_ready:
        if count('scheduled'):
            return result(6, 'ready', f'Готово к утверждению: {n_ready} из {len(active)}', 'accent')
        return result(6, 'ready', 'Готово к утверждению', 'accent')
    n_published = count('published')
    if n_published == len(active):
        return result(7, 'published', 'Вышло', 'success')
    # Дальше остались только scheduled, paused и published.
    if n_published:
        return result(8, 'published', f'Вышло: {n_published} из {len(active)}', 'success')
    if count('paused'):
        return result(9, 'paused', f'На паузе: {count("paused")}', 'muted')
    return result(10, 'scheduled', LIVE_SCHEDULED_LABEL if live else 'Запланировано', 'success')


def _placement_view(material: dict, placement: dict, now_str: str) -> Tuple[dict, str, List[dict]]:
    state, missing = display_state(material, placement, now_str)
    text, media, source = placement_content(material, placement)
    view = copy.deepcopy(placement)
    view.update({
        'effective_text': text,
        'effective_media': media,
        'media_items': media_items(material, media),
        'content_source': source,
        'missing': missing,
        'ready': state == 'ready',
        'display_state': state,
        'display_label': display_label(state, missing, material.get('kind') == 'live'),
        'datetime': placement_datetime(placement),
        'audience_info': audience_info(placement),
    })
    return view, state, missing


def material_json(material: dict, now_str: str, month: Optional[str] = None) -> dict:
    """Материал для API: хранимые поля + date, summary, in_month, agent_draft,
    media[].url и вычисленные поля размещений. in_month — принадлежит ли
    материал месяцу month (без month — True: ответ на правку относится к самому
    материалу). agent_draft — `is_agent_draft` (для «Удалить черновики ИИ»)."""
    out = copy.deepcopy(material)
    out['media'] = [dict(item, url=MEDIA_URL_PREFIX + item['name'])
                    for item in material.get('media') or []]
    views, states = [], []
    for placement in material.get('placements') or []:
        view, state, missing = _placement_view(material, placement, now_str)
        views.append(view)
        states.append((state, missing, placement_place(placement)))
    out['placements'] = views
    out['date'] = material_date(material)
    out['summary'] = material_summary(states, live=material.get('kind') == 'live')
    out['in_month'] = (material.get('month') == month) if month else True
    out['agent_draft'] = is_agent_draft(material)
    return out


def _content_signature(material: dict, placement: dict) -> tuple:
    """Всё, что уходит в публикацию: изменилось — утверждение снимается."""
    return (placement.get('channel'), placement.get('bar'), _segment(placement),
            effective_text(material, placement), tuple(effective_media(material, placement)),
            material.get('kind'), material.get('live_source'))


def _placement_label(placement: dict) -> str:
    """'Telegram · ВО · 9 окт 16:00' — для журнала и сообщений."""
    channel = CHANNELS.get(placement.get('channel'), {}).get('name', placement.get('channel'))
    bar = placement.get('bar')
    bar_short = BAR_ALL_SHORT if bar == BAR_ALL else BAR_BY_KEY.get(bar, {}).get('short', bar)
    when = fmt_date_short(placement['date']) if placement.get('date') else 'без даты'
    if placement.get('time'):
        when += ' ' + placement['time']
    return f'{channel} · {bar_short} · {when}'


def _to_draft(placement: dict) -> None:
    placement['status'] = 'draft'
    placement['approved_at'] = None
    placement['approved_by'] = None
    placement['approved_snapshot'] = None
    placement['failed_error'] = None


# ---------------------------------------------------------------------------
# Живые данные: таплист
# ---------------------------------------------------------------------------

def format_abv(value) -> Optional[str]:
    """Крепость: half-up до 0,01, без хвостовых нулей, десятичная запятая.
    5.0 → '5', 6.5 → '6,5', 7.25 → '7,25'. Нечисло → None."""
    try:
        number = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    text = format(number, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def taplist_line(row: dict) -> str:
    """'{кран}. {пивоварня} — {название}[, {стиль}][, {крепость}%]'."""
    number = row.get('tap_number')
    name = row.get('beer_name') or row.get('iiko_name') or ''
    brewery = (row.get('brewery') or '').strip()
    line = f'{number}. {brewery} — {name}' if brewery else f'{number}. {name}'
    if row.get('style'):
        line += f', {row["style"]}'
    abv = row.get('abv')
    if abv:
        text = format_abv(abv)
        if text and text != '0':
            line += f', {text}%'
    return line


def load_live_data(registry=None):
    """(snapshot, registry) для таплиста — лениво: extensions тяжёлый, импорт
    модуля контент-плана не должен его тянуть. Ни iiko, ни цен здесь нет."""
    from core.taplist import product_catalog
    from core.untappd_registry import load_registry
    if registry is None:
        registry = load_registry()
    import extensions
    snapshot = extensions.taps_manager.get_snapshot(product_catalog(registry))
    return snapshot, registry


def _tap_sort_key(row: dict):
    number = row.get('tap_number')
    try:
        return (0, int(number), '')
    except (TypeError, ValueError):
        return (1, 0, str(number))


def render_live(source, bar, template, pub_date=None, snapshot=None, registry=None, now=None,
                channel=None, has_media=None) -> dict:
    """Подставить живые данные в шаблон и проверить правила остановки.

    -> {ok, text, problems:[{code, text}], length, limit, limit_note, channel,
    has_media, rows, data_at}.
    rows — строки таплиста [{tap_number, brewery, beer_name, style, abv, mapped,
    mapping_message, line}]. ok=False означает «публикация будет остановлена».
    now — момент для data_at и {дата} по умолчанию (для тестов).
    channel/has_media — площадка размещения и есть ли у него фото/видео: предел
    длины = `text_limit_for(channel, has_media)` (1024 подпись Telegram/бота с
    медиа, 4096 без, Instagram 2200). Без channel — 4096, как раньше.
    """
    channel = str(channel).strip() if channel not in (None, '') else None
    if channel is not None and channel not in CHANNELS:
        raise ValueError('Площадка: Telegram, Instagram или Бот')
    with_media = bool(has_media)
    moment = _naive_msk(now if isinstance(now, datetime) else msk_time.now())
    template = '' if template is None else str(template)
    problems: List[dict] = []
    rows_out: List[dict] = []
    limit = text_limit_for(channel, with_media) if channel else TG_TEXT_LIMIT

    def add(code, text):
        problems.append({'code': code, 'text': text})

    if source not in LIVE_SOURCES:
        add('no_live_source', 'не выбран источник данных')
    bar_ok = bar in BAR_KEYS
    rows: List[dict] = []
    if source in LIVE_SOURCES:
        if not bar_ok:
            add('no_bar', 'для таплиста выберите бар')
        else:
            try:
                if snapshot is None or registry is None:
                    loaded_snapshot, loaded_registry = load_live_data(registry)
                    snapshot = loaded_snapshot if snapshot is None else snapshot
                    registry = loaded_registry if registry is None else registry
                from core.taplist import full_taplist
                rows = full_taplist(snapshot, registry, TAPLIST_BAR_IDS[bar], active_only=True)
            except KeyError:
                rows = []
                add('no_data', 'Бар не найден в таплисте')
            except Exception as e:  # noqa: BLE001 — предпросмотр не должен падать 500
                print(f'[CONTENT_PLAN] live data unavailable: {e!r}')
                rows = []
                add('no_data', 'Не удалось прочитать данные таплиста')
            rows = sorted(rows, key=_tap_sort_key)
            if not rows and not problems:
                add('no_data', 'На кранах бара нет активных позиций')
            for row in rows:
                if not row.get('mapped'):
                    add('unverified', f'Кран {row.get("tap_number")}: {row.get("mapping_message") or "нет проверенной связи"}')
    for token in unknown_placeholders(template):
        add('bad_placeholder', f'неизвестная подстановка {token}')

    lines = []
    for row in rows:
        line = taplist_line(row)
        lines.append(line)
        rows_out.append({'tap_number': row.get('tap_number'), 'brewery': row.get('brewery'),
                         'beer_name': row.get('beer_name'), 'style': row.get('style'),
                         'abv': row.get('abv'), 'mapped': bool(row.get('mapped')),
                         'mapping_message': row.get('mapping_message'), 'line': line})

    day = pub_date or moment.date().isoformat()
    values = {'{дата}': fmt_date_ru(day)}
    if bar_ok and source in LIVE_SOURCES:
        values.update({'{бар}': BAR_BY_KEY[bar]['name'], '{таплист}': '\n'.join(lines),
                       '{кранов}': str(len(rows))})
    # Один проход по шаблону: подставленное значение (название пива с «{…}»)
    # повторно не разбирается.
    text = _TOKEN_RE.sub(lambda m: values.get(m.group(0), m.group(0)), template)
    length = len(text)
    if length > limit:
        add('text_too_long', f'текст длиннее {limit} знаков')
    return {'ok': not problems, 'text': text, 'problems': problems, 'length': length,
            'limit': limit, 'limit_note': limit_note_for(channel, with_media),
            'channel': channel, 'has_media': with_media, 'rows': rows_out,
            'data_at': fmt_stamp(moment)}


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------

# origin по умолчанию 'human': материалы до 2026-09-27 создавали только люди
# (MCP тогда не было).
_MATERIAL_DEFAULTS = {
    'title': '', 'kind': 'fixed', 'live_source': None, 'planned_date': None, 'base_text': '',
    'media_required': False, 'note': '', 'series': None, 'copied_from': None,
    'source_review_id': None, 'created_at': None, 'created_by': None, 'updated_at': None,
    'updated_by': None, 'origin': ORIGIN_HUMAN, 'agent_rationale': '', 'shot_list': '',
}
_PLACEMENT_DEFAULTS = {
    'bar': BAR_ALL, 'date': None, 'time': None, 'text': None, 'media': None, 'audience': None,
    'approved_at': None, 'approved_by': None, 'approved_snapshot': None, 'published_at': None,
    'published_by': None, 'failed_error': None, 'updated_at': None, 'updated_by': None,
}
# origin сюда не входит: его ставит сервер при создании (см. `_reject_origin`).
MATERIAL_EDITABLE = ('title', 'kind', 'live_source', 'planned_date', 'base_text', 'note', 'media_required',
                     'agent_rationale', 'shot_list')
PLACEMENT_EDITABLE = ('channel', 'bar', 'date', 'time', 'text', 'media', 'audience')
FIELD_NAMES = {
    'title': 'название', 'kind': 'тип', 'live_source': 'источник данных', 'planned_date': 'дата темы',
    'base_text': 'текст', 'note': 'заметка', 'media_required': '«нужно фото»', 'channel': 'площадка',
    'bar': 'бар', 'date': 'дата', 'time': 'время', 'text': 'свой текст', 'media': 'подборка файлов',
    'audience': 'аудитория', 'agent_rationale': '«почему этот пост»', 'shot_list': '«что снять»',
}


def _empty_data() -> dict:
    return {'version': SCHEMA_VERSION, 'materials': {}, 'log': []}


def _broken(text: str) -> ContentPlanUnavailable:
    return ContentPlanUnavailable(f'Файл контент-плана повреждён: {text}')


def _check_data(data) -> dict:
    """Проверить структуру и дополнить недостающие необязательные поля.
    Любая неожиданность в обязательном — ContentPlanUnavailable (не чиним молча)."""
    if not isinstance(data, dict) or not isinstance(data.get('materials'), dict):
        raise _broken('неожиданная структура')
    log = data.get('log', [])
    if not isinstance(log, list):
        raise _broken('журнал не список')
    for mid, material in data['materials'].items():
        if not isinstance(material, dict) or material.get('id') != mid:
            raise _broken(f'запись материала {mid}')
        month = material.get('month')
        if not isinstance(month, str) or not _MONTH_RE.match(month):
            raise _broken(f'месяц материала {mid}')
        placements = material.setdefault('placements', [])
        media = material.setdefault('media', [])
        if not isinstance(placements, list) or not isinstance(media, list):
            raise _broken(f'запись материала {mid}')
        for key, default in _MATERIAL_DEFAULTS.items():
            material.setdefault(key, copy.deepcopy(default))
        if material['kind'] not in KINDS:
            raise _broken(f'тип материала {mid}')
        # Неизвестное происхождение не «чиним» в 'human': запись поверх стёрла бы
        # значение, которого эта версия не понимает (как с типом выше).
        if material['origin'] not in ORIGINS:
            raise _broken(f'происхождение материала {mid}')
        for item in media:
            if not isinstance(item, dict) or not content_media.is_valid_name(item.get('name')):
                raise _broken(f'файл материала {mid}')
        for placement in placements:
            if (not isinstance(placement, dict) or not isinstance(placement.get('id'), str)
                    or placement.get('channel') not in CHANNELS
                    or placement.get('status') not in STATUSES):
                raise _broken(f'размещение материала {mid}')
            for key, default in _PLACEMENT_DEFAULTS.items():
                placement.setdefault(key, copy.deepcopy(default))
    data['log'] = log
    data['version'] = data.get('version', SCHEMA_VERSION)
    return data


def _clean_text(value, limit: int, field: str) -> str:
    text = '' if value is None else str(value)
    if len(text) > limit:
        raise ValueError(f'{field} длиннее {limit} знаков')
    return text


def _clean_material_fields(fields: dict) -> dict:
    """Проверить переданные поля материала; вернуть только переданные."""
    out = {}
    if 'title' in fields:
        title = _WS.sub(' ', str(fields['title'] or '')).strip()
        if not title:
            raise ValueError('Название обязательно')
        if len(title) > TITLE_MAX:
            raise ValueError(f'Название длиннее {TITLE_MAX} знаков')
        out['title'] = title
    if 'kind' in fields:
        kind = str(fields['kind'] or '').strip()
        if kind not in KINDS:
            raise ValueError('Тип материала: готовая публикация (fixed) или с актуальными данными (live)')
        out['kind'] = kind
    if 'live_source' in fields:
        source = fields['live_source']
        source = None if source in (None, '') else str(source).strip()
        if source is not None and source not in LIVE_SOURCES:
            raise ValueError(f'Неизвестный источник данных «{source}»')
        out['live_source'] = source
    if 'planned_date' in fields:
        out['planned_date'] = parse_date(fields['planned_date'], 'Дата темы')
    if 'base_text' in fields:
        out['base_text'] = _clean_text(fields['base_text'], TEXT_MAX, 'Текст')
    if 'note' in fields:
        out['note'] = _clean_text(fields['note'], NOTE_MAX, 'Заметка')
    if 'media_required' in fields:
        out['media_required'] = parse_bool(fields['media_required'], '«Нужно фото»')
    if 'agent_rationale' in fields:
        out['agent_rationale'] = _clean_text(fields['agent_rationale'], AGENT_TEXT_MAX, '«Почему этот пост»')
    if 'shot_list' in fields:
        out['shot_list'] = _clean_text(fields['shot_list'], AGENT_TEXT_MAX, '«Что снять»')
    return out


def _reject_origin(fields: dict) -> None:
    """origin ставит сервер при создании записи (`origin_of`) — в теле запроса
    его быть не может: иначе агент мог бы выдать свой черновик за работу людей
    (и наоборот)."""
    if 'origin' in fields:
        raise ValueError('Происхождение материала (origin) ставит сервер при создании: «agent», если материал '
                         'создан через MCP, иначе «human». Передавать и менять его нельзя')


def _clean_placement_fields(fields: dict) -> dict:
    out = {}
    if 'channel' in fields:
        channel = str(fields['channel'] or '').strip()
        if channel not in CHANNELS:
            raise ValueError('Площадка: Telegram, Instagram или Бот')
        out['channel'] = channel
    if 'bar' in fields:
        out['bar'] = parse_bar(fields['bar'])
    if 'date' in fields:
        out['date'] = parse_date(fields['date'])
    if 'time' in fields:
        out['time'] = parse_time(fields['time'])
    if 'text' in fields:
        out['text'] = None if fields['text'] is None else _clean_text(fields['text'], TEXT_MAX, 'Текст')
    if 'media' in fields:
        media = fields['media']
        if media is None:
            out['media'] = None
        else:
            if not isinstance(media, list) or not all(isinstance(n, str) for n in media):
                raise ValueError('Подборка файлов: нужен список имён или null (все файлы)')
            unique = []
            for name in media:
                if name not in unique:
                    unique.append(name)
            out['media'] = unique
    if 'audience' in fields:
        out['audience'] = parse_audience(fields['audience'])
    return out


def _check_media_subset(material: dict, media: Optional[List[str]]) -> None:
    if media is None:
        return
    have = {item['name'] for item in material.get('media') or []}
    for name in media:
        if name not in have:
            raise ValueError('Файл не найден в материале')


def _copy_placement(placement: dict, new_date: Optional[str], keep_content: bool,
                    now_str: str, login: str) -> dict:
    media = placement.get('media')
    return {
        'id': _new_id('p_'), 'channel': placement['channel'], 'bar': placement['bar'],
        'date': new_date, 'time': placement.get('time'),
        'text': placement.get('text') if keep_content else None,
        'media': list(media) if keep_content and media is not None else None,
        'audience': copy.deepcopy(placement.get('audience')),
        'status': 'draft', 'approved_at': None, 'approved_by': None, 'approved_snapshot': None,
        'published_at': None, 'published_by': None, 'failed_error': None,
        'updated_at': now_str, 'updated_by': login,
    }


def _copy_material(source: dict, month: str, planned_date: Optional[str], keep_content: bool,
                   now_str: str, login: str, origin: str = ORIGIN_HUMAN) -> dict:
    """Новый материал по образцу source. Материал с актуальными данными всегда
    сохраняет шаблон, файлы и свои версии текста: шаблон — утверждённый дизайн.

    origin — кто выполнил копирование (`origin_of` пользователя), а не origin
    источника: копия — новая запись, её сделал тот, кто нажал «Повторить» или
    «Скопировать месяц». «Почему этот пост» и «Что снять» копируются вместе с
    содержанием (тот же keep): без текста пояснение к нему не имеет смысла."""
    keep = keep_content or source.get('kind') == 'live'
    return {
        'id': _new_id('m_'), 'month': month, 'title': source['title'], 'kind': source['kind'],
        'live_source': source.get('live_source'), 'planned_date': planned_date,
        'base_text': source.get('base_text') or '' if keep else '',
        'media': copy.deepcopy(source.get('media') or []) if keep else [],
        'media_required': bool(source.get('media_required')), 'note': source.get('note') or '',
        'series': None, 'copied_from': None, 'source_review_id': None,
        'origin': origin,
        'agent_rationale': source.get('agent_rationale') or '' if keep else '',
        'shot_list': source.get('shot_list') or '' if keep else '',
        'created_at': now_str, 'created_by': login, 'updated_at': now_str, 'updated_by': login,
        'placements': [],
    }, keep


def copy_anchor(material: dict) -> Optional[str]:
    """Опорная дата материала для copy_month (см. докстроку модуля).

    1) дата темы (planned_date) — она задаёт месяц материала, поэтому её перенос
       по правилу «n-й день недели» гарантированно попадает в месяц назначения;
    2) нет её — самая ранняя дата неотменённого размещения ВНУТРИ месяца
       материала: анонс, стоящий в конце прошлого месяца, не должен утащить
       копию в чужой месяц;
    3) нет и таких — самая ранняя дата неотменённого размещения;
    4) дат нет совсем — None (материал копируется без дат).
    Отменённые размещения не копируются, поэтому и опорой не служат.
    """
    if material.get('planned_date'):
        return material['planned_date']
    dates = sorted(p['date'] for p in material.get('placements') or []
                   if p.get('status') != 'cancelled' and p.get('date'))
    if not dates:
        return None
    inside = [d for d in dates if d[:7] == material.get('month')]
    return (inside or dates)[0]


def _placement_key(placement: dict) -> tuple:
    """Ключ «одного и того же» размещения в разных днях серии."""
    return (placement.get('channel'), placement.get('bar'), _segment(placement), placement.get('time'))


def _key_label(key: tuple, with_time: bool = True) -> str:
    """'TG Лиг 18:00' / 'Бот Сеть (Все подписчики бота)' — для заметок копирования."""
    channel, bar, segment, time = key
    label = placement_place({'channel': channel, 'bar': bar})
    if segment and segment in AUDIENCE_BY_KEY:
        label += f' ({AUDIENCE_BY_KEY[segment]["name"]})'
    if with_time and time:
        label += f' {time}'
    return label


def _member_day(material: dict) -> str:
    day = material.get('planned_date') or material_date(material)
    return fmt_date_short(day) if day else 'без даты'


def series_plan(members: List[dict]) -> dict:
    """Как собрать копию серии из её дней (members — по возрастанию даты).

    -> {template, placements: [(placement, member)], lacking: [(member, [key])],
        times: [(key без времени, [время])], content_differs, all_cancelled}.

    template — самый ранний день серии, где есть неотменённое размещение (нет
    такого — самый ранний день): из него берутся название, текст, файлы, тип.
    placements — объединение неотменённых размещений всех дней без повторов по
    `_placement_key` (площадка, бар, аудитория, время); каждое берётся из
    первого дня, где оно встретилось. lacking — дни, где части объединения нет
    (отменили или удалили). times — одно и то же место (площадка, бар,
    аудитория) с разным временем в разные дни, если ни в одном дне этих времён
    не было вместе: в копию попадают оба — вероятно, время переносили разово.
    content_differs — у дней разный общий текст или набор файлов.
    """
    live = [m for m in members if any(p['status'] != 'cancelled' for p in m['placements'])]
    template = live[0] if live else members[0]
    union: Dict[tuple, Tuple[dict, dict]] = {}
    keys_by_member: List[Tuple[dict, set]] = []
    for member in members:
        keys = set()
        for placement in member['placements']:
            if placement['status'] == 'cancelled':
                continue
            key = _placement_key(placement)
            keys.add(key)
            if key not in union:
                union[key] = (placement, member)
        keys_by_member.append((member, keys))
    lacking = []
    if union:
        for member, keys in keys_by_member:
            missing = [key for key in union if key not in keys]
            if missing:
                lacking.append((member, missing))
    groups: Dict[tuple, List[tuple]] = {}
    for key in union:
        groups.setdefault(key[:3], []).append(key)
    times = []
    for place, keys in groups.items():
        if len(keys) < 2:
            continue
        together = any(sum(1 for key in keys if key in member_keys) > 1 for _m, member_keys in keys_by_member)
        if not together:
            times.append((place, sorted(key[3] or '' for key in keys)))

    def content(material):
        return (material.get('base_text') or '', tuple(item['name'] for item in material.get('media') or []))

    return {
        'template': template,
        'placements': list(union.values()),
        'lacking': lacking,
        'times': times,
        'content_differs': any(content(m) != content(template) for m in members if m is not template),
        'all_cancelled': not union and any(m['placements'] for m in members),
    }


def _fit_subset(subset: Optional[List[str]], names: List[str]) -> Optional[List[str]]:
    """Подборку файлов размещения, взятого из другого дня серии, — к файлам копии.
    Имена, которых у копии нет, выпадают; если выпали все — null («все файлы»):
    пустой список означал бы «без фото», а человек выбирал именно фото."""
    if subset is None:
        return None
    kept = [name for name in subset if name in names]
    return kept if kept or not subset else None


def _meta() -> dict:
    return {
        'bars': [dict(b) for b in BARS],
        'bar_all': {'key': BAR_ALL, 'name': BAR_ALL_NAME, 'short': BAR_ALL_SHORT},
        'channels': [{k: CHANNELS[key][k] for k in ('key', 'name', 'bar_rule', 'text_limit',
                                                     'caption_limit', 'media_max', 'media_required')}
                     for key in CHANNEL_ORDER],
        'audiences': [dict(a, size=None, size_note=AUDIENCE_SIZE_NOTE) for a in AUDIENCES],
        'live_sources': [copy.deepcopy(LIVE_SOURCES[key]) for key in LIVE_SOURCES],
        'delivery_connected': dict(DELIVERY_CONNECTED),
        'states': [{'key': key, 'label': DISPLAY_LABELS.get(key, 'Не хватает данных'),
                    'tone': DISPLAY_TONES[key]} for key in DISPLAY_STATES],
        'live_scheduled_label': LIVE_SCHEDULED_LABEL,
        'cross_month_states': list(CROSS_MONTH_STATES),
        'summary_rules': list(SUMMARY_RULES),
        'readiness_rules': list(READINESS_RULES),
        'copy_rules': list(COPY_RULES),
        'media_limits': {'image_bytes': content_media.MAX_IMAGE_BYTES,
                         'video_bytes': content_media.MAX_VIDEO_BYTES,
                         'per_material': MATERIAL_MEDIA_MAX},
        # Пределы хранения полей материала — чтобы агент (MCP) не упирался в 400
        # вслепую; экран держит те же числа (зеркала в content_plan.js).
        'field_limits': {'title': TITLE_MAX, 'base_text': TEXT_MAX, 'note': NOTE_MAX,
                         'agent_rationale': AGENT_TEXT_MAX, 'shot_list': AGENT_TEXT_MAX},
        'origins': [{'key': key, 'name': ORIGIN_NAMES[key]} for key in ORIGINS],
        'agent_draft_rule': AGENT_DRAFT_RULE,
    }


def _material_sort_key(view: dict):
    return (view.get('date') is not None, view.get('date') or '',
            (view.get('title') or '').casefold(), view.get('created_at') or '', view['id'])


class ContentPlanStore:
    """Контент-план на диске. now_fn — часы (для тестов), media_dir — каталог файлов."""

    def __init__(self, data_file: Optional[str] = None, now_fn: Optional[Callable[[], datetime]] = None,
                 media_dir: Optional[str] = None):
        self.data_file = data_file or get_data_path(DATA_FILE_NAME)
        self._now_fn = now_fn or msk_time.now
        if media_dir is None:
            media_dir = (get_data_path(content_media.MEDIA_DIR_NAME) if data_file is None else
                         os.path.join(os.path.dirname(os.path.abspath(self.data_file)),
                                      content_media.MEDIA_DIR_NAME))
        self.media = content_media.MediaStore(media_dir)
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'

    # ----- время -------------------------------------------------------------

    def now(self) -> datetime:
        """Текущая минута по Москве (наивная)."""
        return _naive_msk(self._now_fn()).replace(second=0, microsecond=0)

    def now_str(self) -> str:
        return fmt_stamp(self.now())

    def today(self) -> str:
        return self.now().date().isoformat()

    # ----- файл --------------------------------------------------------------

    def _load(self) -> dict:
        if not os.path.exists(self.data_file):
            return _empty_data()
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f'[CONTENT_PLAN] cannot read {self.data_file}: {e}')
            raise ContentPlanUnavailable(f'Файл контент-плана не читается: {e}') from e
        return _check_data(data)

    def _save(self, data: dict) -> None:
        if len(data['log']) > LOG_MAX:
            data['log'] = data['log'][-LOG_MAX:]
        atomic_write_json(self.data_file, data)

    @contextmanager
    def _tx(self):
        """read-modify-write под блокировкой. after — действия после записи
        (удаление осиротевших файлов). Исключение в теле — ничего не пишется."""
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            after: List[Callable[[], None]] = []
            yield data, after
            self._save(data)
            for action in after:
                try:
                    action()
                except Exception as e:  # noqa: BLE001 — уборка файлов best-effort
                    print(f'[CONTENT_PLAN] cleanup failed: {e!r}')

    @staticmethod
    def _log(data: dict, now_str: str, login: str, action: str, material_id: Optional[str],
             placement_id: Optional[str], text: str) -> None:
        data['log'].append({'at': now_str, 'by': login, 'action': action,
                            'material_id': material_id, 'placement_id': placement_id, 'text': text})

    @staticmethod
    def _material(data: dict, material_id) -> dict:
        material = data['materials'].get(material_id) if isinstance(material_id, str) else None
        if material is None:
            raise ContentPlanNotFound('Материал не найден')
        return material

    @staticmethod
    def _placement(data: dict, placement_id) -> Tuple[dict, dict]:
        for material in data['materials'].values():
            for placement in material['placements']:
                if placement['id'] == placement_id:
                    return material, placement
        raise ContentPlanNotFound('Размещение не найдено')

    @staticmethod
    def _media_referenced(data: dict, name: str) -> bool:
        """Нужен ли файл: он есть у какого-то материала или в снимке утверждения."""
        for material in data['materials'].values():
            if any(item['name'] == name for item in material['media']):
                return True
            for placement in material['placements']:
                snapshot = placement.get('approved_snapshot') or {}
                if name in (snapshot.get('media') or []):
                    return True
        return False

    def _auto_unapprove(self, data: dict, material: dict, before: Dict[str, tuple],
                        now_str: str, login: str) -> List[str]:
        """Снять утверждение с размещений, у которых изменилось содержание."""
        changed = []
        for placement in material['placements']:
            if placement['status'] not in UNAPPROVE_ON_CONTENT:
                continue
            if placement['id'] not in before:
                continue
            if before[placement['id']] == _content_signature(material, placement):
                continue
            _to_draft(placement)
            placement['updated_at'], placement['updated_by'] = now_str, login
            changed.append(placement['id'])
            self._log(data, now_str, login, 'unapprove_auto', material['id'], placement['id'],
                      f'Утверждение снято: изменилось содержание ({_placement_label(placement)})')
        return changed

    @staticmethod
    def _signatures(material: dict) -> Dict[str, tuple]:
        return {p['id']: _content_signature(material, p) for p in material['placements']}

    # ----- чтение ------------------------------------------------------------

    def meta(self) -> dict:
        return _meta()

    def month_payload(self, month: str) -> dict:
        """Ответ GET /api/content-plan: материалы месяца + справочники + статистика.

        Материалы месяца M = материалы с month == M ПЛЮС материалы, у которых
        есть размещение с датой в M (in_month=False: таблица их не показывает,
        календарь показывает их размещения). Статистика размещений считается по
        размещениям материалов месяца и размещениям, датированным этим месяцем.
        """
        month = parse_month(month)
        data = self._load()
        now_str = self.now_str()
        materials, by_state = [], {}
        n_materials = n_placements = 0
        for material in data['materials'].values():
            in_month = material['month'] == month
            if not in_month and not any((p.get('date') or '')[:7] == month for p in material['placements']):
                continue
            view = material_json(material, now_str, month)
            materials.append(view)
            n_materials += 1 if in_month else 0
            for placement in view['placements']:
                if in_month or (placement.get('date') or '')[:7] == month:
                    n_placements += 1
                    state = placement['display_state']
                    by_state[state] = by_state.get(state, 0) + 1
        materials.sort(key=_material_sort_key)
        payload = {'month': month, 'now': now_str, 'today': now_str[:10], 'scope': 'month',
                   'state': None, 'materials': materials}
        payload.update(_meta())
        payload['stats'] = {'materials': n_materials, 'placements': n_placements, 'by_state': by_state}
        return payload

    def state_payload(self, state) -> dict:
        """Вид «по всем месяцам»: материалы ЛЮБОГО месяца, у которых есть
        размещение в состоянии state (overdue или failed, `CROSS_MONTH_STATES`).

        Зачем: счётчики полосы внимания «Время вышло» и «Ошибки отправки»
        считают размещения за любой месяц, а вид месяца показывает только свой
        месяц — по ссылке счётчика список был бы пуст. Ответ того же вида, что
        month_payload, плюс scope='state' и state; month — текущий месяц по
        Москве; in_month у всех true (строки таблицы показывают свои даты);
        stats — по всем размещениям этих материалов.
        """
        state = str(state or '').strip()
        if state not in CROSS_MONTH_STATES:
            raise ValueError('Состояние для вида по всем месяцам: overdue (время вышло) '
                             'или failed (ошибка отправки)')
        # Дешёвая предпроверка по статусу: overdue бывает только у approved,
        # failed — только у failed; готовность черновиков тут не нужна.
        status = 'approved' if state == 'overdue' else 'failed'
        data = self._load()
        now_str = self.now_str()
        materials, by_state = [], {}
        n_placements = 0
        for material in data['materials'].values():
            if not any(p['status'] == status and display_state(material, p, now_str)[0] == state
                       for p in material['placements']):
                continue
            view = material_json(material, now_str)
            materials.append(view)
            for placement in view['placements']:
                n_placements += 1
                key = placement['display_state']
                by_state[key] = by_state.get(key, 0) + 1
        materials.sort(key=_material_sort_key)
        payload = {'month': now_str[:7], 'now': now_str, 'today': now_str[:10], 'scope': 'state',
                   'state': state, 'materials': materials}
        payload.update(_meta())
        payload['stats'] = {'materials': len(materials), 'placements': n_placements, 'by_state': by_state}
        return payload

    def get_material(self, material_id: str, month: Optional[str] = None) -> dict:
        data = self._load()
        return material_json(self._material(data, material_id), self.now_str(), month)

    def get_material_raw(self, material_id: str) -> dict:
        return copy.deepcopy(self._material(self._load(), material_id))

    def get_placement_raw(self, placement_id: str) -> Tuple[dict, dict]:
        material, placement = self._placement(self._load(), placement_id)
        return copy.deepcopy(material), copy.deepcopy(placement)

    def log_for(self, material_id: str) -> List[dict]:
        """Журнал материала, новые сверху. Удалённый материал с записями — тоже."""
        data = self._load()
        entries = [e for e in data['log'] if e.get('material_id') == material_id]
        if material_id not in data['materials'] and not entries:
            raise ContentPlanNotFound('Материал не найден')
        return list(reversed(entries))

    def attention_counts(self, bar=None, now=None) -> dict:
        """Счётчики для полосы внимания раздела «Гости».

        publications_today — размещения с датой «сегодня» в статусах approved,
        paused, published; delivery_errors — failed за любую дату; overdue —
        approved со временем раньше текущей минуты. Фильтр бара X: bar in (X, 'all');
        '', None и 'all' — вся сеть. now — datetime или 'YYYY-MM-DDTHH:MM'.
        """
        bar = _norm_filter_bar(bar)
        data = self._load()
        if isinstance(now, datetime):
            now_str = fmt_stamp(_naive_msk(now))
        elif isinstance(now, str) and now:
            now_str = now[:16]
        else:
            now_str = self.now_str()
        today = now_str[:10]
        publications = errors = overdue = 0
        for material in data['materials'].values():
            for placement in material['placements']:
                if bar and placement['bar'] not in (bar, BAR_ALL):
                    continue
                status = placement['status']
                if placement.get('date') == today and status in ('approved', 'paused', 'published'):
                    publications += 1
                if status == 'failed':
                    errors += 1
                if status == 'approved':
                    moment = placement_datetime(placement)
                    if moment and moment < now_str:
                        overdue += 1
        return {'publications_today': publications, 'delivery_errors': errors, 'overdue': overdue}

    def approve_preview(self, month, bar=None, channel=None, origin=None) -> dict:
        """Что утвердит кнопка «Утвердить готовые» (черновики месяца под фильтром).

        Размещение в месяце M: его материал относится к M или его дата в M.
        Фильтр бара: placement.bar == bar или 'all'. Рассылки бота — отдельным
        списком: их утверждение требует явного подтверждения аудитории.
        kind в каждой строке — тип материала: у 'live' утверждается шаблон, а
        данные подставятся при выходе (окно показывает это пометкой).
        origin ('agent' | 'human', необязателен) — только материалы этого
        происхождения (фильтр «Только от ИИ» на экране); origin есть и в
        каждой строке — окно помечает посты агента «ИИ».
        """
        month = parse_month(month)
        bar = _norm_filter_bar(bar)
        if bar is not None:
            parse_bar(bar)
        channel = str(channel or '').strip() or None
        if channel is not None and channel not in CHANNELS:
            raise ValueError('Площадка: Telegram, Instagram или Бот')
        origin = str(origin or '').strip() or None
        if origin is not None and origin not in ORIGINS:
            raise ValueError('Происхождение: agent (от ИИ-агента) или human (от людей)')
        data = self._load()
        now_str = self.now_str()
        will, bot, stays = [], [], []
        for material in data['materials'].values():
            material_origin = material.get('origin') or ORIGIN_HUMAN
            if origin and material_origin != origin:
                continue
            for placement in material['placements']:
                if material['month'] != month and (placement.get('date') or '')[:7] != month:
                    continue
                if placement['status'] != 'draft':
                    continue
                if bar and placement['bar'] not in (bar, BAR_ALL):
                    continue
                if channel and placement['channel'] != channel:
                    continue
                item = {'placement_id': placement['id'], 'material_id': material['id'],
                        'title': material['title'], 'kind': material.get('kind') or 'fixed',
                        'origin': material_origin,
                        'channel': placement['channel'], 'bar': placement['bar'],
                        'date': placement.get('date'), 'time': placement.get('time')}
                missing = readiness(material, placement, now_str)
                if missing:
                    stays.append(dict(item, missing=missing))
                elif placement['channel'] == 'bot':
                    bot.append(dict(item, audience=audience_info(placement)))
                else:
                    will.append(item)

        def order(item):
            return (item['date'] is None, item['date'] or '', item['time'] or '',
                    item['title'].casefold(), CHANNEL_ORDER.index(item['channel']), item['placement_id'])

        return {'month': month, 'will_approve': sorted(will, key=order), 'bot': sorted(bot, key=order),
                'stays_draft': sorted(stays, key=order)}

    # ----- материалы ---------------------------------------------------------

    def create_material(self, fields: dict, user: Optional[dict]) -> dict:
        """Создать материал. Поля: month, title, kind, live_source, planned_date,
        base_text, note, media_required, agent_rationale, shot_list,
        source_review_id. Дата темы задаёт месяц. origin ставится по user
        (`origin_of`: через MCP — 'agent'); origin в полях — ValueError.
        -> материал в JSON-форме API (id, month, ...). ValueError — неверные поля."""
        if not isinstance(fields, dict):
            raise ValueError('Нужен объект с полями материала')
        _reject_origin(fields)
        clean = _clean_material_fields({k: fields[k] for k in MATERIAL_EDITABLE if k in fields})
        if 'title' not in clean:
            raise ValueError('Название обязательно')
        planned = clean.get('planned_date')
        month = planned[:7] if planned else parse_month(fields.get('month'))
        kind = clean.get('kind', 'fixed')
        live_source = clean.get('live_source')
        if kind == 'fixed' and live_source:
            raise ValueError('Источник данных бывает только у материала с актуальными данными')
        review_id = fields.get('source_review_id')
        review_id = str(review_id).strip()[:SOURCE_REVIEW_ID_MAX] if review_id else None
        login = _login(user)
        now_str = self.now_str()
        material = {
            'id': _new_id('m_'), 'month': month, 'title': clean['title'], 'kind': kind,
            'live_source': live_source if kind == 'live' else None, 'planned_date': planned,
            'base_text': clean.get('base_text', ''), 'media': [],
            'media_required': clean.get('media_required', False), 'note': clean.get('note', ''),
            'series': None, 'copied_from': None, 'source_review_id': review_id or None,
            'origin': origin_of(user), 'agent_rationale': clean.get('agent_rationale', ''),
            'shot_list': clean.get('shot_list', ''),
            'created_at': now_str, 'created_by': login, 'updated_at': now_str, 'updated_by': login,
            'placements': [],
        }
        with self._tx() as (data, _after):
            data['materials'][material['id']] = material
            text = f'Создан материал «{material["title"]}»'
            if review_id:
                text += ' из отзыва гостя'
            self._log(data, now_str, login, 'create', material['id'], None, text)
        return material_json(material, now_str)

    def update_material(self, material_id: str, fields: dict, user: Optional[dict],
                        month: Optional[str] = None) -> Tuple[dict, List[str]]:
        """Правка материала. -> (материал, [id размещений, с которых снято утверждение]).
        origin не редактируется (ValueError); «Почему этот пост» и «Что снять» —
        не содержание публикации, утверждение не снимают."""
        if not isinstance(fields, dict):
            raise ValueError('Нужен объект с полями материала')
        _reject_origin(fields)
        clean = _clean_material_fields({k: fields[k] for k in MATERIAL_EDITABLE if k in fields})
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material = self._material(data, material_id)
            guard_draft_mode(user, material)
            before = self._signatures(material)
            changed = []
            for key, value in clean.items():
                if material.get(key) != value:
                    material[key] = value
                    changed.append(key)
            if material['kind'] == 'fixed' and material.get('live_source'):
                if clean.get('live_source'):
                    raise ValueError('Источник данных бывает только у материала с актуальными данными')
                material['live_source'] = None
                if 'live_source' not in changed:
                    changed.append('live_source')
            if material.get('planned_date'):
                material['month'] = material['planned_date'][:7]
            unapproved = []
            if changed:
                material['updated_at'], material['updated_by'] = now_str, login
                self._log(data, now_str, login, 'edit', material['id'], None,
                          'Изменено: ' + ', '.join(FIELD_NAMES[k] for k in changed))
                unapproved = self._auto_unapprove(data, material, before, now_str, login)
            result = material_json(material, now_str, month)
        return result, unapproved

    def delete_material(self, material_id: str, user: Optional[dict]) -> bool:
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, after):
            material = self._material(data, material_id)
            if any(p['status'] == 'published' for p in material['placements']):
                raise ContentPlanConflict('У материала есть вышедшие размещения: отмените остальные, '
                                          'а материал оставьте для истории')
            del data['materials'][material_id]
            for item in material['media']:
                name = item['name']
                if not self._media_referenced(data, name):
                    after.append(lambda n=name: self.media.delete(n))
            self._log(data, now_str, login, 'delete', material_id, None,
                      f'Удалён материал «{material["title"]}»')
        return True

    def cancel_material(self, material_id: str, user: Optional[dict],
                        month: Optional[str] = None) -> dict:
        """Отменить все отменяемые размещения материала (массовое действие)."""
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material = self._material(data, material_id)
            for placement in material['placements']:
                if placement['status'] in ACTIONS['cancel'][0]:
                    placement['status'] = 'cancelled'
                    placement['updated_at'], placement['updated_by'] = now_str, login
                    self._log(data, now_str, login, 'cancel', material['id'], placement['id'],
                              f'Отменено: {_placement_label(placement)}')
            result = material_json(material, now_str, month)
        return result

    def delete_agent_drafts(self, month, user: Optional[dict], material_ids=None) -> dict:
        """«Удалить черновики ИИ»: удалить черновики агента плана месяца month.

        Удаляются материалы с month == month, origin 'agent' и всеми
        размещениями draft или cancelled (`is_agent_draft`, AGENT_DRAFT_RULE).
        material_ids (необязательно) сужает набор: экран передаёт ровно те id,
        число которых показал в подтверждении, — если за это время план
        изменился, лишнего не удалится. Без material_ids — все черновики агента
        месяца (так удобнее агенту по MCP).

        Что НЕ удаляется (-> skipped [{id, reason}]): материал агента с
        утверждённым, стоящим на паузе, вышедшим или ошибочным размещением; при
        переданных id ещё — нет такого материала, материал другого месяца,
        материал людей (origin 'human'). Материалы людей без material_ids не
        рассматриваются вовсе. Всё — одной записью файла; журнал — действие
        'delete' на каждый материал; файлы, на которые больше никто не ссылается
        (`_media_referenced`), удаляются с диска после записи.
        -> {deleted: [id], skipped: [{id, reason}]}.
        """
        month = parse_month(month)
        ids: Optional[List[str]] = None
        if material_ids is not None:
            if not isinstance(material_ids, list):
                raise ValueError('material_ids: нужен список id материалов')
            ids = []
            for raw in material_ids:
                mid = str(raw)
                if mid not in ids:
                    ids.append(mid)
            if not ids:
                raise ValueError('Не выбраны материалы')
        login = _login(user)
        now_str = self.now_str()
        deleted: List[str] = []
        skipped: List[dict] = []
        with self._tx() as (data, after):
            candidates = []
            if ids is None:
                candidates = [m for m in data['materials'].values()
                              if m['month'] == month and m.get('origin') == ORIGIN_AGENT]
                candidates.sort(key=lambda m: (m.get('created_at') or '', m['id']))
            else:
                for mid in ids:
                    material = data['materials'].get(mid)
                    if material is None:
                        skipped.append({'id': mid, 'reason': 'материал не найден'})
                    elif material['month'] != month:
                        skipped.append({'id': mid, 'reason': f'«{material["title"]}»: материал из плана '
                                                             f'«{month_label(material["month"])}»'})
                    elif material.get('origin') != ORIGIN_AGENT:
                        skipped.append({'id': mid, 'reason': f'«{material["title"]}»: материал создали люди, '
                                                             'а не агент'})
                    else:
                        candidates.append(material)
            removed = []
            for material in candidates:
                if not is_agent_draft(material):
                    skipped.append({'id': material['id'],
                                    'reason': f'«{material["title"]}»: есть утверждённые, вышедшие или '
                                              'ошибочные размещения — это уже не черновик'})
                    continue
                del data['materials'][material['id']]
                removed.append(material)
                deleted.append(material['id'])
                self._log(data, now_str, login, 'delete', material['id'], None,
                          f'Удалён черновик агента «{material["title"]}» (массовое удаление черновиков ИИ)')
            # Файлы — после удаления всех материалов: общий файл двух удалённых
            # черновиков тоже уходит, а файл, нужный кому-то ещё, остаётся.
            names = []
            for material in removed:
                for item in material['media']:
                    if item['name'] not in names:
                        names.append(item['name'])
            for name in names:
                if not self._media_referenced(data, name):
                    after.append(lambda n=name: self.media.delete(n))
        return {'deleted': deleted, 'skipped': skipped}

    # ----- размещения --------------------------------------------------------

    def add_placements(self, material_id: str, fields: dict, user: Optional[dict],
                       month: Optional[str] = None) -> Tuple[dict, List[str]]:
        """Добавить размещения: по одному на каждый бар из bars (массовое назначение).

        Instagram и бот без баров — на всю сеть ('all'); Telegram без бара — 400.
        date не передан — берётся дата темы; time не передан — пусто.
        """
        if not isinstance(fields, dict):
            raise ValueError('Нужен объект с полями размещения')
        channel = str(fields.get('channel') or '').strip()
        if channel not in CHANNELS:
            raise ValueError('Выберите площадку: Telegram, Instagram или Бот')
        bars = fields.get('bars')
        if bars is None and 'bar' in fields:
            bars = [fields['bar']]
        if isinstance(bars, str):
            bars = [bars]
        if bars in (None, []):
            if channel == 'telegram':
                raise ValueError('Выберите хотя бы один бар')
            bars = [BAR_ALL]
        if not isinstance(bars, list):
            raise ValueError('Бары: нужен список')
        unique = []
        for bar in bars:
            bar = parse_bar(bar)
            if bar not in unique:
                unique.append(bar)
        if BAR_ALL in unique and len(unique) > 1:
            raise ValueError('«Вся сеть» не сочетается с отдельными барами')
        clean = _clean_placement_fields({k: fields[k] for k in ('date', 'time', 'text', 'media', 'audience')
                                         if k in fields})
        if channel != 'bot' and clean.get('audience'):
            raise ValueError('Аудитория задаётся только для рассылки через бота')
        login = _login(user)
        now_str = self.now_str()
        created = []
        with self._tx() as (data, _after):
            material = self._material(data, material_id)
            guard_draft_mode(user, material)
            _check_media_subset(material, clean.get('media'))
            day = clean['date'] if 'date' in clean else material.get('planned_date')
            for bar in unique:
                placement = {
                    'id': _new_id('p_'), 'channel': channel, 'bar': bar, 'date': day,
                    'time': clean.get('time'), 'text': clean.get('text'),
                    'media': list(clean['media']) if clean.get('media') is not None else None,
                    'audience': clean.get('audience') if channel == 'bot' else None,
                    'status': 'draft', 'approved_at': None, 'approved_by': None,
                    'approved_snapshot': None, 'published_at': None, 'published_by': None,
                    'failed_error': None, 'updated_at': now_str, 'updated_by': login,
                }
                material['placements'].append(placement)
                created.append(placement['id'])
                self._log(data, now_str, login, 'add_placement', material['id'], placement['id'],
                          f'Добавлено размещение: {_placement_label(placement)}')
            material['updated_at'], material['updated_by'] = now_str, login
            result = material_json(material, now_str, month)
        return result, created

    def update_placement(self, placement_id: str, fields: dict, user: Optional[dict],
                         month: Optional[str] = None) -> Tuple[dict, List[str]]:
        """Правка размещения (см. «Правила редактирования» в докстроке)."""
        if not isinstance(fields, dict):
            raise ValueError('Нужен объект с полями размещения')
        clean = _clean_placement_fields({k: fields[k] for k in PLACEMENT_EDITABLE if k in fields})
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material, placement = self._placement(data, placement_id)
            guard_draft_mode(user, material)
            if placement['status'] == 'published':
                raise ValueError('Размещение уже вышло')
            if placement['status'] == 'cancelled':
                raise ValueError('Размещение отменено')
            if 'media' in clean:
                _check_media_subset(material, clean['media'])
            before = _content_signature(material, placement)
            changed = []
            for key, value in clean.items():
                if placement.get(key) != value:
                    placement[key] = value
                    changed.append(key)
            if placement['channel'] != 'bot' and placement.get('audience'):
                if clean.get('audience'):
                    raise ValueError('Аудитория задаётся только для рассылки через бота')
                placement['audience'] = None
            unapproved = []
            if placement['status'] in UNAPPROVE_ON_CONTENT and _content_signature(material, placement) != before:
                _to_draft(placement)
                unapproved.append(placement['id'])
                self._log(data, now_str, login, 'unapprove_auto', material['id'], placement['id'],
                          f'Утверждение снято: изменилось содержание ({_placement_label(placement)})')
            if placement['status'] in ('approved', 'paused') and ('date' in changed or 'time' in changed):
                moment = placement_datetime(placement)
                if moment is None:
                    raise ValueError('У утверждённой публикации должны быть дата и время — '
                                     'сначала снимите утверждение')
                if moment < now_str:
                    raise ValueError('Нельзя перенести утверждённую публикацию в прошлое')
            if changed:
                placement['updated_at'], placement['updated_by'] = now_str, login
                self._log(data, now_str, login, 'edit_placement', material['id'], placement['id'],
                          f'{_placement_label(placement)}: изменено — '
                          + ', '.join(FIELD_NAMES[k] for k in changed))
            result = material_json(material, now_str, month)
        return result, unapproved

    def delete_placement(self, placement_id: str, user: Optional[dict],
                         month: Optional[str] = None) -> dict:
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material, placement = self._placement(data, placement_id)
            if placement['status'] == 'published':
                raise ContentPlanConflict('Размещение уже вышло — оно остаётся в истории')
            material['placements'].remove(placement)
            material['updated_at'], material['updated_by'] = now_str, login
            self._log(data, now_str, login, 'delete_placement', material['id'], placement['id'],
                      f'Удалено размещение: {_placement_label(placement)}')
            result = material_json(material, now_str, month)
        return result

    def placement_action(self, placement_id: str, action: str, user: Optional[dict],
                         month: Optional[str] = None) -> dict:
        """Переход статуса размещения (таблица ACTIONS). Неподходящий статус — 409."""
        action = str(action or '').strip()
        if action not in ACTIONS:
            raise ValueError('Неизвестное действие')
        allowed, target = ACTIONS[action]
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material, placement = self._placement(data, placement_id)
            status = placement['status']
            if status not in allowed:
                raise ContentPlanConflict(f'{ACTION_CONFLICT[action]} (сейчас: {STATUS_NAMES[status]})')
            if action == 'resume':
                moment = placement_datetime(placement)
                if moment and moment < now_str:
                    raise ValueError('Время выхода прошло — перенесите дату')
            if target == 'draft':
                _to_draft(placement)
                placement['published_at'] = None
                placement['published_by'] = None
            else:
                placement['status'] = target
            if action == 'mark_published':
                placement['published_at'], placement['published_by'] = now_str, login
            if action == 'retry':
                placement['failed_error'] = None
            placement['updated_at'], placement['updated_by'] = now_str, login
            self._log(data, now_str, login, action, material['id'], placement['id'],
                      f'{ACTION_LOG[action]}: {_placement_label(placement)}')
            result = material_json(material, now_str, month)
        return result

    def approve(self, placement_ids, user: Optional[dict], confirm_bot=False) -> dict:
        """Утвердить готовые черновики. -> {approved: [id], skipped: [{id, reasons}]}.

        Рассылка бота среди запрошенных без confirm_bot=true → ValueError
        «Подтвердите аудиторию рассылки», ничего не утверждается.
        """
        if not isinstance(placement_ids, list) or not placement_ids:
            raise ValueError('Не выбраны публикации для утверждения')
        ids = []
        for pid in placement_ids:
            pid = str(pid)
            if pid not in ids:
                ids.append(pid)
        confirmed = confirm_bot is True or (isinstance(confirm_bot, str)
                                            and confirm_bot.strip().casefold() in _TRUE_WORDS)
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            index = {p['id']: (m, p) for m in data['materials'].values() for p in m['placements']}
            if not confirmed and any(index[pid][1]['channel'] == 'bot' for pid in ids if pid in index):
                raise ValueError('Подтвердите аудиторию рассылки')
            approved, skipped = [], []
            for pid in ids:
                if pid not in index:
                    skipped.append({'id': pid, 'reasons': ['размещение не найдено']})
                    continue
                material, placement = index[pid]
                if placement['status'] != 'draft':
                    skipped.append({'id': pid, 'reasons': [f'уже не черновик ({STATUS_NAMES[placement["status"]]})']})
                    continue
                missing = readiness(material, placement, now_str)
                if missing:
                    skipped.append({'id': pid, 'reasons': [item['text'] for item in missing]})
                    continue
                placement['status'] = 'approved'
                placement['approved_at'], placement['approved_by'] = now_str, login
                placement['approved_snapshot'] = {'text': effective_text(material, placement),
                                                  'media': effective_media(material, placement)}
                placement['updated_at'], placement['updated_by'] = now_str, login
                approved.append(pid)
                self._log(data, now_str, login, 'approve', material['id'], pid,
                          f'Утверждено: {_placement_label(placement)}')
        return {'approved': approved, 'skipped': skipped}

    def bulk_pause(self, bar, action: str, user: Optional[dict]) -> dict:
        """Пауза/снятие паузы по бару или всей сети (см. докстроку модуля).
        -> {changed: n, skipped: [{id, reason}]}."""
        bar = str(bar or '').strip()
        if bar != BAR_ALL and bar not in BAR_KEYS:
            raise ValueError('Выберите бар или всю сеть')
        if action not in ('pause', 'resume'):
            raise ValueError('Действие: pause (пауза) или resume (снять паузу)')
        login = _login(user)
        now_str = self.now_str()
        scope = 'вся сеть' if bar == BAR_ALL else f'бар {BAR_BY_KEY[bar]["short"]}'
        changed, skipped = 0, []
        with self._tx() as (data, _after):
            for material in data['materials'].values():
                for placement in material['placements']:
                    if bar != BAR_ALL and placement['bar'] != bar:
                        continue
                    moment = placement_datetime(placement)
                    past = moment is not None and moment < now_str
                    if action == 'pause':
                        if placement['status'] != 'approved' or past:
                            continue
                        placement['status'] = 'paused'
                    else:
                        if placement['status'] != 'paused':
                            continue
                        if past:
                            skipped.append({'id': placement['id'],
                                            'reason': f'«{material["title"]}», {_placement_label(placement)}: '
                                                      f'время выхода прошло'})
                            continue
                        placement['status'] = 'approved'
                    placement['updated_at'], placement['updated_by'] = now_str, login
                    changed += 1
                    self._log(data, now_str, login, 'bulk_pause' if action == 'pause' else 'bulk_resume',
                              material['id'], placement['id'],
                              f'{"Пауза" if action == "pause" else "Пауза снята"} ({scope}): '
                              f'{_placement_label(placement)}')
        return {'changed': changed, 'skipped': skipped}

    def shift(self, material_id: str, days, user: Optional[dict], month: Optional[str] = None) -> dict:
        """Сдвинуть все невышедшие и неотменённые размещения и дату темы на days."""
        days = parse_days(days)
        login = _login(user)
        now_str = self.now_str()
        today = now_str[:10]
        with self._tx() as (data, _after):
            material = self._material(data, material_id)
            moves = []
            for placement in material['placements']:
                if placement['status'] in ('published', 'cancelled') or not placement.get('date'):
                    continue
                new_day = date.fromisoformat(placement['date']) + timedelta(days=days)
                if not YEAR_MIN <= new_day.year <= YEAR_MAX:
                    raise ValueError('Сдвиг выводит дату за допустимые годы')
                new_day = new_day.isoformat()
                if placement['status'] in ('approved', 'paused'):
                    moment = f'{new_day}T{placement["time"]}' if placement.get('time') else None
                    if (moment and moment < now_str) or (not moment and new_day < today):
                        raise ValueError('Сдвиг не выполнен: утверждённая публикация окажется в прошлом '
                                         f'({_placement_label(placement)})')
                moves.append((placement, new_day))
            for placement, new_day in moves:
                placement['date'] = new_day
                placement['updated_at'], placement['updated_by'] = now_str, login
            if material.get('planned_date'):
                material['planned_date'] = (date.fromisoformat(material['planned_date'])
                                            + timedelta(days=days)).isoformat()
                material['month'] = material['planned_date'][:7]
            material['updated_at'], material['updated_by'] = now_str, login
            sign = '+' if days > 0 else ''
            self._log(data, now_str, login, 'shift', material['id'], None,
                      f'Сдвиг на {sign}{days} дн.: размещений {len(moves)}')
            result = material_json(material, now_str, month)
        return result

    def repeat(self, material_id: str, weekdays, month, user: Optional[dict]) -> dict:
        """Повторить материал в месяце month по дням недели weekdays (0 = пн).

        Для каждой даты месяца с нужным днём недели, не раньше сегодняшнего дня и
        не занятой этой серией (дата темы или дата размещений любого материала
        серии, включая сам источник) создаётся копия: то же название, тип,
        источник, текст, ссылки на файлы, «нужно фото», заметка, «почему этот
        пост», «что снять»; размещения (кроме отменённых) — черновиками на эту
        дату. origin копий — по тому, кто повторяет (`origin_of(user)`), а не
        по источнику. Источник и копии — одна серия {id, weekdays}; дни недели
        серии объединяются с прежними.
        -> {created: [id материалов]}.
        """
        weekdays = parse_weekdays(weekdays)
        month = parse_month(month)
        login = _login(user)
        origin = origin_of(user)
        now_str = self.now_str()
        today = now_str[:10]
        created: List[str] = []
        with self._tx() as (data, _after):
            source = self._material(data, material_id)
            guard_draft_mode(user, source)
            series = source.get('series') or None
            series_id = series['id'] if series and series.get('id') else None
            members = [m for m in data['materials'].values()
                       if series_id and (m.get('series') or {}).get('id') == series_id]
            if source not in members:
                members.append(source)
            occupied = set()
            for member in members:
                occupied.add(member.get('planned_date'))
                occupied.add(material_date(member))
                occupied.update(p.get('date') for p in member['placements'] if p['status'] != 'cancelled')
            occupied.discard(None)
            copies = []
            for day in month_days(month):
                iso = day.isoformat()
                if day.weekday() not in weekdays or iso < today or iso in occupied:
                    continue
                clone, _keep = _copy_material(source, month, iso, True, now_str, login, origin)
                for placement in source['placements']:
                    if placement['status'] == 'cancelled':
                        continue
                    clone['placements'].append(_copy_placement(placement, iso, True, now_str, login))
                copies.append(clone)
            if copies:
                union = sorted(set((series or {}).get('weekdays') or []) | set(weekdays))
                new_series = {'id': series_id or _new_id('s_'), 'weekdays': union}
                for member in members + copies:
                    member['series'] = dict(new_series, weekdays=list(union))
                for clone in copies:
                    data['materials'][clone['id']] = clone
                    created.append(clone['id'])
                    self._log(data, now_str, login, 'repeat', clone['id'], None,
                              f'Создан повтором материала «{source["title"]}» на {fmt_date_ru(clone["planned_date"])}')
                days_text = ', '.join(WEEKDAY_SHORT[d] for d in weekdays)
                self._log(data, now_str, login, 'repeat', source['id'], None,
                          f'Повтор по дням ({days_text}) в {month_label(month)}: создано {len(copies)}')
        return {'created': created}

    def copy_month(self, from_month, to_month, with_content, user: Optional[dict]) -> dict:
        """Скопировать план месяца from_month в to_month.

        - to_month не раньше текущего месяца (иначе 400); месяцы не совпадают.
        - Если в to_month уже есть копия материала из from_month (copied_from) — 409.
        - Обычный материал: опорная дата (`copy_anchor`: дата темы, иначе самая
          ранняя дата неотменённого размещения в месяце-источнике, иначе самая
          ранняя вообще) переносится по правилу «n-й день недели месяца»
          (`map_nth_weekday`; n-го нет — последний такой день, с заметкой). ВСЕ
          остальные даты материала (размещения, дата темы) сдвигаются на ту же
          разницу в днях: она кратна 7, поэтому дни недели, порядок и интервалы
          сохраняются. Дата, ушедшая за to_month, остаётся — о ней заметка.
          Материалы без дат копируются без дат.
        - Серии: материалы одного series.id перегенерируются на каждый день
          to_month с днём недели из series.weekdays (новая серия). Размещения
          копии — объединение неотменённых размещений всех дней серии
          (`series_plan`), текст и файлы — из самого раннего дня с неотменённым
          размещением; если дни различались — заметка.
        - Даты раньше сегодняшнего дня сохраняются (черновик покажет «время
          выхода уже прошло»), о них — заметка.
        - with_content False: у готовых публикаций текст и файлы очищаются (свои
          версии текста и подборки — тоже); у материалов с актуальными данными
          шаблон и файлы остаются. True — всё копируется (ссылки на те же файлы).
          «Почему этот пост» и «Что снять» идут вместе с содержанием (очищаются
          или копируются вместе с текстом).
        - Все размещения — черновики; утверждение не переносится; copied_from = id
          источника (у серии — id дня-образца). Отменённые размещения не копируются.
        - origin копий — по тому, кто копирует (`origin_of(user)`): человек —
          'human', агент через MCP — 'agent'.
        -> {created: n, notes: [...]}.
        """
        from_month = parse_month(from_month, 'Месяц-источник')
        to_month = parse_month(to_month, 'Месяц назначения')
        keep_content = parse_bool(with_content, 'Копировать тексты и фото') if with_content is not None else False
        login = _login(user)
        origin = origin_of(user)
        now_str = self.now_str()
        today = now_str[:10]
        if to_month < now_str[:7]:
            raise ValueError('Нельзя копировать в прошедший месяц')
        if from_month == to_month:
            raise ValueError('Месяц-источник и месяц назначения совпадают')
        offset = months_between(from_month, to_month)
        notes: List[str] = []
        created: List[dict] = []
        with self._tx() as (data, _after):
            sources = [m for m in data['materials'].values() if m['month'] == from_month]
            sources.sort(key=lambda m: (material_date(m) is None, material_date(m) or '',
                                        m.get('created_at') or '', m['id']))
            source_ids = {m['id'] for m in sources}
            if any(m['month'] == to_month and m.get('copied_from') in source_ids
                   for m in data['materials'].values()):
                raise ContentPlanConflict('Этот месяц уже скопирован')
            if not sources:
                return {'created': 0, 'notes': [f'В месяце {month_label(from_month)} нет материалов']}

            def note(text):
                if text not in notes:
                    notes.append(text)

            def past_note(title, days):
                past = sorted({d for d in days if d and d < today})
                if past:
                    note(f'«{title}»: ' + ', '.join(fmt_date_short(d) for d in past)
                         + ' — дата уже прошла, черновик не утвердится: перенесите или удалите')

            series_members: Dict[str, List[dict]] = {}
            regular = []
            for material in sources:
                series = material.get('series') or {}
                if series.get('id') and series.get('weekdays'):
                    series_members.setdefault(series['id'], []).append(material)
                else:
                    regular.append(material)

            for members in series_members.values():
                plan = series_plan(members)
                template = plan['template']
                title = template['title']
                weekdays = sorted({d for m in members for d in (m['series'].get('weekdays') or [])})
                new_series = {'id': _new_id('s_'), 'weekdays': weekdays}
                # Живой материал всегда сохраняет шаблон и файлы (см. _copy_material).
                keep = keep_content or template.get('kind') == 'live'
                days = []
                for day in month_days(to_month):
                    if day.weekday() not in weekdays:
                        continue
                    iso = day.isoformat()
                    days.append(iso)
                    clone, _keep = _copy_material(template, to_month, iso, keep_content, now_str, login, origin)
                    clone['series'] = dict(new_series, weekdays=list(weekdays))
                    clone['copied_from'] = template['id']
                    names = [item['name'] for item in clone['media']]
                    for placement, member in plan['placements']:
                        copied = _copy_placement(placement, iso, keep, now_str, login)
                        if member is not template:
                            copied['media'] = _fit_subset(copied['media'], names)
                        clone['placements'].append(copied)
                    created.append(clone)
                if plan['all_cancelled']:
                    note(f'Серия «{title}»: все размещения отменены — копии созданы без размещений')
                if plan['lacking']:
                    parts = []
                    for member, keys in plan['lacking']:
                        active = [p for p in member['placements'] if p['status'] != 'cancelled']
                        if not active:
                            what = 'все размещения отменены' if member['placements'] else 'без размещений'
                        else:
                            what = 'нет ' + ', '.join(_key_label(k) for k in keys)
                        parts.append(f'{_member_day(member)} — {what}')
                    note(f'Серия «{title}»: не во все дни были одинаковые размещения ('
                         + '; '.join(parts) + ') — в копию взяты размещения всех дней серии')
                for place, times in plan['times']:
                    note(f'Серия «{title}»: {_key_label(place + (None,))} — в разные дни разное время ('
                         + ', '.join(t or 'без времени' for t in times)
                         + '): в копию взято каждое время, лишнее удалите')
                if keep and plan['content_differs']:
                    note(f'Серия «{title}»: тексты или файлы дней серии различались — '
                         f'в копию взяты из дня {_member_day(template)}')
                past_note(title, days)

            for material in regular:
                title = material['title']
                anchor = copy_anchor(material)
                delta = 0
                if anchor:
                    new_anchor, fallback = map_nth_weekday(anchor, offset)
                    if fallback:
                        nth, weekday = fallback
                        note(f'«{title}»: {nth}-{WEEKDAY_ORDINAL_SUFFIX[weekday]} '
                             f'{WEEKDAY_NAMES[weekday]} → последняя')
                    delta = (date.fromisoformat(new_anchor) - date.fromisoformat(anchor)).days

                def moved(day_iso, delta=delta):
                    if not day_iso:
                        return None
                    return (date.fromisoformat(day_iso) + timedelta(days=delta)).isoformat()

                planned = moved(material.get('planned_date'))
                clone, keep = _copy_material(material, to_month, planned, keep_content, now_str, login, origin)
                clone['copied_from'] = material['id']
                for placement in material['placements']:
                    if placement['status'] != 'cancelled':
                        clone['placements'].append(
                            _copy_placement(placement, moved(placement.get('date')), keep, now_str, login))
                created.append(clone)
                dates = [planned] + [p['date'] for p in clone['placements']]
                outside = sorted({d for d in dates if d and d[:7] != to_month})
                if outside:
                    note(f'«{title}»: ' + ', '.join(fmt_date_short(d) for d in outside)
                         + f' — вне месяца «{month_label(to_month)}»: даты сдвинуты вместе с опорной, '
                           'порядок и интервалы размещений сохранены')
                past_note(title, dates)

            for clone in created:
                data['materials'][clone['id']] = clone
                self._log(data, now_str, login, 'copy_month', clone['id'], None,
                          f'Скопирован из плана «{month_label(from_month)}»'
                          + (' с текстами и фото' if keep_content else ''))
        return {'created': len(created), 'notes': notes}

    # ----- файлы -------------------------------------------------------------

    def add_media(self, material_id: str, name: str, size: int, original_name, user: Optional[dict],
                  month: Optional[str] = None) -> Tuple[dict, List[str]]:
        """Привязать уже сохранённый файл к материалу. Размещения «все файлы»
        получают его автоматически — их утверждение снимается."""
        if not content_media.is_valid_name(name):
            raise ValueError('Недопустимое имя файла')
        original = os.path.basename(str(original_name or '').replace('\\', '/')).strip()
        original = original[:ORIGINAL_NAME_MAX] or name
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, _after):
            material = self._material(data, material_id)
            if len(material['media']) >= MATERIAL_MEDIA_MAX:
                raise ValueError(f'У материала уже {MATERIAL_MEDIA_MAX} файлов — удалите лишние')
            before = self._signatures(material)
            material['media'].append({'name': name, 'kind': content_media.kind_of(name),
                                      'size': int(size), 'original_name': original,
                                      'uploaded_at': now_str, 'uploaded_by': login})
            material['updated_at'], material['updated_by'] = now_str, login
            self._log(data, now_str, login, 'media_add', material['id'], None, f'Добавлен файл «{original}»')
            unapproved = self._auto_unapprove(data, material, before, now_str, login)
            result = material_json(material, now_str, month)
        return result, unapproved

    def remove_media(self, material_id: str, name: str, user: Optional[dict],
                     month: Optional[str] = None) -> Tuple[dict, List[str]]:
        """Убрать файл из материала и из подборок его размещений, кроме вышедших и
        отменённых: они только для чтения (правка не должна переписывать историю,
        а вышедшее показывает снимок). С диска — только если на файл больше никто
        не ссылается (снимок вышедшего размещения — тоже ссылка)."""
        if not content_media.is_valid_name(name):
            raise ContentPlanNotFound('Файл не найден')
        login = _login(user)
        now_str = self.now_str()
        with self._tx() as (data, after):
            material = self._material(data, material_id)
            item = next((m for m in material['media'] if m['name'] == name), None)
            if item is None:
                raise ContentPlanNotFound('Файл не найден')
            before = self._signatures(material)
            material['media'] = [m for m in material['media'] if m['name'] != name]
            for placement in material['placements']:
                if placement['status'] in ('published', 'cancelled'):
                    continue
                if placement.get('media') is not None and name in placement['media']:
                    placement['media'] = [n for n in placement['media'] if n != name]
            material['updated_at'], material['updated_by'] = now_str, login
            self._log(data, now_str, login, 'media_delete', material['id'], None,
                      f'Удалён файл «{item.get("original_name") or name}»')
            unapproved = self._auto_unapprove(data, material, before, now_str, login)
            if not self._media_referenced(data, name):
                after.append(lambda: self.media.delete(name))
            result = material_json(material, now_str, month)
        return result, unapproved


_store: Optional[ContentPlanStore] = None
_store_guard = threading.Lock()


def get_content_plan_store(data_file: Optional[str] = None) -> ContentPlanStore:
    """Ленивый синглтон на процесс. data_file (для тестов) заменяет синглтон
    магазином на этом файле — последующие вызовы без аргумента вернут его же."""
    global _store
    with _store_guard:
        if data_file is not None and (_store is None or _store.data_file != data_file):
            _store = ContentPlanStore(data_file)
        elif _store is None:
            _store = ContentPlanStore()
        return _store
