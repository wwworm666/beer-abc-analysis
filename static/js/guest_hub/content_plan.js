/* Страница «Контент-план» раздела «Гости» (/content-plan).

   Что здесь:
     - полоса фильтров: месяц, бар (общий для раздела: GH.getBar / GH.setBar),
       площадка, вид «Таблица | Календарь»; действия «Утвердить готовые» и
       «Добавить материал»; под полосой — сводка месяца и вторичные действия
       «Скопировать прошлый месяц» и «Пауза»;
     - таблица месяца (материалы плана по неделям) и календарь (все размещения,
       датированные месяцем) со слоем отзывов по дням;
     - карточка материала справа: название, тип, дата темы, содержание (текст
       или шаблон, фото и видео), размещения с редактором, предпросмотр,
       повтор и перенос, история;
     - диалоги «Утвердить готовые» и «Скопировать прошлый месяц», меню паузы,
       массовые действия над отмеченными строками таблицы;
     - ИИ-агент (MCP): пометка «ИИ» у материалов агента (origin 'agent' ставит
       сервер) в таблице, календаре и шапке карточки; в карточке — «Почему этот
       пост» (agent_rationale) и «Что снять» (shot_list) с автосохранением;
       чип «Только от ИИ» (?origin=agent) и «Удалить черновики ИИ» рядом со
       сводкой; кнопка «Бриф для агента» — выдвижная карточка брифа сети
       (GET / PUT /api/content-plan/brief, поля и пределы — из ответа сервера).

   Источник истины — ответ GET /api/content-plan?month=. Состояние размещения
   (display_state, display_label, missing) и сводка материала (summary)
   приходят посчитанными сервером (core/content_plan.py, правила — в его
   докстроке и в подсказках на экране). Клиент их НЕ пересчитывает: только
   фильтрует, группирует и рисует. После любого изменения месяц перечитывается
   целиком и экран перерисовывается; открытая карточка остаётся на том же
   материале, прокрутка и фокус в поле ввода сохраняются.

   Фильтры: бар X — размещения с bar == X и размещения на всю сеть ('all');
   площадка — по channel; состояние (?state=) — по display_state. Материал
   без подходящих размещений скрывается; тема без размещений видна при фильтрах
   бара и площадки, но не при фильтре состояния (у неё нет состояния).

   Адрес: ?month=YYYY-MM, ?view=table|calendar, ?open=<id материала>,
   ?state=overdue|failed|incomplete|ready|scheduled|paused, ?origin=agent
   (только материалы ИИ-агента), ?brief=1 (открыть бриф для агента).

   Сквозной вид: ?state=overdue|failed БЕЗ ?month= (так ведут ссылки полосы
   «Требует внимания»: там считаются размещения любых месяцев) — страница
   грузит GET /api/content-plan?state=<состояние> без месяца: все материалы,
   у которых есть размещения в этом состоянии, из любого месяца; таблица
   группирует их по месяцам. Чип «Все месяцы · …» с крестиком, стрелки месяца,
   переход в календарь и фильтр другого состояния возвращают обычный месяц.
   Если сервер не ответил scope: 'state', страница честно остаётся в месяце.

   Цвет размещения — по display_state (не по тону сервера): у каждого
   состояния свой вид (контур, заливка, зачёркивание), легенда та же, что на
   чипах. Сводка материала (колонка «Готовность») — тоном сервера.

   Дата и время в карточке сохраняются только целым значением: набор с
   клавиатуры сохраняется при уходе из поля или по Enter, выбор в календаре
   браузера — сразу; пока в поле идёт набор, карточка не перерисовывается
   (иначе браузер сбрасывает позицию ввода, и сохраняются обрывки даты).

   Стиль: IIFE, 'use strict', ES5 (var, function), как static/js/draft/draft.js.
*/
(function () {
    'use strict';

    var GH = window.GH;
    var API = '/api/content-plan';

    // ==================== константы ====================

    // Автосохранение текста: запрос уходит через 700 мс после последнего
    // нажатия клавиши (спецификация, п. 4) и сразу — при уходе из поля.
    var AUTOSAVE_MS = 700;
    // Календарь: в клетке дня видно не больше 4 размещений, остальные — «ещё N»;
    // день с 3 и более РАЗНЫМИ материалами (без отменённых) получает метку
    // плотности: таплист на четыре бара — один материал, а не перегрузка дня.
    var CAL_MAX_PILLS = 4;
    var CAL_DENSE_MIN = 3;
    // История в карточке: последние 8 записей, остальные — по «Показать все».
    var LOG_SHOWN = 8;
    // Время нового размещения по умолчанию (спецификация, п. 4).
    var DEFAULT_TIME = '12:00';
    // Сдвиг материала: зеркало SHIFT_DAYS_MAX в core/content_plan.py (сервер
    // проверяет сам; здесь — только подсказка и ранняя проверка ввода).
    var SHIFT_MAX = 60;
    // Название: зеркало TITLE_MAX в core/content_plan.py (атрибут maxlength).
    var TITLE_MAX = 200;
    // «Почему этот пост» и «Что снять»: зеркало AGENT_TEXT_MAX в
    // core/content_plan.py (предел хранения, как у заметки; сервер проверяет
    // сам, здесь — счётчик под полем).
    var AGENT_TEXT_MAX = 2000;
    // Происхождение материала: 'agent' — создан ИИ-агентом через MCP (ставит
    // сервер при создании, не редактируется). Фильтр «Только от ИИ» — ?origin=agent.
    var ORIGIN_AGENT = 'agent';
    // Подтверждение «Удалить черновики ИИ» называет материалы поимённо, но не
    // больше 8 (окно не должно уезжать за экран); остальные — «и ещё N».
    var AGENT_DEL_SHOWN = 8;
    // 1 МБ = 1024 x 1024 байт — как пределы MAX_IMAGE_BYTES / MAX_VIDEO_BYTES
    // в core/content_media.py.
    var MB = 1024 * 1024;
    var MEDIA_ACCEPT = 'image/jpeg,image/png,image/webp,video/mp4';
    var STATE_FILTERS = ['overdue', 'failed', 'incomplete', 'ready', 'scheduled', 'paused'];
    // Состояния, для которых есть сквозной вид по всем месяцам (?state= без
    // ?month=): их считает полоса «Требует внимания» за любой месяц.
    var SCOPE_STATES = ['overdue', 'failed'];
    var SCOPE_NAMES = { overdue: 'Время вышло', failed: 'Ошибки отправки' };
    var CHANNEL_KEYS = ['telegram', 'instagram', 'bot'];
    var MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
    var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
    var TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
    // Допустимые даты — зеркало YEAR_MIN / YEAR_MAX в core/content_plan.py
    // (сервер проверяет сам; здесь — атрибуты min/max поля и ранняя проверка,
    // чтобы не отправлять заведомо отклоняемую дату).
    var YEAR_MIN = 2020;
    var YEAR_MAX = 2100;
    var DATE_MIN = YEAR_MIN + '-01-01';
    var DATE_MAX = YEAR_MAX + '-12-31';
    // Дата и время: изменение, пришедшее меньше чем через 1 с после нажатия
    // клавиши в этом поле, — набор с клавиатуры (браузер шлёт change на каждый
    // сегмент: «2» в дне уже даёт целую, но не ту дату). Такое значение ждёт
    // ухода из поля или Enter. Изменение без нажатия клавиши — выбор в
    // календаре или часах браузера: значение целое, сохраняется сразу.
    var DT_TYPING_MS = 1000;

    // Вид состояния размещения: оттенок (класс тона hub.css) + начертание
    // (класс gh-cp-st-<состояние> в content_plan.css). Черновики — контуром
    // (ещё не решено), утверждённое и факты — заливкой, пауза и отмена —
    // приглушённо. Так «Вышло» не путается с «Запланировано», а «Время вышло»
    // — с «Не хватает»:
    //   incomplete — пунктирный контур, оранжевый: черновику чего-то не хватает;
    //   ready      — контур, акцент: можно утверждать;
    //   scheduled  — спокойная графитовая заливка: в очереди;
    //   overdue    — оранжевая заливка: время вышло, выход не отмечен;
    //   paused     — серый, пунктир: остановлено;
    //   published  — зелёная заливка: вышло;
    //   failed     — красная заливка: ошибка отправки;
    //   cancelled  — серый, зачёркнуто.
    var STATE_HUE = {
        incomplete: 'warning', ready: 'accent', scheduled: 'muted', overdue: 'warning',
        paused: 'muted', published: 'success', failed: 'danger', cancelled: 'muted'
    };
    var LEGEND_STATES = ['incomplete', 'ready', 'scheduled', 'overdue', 'paused', 'published', 'failed', 'cancelled'];
    // Вышедшее размещение показывает снимок на момент утверждения (сервер:
    // content_source 'snapshot'), а не текущий текст материала.
    var SNAPSHOT_NOTE = 'Так вышло: текст и файлы на момент утверждения';
    var LIVE_NOW_NOTE = 'данные на сейчас, не на момент выхода';

    var KIND_HINTS = {
        fixed: 'текст и фото утверждаются заранее и выходят ровно такими, какими их утвердили.',
        live: 'шаблон: в момент выхода в него подставляются свежие данные таплиста бара.'
    };
    var LIVE_EXPLAIN = 'При выходе подставляются только данные таплиста; остальной текст не меняется. ' +
        'Если данных нет или они не проверены — публикация остановится.';
    var BOT_NOTE = 'Рассылка через бота добавляется отдельно и никогда не включается выбором всех баров.';
    var APPROVE_TEXT = 'Утверждаются только эти подготовленные материалы. Незаконченные остаются ' +
        'черновиками и не уходят.';
    var SIZE_UNKNOWN = 'неизвестно: бот не подключён';

    // Пометка «ИИ»: материал создал ИИ-агент через MCP (сервер ставит origin
    // 'agent' при создании; копия, которую сделал человек, — уже не «ИИ»).
    var AI_TIP = 'Материал создал ИИ-агент (через MCP) от имени владельца. Проверьте текст, фото и размещения ' +
        'перед утверждением: агент только готовит черновики.';
    var WHY_PLACEHOLDER = 'Зачем этот пост: повод, рубрика, на какие данные он опирается. Агент заполняет сам, ' +
        'можно дописать.';
    var SHOTS_PLACEHOLDER = 'Список кадров: что снять, где и как. Например: краны крупно; бармен наливает; ' +
        'стол с закусками у окна.';
    var AGENT_FIELD_TIP = 'Предел хранения — ' + AGENT_TEXT_MAX + ' знаков, как у заметки: это пояснение и список ' +
        'кадров, а не текст поста. В публикацию не уходит, утверждение не снимает.';

    // Пояснение к каждому состоянию размещения (подсказка на бейдже). Само
    // состояние считает сервер; здесь только слова о том, что оно значит.
    var STATE_TIPS = {
        incomplete: 'Черновик, которому чего-то не хватает для утверждения.',
        ready: 'Черновик заполнен полностью: его можно утвердить.',
        scheduled: 'Утверждено, время выхода ещё впереди.',
        overdue: 'Утверждено, время выхода прошло, а выход не отмечен. Пока отправка не ' +
            'подключена, отметьте выход вручную.',
        paused: 'Утверждено, но остановлено: не выйдет, пока паузу не снимут.',
        published: 'Вышло (пока отмечается вручную).',
        failed: 'Ошибка отправки. Можно повторить отправку.',
        cancelled: 'Отменено: остаётся в плане для истории, можно вернуть.'
    };

    // Действия над размещением по хранимому статусу (переходы — ACTIONS в
    // core/content_plan.py; неподходящий переход сервер отклонит с 409).
    var ACTIONS_BY_STATUS = {
        draft: ['approve', 'cancel', 'delete'],
        approved: ['pause', 'unapprove', 'mark_published', 'cancel', 'delete'],
        paused: ['resume', 'unapprove', 'mark_published', 'cancel', 'delete'],
        failed: ['retry', 'mark_published', 'cancel', 'delete'],
        cancelled: ['restore', 'delete'],
        published: []
    };
    var ACTION_LABELS = {
        approve: 'Утвердить', pause: 'Пауза', resume: 'Снять паузу',
        unapprove: 'Снять утверждение', mark_published: 'Отметить вышедшим',
        cancel: 'Отменить', restore: 'Вернуть', retry: 'Повторить отправку', delete: 'Удалить'
    };

    var X_SVG = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">' +
        '<path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke-width="1.6" stroke-linecap="round"/></svg>';
    var PLUS_SVG = '<svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">' +
        '<path d="M6 1.5v9M1.5 6h9" stroke-width="1.8" stroke-linecap="round"/></svg>';

    // ==================== состояние ====================

    var S = {
        month: null,
        view: 'table',
        bar: '',                 // '' = все бары
        channel: '',             // '' = все площадки
        stateFilter: '',
        origin: '',              // '' — все материалы, 'agent' — только от ИИ (?origin=agent)
        scope: '',               // 'state' — сквозной вид по всем месяцам (?state= без ?month=)
        data: null,              // ответ GET /api/content-plan
        extra: {},               // id -> материал, открытый в карточке, но выпавший из списка сквозного вида
        seq: 0,                  // номер последнего запроса месяца (старые ответы отбрасываются)
        selected: {},            // id материала -> true (массовые действия)
        openId: null,            // открытая карточка
        focusPid: null,          // размещение, по которому карточку открыли
        scrollToPid: null,
        expanded: {},            // id размещения -> редактор раскрыт
        previewPid: null,
        addForm: null,
        live: null,              // проверка шаблона на текущих данных {mid, loading, result, error}
        liveBar: '',
        previewLive: {},         // ключ размещения -> {loading} | {result} | {error}
        log: null,               // {id, entries, error, all}
        shiftDays: '',
        repeatDays: [],
        dirty: {},               // ключ поля автосохранения -> несохранённое значение
        savedVal: {},            // ключ -> значение, сохранённое, пока поле было в фокусе (см. saveKey)
        dtPending: {},           // data-fk поля даты/времени -> набрано с клавиатуры, ещё не сохранено
        dtKeyAt: {},             // data-fk поля даты/времени -> время последнего нажатия клавиши, мс
        drawerStale: false,      // перерисовку карточки отложили, пока в поле даты/времени идёт набор
        pickFor: null,           // id материала, для которого открыт выбор файлов
        keepalive: false,        // запросы уходят с keepalive (уход со страницы)
        saving: 0,
        saveState: '',
        saveError: '',
        uploading: null,
        knownMonth: {},          // id материала -> месяц (карточка следует за материалом)
        resolving: null,
        reviewsOn: false,
        reviewsKey: null,
        reviewsDays: null,
        reviewsErr: false,
        calOpen: {},             // день -> показаны все размещения
        approve: null,
        copy: null,
        pendingOpen: null,
        // Бриф для агента: {loading} | {error} | {data: ответ GET, examples: [..]}.
        // examples — список примеров на экране (с пустыми, которые только что
        // добавили): сервер пустые отбрасывает, поэтому экран держит свой.
        brief: null,
        briefDirty: {},          // ключ поля брифа -> несохранённое значение
        briefSaving: 0,
        briefSave: '',           // '' | 'dirty' | 'saving' | 'saved' | 'error'
        briefError: ''
    };

    var el = {};
    var savers = {};
    // Автосохранение полей брифа: свои отложенные вызовы (PUT брифа, а не PATCH
    // материала), но сбрасываются вместе с остальными (flushSavers).
    var briefSavers = {};

    // ==================== мелочи ====================

    function byId(id) { return document.getElementById(id); }
    function enc(value) { return encodeURIComponent(value === null || value === undefined ? '' : value); }
    function esc(value) { return GH.esc(value); }
    function tip(text) { return text ? ' data-tip="' + esc(text) + '"' : ''; }
    function help(text) {
        return '<button type="button" class="gh-help"' + tip(text) + ' aria-label="Пояснение">?</button>';
    }
    function nText(n, one, few, many) { return n + ' ' + GH.plural(n, one, few, many); }
    function multiline(text) { return esc(text).replace(/\n/g, '<br>'); }
    function closest(node, selector) {
        return node && node.closest ? node.closest(selector) : null;
    }
    function pad2(n) { return (n < 10 ? '0' : '') + n; }
    function each(list, fn) { for (var i = 0; i < (list || []).length; i++) fn(list[i], i); }
    function findIn(list, key) {
        for (var i = 0; i < (list || []).length; i++) if (list[i].key === key) return list[i];
        return null;
    }
    function currentMonth() {
        return S.data && S.data.today ? S.data.today.slice(0, 7) : GH.mskNow().month;
    }

    // Длина текста в символах Unicode, как len() на сервере: суррогатная пара
    // (символ вне BMP) считается одним символом, а не двумя.
    function charLen(text) {
        return String(text || '').replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, '_').length;
    }

    // '9 окт' (без дня недели).
    function dayMon(iso) {
        var s = GH.fmtDateShort(iso);
        var i = s.indexOf(',');
        return i > 0 ? s.slice(0, i) : s;
    }
    // '9 окт, пт · 16:00' / 'без даты · без времени'.
    function whenText(p) {
        return (p.date ? GH.fmtDateShort(p.date) : 'без даты') + ' · ' + (p.time || 'без времени');
    }
    function weekdaysText(list) {
        var out = [];
        each(list, function (d) { if (GH.WEEKDAYS[d]) out.push(GH.WEEKDAYS[d].toLowerCase()); });
        return out.join(', ');
    }
    // Размер файла: от 1 МБ — в МБ с одним знаком (half-up), иначе в КБ целых.
    function fileSize(bytes) {
        var n = Number(bytes) || 0;
        if (n >= MB) return GH.fmtNum(n / MB, 1) + ' МБ';
        return GH.fmtNum(Math.max(1, n / 1024), 0) + ' КБ';
    }
    function mbText(bytes) {
        return bytes ? GH.fmtNum(bytes / MB, 0) + ' МБ' : '—';
    }

    // ==================== справочники из ответа ====================

    function stateInfo(key) {
        return findIn(S.data && S.data.states, key) || { key: key, label: String(key), tone: 'muted' };
    }
    function channelInfo(key) {
        return findIn(S.data && S.data.channels, key) || { key: key, name: GH.CHANNEL_NAMES[key] || key };
    }
    function chName(key) { return GH.CHANNEL_NAMES[key] || channelInfo(key).name || key; }
    function chShort(key) { return GH.CHANNEL_SHORT[key] || key; }
    function audiences() { return (S.data && S.data.audiences) || []; }
    function liveSources() { return (S.data && S.data.live_sources) || []; }

    function materials() { return (S.data && S.data.materials) || []; }
    function inPayload(id) {
        var list = materials();
        for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
        return null;
    }
    // Материал из ответа месяца; в сквозном виде — ещё и открытый в карточке
    // материал, который выпал из списка (например, его последнее просроченное
    // размещение отметили вышедшим): карточка остаётся на нём, а не прыгает
    // в его месяц.
    function findMaterial(id) {
        return inPayload(id) || (S.scope && S.extra[id]) || null;
    }
    function findPlacement(m, pid) {
        var list = (m && m.placements) || [];
        for (var i = 0; i < list.length; i++) if (list[i].id === pid) return list[i];
        return null;
    }
    function current() { return S.openId ? findMaterial(S.openId) : null; }

    // Статусы, которые сервер возвращает в черновик при смене содержания —
    // зеркало UNAPPROVE_ON_CONTENT в core/content_plan.py. По ним считаются
    // предупреждения «правка снимет утверждение».
    function locksOnContent(p) {
        return p.status === 'approved' || p.status === 'paused' || p.status === 'failed';
    }

    // Классы вида состояния размещения (см. STATE_HUE): тон + начертание.
    function stateCls(state) {
        if (!Object.prototype.hasOwnProperty.call(STATE_HUE, state)) return GH.toneClass('muted');
        return GH.toneClass(STATE_HUE[state]) + ' gh-cp-st-' + state;
    }
    // Подпись состояния на бейдже: у «Не хватает» подробности идут отдельной
    // строкой, поэтому бейдж короткий; у остальных — подпись сервера (у живого
    // материала «Шаблон утверждён, данные — при выходе» вместо «Запланировано»).
    function stateLabel(p) {
        var info = stateInfo(p.display_state);
        if (p.display_state === 'incomplete' || !p.display_label) return info.label;
        return p.display_label;
    }

    // Файлы, которые показывает размещение: сервер отдаёт media_items
    // [{name, kind, url}] — у вышедшего это снимок на момент утверждения, даже
    // если файл уже убрали из материала. Старый ответ без media_items — ищем
    // по имени среди файлов материала.
    function placementFiles(m, p) {
        if (p && p.media_items) return p.media_items;
        return mediaFor(m, (p && p.effective_media) || []);
    }

    function legendHtml() {
        var html = '';
        each(LEGEND_STATES, function (key) {
            html += '<span class="gh-cp-legend-i"' + tip(STATE_TIPS[key]) + '><span class="gh-cp-sw ' +
                stateCls(key) + '"></span>' + esc(stateInfo(key).label) + '</span>';
        });
        return '<span class="gh-cp-legend" aria-label="Цвета состояний">' + html + '</span>';
    }

    // ==================== фильтры ====================

    function placementMatches(p) {
        if (S.bar && p.bar !== S.bar && p.bar !== 'all') return false;
        if (S.channel && p.channel !== S.channel) return false;
        if (S.stateFilter && p.display_state !== S.stateFilter) return false;
        return true;
    }
    // Фильтр «Только от ИИ» (?origin=agent): материал целиком — его origin
    // ставит сервер при создании (core/content_plan.py, origin_of).
    function originMatches(m) {
        return !S.origin || m.origin === S.origin;
    }
    function materialVisible(m) {
        if (!originMatches(m)) return false;
        var pls = m.placements || [];
        if (!pls.length) return !S.stateFilter;
        for (var i = 0; i < pls.length; i++) if (placementMatches(pls[i])) return true;
        return false;
    }
    // Строка таблицы: материал этого месяца. Пока включён фильтр состояния —
    // ещё и материал другого месяца, у которого подходящее размещение датировано
    // этим месяцем: сводка месяца (stats.by_state сервера) считает и такие
    // размещения, и без этого кнопка «Время вышло: 1» вела бы в пустую таблицу.
    // Такие строки помечены «план: <месяц>».
    function inTable(m) {
        if (m.in_month) return true;
        if (!S.stateFilter) return false;
        var pls = m.placements || [];
        for (var i = 0; i < pls.length; i++) {
            var p = pls[i];
            if (p.date && p.date.slice(0, 7) === S.month && placementMatches(p)) return true;
        }
        return false;
    }
    function tableMaterials() {
        var out = [];
        each(materials(), function (m) { if (inTable(m) && materialVisible(m)) out.push(m); });
        return out;
    }
    function filtersActive() { return !!(S.bar || S.channel || S.stateFilter || S.origin); }

    // Материалы ИИ-агента в плане на экране: total — сколько их (для чипа
    // «Только от ИИ»), drafts — черновики ИИ плана этого месяца (agent_draft
    // считает сервер: все размещения — черновики или отменены) для «Удалить
    // черновики ИИ». В сквозном виде (все месяцы) удаления нет: оно — по месяцу.
    function agentStats() {
        var out = { total: 0, drafts: [] };
        each(materials(), function (m) {
            if (m.origin !== ORIGIN_AGENT || !m.in_month) return;
            out.total++;
            if (m.agent_draft && !S.scope) out.drafts.push(m);
        });
        return out;
    }

    // ==================== загрузка и изменения ====================

    function withMonth(url) {
        return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'month=' + enc(S.month);
    }

    // Параметры запроса: keepalive — только при уходе со страницы (pagehide):
    // браузер довезёт запрос, даже когда страница уже закрыта.
    function apiOpts() { return S.keepalive ? { keepalive: true } : undefined; }

    // Полоса «Требует внимания» (common.js) считает то же, что меняет эта
    // страница: после каждого успешного изменения её числа перечитываются.
    function refreshAttention() {
        if (GH.loadAttention) GH.loadAttention();
    }

    // Что грузить: сквозной вид — GET ?state= без месяца (контракт A.1), иначе
    // месяц.
    function listUrl() {
        return S.scope ? API + '?state=' + enc(S.stateFilter) : API + '?month=' + enc(S.month);
    }

    // opts.material — свежий материал из ответа на изменение: в сквозном виде
    // карточка остаётся на нём, даже если он выпал из списка.
    function load(opts) {
        var my = ++S.seq;
        var fresh = opts && opts.material;
        if (!S.data) showMsg('Загружаю план…', false);
        return GH.api('GET', listUrl()).then(function (data) {
            if (my !== S.seq) return false;
            data = data || {};
            if (S.scope && data.scope !== 'state') {
                // Сервер не знает сквозного вида: это ответ за текущий месяц.
                // Остаёмся в месяце с фильтром состояния — подпись «Все месяцы»
                // над одним месяцем была бы неправдой.
                S.scope = '';
                GH.setParams({ month: data.month || S.month });
            }
            if (data.month && MONTH_RE.test(data.month)) S.month = data.month;
            S.data = data;
            S.extra = {};
            if (S.scope && fresh && fresh.id === S.openId && !inPayload(fresh.id)) S.extra[fresh.id] = fresh;
            hideErr();
            pruneSelection();
            renderAll();
            afterLoad();
            return true;
        }, function (err) {
            if (my !== S.seq) return false;
            showLoadError(err);
            return false;
        });
    }
    // Перечитать план после успешного изменения (и полосу внимания).
    function reload(opts) {
        refreshAttention();
        return load(opts);
    }

    // Карточка открыта, а материала в месяце больше нет (перенесли дату темы,
    // сдвинули, открыли ссылкой на другой месяц) — ищем его месяц.
    function afterLoad() {
        if (!S.openId) return;
        var m = findMaterial(S.openId);
        if (m) {
            S.knownMonth[m.id] = m.month;
            loadLog();
            return;
        }
        resolveMissing(S.openId);
    }

    function resolveMissing(id) {
        if (S.resolving === id) return;
        S.resolving = id;
        GH.api('GET', API + '/materials/' + enc(id)).then(function (res) {
            var mat = res && res.material;
            if (S.scope && mat) {
                // Сквозной вид: месяц не переключаем — карточка остаётся на
                // материале, даже если его уже нет в списке.
                S.resolving = null;
                S.extra[mat.id] = mat;
                S.knownMonth[mat.id] = mat.month;
                if (S.openId !== mat.id) return;
                if (drawerOpen()) renderDrawer();
                else openMaterial(mat.id, S.focusPid);
                loadLog();
                return;
            }
            var mon = mat && mat.month;
            if (mon && mon !== S.month) {
                GH.toast('Материал в плане «' + GH.monthLabel(mon) + '» — открываю этот месяц', 'muted');
                S.month = mon;
                S.selected = {};
                S.calOpen = {};
                GH.setParams({ month: mon });
                renderChrome();
                load().then(function () {
                    S.resolving = null;
                    if (findMaterial(id)) openMaterial(id, S.focusPid);
                    else closeMissing('Материал не найден в плане');
                });
                return;
            }
            S.resolving = null;
            closeMissing('Материал не найден в плане этого месяца');
        }, function (err) {
            S.resolving = null;
            closeMissing(err.status === 404 ? 'Материал не найден — возможно, его удалили' : err.message);
        });
    }

    function closeMissing(message) {
        GH.toast(message, 'warning');
        if (!el.drawer.hidden) {
            GH.closeDrawer(el.drawer);
        } else {
            S.openId = null;
            GH.setParams({ open: null });
        }
    }

    // 'TG ВО 9 окт 16:00, IG Сеть 10 окт 12:00' — размещения с id из списка
    // (по свежему материалу из ответа сервера).
    function placementNames(m, ids) {
        var out = [];
        each(ids, function (id) {
            var p = findPlacement(m, id);
            if (p) out.push(chShort(p.channel) + ' ' + GH.barShort(p.bar) + (p.date ? ' ' + dayMon(p.date) : '') +
                (p.time ? ' ' + p.time : ''));
        });
        return out.join(', ');
    }

    function noteUnapproved(res) {
        var list = res && res.unapproved;
        if (list && list.length) {
            var names = res.material ? placementNames(res.material, list) : '';
            GH.toast('Утверждение снято с ' + nText(list.length, 'размещения', 'размещений', 'размещений') +
                (names ? ' (' + names + ')' : '') + ': изменилось содержание. Проверьте и утвердите заново.',
                'warning');
        }
    }

    function reportError(err) {
        var message = (err && err.message) || 'Ошибка запроса';
        if (err && err.status === 503) showErr('Хранилище плана недоступно: ' + message +
            '. Файл не перезаписывается — сообщите администратору.');
        GH.toast(message, 'danger');
    }

    // Изменение данных: запрос -> перечитать месяц -> перерисовать.
    // -> Promise<ответ сервера | null при ошибке> (ошибку уже показали).
    // Ошибка 400 (сервер отклонил значение, например перенос утверждённой
    // публикации в прошлое): поля карточки перерисовываются из последнего
    // ответа сервера, чтобы в поле не осталось несохранённое значение.
    function mutate(method, url, body) {
        return GH.api(method, withMonth(url), body, apiOpts()).then(function (res) {
            noteUnapproved(res);
            if (res && res.material) S.knownMonth[res.material.id] = res.material.month;
            return reload({ material: res && res.material }).then(function () { return res || {}; });
        }, function (err) {
            reportError(err);
            if (err.status === 404 || err.status === 409) reload();
            else if (current()) renderDrawer();
            return null;
        });
    }

    // ==================== сообщения ====================

    function showMsg(text, isErr) {
        el.msg.textContent = text;
        el.msg.classList.toggle('is-err', !!isErr);
        el.msg.hidden = false;
        el.table.hidden = true;
        el.cal.hidden = true;
    }
    function showErr(text) {
        el.errText.textContent = text;
        el.err.hidden = false;
    }
    function hideErr() { el.err.hidden = true; }
    function showLoadError(err) {
        var text = err.status === 503
            ? 'Хранилище плана недоступно: ' + err.message + '. Файл не перезаписывается — сообщите администратору.'
            : 'Не удалось загрузить план: ' + err.message;
        showErr(text);
        // Подробности — в баннере выше; на месте плана — короткое сообщение.
        if (!S.data) showMsg('План не загрузился. Причина — в сообщении выше, там же кнопка «Повторить».', true);
        else GH.toast(err.message, 'danger');
    }

    // ==================== отрисовка страницы ====================

    function renderAll() {
        var y = window.pageYOffset;
        renderChrome();
        renderSummary();
        renderOrigin();
        renderStateBar();
        renderView();
        renderBulk();
        if (S.openId && findMaterial(S.openId)) renderDrawer();
        if (Math.abs(window.pageYOffset - y) > 1) window.scrollTo(0, y);
    }

    function renderChrome() {
        el.monthLabel.textContent = S.scope ? 'Все месяцы' : GH.monthLabel(S.month);
        // В режиме «Все месяцы» (?state без ?month) утверждение и копирование
        // выключены: обе операции работают с одним месяцем, а на экране — выборка
        // из разных месяцев. Иначе кнопка молча действовала бы на текущий месяц.
        var scopeTip = S.scope ? 'Недоступно в режиме «Все месяцы»: выберите месяц стрелками' : '';
        el.approveBtn.disabled = !!S.scope;
        el.copyBtn.disabled = !!S.scope;
        el.approveBtn.title = scopeTip;
        el.copyBtn.title = scopeTip;
        el.barLabel.textContent = S.bar ? GH.barName(S.bar) : 'Все бары';
        el.chLabel.textContent = S.channel ? chName(S.channel) : 'Все площадки';
        GH.setSeg(el.viewSeg, S.view);
        var dc = S.data && S.data.delivery_connected;
        var anyConnected = false;
        if (dc) for (var k in dc) if (Object.prototype.hasOwnProperty.call(dc, k) && dc[k]) anyConnected = true;
        el.delivery.hidden = !dc || anyConnected;
    }

    function sumItem(stateKey, label, n, text, cls) {
        var inner = '<span>' + esc(label) + '</span><b>' + esc(n) + '</b>';
        var klass = 'gh-sumline-i gh-cp-sum-i' + (cls ? ' ' + cls : '');
        if (!stateKey) return '<span class="' + klass + '"' + tip(text) + '>' + inner + '</span>';
        if (S.stateFilter === stateKey) klass += ' is-on';
        return '<button type="button" class="' + klass + '" data-state="' + esc(stateKey) + '"' +
            tip(text + '\nНажмите, чтобы показать только их.') + '>' + inner + '</button>';
    }

    function renderSummary() {
        if (!S.data) { el.sum.innerHTML = ''; return; }
        var st = S.data.stats || {};
        var by = st.by_state || {};
        var scope = S.scope
            ? '\nСчитает сервер по материалам всех месяцев, у которых есть размещения в состоянии «' +
                SCOPE_NAMES[S.stateFilter] + '», без учёта фильтров.'
            : '\nСчитает сервер по всему месяцу, без учёта фильтров.';
        var html = sumItem('', 'Материалов', st.materials || 0, (S.scope
            ? 'Материалы любых месяцев, у которых есть размещения в этом состоянии.'
            : 'Материалы плана этого месяца: темы и публикации, отнесённые к месяцу (по дате темы ' +
                'или по месяцу, в котором их создали).') + scope);
        html += sumItem('', 'Размещений', st.placements || 0, (S.scope
            ? 'Все размещения этих материалов, во всех состояниях.'
            : 'Размещения материалов месяца и размещения, дата которых попадает в этот месяц, во всех ' +
                'состояниях, включая вышедшие и отменённые.') + scope);
        html += sumItem('ready', stateInfo('ready').label, by.ready || 0,
            'Черновики, у которых заполнено всё: текст, фото там, где они нужны, бар, аудитория, ' +
            'дата и время впереди.' + scope, 'is-accent');
        html += sumItem('scheduled', stateInfo('scheduled').label, by.scheduled || 0,
            'Утверждённые размещения, время выхода которых ещё впереди.' + scope);
        html += sumItem('incomplete', stateInfo('incomplete').label, by.incomplete || 0,
            'Черновики, которым чего-то не хватает для утверждения: текста, фото, бара, аудитории, ' +
            'даты или времени — или время выхода уже прошло.' + scope, by.incomplete ? 'is-warn' : '');
        if (by.overdue) {
            html += sumItem('overdue', 'Время вышло', by.overdue,
                'Утверждённые размещения, время выхода которых прошло, а выход не отмечен.' + scope, 'is-warn');
        }
        if (by.paused) {
            html += sumItem('paused', stateInfo('paused').label, by.paused,
                'Утверждённые, но остановленные размещения.' + scope);
        }
        if (by.failed) {
            html += sumItem('failed', 'Ошибки отправки', by.failed,
                'Размещения, которые не удалось отправить.' + scope, 'is-warn');
        }
        el.sum.innerHTML = html;
    }

    // Чип «Только от ИИ» и «Удалить черновики ИИ» рядом со сводкой. Блок виден,
    // когда в плане есть материалы агента или фильтр включён (снять его можно
    // всегда); кнопка удаления — когда в плане месяца есть черновики ИИ.
    function renderOrigin() {
        if (!S.data) { el.origin.hidden = true; return; }
        var st = agentStats();
        var on = S.origin === ORIGIN_AGENT;
        el.origin.hidden = !st.total && !on;
        el.originBtn.classList.toggle('is-on', on);
        el.originBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
        el.originN.textContent = String(st.total);
        var n = st.drafts.length;
        el.agentDel.hidden = !n;
        el.agentDel.textContent = 'Удалить черновики ИИ: ' + n;
        el.agentDel.setAttribute('data-tip', ((S.data && S.data.agent_draft_rule) ||
            'Черновик ИИ — материал агента, у которого все размещения — черновики или отменены.') +
            '\nУдаляются только черновики ИИ плана «' + GH.monthLabel(S.month) + '», перед удалением — ' +
            'подтверждение со списком.');
    }

    function setOrigin(value) {
        S.origin = value === ORIGIN_AGENT ? ORIGIN_AGENT : '';
        GH.setParams({ origin: S.origin || null });
        renderOrigin();
        renderView();
        renderBulk();
    }

    function renderStateBar() {
        if (!S.stateFilter) {
            el.stateBar.hidden = true;
            el.stateBar.innerHTML = '';
            return;
        }
        var info = stateInfo(S.stateFilter);
        if (S.scope) {
            el.stateBar.innerHTML =
                '<span class="gh-cp-statebar-t">Список за все месяцы: материалы, у которых есть такие размещения</span>' +
                '<span class="gh-chip gh-cp-scopechip ' + stateCls(S.stateFilter) + '"' +
                    tip('Материалы любых месяцев с размещениями в состоянии «' + info.label + '». Сюда ведёт ' +
                        'полоса «Требует внимания»: она считает такие размещения за все месяцы.\n' +
                        STATE_TIPS[S.stateFilter] + '\nКрестик — вернуться к плану текущего месяца.') + '>' +
                    '<span class="gh-chip-dot"></span>Все месяцы · ' + esc(SCOPE_NAMES[S.stateFilter]) +
                    '<button type="button" class="gh-chip-x" data-act="clear-state" ' +
                        'aria-label="Закрыть список за все месяцы">' + X_SVG + '</button>' +
                '</span>';
            el.stateBar.hidden = false;
            return;
        }
        el.stateBar.innerHTML =
            '<span class="gh-cp-statebar-t">Показаны только размещения в состоянии</span>' +
            '<span class="gh-chip ' + stateCls(S.stateFilter) + '"' + tip(STATE_TIPS[S.stateFilter]) + '>' +
                '<span class="gh-chip-dot"></span>' + esc(info.label) +
                '<button type="button" class="gh-chip-x" data-act="clear-state" aria-label="Снять фильтр состояния">' +
                    X_SVG + '</button>' +
            '</span>';
        el.stateBar.hidden = false;
    }

    function setStateFilter(value) {
        var next = STATE_FILTERS.indexOf(value) >= 0 ? value : '';
        // Сквозной вид держится на одном состоянии: другой фильтр или снятие
        // фильтра возвращают обычный план текущего месяца.
        if (S.scope) { leaveScope(S.month, next); return; }
        S.stateFilter = next;
        GH.setParams({ state: S.stateFilter || null });
        renderSummary();
        renderStateBar();
        renderView();
        renderBulk();
    }

    // Выход из сквозного вида в месяц mon; state — фильтр состояния, который
    // остаётся ('' — без фильтра). Если фильтр остаётся, месяц пишется в адрес
    // явно: иначе перезагрузка страницы (?state= без ?month=) снова открыла бы
    // сквозной вид.
    function leaveScope(mon, state) {
        flushAll();
        S.scope = '';
        S.extra = {};
        S.month = MONTH_RE.test(mon || '') ? mon : GH.mskNow().month;
        S.stateFilter = STATE_FILTERS.indexOf(state) >= 0 ? state : '';
        S.selected = {};
        S.calOpen = {};
        var params = { state: S.stateFilter || null };
        params.month = (S.stateFilter || S.month !== GH.mskNow().month) ? S.month : null;
        GH.setParams(params);
        renderChrome();
        renderStateBar();
        load();
        if (S.reviewsOn) loadReviews();
    }

    function renderView() {
        if (!S.data) return;
        el.msg.hidden = true;
        el.table.hidden = S.view !== 'table';
        el.cal.hidden = S.view !== 'calendar';
        if (S.view === 'table') renderTable();
        else renderCalendar();
    }

    function emptyHtml() {
        if (S.scope && !materials().length) {
            return '<div class="gh-empty">' +
                '<div class="gh-empty-t">Размещений в состоянии «' + esc(stateInfo(S.stateFilter).label) +
                    '» нет ни в одном месяце</div>' +
                '<div class="gh-empty-s">Всё отмечено: полоса «Требует внимания» обновится сама.</div>' +
                '<div class="gh-empty-a"><button type="button" class="gh-btn" data-act="leave-scope">' +
                    'К плану текущего месяца</button></div></div>';
        }
        var any = false;
        each(materials(), function (m) { if (m.in_month) any = true; });
        if (!any) {
            return '<div class="gh-empty">' +
                '<div class="gh-empty-t">В плане «' + esc(GH.monthLabel(S.month)) + '» пока нет материалов</div>' +
                '<div class="gh-empty-s">Добавьте тему или публикацию. Можно начать с копии прошлого месяца: ' +
                    'даты перенесутся по дням недели, копии откроются черновиками.</div>' +
                '<div class="gh-empty-a">' +
                    '<button type="button" class="gh-btn gh-btn-primary" data-act="add">' + PLUS_SVG +
                        'Добавить материал</button>' +
                    '<button type="button" class="gh-btn" data-act="copy">Скопировать прошлый месяц</button>' +
                '</div></div>';
        }
        if (S.origin && !agentStats().total) {
            return '<div class="gh-empty">' +
                '<div class="gh-empty-t">Материалов от ИИ в плане «' + esc(GH.monthLabel(S.month)) + '» нет</div>' +
                '<div class="gh-empty-s">ИИ-агент готовит черновики через MCP; они появятся здесь с пометкой ' +
                    '«ИИ». Правила, по которым он пишет, — в «Бриф для агента».</div>' +
                '<div class="gh-empty-a"><button type="button" class="gh-btn" data-act="origin-off">' +
                    'Показать все материалы</button></div></div>';
        }
        return '<div class="gh-empty">' +
            '<div class="gh-empty-t">Под выбранные фильтры ничего не попало</div>' +
            '<div class="gh-empty-s">Фильтры: бар, площадка' + (S.stateFilter ? ', состояние' : '') +
                (S.origin ? ', только от ИИ' : '') + '. Материалы без подходящих размещений скрыты.</div>' +
            '<div class="gh-empty-a"><button type="button" class="gh-btn" data-act="reset-filters">' +
                'Сбросить фильтры</button></div></div>';
    }

    // ==================== таблица ====================

    function weekStart(iso) { return GH.addDays(iso, -GH.weekday(iso)); }
    // Группа строки: неделя (понедельник) в плане месяца; месяц ('YYYY-MM') в
    // сквозном виде — там строки из разных месяцев.
    function groupKey(m) {
        if (!m.date) return '';
        return S.scope ? m.date.slice(0, 7) : weekStart(m.date);
    }
    function rangeLabel(a, b) {
        if (a.slice(0, 7) === b.slice(0, 7)) return (+a.slice(8)) + '–' + GH.fmtDate(b);
        return GH.fmtDate(a) + ' – ' + GH.fmtDate(b);
    }
    function groupRow(key, n) {
        var label;
        var hint;
        if (!key) {
            label = 'Без даты';
            hint = 'Темы без даты: у материала нет ни даты темы, ни размещений с датой.';
        } else if (S.scope) {
            label = GH.monthLabel(key);
            hint = 'Месяц даты материала: самой ранней даты его неотменённых размещений, иначе даты темы.';
        } else {
            var end = GH.addDays(key, 6);
            label = 'Неделя ' + rangeLabel(key, end);
            var today = S.data.today;
            if (today >= key && today <= end) label += ' · эта неделя';
            hint = 'Неделя с понедельника по воскресенье. Дата материала — самая ранняя дата его ' +
                'неотменённых размещений, иначе дата темы.';
        }
        return '<tr class="is-group gh-cp-grp"><td colspan="5"><span' + tip(hint) + '>' + esc(label) +
            '</span><span class="gh-cp-grp-n">' + esc(nText(n, 'материал', 'материала', 'материалов')) +
            '</span></td></tr>';
    }

    // Пометка «ИИ» у материала агента (таблица, календарь, шапка карточки).
    // withTip — своя подсказка; в плашке календаря её нет: там пояснение уже
    // в подсказке всей плашки (pillTip), а метка слишком мала для наведения.
    function aiMark(m, withTip) {
        if (!m || m.origin !== ORIGIN_AGENT) return '';
        return '<span class="gh-cp-ai"' + (withTip ? tip(AI_TIP) : ' aria-label="от ИИ"') + '>ИИ</span>';
    }

    function tagsHtml(m) {
        var out = '';
        if (m.kind === 'live') {
            out += '<span class="gh-badge gh-tone-accent"' + tip('Материал с актуальными данными: текст — шаблон, ' +
                'при выходе в него подставляются данные таплиста бара. Проверка — в карточке материала.') +
                '>Живые данные: ' + (m.live_source === 'taplist' ? 'таплист' : 'источник не выбран') + '</span>';
        }
        if (m.series && m.series.weekdays && m.series.weekdays.length) {
            var days = weekdaysText(m.series.weekdays);
            out += '<span class="gh-badge"' + tip('Серия повторов по дням недели: ' + days + '. Серию создаёт ' +
                '«Повторять в этом месяце по дням недели» в карточке; при копировании месяца серия ' +
                'создаётся заново.') + '>серия: ' + esc(days) + '</span>';
        }
        if (m.source_review_id) {
            out += '<span class="gh-badge"' + tip('Материал создан из отзыва гостя на странице «Отзывы».') +
                '>из отзыва</span>';
        }
        if (m.copied_from) {
            out += '<span class="gh-badge"' + tip('Копия материала из плана прошлого месяца.') + '>копия</span>';
        }
        if (!m.in_month && m.month) {
            out += '<span class="gh-badge gh-tone-muted"' + tip('Материал из плана «' + GH.monthLabel(m.month) +
                '»: в таблице этого месяца он виден, пока включён фильтр состояния, потому что его размещение ' +
                'датировано этим месяцем.') + '>план: ' + esc(GH.monthLabel(m.month)) + '</span>';
        }
        return out;
    }

    function excerpt(m) {
        var t = String(m.base_text || '').replace(/\s+/g, ' ').trim();
        return t.length > 160 ? t.slice(0, 160) + '…' : t;
    }

    function chipTip(m, p) {
        var when = p.date ? GH.fmtDate(p.date) + (p.time ? ', ' + p.time : ', без времени') : 'без даты';
        var lines = [chName(p.channel) + ' · ' + GH.barName(p.bar) + ' · ' + when, p.display_label];
        if (p.audience_info) lines.push('Аудитория: ' + p.audience_info.name);
        return lines.join('\n');
    }

    function chipHtml(m, p) {
        var when = (p.date && p.date !== m.date ? dayMon(p.date) + ' ' : '') + (p.time || '—');
        return '<button type="button" class="gh-chip gh-cp-chip ' + stateCls(p.display_state) +
            (p.display_state === 'cancelled' ? ' is-cancel' : '') + '" data-open="' + esc(m.id) +
            '" data-pid="' + esc(p.id) + '"' + tip(chipTip(m, p)) + '>' +
            '<span class="gh-chip-dot"></span><b>' + esc(chShort(p.channel)) + '</b>' +
            esc(GH.barShort(p.bar)) + '<span class="gh-cp-chip-t">' + esc(when) + '</span></button>';
    }

    function chipsHtml(m) {
        var pls = m.placements || [];
        if (!pls.length) {
            return '<span class="gh-cp-none"' + tip('Размещений нет: это тема. Добавьте, где и когда она ' +
                'выйдет, в карточке материала.') + '>только тема</span>';
        }
        var html = '';
        var hidden = 0;
        each(pls, function (p) {
            if (placementMatches(p)) html += chipHtml(m, p);
            else hidden++;
        });
        if (hidden) {
            html += '<span class="gh-chip gh-cp-chip-more"' + tip('Скрыто фильтром: ' +
                nText(hidden, 'размещение', 'размещения', 'размещений') +
                ' на других барах, площадках или в других состояниях.') + '>+' + hidden + '</span>';
        }
        return '<div class="gh-chips">' + html + '</div>';
    }

    function readyTip(m) {
        var s = m.summary || {};
        var counts = s.counts || {};
        // Полная подпись — первой строкой: в таблице длинная подпись («Не
        // хватает: нет фото — IG Сеть; …») обрезается до двух строк.
        var lines = s.label ? [s.label, ''] : [];
        if (!(m.placements || []).length) {
            lines.push('Размещений нет: это тема без публикаций.');
        } else {
            lines.push('Размещений без отменённых: ' + (s.total || 0) + ', из них готово к утверждению: ' +
                (s.ready || 0) + '.');
            var parts = [];
            each((S.data && S.data.states) || [], function (info) {
                if (counts[info.key]) parts.push(info.label + ' — ' + counts[info.key]);
            });
            if (parts.length) lines.push('По состояниям: ' + parts.join('; ') + '.');
            // Разбивка сервера: чего не хватает и где (summary.missing).
            if ((s.missing || []).length) {
                lines.push('Чего не хватает и где:');
                each(s.missing, function (x) {
                    lines.push('— ' + x.text + ': ' + (x.everywhere ? 'во всех размещениях' :
                        (x.where || []).join(', ')));
                });
            }
        }
        lines.push('');
        lines.push('Как проверяется готовность:');
        each((S.data && S.data.readiness_rules) || [], function (r) { lines.push(r); });
        return lines.join('\n');
    }
    function summaryRulesTip() {
        var rules = (S.data && S.data.summary_rules) || [];
        return 'Готовность материала — сводка по его размещениям. ' + rules.join('\n');
    }
    function readyHtml(m) {
        var s = m.summary || {};
        return '<span class="gh-badge gh-cp-ready ' + GH.toneClass(s.tone) + '"' + tip(readyTip(m)) + '>' +
            esc(s.label || '') + '</span>';
    }

    function rowHtml(m, repeatDate) {
        var today = S.data.today;
        var sel = !!S.selected[m.id];
        var cls = 'is-click gh-cp-row' + (sel ? ' is-sel' : '') + (m.date && m.date < today ? ' is-past' : '');
        var date;
        if (!m.date) {
            date = '<span class="gh-cp-d is-none">без даты</span>';
        } else {
            date = '<span class="gh-cp-d' + (repeatDate ? ' is-rep' : '') + '">' + esc(GH.fmtDateShort(m.date)) +
                '</span>' + (m.date === today ? '<span class="gh-badge gh-tone-accent gh-cp-today">сегодня</span>' : '');
        }
        var tags = tagsHtml(m);
        var ex = excerpt(m);
        return '<tr class="' + cls + '" data-mid="' + esc(m.id) + '">' +
            '<td class="gh-cp-c-sel"><label class="gh-cp-cbx"><input type="checkbox" data-sel="' + esc(m.id) + '"' +
                (sel ? ' checked' : '') + ' aria-label="Выбрать: ' + esc(m.title) + '"></label></td>' +
            '<td class="gh-cp-c-date">' + date + '</td>' +
            '<td class="gh-cp-c-mat">' + aiMark(m, true) +
                '<button type="button" class="gh-cp-mt" data-open="' + esc(m.id) + '">' + esc(m.title) + '</button>' +
                (tags ? '<div class="gh-cp-tags">' + tags + '</div>' : '') +
                (ex ? '<div class="gh-cp-ex">' + esc(ex) + '</div>' : '') + '</td>' +
            '<td class="gh-cp-c-pl">' + chipsHtml(m) + '</td>' +
            '<td class="gh-cp-c-ready">' + readyHtml(m) + '</td>' +
            '</tr>';
    }

    function renderTable() {
        var list = tableMaterials();
        if (!list.length) { el.table.innerHTML = emptyHtml(); return; }
        var counts = {};
        each(list, function (m) { var g = groupKey(m); counts[g] = (counts[g] || 0) + 1; });
        var allSel = true;
        each(list, function (m) { if (!S.selected[m.id]) allSel = false; });
        // Легенда та же, что в календаре: цвет чипа — состояние размещения.
        var html = '<div class="gh-cp-tablebar">' + legendHtml() + '</div>' +
            '<div class="gh-table-wrap gh-cp-tablewrap"><table class="gh-table gh-cp-table"><thead><tr>' +
            '<th class="gh-cp-c-sel"><label class="gh-cp-cbx"><input type="checkbox" data-selall' +
                (allSel ? ' checked' : '') + ' aria-label="Выбрать все строки"></label></th>' +
            '<th class="gh-cp-c-date">Дата</th>' +
            '<th class="gh-cp-c-mat">Материал</th>' +
            '<th class="gh-cp-c-pl">Размещения ' + help('Площадка (TG — Telegram, IG — Instagram, Бот — ' +
                'рассылка), бар (Сеть — на всю сеть) и время выхода. Цвет и начертание — состояние ' +
                'размещения (легенда над таблицей): черновики — контуром, утверждённое и вышедшее — ' +
                'заливкой. Нажмите, чтобы открыть размещение в карточке.') + '</th>' +
            '<th class="gh-cp-c-ready">Готовность ' + help(summaryRulesTip()) + '</th>' +
            '</tr></thead><tbody>';
        var lastGroup = null;
        var lastDate = null;
        each(list, function (m) {
            var g = groupKey(m);
            if (g !== lastGroup) {
                html += groupRow(g, counts[g]);
                lastGroup = g;
                lastDate = null;
            }
            html += rowHtml(m, !!m.date && m.date === lastDate);
            lastDate = m.date;
        });
        html += '</tbody></table></div>';
        el.table.innerHTML = html;
        var head = el.table.querySelector('[data-selall]');
        if (head && !allSel) {
            var some = false;
            each(list, function (m) { if (S.selected[m.id]) some = true; });
            head.indeterminate = some;
        }
    }

    // ==================== календарь ====================

    function sortDay(a, b) {
        var ta = a.p ? (a.p.time || '99:99') : '00:00';
        var tb = b.p ? (b.p.time || '99:99') : '00:00';
        var ca = a.p && a.p.display_state === 'cancelled' ? 1 : 0;
        var cb = b.p && b.p.display_state === 'cancelled' ? 1 : 0;
        if (ca !== cb) return ca - cb;
        if (ta !== tb) return ta < tb ? -1 : 1;
        var xa = a.p ? CHANNEL_KEYS.indexOf(a.p.channel) : -1;
        var xb = b.p ? CHANNEL_KEYS.indexOf(b.p.channel) : -1;
        if (xa !== xb) return xa - xb;
        return a.m.title < b.m.title ? -1 : (a.m.title > b.m.title ? 1 : 0);
    }

    // День -> [{m, p}] размещений с датой в месяце (под фильтрами) и тем
    // (материалов месяца без размещений в этом месяце, но с датой темы в нём).
    function calendarItems() {
        var days = {};
        function push(day, item) { (days[day] = days[day] || []).push(item); }
        each(materials(), function (m) {
            if (!originMatches(m)) return;
            var datedHere = false;
            each(m.placements, function (p) {
                if (!p.date || p.date.slice(0, 7) !== S.month) return;
                datedHere = true;
                if (placementMatches(p)) push(p.date, { m: m, p: p });
            });
            if (m.in_month && !datedHere && m.planned_date && m.planned_date.slice(0, 7) === S.month &&
                    materialVisible(m) && !S.stateFilter) {
                push(m.planned_date, { m: m, theme: true });
            }
        });
        for (var d in days) if (Object.prototype.hasOwnProperty.call(days, d)) days[d].sort(sortDay);
        return days;
    }

    function pillTip(x) {
        var ai = x.m.origin === ORIGIN_AGENT ? '\nИИ: материал создал агент (через MCP).' : '';
        if (x.theme) {
            return '«' + x.m.title + '»\nТема на этот день: размещений в этом месяце пока нет. ' +
                'Нажмите, чтобы открыть карточку.' + ai;
        }
        return chipTip(x.m, x.p) + '\nМатериал: «' + x.m.title + '»' + ai;
    }
    function pillHtml(x) {
        if (x.theme) {
            return '<button type="button" class="gh-cp-pill is-theme" data-open="' + esc(x.m.id) + '"' +
                tip(pillTip(x)) + '>' + aiMark(x.m, false) + '<span class="gh-cp-pill-n">Тема: ' +
                esc(x.m.title) + '</span></button>';
        }
        var p = x.p;
        return '<button type="button" class="gh-cp-pill ' + stateCls(p.display_state) +
            (p.display_state === 'cancelled' ? ' is-cancel' : '') + '" data-open="' + esc(x.m.id) +
            '" data-pid="' + esc(p.id) + '"' + tip(pillTip(x)) + '>' +
            '<span class="gh-cp-pill-t">' + esc(p.time || '—') + '</span> ' +
            esc(chShort(p.channel) + ' ' + GH.barShort(p.bar)) + ' · ' + aiMark(x.m, false) +
            '<span class="gh-cp-pill-n">' + esc(x.m.title) + '</span></button>';
    }

    // Сводка дня календаря (по видимым под фильтрами пунктам, без отменённых):
    //   materials — число РАЗНЫХ материалов (темы тоже): один «Таплист пятницы»
    //     на четыре бара — одна публикация в канале каждого бара, а не
    //     перегрузка дня; метка плотности ставится от CAL_DENSE_MIN материалов;
    //   placements — число размещений (для подсказки);
    //   clash — в этот день и пост (Telegram / Instagram), и рассылка бота для
    //     пересекающейся аудитории: охваты пересекаются, если один из них на всю
    //     сеть ('all') или бар совпадает. Гость может получить одно и то же
    //     дважды — повод проверить, нужно ли это.
    function dayStats(list) {
        var seen = {};
        var out = { materials: 0, placements: 0, clash: false };
        var posts = [];
        var bots = [];
        each(list, function (x) {
            if (x.p && x.p.display_state === 'cancelled') return;
            if (!seen[x.m.id]) { seen[x.m.id] = true; out.materials++; }
            if (!x.p) return;
            out.placements++;
            (x.p.channel === 'bot' ? bots : posts).push(x.p);
        });
        each(bots, function (b) {
            each(posts, function (p) {
                if (b.bar === 'all' || p.bar === 'all' || b.bar === p.bar) out.clash = true;
            });
        });
        return out;
    }
    function densityTip(st) {
        return 'Материалов в этот день: ' + st.materials + ' (размещений без отменённых: ' + st.placements + '). ' +
            'Метка плотности ставится от ' + CAL_DENSE_MIN + ' разных материалов в день: один материал на ' +
            'несколько баров или площадок считается один раз.';
    }
    var CLASH_TIP = 'В этот день и пост (Telegram или Instagram), и рассылка бота для пересекающейся аудитории ' +
        '(одного бара или всей сети): гость может получить одно и то же дважды. Проверьте, нужно ли это.';
    function dayMarks(st, dense) {
        return (st.clash ? '<span class="gh-cp-day-clash"' + tip(CLASH_TIP) + '>пост + бот</span>' : '') +
            (dense ? '<span class="gh-cp-day-cnt"' + tip(densityTip(st)) + '>' + st.materials + '</span>' : '');
    }

    function reviewsHtml(day) {
        if (!S.reviewsOn || !S.reviewsDays) return '';
        var r = S.reviewsDays[day];
        if (!r || !r.count) return '';
        var avg = r.avg === null || r.avg === undefined ? '' : ' · ' + GH.fmtNum(r.avg, 1);
        var text = 'Отзывы за день: ' + r.count + ', с оценкой: ' + (r.rated || 0) + '.';
        if (avg) {
            text += '\nСредняя оценка = сумма оценок / число отзывов с оценкой, округление половины ' +
                'вверх до 0,1.';
        }
        text += '\nОтзывы — со страницы «Отзывы», фильтр бара общий.';
        return '<span class="gh-cp-day-rv"' + tip(text) + '>' + r.count + ' отз' + avg + '</span>';
    }

    function dayCell(c, list) {
        var today = S.data.today;
        var past = c.iso < today;
        var canAdd = !c.out && !past;
        var st = dayStats(list);
        var dense = !c.out && st.materials >= CAL_DENSE_MIN;
        var cls = 'gh-cp-day' + (c.out ? ' is-out' : '') + (c.iso === today ? ' is-today' : '') +
            (past && !c.out ? ' is-past' : '') + (dense ? ' is-dense' : '') + (canAdd ? ' is-add' : '');
        var html = '<div class="' + cls + '" data-day="' + esc(c.iso) + '">' +
            '<div class="gh-cp-day-h"><span class="gh-cp-day-n">' + (+c.iso.slice(8)) + '</span>' +
            (c.iso === today ? '<span class="gh-cp-day-today">сегодня</span>' : '') +
            (c.out ? '' : dayMarks(st, dense)) +
            '</div>';
        if (!c.out) html += reviewsHtml(c.iso);
        if (!c.out && list.length) {
            var limit = S.calOpen[c.iso] ? list.length : CAL_MAX_PILLS;
            html += '<div class="gh-cp-day-list">';
            for (var i = 0; i < list.length && i < limit; i++) html += pillHtml(list[i]);
            html += '</div>';
            if (list.length > CAL_MAX_PILLS) {
                html += '<button type="button" class="gh-cp-more" data-cal-more="' + esc(c.iso) + '">' +
                    (S.calOpen[c.iso] ? 'свернуть' : 'ещё ' + (list.length - CAL_MAX_PILLS)) + '</button>';
            }
        }
        if (canAdd) {
            html += '<button type="button" class="gh-cp-day-add" data-add-day="' + esc(c.iso) + '"' +
                ' aria-label="Новый материал на ' + esc(GH.fmtDate(c.iso)) + '">' + PLUS_SVG + 'материал</button>';
        }
        return html + '</div>';
    }

    function calbarHtml() {
        var note = '';
        if (S.reviewsOn && S.reviewsErr) note = '<span class="gh-cp-rvnote">отзывы недоступны</span>';
        else if (S.reviewsOn && !S.reviewsDays) note = '<span class="gh-cp-rvnote">загружаю отзывы…</span>';
        return '<div class="gh-cp-calbar">' +
            '<label class="gh-check"' + tip('Показать в днях число отзывов и среднюю оценку ' +
                '(страница «Отзывы», фильтр бара общий).') + '><input type="checkbox" data-cal="reviews"' +
                (S.reviewsOn ? ' checked' : '') + '><span>Отзывы</span></label>' + note +
            '<span class="gh-grow"></span>' + legendHtml() +
            '</div>';
    }

    function renderCalendar() {
        var items = calendarItems();
        var first = S.month + '-01';
        var lead = GH.weekday(first);
        var total = GH.daysInMonth(S.month);
        var cells = [];
        var i;
        for (i = lead; i > 0; i--) cells.push({ iso: GH.addDays(first, -i), out: true });
        for (i = 1; i <= total; i++) cells.push({ iso: S.month + '-' + pad2(i) });
        var last = S.month + '-' + pad2(total);
        var k = 1;
        while (cells.length % 7) cells.push({ iso: GH.addDays(last, k++), out: true });

        var head = '';
        each(GH.WEEKDAYS, function (w, idx) {
            head += '<div class="gh-cp-wd' + (idx >= 5 ? ' is-weekend' : '') + '">' + esc(w) + '</div>';
        });
        var grid = '';
        each(cells, function (c) { grid += dayCell(c, c.out ? [] : (items[c.iso] || [])); });

        // Телефон: список по дням вместо сетки (CSS прячет одно из двух).
        var agenda = '';
        var today = S.data.today;
        var days = [];
        for (var d in items) if (Object.prototype.hasOwnProperty.call(items, d)) days.push(d);
        if (today.slice(0, 7) === S.month && days.indexOf(today) < 0) days.push(today);
        days.sort();
        each(days, function (day) {
            var list = items[day] || [];
            var canAdd = day >= today;
            var st = dayStats(list);
            agenda += '<section class="gh-cp-ag-day' + (day === today ? ' is-today' : '') +
                (day < today ? ' is-past' : '') + '">' +
                '<div class="gh-cp-ag-h"><span class="gh-cp-ag-d">' + esc(GH.fmtDateShort(day)) + '</span>' +
                (day === today ? '<span class="gh-badge gh-tone-accent">сегодня</span>' : '') +
                reviewsHtml(day) + dayMarks(st, st.materials >= CAL_DENSE_MIN) + '<span class="gh-grow"></span>' +
                (canAdd ? '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-add-day="' +
                    esc(day) + '">' + PLUS_SVG + 'материал</button>' : '') + '</div>' +
                '<div class="gh-cp-ag-list">';
            if (!list.length) agenda += '<span class="gh-cp-none">публикаций нет</span>';
            each(list, function (x) { agenda += pillHtml(x); });
            agenda += '</div></section>';
        });
        if (!days.length) {
            agenda = '<div class="gh-empty"><div class="gh-empty-t">В этом месяце нет публикаций с датой</div>' +
                '<div class="gh-empty-s">' + (filtersActive() ? 'Попробуйте снять фильтры.' :
                    'Добавьте материал и его размещения.') + '</div></div>';
        }

        el.cal.innerHTML = calbarHtml() +
            '<div class="gh-cp-cal"><div class="gh-cp-cal-head">' + head + '</div>' +
            '<div class="gh-cp-grid">' + grid + '</div></div>' +
            '<div class="gh-cp-agenda">' + agenda + '</div>';
    }

    function loadReviews() {
        var key = S.month + '|' + S.bar;
        if (S.reviewsKey === key && (S.reviewsDays || S.reviewsErr)) return;
        S.reviewsKey = key;
        S.reviewsDays = null;
        S.reviewsErr = false;
        GH.api('GET', '/api/reviews/daily?month=' + enc(S.month) + '&bar=' + enc(S.bar)).then(function (res) {
            if (S.reviewsKey !== key) return;
            S.reviewsDays = (res && res.days) || {};
            if (S.view === 'calendar' && S.data) renderView();
        }, function () {
            // Слой отзывов необязателен: бэкенда отзывов может не быть.
            if (S.reviewsKey !== key) return;
            S.reviewsDays = {};
            S.reviewsErr = true;
            if (S.view === 'calendar' && S.data) renderView();
        });
    }

    // ==================== выбор строк и массовые действия ====================

    function selectedIds() {
        var out = [];
        for (var id in S.selected) if (Object.prototype.hasOwnProperty.call(S.selected, id) && S.selected[id]) out.push(id);
        return out;
    }
    function pruneSelection() {
        var keep = {};
        each(materials(), function (m) { if (inTable(m) && S.selected[m.id]) keep[m.id] = true; });
        S.selected = keep;
    }
    function renderBulk() {
        var ids = selectedIds();
        el.bulk.hidden = !ids.length || S.view !== 'table';
        el.bulkN.textContent = 'Выбрано: ' + nText(ids.length, 'материал', 'материала', 'материалов');
    }

    function parseDays(value) {
        var text = String(value === null || value === undefined ? '' : value).replace(/−/g, '-').trim();
        if (!/^[-+]?\d+$/.test(text)) return null;
        var n = parseInt(text, 10);
        if (!n || Math.abs(n) > SHIFT_MAX) return null;
        return n;
    }

    function runBulk(action, ids, days) {
        var body = { material_ids: ids, action: action };
        if (action === 'shift') body.days = days;
        GH.api('POST', withMonth(API + '/bulk'), body).then(function (res) {
            var failed = (res && res.failed) || [];
            var done = (res && res.done) || 0;
            var failedIds = {};
            each(failed, function (f) { failedIds[f.id] = true; });
            S.selected = failedIds;
            if (done) GH.toast('Готово: ' + nText(done, 'материал', 'материала', 'материалов'), 'success');
            if (failed.length) {
                var m = findMaterial(failed[0].id);
                GH.toast('Не выполнено для ' + nText(failed.length, 'материала', 'материалов', 'материалов') +
                    ': ' + (m ? '«' + m.title + '» — ' : '') + failed[0].error, 'danger');
            }
            reload();
        }, reportError);
    }

    function bulkAction(kind) {
        var ids = selectedIds();
        if (kind === 'clear') { S.selected = {}; renderView(); renderBulk(); return; }
        if (!ids.length) return;
        var what = nText(ids.length, 'материал', 'материала', 'материалов');
        if (kind === 'shift') {
            GH.prompt({
                title: 'Сдвинуть выбранные: ' + what,
                text: 'Сдвигаются дата темы и даты всех невышедших и неотменённых размещений. От −' +
                    SHIFT_MAX + ' до ' + SHIFT_MAX + ' дней, минус — раньше. Материал, у которого ' +
                    'утверждённая публикация окажется в прошлом, не сдвинется.',
                label: 'На сколько дней', value: '7', ok: 'Сдвинуть'
            }).then(function (value) {
                if (value === null) return;
                var days = parseDays(value);
                if (days === null) {
                    GH.toast('Сдвиг: целое число дней от −' + SHIFT_MAX + ' до ' + SHIFT_MAX + ', кроме 0', 'warning');
                    return;
                }
                runBulk('shift', ids, days);
            });
        } else if (kind === 'cancel') {
            GH.confirm({
                title: 'Отменить размещения: ' + what + '?',
                text: 'Все невышедшие размещения выбранных материалов станут отменёнными. Они останутся ' +
                    'в плане для истории, их можно вернуть по одному в карточке.',
                ok: 'Отменить размещения', cancel: 'Не отменять', danger: true
            }).then(function (ok) { if (ok) runBulk('cancel', ids); });
        } else if (kind === 'delete') {
            GH.confirm({
                title: 'Удалить ' + what + '?',
                text: 'Материалы и их размещения удаляются без возможности вернуть. Материалы с вышедшими ' +
                    'размещениями не удалятся: они остаются для истории.',
                ok: 'Удалить', danger: true
            }).then(function (ok) { if (ok) runBulk('delete', ids); });
        }
    }

    // ==================== новый материал ====================

    function addMaterial(day) {
        GH.prompt({
            title: day ? 'Новый материал на ' + GH.fmtDate(day) : 'Новый материал',
            text: day ? '' : 'Материал появится в плане «' + GH.monthLabel(S.month) + '». Дату, текст и ' +
                'размещения можно задать в карточке.',
            label: 'Название', placeholder: 'Например: Таплист пятницы', ok: 'Создать'
        }).then(function (title) {
            if (title === null) return;
            title = title.replace(/\s+/g, ' ').trim();
            if (!title) { GH.toast('Название обязательно', 'warning'); return; }
            var body = { month: S.month, title: title.slice(0, TITLE_MAX) };
            if (day) body.planned_date = day;
            GH.api('POST', withMonth(API + '/materials'), body).then(function (res) {
                var id = res && res.material && res.material.id;
                if (!id) return;
                S.knownMonth[id] = res.material.month;
                reload({ material: res.material }).then(function () { openMaterial(id); });
            }, reportError);
        });
    }

    // ==================== автосохранение ====================

    function dirtyOr(key, value) {
        return Object.prototype.hasOwnProperty.call(S.dirty, key) ? S.dirty[key] : value;
    }

    // Ключ поля: 'm:<id материала>:title|base_text|note' или 'p:<id размещения>:text'.
    function saveRequest(key, value) {
        var parts = key.split(':');
        var body = {};
        body[parts[2]] = value;
        if (parts[0] === 'm') return { url: API + '/materials/' + enc(parts[1]), body: body };
        return { url: API + '/placements/' + enc(parts[1]), body: body };
    }

    function saveKey(key) {
        if (!Object.prototype.hasOwnProperty.call(S.dirty, key)) return Promise.resolve(null);
        var value = S.dirty[key];
        if (/:title$/.test(key) && !String(value).trim()) {
            setSave('error', 'название не может быть пустым');
            return Promise.resolve(null);
        }
        var req = saveRequest(key, value);
        S.saving++;
        setSave('saving');
        return GH.api('PATCH', withMonth(req.url), req.body, apiOpts()).then(function (res) {
            S.saving--;
            if (S.dirty[key] === value) {
                // Поле всё ещё в фокусе — в нём остаётся то, что человек набрал,
                // а не значение сервера: сервер нормализует название (пробелы по
                // краям срезаются), и перерисовка съела бы только что набранный
                // пробел между словами. Локальное значение уходит при уходе из
                // поля (onDrawerFocusOut).
                if (fieldFocused(key)) S.savedVal[key] = value;
                else delete S.dirty[key];
            }
            setSave(S.saving || anyPending() ? 'saving' : 'saved');
            noteUnapproved(res);
            return reload({ material: res && res.material });
        }, function (err) {
            S.saving--;
            setSave('error', err.message);
            reportError(err);
            if (err.status === 404) { delete S.dirty[key]; load(); }
            return null;
        });
    }

    function fieldFocused(key) {
        var a = document.activeElement;
        return !!(a && a.getAttribute && el.drawer.contains(a) && a.getAttribute('data-save-key') === key);
    }
    // Название так, как его сохранит сервер: пробелы подряд — один, по краям —
    // нет (core/content_plan.py). Применяется к полю только при уходе из него.
    function normTitle(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    function saver(key) {
        if (!savers[key]) savers[key] = GH.debounce(function () { return saveKey(key); }, AUTOSAVE_MS);
        return savers[key];
    }
    function anyPending() {
        for (var k in savers) if (Object.prototype.hasOwnProperty.call(savers, k) && savers[k].pending()) return true;
        return false;
    }
    // Сохранить всё несохранённое сразу: тексты (отложенное автосохранение) и
    // набранную с клавиатуры дату/время (если значение целое). Вызывается при
    // закрытии карточки, смене месяца, открытии диалогов и уходе со страницы.
    function flushAll() {
        dtFlushAll();
        return flushSavers();
    }
    // Только отложенные тексты: карточки материала и брифа для агента.
    function flushSavers() {
        var out = [];
        for (var k in savers) {
            if (Object.prototype.hasOwnProperty.call(savers, k) && savers[k].pending()) out.push(savers[k].flush());
        }
        out.push(flushBrief());
        return Promise.all(out);
    }

    function saveText() {
        if (S.saveState === 'saving' || S.saveState === 'dirty') return 'Сохраняется…';
        if (S.saveState === 'saved') return 'Сохранено';
        if (S.saveState === 'error') return 'Не сохранено: ' + (S.saveError || 'ошибка');
        return '';
    }
    function setSave(stateName, message) {
        S.saveState = stateName;
        S.saveError = message || '';
        updateSaveIndicator();
    }
    function updateSaveIndicator() {
        var nodes = el.drawer.querySelectorAll('[data-save]');
        var text = saveText();
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].textContent = text;
            nodes[i].className = 'gh-save' + (S.saveState === 'saving' || S.saveState === 'dirty' ? ' is-saving' :
                S.saveState === 'saved' ? ' is-saved' : S.saveState === 'error' ? ' is-error' : '');
        }
    }

    // ==================== дата и время ====================
    // Поля даты и времени (data-dt="date"|"time") сохраняются только целым
    // значением и не во время набора. Браузер шлёт change на каждый сегмент
    // (день, месяц, год): «2» в дне уже даёт целую, но не ту дату, а стёртый
    // сегмент — пустое значение. Раньше каждое такое значение уходило на
    // сервер, а перерисовка после ответа сбрасывала позицию ввода — так
    // утверждённая публикация уезжала на чужой день. Правила:
    //   - change без нажатия клавиши в этом поле за последние DT_TYPING_MS —
    //     выбор в календаре или часах браузера: значение целое, сохраняется сразу;
    //   - иначе значение ждёт Enter или ухода из поля (focusout);
    //   - неполное значение (validity.badInput) или дата вне YEAR_MIN..YEAR_MAX
    //     не отправляется: поле возвращается к сохранённому, тост объясняет;
    //   - поле стёрто целиком (пусто без badInput) — отправляется null (у
    //     утверждённого сервер откажет, и поле вернётся — см. mutate);
    //   - то же значение, что сохранено, не отправляется;
    //   - пока в поле идёт набор, карточка не перерисовывается (dtBusy):
    //     перерисовку откладываем до ухода из поля.

    function isDT(node) { return !!(node && node.getAttribute && node.getAttribute('data-dt')); }

    // Поле -> {stored, send(value)}: сохранённое значение и как отправить новое.
    // Форма «Добавить размещение» хранит значение у себя (S.addForm), запроса нет.
    function dtTarget(node) {
        var m = current();
        if (!m) return null;
        var add = node.getAttribute('data-add');
        if (add === 'date' || add === 'time') {
            var f = addFormState(m);
            return { stored: f[add] || '', send: function (v) { f[add] = v || ''; } };
        }
        if (node.getAttribute('data-mf') === 'planned_date') {
            return { stored: m.planned_date || '', send: function (v) { patchMaterial(m.id, { planned_date: v }); } };
        }
        var pf = node.getAttribute('data-pf');
        var p = findPlacement(m, node.getAttribute('data-pid'));
        if (!p || (pf !== 'date' && pf !== 'time')) return null;
        return {
            stored: (pf === 'date' ? p.date : p.time) || '',
            send: function (v) {
                var body = {};
                body[pf] = v;
                patchPlacement(p.id, body);
            }
        };
    }

    // Значение поля -> {ok: true, value} ('' — поле стёрто) | {ok: false, why}.
    function dtValue(node) {
        var isDate = node.getAttribute('data-dt') === 'date';
        var value = String(node.value || '');
        if (node.validity && node.validity.badInput) {
            return { ok: false, why: isDate ? 'Дата введена не полностью' : 'Время введено не полностью' };
        }
        if (!value) return { ok: true, value: '' };
        if (isDate) {
            if (!DATE_RE.test(value)) return { ok: false, why: 'Дата: нужен формат ДД.ММ.ГГГГ' };
            if (value < DATE_MIN || value > DATE_MAX) {
                return { ok: false, why: 'Дата: год от ' + YEAR_MIN + ' до ' + YEAR_MAX };
            }
            return { ok: true, value: value };
        }
        // 'ЧЧ:ММ:СС' (если браузер показывает секунды) -> 'ЧЧ:ММ', как на сервере.
        value = value.slice(0, 5);
        if (!TIME_RE.test(value)) return { ok: false, why: 'Время: нужен формат ЧЧ:ММ' };
        return { ok: true, value: value };
    }

    // Сохранить значение поля, если оно целое и новое (правила — выше).
    function dtCommit(node) {
        var fk = node.getAttribute('data-fk');
        delete S.dtPending[fk];
        delete S.dtKeyAt[fk];
        var target = dtTarget(node);
        if (!target) return;
        var v = dtValue(node);
        if (!v.ok) {
            node.value = target.stored;
            GH.toast(v.why + ' — оставлено прежнее значение', 'warning');
        } else if (v.value !== target.stored) {
            target.send(v.value || null);
            // Запрос перечитает план и перерисует карточку сам.
            if (!node.getAttribute('data-add')) return;
        }
        if (S.drawerStale) renderDrawerSoon();
    }

    function dtChange(node) {
        var fk = node.getAttribute('data-fk');
        var typing = Date.now() - (S.dtKeyAt[fk] || 0) < DT_TYPING_MS;
        if (!typing && !(node.validity && node.validity.badInput)) { dtCommit(node); return; }
        S.dtPending[fk] = true;
    }

    // Набранное с клавиатуры, но не сохранённое — сохранить сейчас (если целое).
    function dtFlushAll() {
        var keys = [];
        for (var fk in S.dtPending) if (Object.prototype.hasOwnProperty.call(S.dtPending, fk)) keys.push(fk);
        each(keys, function (key) {
            var node = el.drawer.querySelector('[data-fk="' + key + '"]');
            if (node) dtCommit(node);
            else delete S.dtPending[key];
        });
    }

    // В поле даты/времени идёт набор — перерисовка карточки подождёт.
    function dtBusy() {
        var a = document.activeElement;
        if (!isDT(a) || !el.drawer.contains(a)) return false;
        var fk = a.getAttribute('data-fk');
        return !!S.dtPending[fk] || Date.now() - (S.dtKeyAt[fk] || 0) < DT_TYPING_MS;
    }
    // Отложенная перерисовка — после того, как фокус перешёл в следующее поле
    // (в самом focusout он ещё нигде), чтобы restoreFocus вернул его туда.
    function renderDrawerSoon() {
        setTimeout(function () { if (S.drawerStale && current()) renderDrawer(); }, 0);
    }

    // Фокус и выделение в поле карточки переживают перерисовку.
    function captureFocus(root) {
        var a = document.activeElement;
        if (!a || !root.contains(a)) return null;
        var key = a.getAttribute('data-fk');
        if (!key) return { key: null };
        var f = { key: key };
        try {
            if (typeof a.selectionStart === 'number') { f.s = a.selectionStart; f.e = a.selectionEnd; }
        } catch (e) { /* у date/number выделения нет */ }
        return f;
    }
    function restoreFocus(root, f) {
        if (!f) return;
        var node = f.key ? root.querySelector('[data-fk="' + f.key + '"]') : null;
        try {
            if (node) {
                node.focus({ preventScroll: true });
                if (typeof f.s === 'number' && typeof node.setSelectionRange === 'function') {
                    node.setSelectionRange(f.s, f.e);
                }
            } else {
                root.focus({ preventScroll: true });
            }
        } catch (e) { /* фокус не критичен */ }
    }

    // ==================== карточка материала ====================

    function drawerOpen() { return !el.drawer.hidden; }

    function openMaterial(id, pid) {
        var same = S.openId === id;
        if (!same) {
            S.expanded = {};
            S.previewPid = null;
            S.addForm = null;
            S.live = null;
            S.log = { id: id, entries: null, error: null, all: false };
            S.shiftDays = '';
            S.repeatDays = [];
            S.focusPid = null;
        }
        S.openId = id;
        if (pid) {
            S.expanded[pid] = true;
            S.previewPid = pid;
            S.focusPid = pid;
            S.scrollToPid = pid;
        }
        GH.setParams({ open: id });
        var m = findMaterial(id);
        if (!m) { resolveMissing(id); return; }
        S.knownMonth[id] = m.month;
        renderDrawer();
        if (!drawerOpen()) {
            GH.openDrawer(el.drawer, { onClose: onDrawerClose });
            fitTitle();
        }
        if (!same) {
            var body = el.drawer.querySelector('.gh-drawer-body');
            if (body && !S.scrollToPid) body.scrollTop = 0;
            loadLog();
        }
        if (S.scrollToPid) scrollToPlacement();
    }

    function scrollToPlacement() {
        var pid = S.scrollToPid;
        S.scrollToPid = null;
        var body = el.drawer.querySelector('.gh-drawer-body');
        var node = pid ? el.drawer.querySelector('[data-pl="' + pid + '"]') : null;
        if (!body || !node) return;
        var top = node.getBoundingClientRect().top - body.getBoundingClientRect().top;
        body.scrollTop += top - 16;
    }

    function onDrawerClose() {
        flushAll();
        S.openId = null;
        S.focusPid = null;
        GH.setParams({ open: null });
    }

    function sub(title, note) {
        return '<div class="gh-sub"><span class="gh-sub-t">' + esc(title) + '</span><span class="gh-sub-line"></span>' +
            (note ? '<span class="gh-sub-s">' + esc(note) + '</span>' : '') + '</div>';
    }
    // fk — ключ фокуса (data-fk): кнопка остаётся в фокусе после перерисовки.
    function segBtn(value, label, currentValue, fk) {
        var on = value === currentValue;
        return '<button type="button" class="gh-seg-btn' + (on ? ' is-on' : '') + '" data-value="' + esc(value) +
            '"' + (fk ? ' data-fk="' + esc(fk + value) + '"' : '') + ' aria-pressed="' + (on ? 'true' : 'false') + '">' +
            esc(label) + '</button>';
    }
    function field(cap, control, extraClass) {
        return '<div class="gh-field' + (extraClass ? ' ' + extraClass : '') + '"><span class="gh-field-cap">' +
            cap + '</span>' + control + '</div>';
    }
    // Поля даты и времени: data-dt включает правила «дата и время» (сохранение
    // целым значением). attrs — готовые атрибуты (data-fk и адрес поля).
    var DT_HELP = 'Набранные с клавиатуры дата и время сохраняются по Enter или при уходе из поля; ' +
        'выбранные в календаре — сразу.';
    function dateInput(attrs, value, label) {
        return '<input type="date" class="gh-input" data-dt="date" ' + attrs + ' min="' + DATE_MIN + '" max="' +
            DATE_MAX + '" value="' + esc(value || '') + '" aria-label="' + esc(label) + '">';
    }
    function timeInput(attrs, value, label) {
        return '<input type="time" class="gh-input" data-dt="time" ' + attrs + ' value="' + esc(value || '') +
            '" aria-label="' + esc(label) + '">';
    }

    function renderDrawer() {
        var m = current();
        if (!m) return;
        // Пересборка innerHTML заменила бы поле даты/времени, в котором человек
        // сейчас набирает значение (см. «дата и время»): откладываем до ухода
        // из поля.
        if (dtBusy()) { S.drawerStale = true; return; }
        S.drawerStale = false;
        var oldBody = el.drawer.querySelector('.gh-drawer-body');
        var scroll = oldBody ? oldBody.scrollTop : 0;
        var focus = captureFocus(el.drawer);
        el.drawer.innerHTML = drawerHead(m) +
            '<div class="gh-drawer-body">' +
                secMain(m) + secWhy(m) + secContent(m) + secShots(m) + secPlacements(m) + secPreview(m) +
                secRepeat(m) + secLog(m) +
            '</div>' + drawerFoot(m);
        var body = el.drawer.querySelector('.gh-drawer-body');
        if (body) body.scrollTop = scroll;
        restoreFocus(el.drawer, focus);
        fitTitle();
        updateSaveIndicator();
        maybeLoadPreviewLive(m);
    }

    // Название — однострочное по смыслу, но длинное должно переноситься, а не
    // обрезаться (на телефоне): поле растёт по высоте текста.
    function fitTitle() {
        var t = el.drawer.querySelector('.gh-cp-title');
        if (!t) return;
        t.style.height = 'auto';
        // Скрытая карточка (ещё не открыта) даёт scrollHeight 0 — высоту не
        // фиксируем, openMaterial подгонит её после открытия.
        if (t.scrollHeight) t.style.height = t.scrollHeight + 'px';
    }

    // Перерисовать одну секцию карточки (история, предпросмотр), не трогая поля.
    function renderSection(name) {
        var m = current();
        if (!m) return;
        var node = el.drawer.querySelector('[data-sec="' + name + '"]');
        if (!node) return;
        var html = name === 'log' ? secLog(m) : name === 'preview' ? secPreview(m) : '';
        if (!html) return;
        var focus = captureFocus(node);
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        if (!tmp.firstChild) return;
        node.parentNode.replaceChild(tmp.firstChild, node);
        if (focus) restoreFocus(el.drawer, focus);
    }

    function drawerHead(m) {
        var key = 'm:' + m.id + ':title';
        var subParts = ['План: ' + GH.monthLabel(m.month)];
        if (!m.in_month) subParts.push('в этом месяце — только размещения');
        if (m.updated_at) subParts.push('изменено ' + GH.fmtDateTime(m.updated_at) + (m.updated_by ? ', ' + m.updated_by : ''));
        // Материал агента: пометка «ИИ» и кто его создал (created_by сервера —
        // «<login> · агент»), чтобы при проверке было видно, чей это черновик.
        var ai = m.origin === ORIGIN_AGENT
            ? aiMark(m, true) + '<span class="gh-cp-ai-t">Подготовил ИИ-агент' +
                (m.created_at ? ' ' + esc(GH.fmtDateTime(m.created_at)) : '') + '</span> · '
            : '';
        return '<div class="gh-drawer-head">' +
            '<div class="gh-drawer-h">' +
                '<textarea class="gh-cp-title" rows="1" data-fk="title" data-save-key="' + esc(key) + '" maxlength="' +
                    TITLE_MAX + '" autocomplete="off" aria-label="Название материала" ' +
                    'placeholder="Название материала">' + esc(dirtyOr(key, m.title)) + '</textarea>' +
                '<div class="gh-drawer-s">' + ai + esc(subParts.join(' · ')) + '</div>' +
            '</div>' +
            '<button type="button" class="gh-x" data-gh-close aria-label="Закрыть карточку">' + X_SVG + '</button>' +
        '</div>';
    }

    function secMain(m) {
        var kind = m.kind === 'live' ? 'live' : 'fixed';
        var s = m.summary || {};
        var dateNote = m.date
            ? 'В плане: ' + GH.fmtDateShort(m.date)
            : 'В плане без даты';
        return '<section class="gh-cp-sec gh-cp-main" data-sec="main">' +
            '<div class="gh-cp-kind">' +
                '<div class="gh-seg gh-seg-block" data-kind-seg role="group" aria-label="Тип материала">' +
                    segBtn('fixed', 'Готовая публикация', kind, 'kind_') +
                    segBtn('live', 'С актуальными данными', kind, 'kind_') +
                '</div>' +
                '<div class="gh-cp-kind-hints">' +
                    '<p class="' + (kind === 'fixed' ? 'is-on' : '') + '"><b>Готовая публикация</b> — ' +
                        KIND_HINTS.fixed + '</p>' +
                    '<p class="' + (kind === 'live' ? 'is-on' : '') + '"><b>С актуальными данными</b> — ' +
                        KIND_HINTS.live + '</p>' +
                '</div>' +
            '</div>' +
            '<div class="gh-cp-main-row">' +
                field('Дата темы ' + help('Дата темы — ориентир для плана, если размещений ещё нет. ' +
                    'Дата материала в таблице — самая ранняя дата его неотменённых размещений, иначе дата ' +
                    'темы. Дата темы задаёт месяц плана.\n' + DT_HELP),
                    dateInput('data-mf="planned_date" data-fk="planned_date"', m.planned_date, 'Дата темы'), 'gh-cp-pdate') +
                field('Готовность ' + help(summaryRulesTip()),
                    '<span class="gh-cp-state"><span class="gh-badge gh-cp-ready ' + GH.toneClass(s.tone) + '"' +
                        tip(readyTip(m)) + '>' + esc(s.label || '') + '</span>' +
                    '<span class="gh-cp-datenote">' + esc(dateNote) + '</span></span>') +
            '</div>' +
        '</section>';
    }

    // Самый строгий лимит длины среди размещений, которые берут общий текст
    // (свою версию текста и вышедшие/отменённые не учитываем). Лимиты — из
    // ответа сервера (channels): у Telegram и бота с медиа — подпись.
    function commonLimit(m) {
        var best = null;
        each(m.placements, function (p) {
            if (p.text !== null && p.text !== undefined) return;
            if (p.status === 'cancelled' || p.status === 'published') return;
            var ch = channelInfo(p.channel);
            var hasMedia = (p.effective_media || []).length > 0;
            var lim = hasMedia ? ch.caption_limit : ch.text_limit;
            if (!lim) return;
            if (!best || lim < best.limit) {
                best = { limit: lim, why: ch.name + (hasMedia && ch.caption_limit !== ch.text_limit ? ', с фото' : '') };
            }
        });
        return best;
    }
    function limitsTip() {
        var parts = [];
        each((S.data && S.data.channels) || [], function (ch) {
            parts.push(ch.name + ': ' + (ch.caption_limit !== ch.text_limit
                ? ch.text_limit + ' без фото, ' + ch.caption_limit + ' с фото (подпись)'
                : ch.text_limit));
        });
        return 'Лимиты площадок, знаков: ' + parts.join('; ') + '. Длина считается в символах. ' +
            'Текст длиннее лимита не даст утвердить размещение.';
    }
    function counterHtml(key, text, limit, why) {
        var n = charLen(text);
        if (!limit) {
            return '<span class="gh-counter" data-counter="' + esc(key) + '"' + tip(limitsTip()) + '>' +
                nText(n, 'знак', 'знака', 'знаков') + '</span>';
        }
        return '<span class="gh-counter' + (n > limit ? ' is-over' : '') + '" data-counter="' + esc(key) +
            '" data-limit="' + limit + '"' + tip('Лимит ' + limit + ' — ' + why + '. ' + limitsTip()) + '>' +
            n + ' / ' + limit + '</span>';
    }
    function updateCounter(input) {
        var key = input.getAttribute('data-save-key');
        var node = key ? el.drawer.querySelector('[data-counter="' + key + '"]') : null;
        if (!node) return;
        var n = charLen(input.value);
        var limit = Number(node.getAttribute('data-limit')) || 0;
        node.textContent = limit ? n + ' / ' + limit : nText(n, 'знак', 'знака', 'знаков');
        node.classList.toggle('is-over', !!limit && n > limit);
    }

    function secContent(m) {
        var live = m.kind === 'live';
        var key = 'm:' + m.id + ':base_text';
        var text = dirtyOr(key, m.base_text || '');
        var html = sub('Содержание', live ? 'шаблон с подстановками' : 'общий текст всех размещений');
        if (live) html += liveSourceHtml(m);
        var lim = live ? null : commonLimit(m);
        var counter = live
            ? '<span class="gh-counter" data-counter="' + esc(key) + '"' + tip('Длина шаблона. Итоговая длина ' +
                'с подставленным таплистом видна в проверке на текущих данных (предел без площадки — 4096 ' +
                'знаков, сообщение Telegram) и в предпросмотре каждого размещения — там предел своей ' +
                'площадки. ' + limitsTip()) + '>' + nText(charLen(text), 'знак', 'знака', 'знаков') + ' в шаблоне</span>'
            : counterHtml(key, text, lim && lim.limit, lim && lim.why);
        html += field(live ? 'Шаблон' : 'Общий текст',
            '<textarea class="gh-textarea gh-cp-text" rows="8" data-fk="base_text" data-save-key="' + esc(key) + '" ' +
                'aria-label="' + (live ? 'Шаблон' : 'Общий текст') + '" placeholder="' +
                (live ? 'Например: Сегодня на кранах {бар}:\n{таплист}' : 'Текст публикации') + '">' +
                esc(text) + '</textarea>' +
            '<div class="gh-cp-textfoot"><span class="gh-save" data-save></span>' + counter + '</div>');
        var locked = 0;
        each(m.placements, function (p) {
            if (locksOnContent(p) && (p.text === null || p.text === undefined)) locked++;
        });
        if (locked) {
            html += '<div class="gh-cp-warn">Правка ' + (live ? 'шаблона' : 'общего текста') + ' снимет утверждение ' +
                'с размещений, которые его используют: ' + locked + '.</div>';
        }
        if (live) html += liveCheckHtml(m);
        html += mediaHtml(m);
        var noteKey = 'm:' + m.id + ':note';
        html += field('Заметка для команды',
            '<textarea class="gh-textarea gh-cp-notearea" rows="2" data-fk="note" data-save-key="' + esc(noteKey) + '" ' +
                'aria-label="Заметка для команды" placeholder="Видна только в плане, в публикацию не уходит">' +
                esc(dirtyOr(noteKey, m.note || '')) + '</textarea>', 'gh-cp-note');
        return '<section class="gh-cp-sec" data-sec="content">' + html + '</section>';
    }

    // «Почему этот пост» (agent_rationale) и «Что снять» (shot_list): строки до
    // AGENT_TEXT_MAX, автосохранение как у текста (ключ 'm:<id>:<поле>' ->
    // PATCH материала). В публикацию не уходят и утверждение не снимают.
    function agentFieldHtml(m, field, label, placeholder, cls) {
        var key = 'm:' + m.id + ':' + field;
        var text = dirtyOr(key, m[field] || '');
        var n = charLen(text);
        return '<textarea class="gh-textarea ' + cls + '" rows="3" data-fk="' + field + '" data-save-key="' +
                esc(key) + '" aria-label="' + esc(label) + '" placeholder="' + esc(placeholder) + '">' + esc(text) +
            '</textarea>' +
            '<div class="gh-cp-textfoot"><span class="gh-save" data-save></span>' +
                '<span class="gh-counter' + (n > AGENT_TEXT_MAX ? ' is-over' : '') + '" data-counter="' + esc(key) +
                    '" data-limit="' + AGENT_TEXT_MAX + '"' + tip(AGENT_FIELD_TIP) + '>' + n + ' / ' + AGENT_TEXT_MAX +
                '</span></div>';
    }
    // Сразу под основными полями: при проверке черновика агента владелец
    // сначала читает, зачем пост, и только потом — сам текст.
    function secWhy(m) {
        var agent = m.origin === ORIGIN_AGENT;
        return '<section class="gh-cp-sec" data-sec="why">' +
            sub('Почему этот пост', agent ? 'пояснение агента' : 'по желанию') +
            agentFieldHtml(m, 'agent_rationale', 'Почему этот пост', WHY_PLACEHOLDER, 'gh-cp-agentarea') +
            '</section>';
    }
    // После «Содержания» (там фото и видео): что нужно снять для этого поста.
    function secShots(m) {
        var agent = m.origin === ORIGIN_AGENT;
        return '<section class="gh-cp-sec" data-sec="shots">' +
            sub('Что снять', agent ? 'список кадров от агента' : 'список кадров') +
            agentFieldHtml(m, 'shot_list', 'Что снять', SHOTS_PLACEHOLDER, 'gh-cp-agentarea') +
            '</section>';
    }

    function liveSourceHtml(m) {
        var opts = '<option value="">Не выбран</option>';
        each(liveSources(), function (s) {
            opts += '<option value="' + esc(s.key) + '"' + (s.key === m.live_source ? ' selected' : '') + '>' +
                esc(s.name) + '</option>';
        });
        var src = findIn(liveSources(), m.live_source);
        var chips = '';
        if (src) {
            each(src.placeholders, function (ph) {
                chips += '<button type="button" class="gh-chip gh-cp-token" data-act="token" data-token="' +
                    esc(ph.token) + '"' + tip(ph.token + ' — ' + ph.hint) + '>' + esc(ph.token) + '</button>';
            });
        }
        return '<div class="gh-cp-live">' +
            field('Источник данных', '<select class="gh-select" data-mf="live_source" data-fk="live_source" ' +
                'aria-label="Источник данных">' + opts + '</select>', 'gh-cp-src') +
            (chips ? field('Подстановки — нажмите, чтобы вставить в шаблон ' + help('Любая другая подстановка ' +
                'в фигурных скобках — ошибка: размещение не пройдёт проверку готовности.'),
                '<div class="gh-chips">' + chips + '</div>') : '') +
            '</div>';
    }

    function liveDefaultBar(m) {
        if (S.liveBar) return S.liveBar;
        var found = '';
        each(m.placements, function (p) { if (!found && GH.isBar(p.bar)) found = p.bar; });
        return found || GH.getBar() || GH.BARS[0].key;
    }

    function liveCheckHtml(m) {
        var barKey = liveDefaultBar(m);
        var opts = '';
        each(GH.BARS, function (b) {
            opts += '<option value="' + esc(b.key) + '"' + (b.key === barKey ? ' selected' : '') + '>' +
                esc(b.name) + '</option>';
        });
        var r = S.live && S.live.mid === m.id ? S.live : null;
        var html = '<div class="gh-cp-livebox">' +
            '<p class="gh-cp-explain">' + esc(LIVE_EXPLAIN) + '</p>' +
            '<div class="gh-cp-livebar">' +
                field('Бар', '<select class="gh-select" data-live="bar" data-fk="live_bar" aria-label="Бар для проверки">' +
                    opts + '</select>') +
                '<button type="button" class="gh-btn" data-act="live-check"' + (r && r.loading ? ' disabled' : '') + '>' +
                    (r && r.loading ? '<span class="gh-spin"></span>' : '') + 'Проверить на текущих данных</button>' +
            '</div>';
        if (r && r.error) html += '<div class="gh-field-err">' + esc(r.error) + '</div>';
        if (r && r.result) html += liveResultHtml(r.result, r.bar);
        return html + '</div>';
    }

    function liveResultHtml(res, barKey) {
        var problems = res.problems || [];
        var html = '<div class="gh-cp-liveres">' +
            '<div class="gh-cp-liveres-h"><span>' + esc(GH.barName(barKey)) + ' · данные на ' +
                esc(GH.fmtDateTime(res.data_at)) + '</span>' +
                '<span class="gh-counter' + (res.length > res.limit ? ' is-over' : '') + '"' +
                    tip('Длина итогового текста с подставленными данными / предел. ' + (res.limit_note ||
                        'Площадка не выбрана: предел сообщения Telegram') + '. Предел конкретной площадки — в ' +
                        'предпросмотре размещения. ' + limitsTip()) + '>' +
                    esc(res.length) + ' / ' + esc(res.limit) + '</span></div>';
        if (problems.length) {
            var texts = [];
            each(problems, function (p) { texts.push(p.text); });
            html += '<div class="gh-cp-stop"><b>Публикация будет остановлена:</b> ' + esc(texts.join('; ')) + '</div>';
        } else {
            html += '<div class="gh-cp-go">Сейчас проверка пройдена. В момент выхода данные подставятся заново.</div>';
        }
        html += '<div class="gh-cp-rendered">' + (res.text ? multiline(res.text) :
            '<span class="gh-muted">Текст пуст</span>') + '</div>';
        return html + '</div>';
    }

    function mediaHtml(m) {
        var list = m.media || [];
        var items = '';
        each(list, function (f) {
            var name = f.original_name || f.name;
            var thumb = f.kind === 'video'
                ? '<video src="' + esc(f.url) + '" muted preload="metadata"></video><span class="gh-cp-media-kind">видео</span>'
                : '<img src="' + esc(f.url) + '" alt="' + esc(name) + '" loading="lazy">';
            items += '<figure class="gh-cp-media-i">' +
                '<div class="gh-cp-media-th">' + thumb + '</div>' +
                '<figcaption class="gh-cp-media-cap"><span class="gh-cp-media-nm">' + esc(name) + '</span>' +
                    '<span class="gh-cp-media-sz">' + esc(fileSize(f.size)) + '</span></figcaption>' +
                '<button type="button" class="gh-cp-media-x" data-act="media-del" data-name="' + esc(f.name) + '" ' +
                    'aria-label="Удалить файл ' + esc(name) + '">' + X_SVG + '</button>' +
            '</figure>';
        });
        var lim = (S.data && S.data.media_limits) || {};
        var up = S.uploading && S.uploading.mid === m.id ? S.uploading : null;
        var drop = '<div class="gh-cp-drop' + (up ? ' is-busy' : '') + '" data-drop>';
        if (up) {
            drop += '<span class="gh-spin"></span><span class="gh-cp-drop-t">Загрузка: ' +
                Math.min(up.done + 1, up.total) + ' из ' + up.total + '…</span>';
        } else {
            // Само поле выбора файлов (#cpFile) живёт вне карточки: карточка
            // перерисовывается целиком (автосохранение, ответы сервера), и поле
            // внутри неё отрывалось бы от страницы, пока открыт системный диалог
            // выбора, — выбранный файл молча терялся.
            drop += '<span class="gh-cp-drop-t">Перетащите фото или видео сюда</span>' +
                '<button type="button" class="gh-btn gh-btn-sm gh-cp-upload" data-act="pick-files">' +
                    'Выбрать файлы</button>';
        }
        drop += '<span class="gh-cp-drop-s">JPEG, PNG, WEBP до ' + esc(mbText(lim.image_bytes)) + ', MP4 до ' +
            esc(mbText(lim.video_bytes)) + '; у материала до ' + esc(lim.per_material || '—') + ' файлов</span></div>';
        // Новый файл входит во все размещения с набором «все файлы» (media ==
        // null) — у утверждённых из них это смена содержания, утверждение
        // снимется (core/content_plan.py, add_media). Предупреждаем заранее.
        var inherit = 0;
        each(m.placements, function (p) {
            if (locksOnContent(p) && (p.media === null || p.media === undefined)) inherit++;
        });
        if (inherit) {
            drop += '<div class="gh-cp-warn">Новый файл попадёт во все размещения с набором «все файлы» и снимет ' +
                'утверждение с ' + nText(inherit, 'размещения', 'размещений', 'размещений') +
                '. У размещений со своей подборкой файлов утверждение сохранится.</div>';
        }
        var req = '<div class="gh-cp-req"><label class="gh-cb"><input type="checkbox" data-mf="media_required" ' +
            'data-fk="media_required"' + (m.media_required ? ' checked' : '') + '><span>Нужно фото</span></label>' +
            help('Отметьте, если публикация без фото не имеет смысла: размещения без фото будут в состоянии ' +
                '«Не хватает: нет фото». Для Instagram фото обязательно всегда.') + '</div>';
        return sub('Фото и видео', list.length ? nText(list.length, 'файл', 'файла', 'файлов') : 'нет файлов') +
            (items ? '<div class="gh-cp-media">' + items + '</div>' : '') + drop + req;
    }

    // ----- размещения -----

    function stateTip(p) {
        var text = p.display_label + '\n' + (STATE_TIPS[p.display_state] || '');
        return text;
    }

    function barOptions(p, channel, selected) {
        var html = '';
        var allowAll = channel !== 'telegram';
        if (allowAll || selected === 'all') {
            html += '<option value="all"' + (selected === 'all' ? ' selected' : '') + '>' +
                (allowAll ? 'Вся сеть' : 'Вся сеть — выберите бар') + '</option>';
        }
        each(GH.BARS, function (b) {
            html += '<option value="' + esc(b.key) + '"' + (b.key === selected ? ' selected' : '') + '>' +
                esc(b.name) + '</option>';
        });
        return html;
    }

    function audienceOptions(selected, placeholder) {
        var html = '<option value="">' + esc(placeholder) + '</option>';
        each(audiences(), function (a) {
            html += '<option value="' + esc(a.key) + '"' + (a.key === selected ? ' selected' : '') + '>' +
                esc(a.name) + '</option>';
        });
        return html;
    }
    function audienceNote(key) {
        var a = findIn(audiences(), key);
        var note = a && a.size_note ? a.size_note : 'Бот не подключён: размер аудитории появится после интеграции';
        var bar = a && a.needs_bar ? ' Для этой аудитории нужен конкретный бар.' : '';
        return '<div class="gh-field-hint">Размер: ' + (a && a.size !== null && a.size !== undefined ?
            esc(GH.fmtNum(a.size, 0)) : 'неизвестно') + '. ' + esc(note) + '.' + esc(bar) + '</div>';
    }

    function actionButtons(m, p) {
        var list = ACTIONS_BY_STATUS[p.status] || [];
        var html = '';
        each(list, function (a) {
            var cls = 'gh-btn gh-btn-sm';
            var extra = '';
            if (a === 'approve') {
                cls += ' gh-btn-primary';
                if (!p.ready) {
                    extra = ' disabled';
                }
            } else if (a === 'delete') {
                cls += ' gh-btn-ghost gh-cp-del';
            } else if (a === 'cancel') {
                cls += ' gh-btn-ghost';
            }
            html += '<button type="button" class="' + cls + '" data-act="pl-' + a + '" data-pid="' + esc(p.id) + '"' +
                extra + '>' + esc(ACTION_LABELS[a]) + '</button>';
        });
        if (!html) return '';
        var hint = '';
        if (p.status === 'draft' && !p.ready) hint = '<span class="gh-cp-acthint">Утвердить можно, когда всё заполнено</span>';
        return '<div class="gh-cp-pl-acts">' + html + hint + '</div>';
    }

    function placementMeta(m, p) {
        var parts = [];
        if (p.channel === 'bot') {
            parts.push('Аудитория: ' + (p.audience_info ? p.audience_info.name + ' · размер: ' + SIZE_UNKNOWN : 'не выбрана'));
        }
        if (p.text !== null && p.text !== undefined) parts.push('своя версия текста');
        if (p.media !== null && p.media !== undefined) {
            parts.push('своя подборка: ' + (p.effective_media || []).length + ' из ' + (m.media || []).length + ' файлов');
        }
        if ((p.status === 'approved' || p.status === 'paused') && p.approved_at) {
            parts.push('утверждено ' + GH.fmtDateTime(p.approved_at) + (p.approved_by ? ', ' + p.approved_by : ''));
        }
        if (p.status === 'published' && p.published_at) {
            parts.push('вышло ' + GH.fmtDateTime(p.published_at) + (p.published_by ? ', отметил ' + p.published_by : ''));
        }
        if (p.status === 'failed' && p.failed_error) parts.push('ошибка: ' + p.failed_error);
        if (!parts.length) return '';
        return '<div class="gh-cp-pl-meta">' + esc(parts.join(' · ')) + '</div>';
    }

    function editorHtml(m, p) {
        var locked = p.status === 'approved' || p.status === 'paused' || p.status === 'failed';
        var html = '<div class="gh-cp-ed">';
        if (locked) {
            html += '<div class="gh-cp-warn">Изменение снимет утверждение: текст, фото, бар и аудитория — это ' +
                'содержание публикации. Перенос даты и времени утверждение сохраняет.</div>';
        }
        html += '<div class="gh-form-row">' +
            field('Бар', '<select class="gh-select" data-pf="bar" data-pid="' + esc(p.id) + '" data-fk="pb:' + esc(p.id) +
                '" aria-label="Бар">' + barOptions(p, p.channel, p.bar) + '</select>') +
            field('Дата ' + help(DT_HELP), dateInput('data-pf="date" data-pid="' + esc(p.id) + '" data-fk="pd:' +
                esc(p.id) + '"', p.date, 'Дата выхода')) +
            field('Время', timeInput('data-pf="time" data-pid="' + esc(p.id) + '" data-fk="ptm:' + esc(p.id) + '"',
                p.time, 'Время выхода')) +
            '</div>';
        if (p.channel === 'bot') {
            var seg = p.audience && p.audience.segment ? p.audience.segment : '';
            html += field('Аудитория рассылки', '<select class="gh-select" data-pf="audience" data-pid="' + esc(p.id) +
                '" data-fk="pa:' + esc(p.id) + '" aria-label="Аудитория рассылки">' +
                audienceOptions(seg, 'Выберите аудиторию') + '</select>' + audienceNote(seg));
        }
        var own = p.text !== null && p.text !== undefined;
        html += '<label class="gh-cb gh-cp-own"><input type="checkbox" data-pf="own" data-pid="' + esc(p.id) + '"' +
            ' data-fk="po:' + esc(p.id) + '"' +
            (own ? ' checked' : '') + '><span>Своя версия текста для этого размещения</span></label>';
        if (own) {
            var key = 'p:' + p.id + ':text';
            var text = dirtyOr(key, p.text);
            var ch = channelInfo(p.channel);
            var hasMedia = (p.effective_media || []).length > 0;
            var limit = m.kind === 'live' ? 0 : (hasMedia ? ch.caption_limit : ch.text_limit);
            var why = ch.name + (hasMedia && ch.caption_limit !== ch.text_limit ? ', с фото' : '');
            html += '<textarea class="gh-textarea gh-cp-owntext" rows="6" data-fk="pt:' + esc(p.id) +
                '" data-save-key="' + esc(key) + '" aria-label="Своя версия текста">' + esc(text) + '</textarea>' +
                '<div class="gh-cp-textfoot"><span class="gh-save" data-save></span>' +
                counterHtml(key, text, limit, why) + '</div>';
        } else {
            html += '<div class="gh-field-hint">Используется общий текст материала.</div>';
        }
        var media = m.media || [];
        if (media.length) {
            var all = p.media === null || p.media === undefined;
            var mh = '<label class="gh-cb"><input type="checkbox" data-pf="media-all" data-pid="' + esc(p.id) + '"' +
                ' data-fk="pma:' + esc(p.id) + '"' +
                (all ? ' checked' : '') + '><span>Все файлы материала</span></label>';
            if (!all) {
                mh += '<div class="gh-checks gh-cp-mediasel">';
                each(media, function (f) {
                    var on = (p.media || []).indexOf(f.name) >= 0;
                    mh += '<label class="gh-check"><input type="checkbox" data-pf="media-item" data-pid="' + esc(p.id) +
                        '" data-fk="pmi:' + esc(p.id) + ':' + esc(f.name) + '" value="' + esc(f.name) + '"' + (on ? ' checked' : '') + '><span>' +
                        esc(f.original_name || f.name) + '</span></label>';
                });
                mh += '</div>';
            }
            html += field('Фото и видео этого размещения', mh);
        }
        return html + '</div>';
    }

    // Вышедшее (или с ошибкой отправки) размещение: что ушло на самом деле.
    // content_source 'snapshot' — сервер отдал текст и файлы из снимка на момент
    // утверждения; у живого материала данные таплиста в снимке не хранятся.
    function sentHtml(m, p) {
        if (p.status !== 'published' && p.status !== 'failed') return '';
        var files = placementFiles(m, p);
        var note = p.content_source === 'snapshot' ? SNAPSHOT_NOTE : '';
        if (m.kind === 'live' && p.status === 'published') {
            note = (note ? note + '. ' : '') + 'Таплист в предпросмотре — ' + LIVE_NOW_NOTE;
        }
        if (!note && !files.length) return '';
        return '<div class="gh-cp-pl-sent">' + (note ? '<span class="gh-cp-sent-note">' + esc(note) + '</span>' : '') +
            thumbsHtml(files, 'gh-cp-pl-files') + '</div>';
    }

    function placementHtml(m, p) {
        var open = !!S.expanded[p.id];
        var editable = p.status !== 'published' && p.status !== 'cancelled';
        var cls = 'gh-cp-pl' + (open && editable ? ' is-open' : '') + (S.focusPid === p.id ? ' is-focus' : '') +
            (p.status === 'cancelled' ? ' is-cancel' : '');
        var html = '<div class="' + cls + '" data-pl="' + esc(p.id) + '">' +
            '<div class="gh-cp-pl-h"><div class="gh-cp-pl-info">' +
                '<span class="gh-dot ' + stateCls(p.display_state) + '"></span>' +
                '<span class="gh-cp-pl-ch">' + esc(chName(p.channel)) + '</span>' +
                '<span class="gh-cp-pl-bar">' + esc(GH.barName(p.bar)) + '</span>' +
                '<span class="gh-cp-pl-when">' + esc(whenText(p)) + '</span>' +
                '<span class="gh-badge gh-cp-stbadge ' + stateCls(p.display_state) + '"' + tip(stateTip(p)) + '>' +
                    esc(stateLabel(p)) + '</span>' +
                '</div>' +
                (editable ? '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm gh-cp-pl-tg" data-act="toggle-pl" ' +
                    'data-pid="' + esc(p.id) + '" data-fk="tg:' + esc(p.id) + '" aria-expanded="' + (open ? 'true' : 'false') + '">' +
                    (open ? 'Свернуть' : 'Изменить') + '</button>' : '') +
            '</div>';
        if (p.display_state === 'incomplete' && (p.missing || []).length) {
            var miss = [];
            each(p.missing, function (x) { miss.push(x.text); });
            html += '<div class="gh-cp-pl-miss">Не хватает: ' + esc(miss.join(', ')) + '</div>';
        }
        html += placementMeta(m, p);
        html += sentHtml(m, p);
        html += actionButtons(m, p);
        if (open && editable) html += editorHtml(m, p);
        return html + '</div>';
    }

    function addFormState(m) {
        if (!S.addForm || S.addForm.mid !== m.id) {
            S.addForm = {
                mid: m.id, channel: 'telegram', bars: [], bar: 'all', audience: '',
                date: m.planned_date || m.date || '', time: DEFAULT_TIME
            };
        }
        return S.addForm;
    }

    function addFormHtml(m) {
        var f = addFormState(m);
        var html = '<div class="gh-cp-add">' +
            '<div class="gh-cp-add-h">Добавить размещение</div>' +
            '<div class="gh-seg" data-add-seg role="group" aria-label="Площадка">';
        each(CHANNEL_KEYS, function (k) { html += segBtn(k, chName(k), f.channel, 'add_ch_'); });
        html += '</div>';
        var valid = true;
        var count = 1;
        if (f.channel === 'telegram') {
            var allOn = f.bars.length === GH.BARS.length;
            var checks = '<label class="gh-check"><input type="checkbox" data-add="allbars" data-fk="add_all"' +
                (allOn ? ' checked' : '') + '><span>Все бары</span></label>';
            each(GH.BARS, function (b) {
                checks += '<label class="gh-check"><input type="checkbox" data-add="bar" data-fk="add_bar_' + esc(b.key) +
                    '" value="' + esc(b.key) + '"' +
                    (f.bars.indexOf(b.key) >= 0 ? ' checked' : '') + '><span' + tip(b.name) + '>' + esc(b.short) +
                    '</span></label>';
            });
            html += field('Бары — у каждого бара свой канал', '<div class="gh-checks">' + checks + '</div>' +
                '<div class="gh-field-hint">По одному размещению на каждый отмеченный бар.</div>');
            valid = f.bars.length > 0;
            count = f.bars.length;
        } else {
            html += field(f.channel === 'instagram' ? 'Аккаунт' : 'Бар (охват рассылки)',
                '<select class="gh-select" data-add="barsel" data-fk="add_bar" aria-label="Бар">' +
                    barOptions(null, f.channel, f.bar) + '</select>' +
                (f.channel === 'instagram'
                    ? '<div class="gh-field-hint">Instagram — один аккаунт сети, поэтому по умолчанию «Вся сеть».</div>'
                    : ''));
        }
        if (f.channel === 'bot') {
            html += field('Аудитория рассылки', '<select class="gh-select" data-add="audience" data-fk="add_aud" ' +
                'aria-label="Аудитория рассылки">' + audienceOptions(f.audience, 'Выберите аудиторию') + '</select>' +
                audienceNote(f.audience));
            valid = !!f.audience;
        }
        html += '<div class="gh-form-row">' +
            field('Дата', dateInput('data-add="date" data-fk="add_date"', f.date, 'Дата выхода')) +
            field('Время', timeInput('data-add="time" data-fk="add_time"', f.time, 'Время выхода')) +
            '</div>';
        html += '<p class="gh-cp-botnote">' + esc(BOT_NOTE) + '</p>';
        var label = f.channel === 'telegram' && count > 1
            ? 'Добавить ' + nText(count, 'размещение', 'размещения', 'размещений')
            : 'Добавить размещение';
        html += '<button type="button" class="gh-btn gh-btn-primary gh-btn-sm" data-act="add-pl"' +
            (valid ? '' : ' disabled') + '>' + PLUS_SVG + esc(label) + '</button>';
        return html + '</div>';
    }

    function secPlacements(m) {
        var pls = m.placements || [];
        var html = sub('Размещения', pls.length ? nText(pls.length, 'размещение', 'размещения', 'размещений') : 'пока нет');
        if (!pls.length) {
            html += '<p class="gh-cp-explain">Пока это только тема. Добавьте, где и когда она выйдет: ' +
                'Telegram-канал бара, Instagram сети или рассылка бота.</p>';
        }
        each(pls, function (p) { html += placementHtml(m, p); });
        html += addFormHtml(m);
        return '<section class="gh-cp-sec" data-sec="placements">' + html + '</section>';
    }

    // ----- предпросмотр -----

    function mediaFor(m, names) {
        var out = [];
        each(names, function (n) {
            each(m.media, function (f) { if (f.name === n) out.push(f); });
        });
        return out;
    }
    // Ключ проверки живых данных: всё, от чего зависят текст и предел длины
    // (площадка и есть ли файлы — предел подписи к фото меньше).
    function previewKey(m, p) {
        return [p.id, p.bar, p.date || '', m.live_source || '', p.effective_text || '', p.channel,
                placementFiles(m, p).length ? 'media' : 'text'].join('|');
    }
    function previewTarget(m) {
        var list = [];
        each(m.placements, function (p) { if (p.status !== 'cancelled') list.push(p); });
        var cur = null;
        each(list, function (p) { if (p.id === S.previewPid) cur = p; });
        return { list: list, cur: cur || list[0] || null };
    }

    function maybeLoadPreviewLive(m) {
        if (m.kind !== 'live') return;
        var t = previewTarget(m);
        var p = t.cur;
        if (!p) return;
        var key = previewKey(m, p);
        if (S.previewLive[key]) return;
        S.previewLive[key] = { loading: true };
        // channel и has_media — предел длины этой площадки (контракт A.3):
        // Telegram и бот с файлами — подпись 1024, без файлов — 4096, Instagram
        // — 2200. Без них сервер берёт 4096.
        var body = { source: m.live_source || '', bar: p.bar, material_id: m.id, template: p.effective_text || '',
                     channel: p.channel, has_media: placementFiles(m, p).length > 0 };
        if (p.date) body.date = p.date;
        GH.api('POST', API + '/live-preview', body).then(function (res) {
            S.previewLive[key] = { result: res || {} };
            renderSection('preview');
        }, function (err) {
            S.previewLive[key] = { error: err.message };
            renderSection('preview');
        });
    }

    function thumbsHtml(files, cls) {
        if (!files.length) return '';
        var html = '<div class="gh-cp-pv-media ' + cls + '" data-n="' + Math.min(files.length, 4) + '">';
        for (var i = 0; i < files.length && i < 4; i++) {
            var f = files[i];
            html += f.kind === 'video'
                ? '<span class="gh-cp-pv-vid">видео</span>'
                : '<img src="' + esc(f.url) + '" alt="" loading="lazy">';
        }
        if (files.length > 4) html += '<span class="gh-cp-pv-more">+' + (files.length - 4) + '</span>';
        return html + '</div>';
    }

    function previewHtml(m, p) {
        var ch = channelInfo(p.channel);
        var files = placementFiles(m, p);
        var text = '';
        var length = 0;
        var limit = 0;
        var problems = [];
        var state = 'ok';
        if (m.kind === 'live') {
            var r = S.previewLive[previewKey(m, p)];
            if (!r || r.loading) {
                state = 'loading';
            } else if (r.error) {
                state = 'error';
                problems = [{ text: r.error }];
            } else {
                text = r.result.text || '';
                length = r.result.length || 0;
                limit = r.result.limit || 0;
                problems = r.result.problems || [];
            }
        } else {
            text = p.effective_text || '';
            length = charLen(text);
            limit = files.length ? ch.caption_limit : ch.text_limit;
        }
        var body;
        if (state === 'loading') {
            body = '<div class="gh-cp-loading"><span class="gh-spin"></span>Подставляю текущие данные…</div>';
        } else {
            var textHtml = text ? multiline(text) : '<span class="gh-muted">Текста пока нет</span>';
            var time = p.time || '—';
            if (p.channel === 'instagram') {
                var first = files[0];
                var media = first
                    ? (first.kind === 'video' ? '<span class="gh-cp-pv-vid">видео</span>'
                        : '<img src="' + esc(first.url) + '" alt="" loading="lazy">')
                    : '<span class="gh-cp-ig-empty">нет фото — Instagram требует хотя бы одно</span>';
                body = '<div class="gh-cp-ig">' +
                    '<div class="gh-cp-ig-head"><span class="gh-cp-av">IG</span><b>' +
                        esc(p.bar === 'all' ? 'Аккаунт сети' : 'Аккаунт · ' + GH.barName(p.bar)) + '</b></div>' +
                    '<div class="gh-cp-ig-media">' + media +
                        (files.length > 1 ? '<span class="gh-cp-ig-count">1 / ' + files.length + '</span>' : '') + '</div>' +
                    '<div class="gh-cp-ig-cap">' + textHtml + '</div>' +
                '</div>';
            } else {
                var head = p.channel === 'bot'
                    ? 'Бот · ' + (p.audience_info ? p.audience_info.name : 'аудитория не выбрана') +
                        (p.bar !== 'all' ? ' · ' + GH.barName(p.bar) : '')
                    : 'Канал бара · ' + GH.barName(p.bar);
                body = '<div class="gh-cp-tg' + (p.channel === 'bot' ? ' is-bot' : '') + '">' +
                    '<div class="gh-cp-tg-head"><span class="gh-cp-av">' + esc(chShort(p.channel)) + '</span>' +
                        '<span>' + esc(head) + '</span></div>' +
                    '<div class="gh-cp-bubble">' + thumbsHtml(files, '') +
                        '<div class="gh-cp-bubble-t">' + textHtml + '</div>' +
                        '<div class="gh-cp-bubble-time">' + esc(time) + '</div>' +
                    '</div>' +
                '</div>';
            }
        }
        var foot = '';
        var liveNote = '';
        var limitNote = '';
        if (m.kind === 'live') {
            liveNote = p.status === 'published' ? LIVE_NOW_NOTE : 'данные на сейчас';
            var lr = S.previewLive[previewKey(m, p)];
            limitNote = lr && lr.result && lr.result.limit_note ? lr.result.limit_note + '. ' : '';
        }
        if (state !== 'loading' && limit) {
            var kindText = files.length && ch.caption_limit !== ch.text_limit ? 'подпись к фото' : 'текст';
            foot = '<div class="gh-cp-pv-foot"><span class="gh-counter' + (length > limit ? ' is-over' : '') + '"' +
                tip((m.kind === 'live' ? 'Длина текста с подставленными данными' : 'Длина итогового текста') +
                    ' / лимит площадки: ' + kindText + '. ' + limitNote + limitsTip()) + '>' + length + ' / ' + limit +
                '</span>' + (liveNote ? '<span class="gh-cp-pv-note">' + esc(liveNote) + '</span>' : '') + '</div>';
        }
        if (p.content_source === 'snapshot') {
            foot += '<div class="gh-cp-sent-note"' + tip('Размещение уже ' + (p.status === 'failed'
                ? 'пытались отправить' : 'вышло') + ': показаны текст и файлы, которые были утверждены, даже ' +
                'если общий текст или файлы материала потом поменяли.') + '>' + esc(SNAPSHOT_NOTE) + '</div>';
        }
        if (problems.length) {
            var texts = [];
            each(problems, function (x) { texts.push(x.text); });
            foot += '<div class="gh-cp-stop"><b>Публикация будет остановлена:</b> ' + esc(texts.join('; ')) + '</div>';
        }
        return '<div class="gh-cp-pv">' + body + foot + '</div>';
    }

    function secPreview(m) {
        var t = previewTarget(m);
        var html = sub('Предпросмотр', 'как увидят гости');
        if (!t.cur) {
            html += '<p class="gh-cp-explain">Предпросмотр появится, когда у материала будут размещения.</p>';
        } else {
            html += '<div class="gh-cp-ptabs" role="tablist">';
            each(t.list, function (p) {
                var on = p.id === t.cur.id;
                html += '<button type="button" role="tab" class="gh-cp-ptab' + (on ? ' is-on' : '') + '" data-act="ptab" ' +
                    'data-pid="' + esc(p.id) + '" data-fk="ptab:' + esc(p.id) + '" aria-selected="' + (on ? 'true' : 'false') + '">' +
                    esc(chShort(p.channel) + ' ' + GH.barShort(p.bar) + (p.time ? ' ' + p.time : '')) + '</button>';
            });
            html += '</div>' + previewHtml(m, t.cur);
        }
        return '<section class="gh-cp-sec" data-sec="preview">' + html + '</section>';
    }

    // ----- повтор, перенос, история -----

    function secRepeat(m) {
        var html = sub('Повтор и перенос', '');
        html += '<div class="gh-cp-rep-row">' +
            field('Сдвинуть на, дней', '<input type="number" class="gh-input" min="-' + SHIFT_MAX + '" max="' + SHIFT_MAX +
                '" step="1" data-rep="days" data-fk="shift_days" value="' + esc(S.shiftDays) + '" placeholder="7" ' +
                'aria-label="Сдвиг в днях">', 'gh-cp-days') +
            '<button type="button" class="gh-btn" data-act="shift">Сдвинуть</button>' +
            '</div>' +
            '<div class="gh-field-hint">Сдвигает дату темы и даты всех невышедших и неотменённых размещений. ' +
                'От −' + SHIFT_MAX + ' до ' + SHIFT_MAX + ' дней, минус — раньше. Если утверждённая публикация ' +
                'окажется в прошлом, ничего не сдвинется.</div>';
        var checks = '';
        each(GH.WEEKDAYS, function (w, i) {
            checks += '<label class="gh-check"><input type="checkbox" data-rep="wd" value="' + i + '"' +
                (S.repeatDays.indexOf(i) >= 0 ? ' checked' : '') + '><span>' + esc(w) + '</span></label>';
        });
        html += field('Повторять в этом месяце по дням недели', '<div class="gh-checks">' + checks + '</div>', 'gh-cp-rep-days') +
            '<button type="button" class="gh-btn" data-act="repeat"' + (S.repeatDays.length ? '' : ' disabled') + '>' +
                'Создать повторы</button>' +
            '<div class="gh-field-hint">Копия материала — на каждый выбранный день недели месяца «' +
                esc(GH.monthLabel(S.month)) + '», начиная с сегодняшнего дня. Дни, уже занятые этой серией, ' +
                'пропускаются. Копии — черновики с теми же размещениями, текстом и фото; утверждение не копируется.</div>';
        if (m.series && m.series.id) {
            var n = 0;
            each(materials(), function (x) { if (x.series && x.series.id === m.series.id) n++; });
            html += '<div class="gh-cp-series"' + tip('Материалы одной серии в загруженном месяце.') + '>Серия: ' +
                esc(weekdaysText(m.series.weekdays)) + ' · в этом месяце ' +
                esc(nText(n, 'материал', 'материала', 'материалов')) + '</div>';
        }
        return '<section class="gh-cp-sec" data-sec="repeat">' + html + '</section>';
    }

    function secLog(m) {
        var lg = S.log && S.log.id === m.id ? S.log : null;
        var html = sub('История', lg && lg.entries ? nText(lg.entries.length, 'запись', 'записи', 'записей') : '');
        if (!lg || (!lg.entries && !lg.error)) {
            html += '<p class="gh-cp-explain">Загружаю историю…</p>';
        } else if (lg.error) {
            html += '<p class="gh-field-err">' + esc(lg.error) + '</p>';
        } else if (!lg.entries.length) {
            html += '<p class="gh-cp-explain">Записей пока нет.</p>';
        } else {
            var list = lg.all ? lg.entries : lg.entries.slice(0, LOG_SHOWN);
            html += '<ol class="gh-cp-log">';
            each(list, function (e) {
                html += '<li class="gh-cp-log-i"><span class="gh-cp-log-at">' + esc(GH.fmtDateTime(e.at)) + '</span>' +
                    '<span class="gh-cp-log-t">' + esc(e.text) + '</span>' +
                    '<span class="gh-cp-log-by">' + esc(e.by) + '</span></li>';
            });
            html += '</ol>';
            if (!lg.all && lg.entries.length > LOG_SHOWN) {
                html += '<button type="button" class="gh-link gh-cp-logmore" data-act="log-all">Показать все: ' +
                    lg.entries.length + '</button>';
            }
        }
        return '<section class="gh-cp-sec" data-sec="log">' + html + '</section>';
    }

    function loadLog() {
        var id = S.openId;
        if (!id) return;
        if (!S.log || S.log.id !== id) S.log = { id: id, entries: null, error: null, all: false };
        GH.api('GET', API + '/materials/' + enc(id) + '/log').then(function (res) {
            if (!S.log || S.log.id !== id) return;
            S.log.entries = (res && res.entries) || [];
            S.log.error = null;
            renderSection('log');
        }, function (err) {
            if (!S.log || S.log.id !== id) return;
            S.log.error = 'История недоступна: ' + err.message;
            renderSection('log');
        });
    }

    function drawerFoot(m) {
        return '<div class="gh-drawer-foot">' +
            '<button type="button" class="gh-btn gh-btn-danger gh-btn-outline gh-btn-sm" data-act="delete">' +
                'Удалить материал</button>' +
            '<span class="gh-grow"></span>' +
            '<span class="gh-save" data-save></span>' +
            '<button type="button" class="gh-btn gh-btn-sm" data-gh-close>Закрыть</button>' +
        '</div>';
    }

    // ----- действия карточки -----

    function patchMaterial(id, fields) {
        return mutate('PATCH', API + '/materials/' + enc(id), fields);
    }
    function patchPlacement(pid, fields) {
        return mutate('PATCH', API + '/placements/' + enc(pid), fields);
    }

    function changeKind(m, kind) {
        if (m.kind === kind) return;
        var locked = 0;
        each(m.placements, function (p) {
            if (p.status === 'approved' || p.status === 'paused' || p.status === 'failed') locked++;
        });
        var body = { kind: kind };
        // Источник данных один (таплист) — выбираем его сразу, чтобы материал
        // не встал в «не выбран источник данных» без причины.
        var sources = liveSources();
        if (kind === 'live' && !m.live_source && sources.length === 1) body.live_source = sources[0].key;
        var go = function () { patchMaterial(m.id, body); };
        if (!locked) { go(); return; }
        GH.confirm({
            title: 'Сменить тип материала?',
            text: 'Утверждение снимется с ' + nText(locked, 'размещения', 'размещений', 'размещений') +
                ': тип материала — часть содержания публикации.',
            ok: 'Сменить тип'
        }).then(function (ok) {
            if (ok) go();
            else renderDrawer();
        });
    }

    function insertToken(token) {
        var ta = el.drawer.querySelector('textarea[data-fk="base_text"]');
        if (!ta) return;
        var start = typeof ta.selectionStart === 'number' ? ta.selectionStart : ta.value.length;
        var end = typeof ta.selectionEnd === 'number' ? ta.selectionEnd : start;
        ta.value = ta.value.slice(0, start) + token + ta.value.slice(end);
        var caret = start + token.length;
        try { ta.focus({ preventScroll: true }); ta.setSelectionRange(caret, caret); } catch (e) { /* не критично */ }
        onDrawerInput({ target: ta });
    }

    function runLiveCheck(m) {
        var ta = el.drawer.querySelector('textarea[data-fk="base_text"]');
        var barKey = liveDefaultBar(m);
        S.liveBar = barKey;
        S.live = { mid: m.id, loading: true, bar: barKey };
        renderDrawer();
        var body = { source: m.live_source || '', bar: barKey, material_id: m.id,
                     template: ta ? ta.value : (m.base_text || '') };
        if (m.date) body.date = m.date;
        GH.api('POST', API + '/live-preview', body).then(function (res) {
            if (!S.live || S.live.mid !== m.id) return;
            S.live = { mid: m.id, result: res || {}, bar: barKey };
            if (current()) renderDrawer();
        }, function (err) {
            if (!S.live || S.live.mid !== m.id) return;
            S.live = { mid: m.id, error: err.message, bar: barKey };
            if (current()) renderDrawer();
        });
    }

    function approveOne(m, p) {
        var send = function (confirmBot) {
            GH.api('POST', API + '/approve', { placement_ids: [p.id], confirm_bot: !!confirmBot }).then(function (res) {
                var skipped = (res && res.skipped) || [];
                if (res && res.approved && res.approved.length) GH.toast('Утверждено: ' + chName(p.channel) + ' · ' +
                    GH.barName(p.bar), 'success');
                if (skipped.length) {
                    GH.toast('Не утверждено: ' + ((skipped[0].reasons || []).join(', ') || 'размещение не готово'), 'warning');
                }
                reload();
            }, function (err) { reportError(err); reload(); });
        };
        if (p.channel !== 'bot') { send(false); return; }
        GH.confirm({
            title: 'Утвердить рассылку через бота?',
            text: 'Аудитория: ' + (p.audience_info ? p.audience_info.name : 'не выбрана') + '.\nРазмер: ' + SIZE_UNKNOWN +
                '.\nПроверьте аудиторию: разосланное сообщение не отзовёшь.',
            ok: 'Утвердить рассылку'
        }).then(function (ok) { if (ok) send(true); });
    }

    function placementAction(m, p, action) {
        var run = function () {
            if (action === 'delete') return mutate('DELETE', API + '/placements/' + enc(p.id));
            return mutate('POST', API + '/placements/' + enc(p.id) + '/action', { action: action });
        };
        var what = chName(p.channel) + ' · ' + GH.barName(p.bar) + ' · ' + whenText(p);
        if (action === 'cancel') {
            GH.confirm({ title: 'Отменить размещение?', text: what + '\nРазмещение останется в плане как ' +
                'отменённое, его можно вернуть.', ok: 'Отменить размещение', cancel: 'Не отменять', danger: true })
                .then(function (ok) { if (ok) run(); });
        } else if (action === 'mark_published') {
            GH.confirm({ title: 'Отметить как вышедшее?', text: what + '\nПосле отметки размещение нельзя изменить ' +
                'или удалить — оно остаётся в истории.', ok: 'Отметить вышедшим' })
                .then(function (ok) { if (ok) run(); });
        } else if (action === 'delete') {
            GH.confirm({ title: 'Удалить размещение?', text: what + '\nРазмещение удаляется без возможности вернуть. ' +
                'Чтобы оставить его в истории, отмените его вместо удаления.', ok: 'Удалить', danger: true })
                .then(function (ok) { if (ok) run(); });
        } else {
            run();
        }
    }

    function addPlacements(m) {
        var f = addFormState(m);
        var body = { channel: f.channel, date: f.date || null, time: f.time || null };
        if (f.channel === 'telegram') {
            if (!f.bars.length) { GH.toast('Отметьте хотя бы один бар', 'warning'); return; }
            body.bars = f.bars.slice();
        } else {
            body.bars = [f.bar || 'all'];
        }
        if (f.channel === 'bot') {
            if (!f.audience) { GH.toast('Выберите аудиторию рассылки', 'warning'); return; }
            body.audience = { segment: f.audience };
        }
        mutate('POST', API + '/materials/' + enc(m.id) + '/placements', body).then(function (res) {
            if (!res) return;
            var n = (res.created || []).length;
            GH.toast('Добавлено: ' + nText(n, 'размещение', 'размещения', 'размещений'), 'success');
            if (S.addForm && S.addForm.mid === m.id) { S.addForm.bars = []; S.addForm.audience = ''; }
            if (current()) renderDrawer();
        });
    }

    function shiftMaterial(m) {
        var days = parseDays(S.shiftDays);
        if (days === null) {
            GH.toast('Сдвиг: целое число дней от −' + SHIFT_MAX + ' до ' + SHIFT_MAX + ', кроме 0', 'warning');
            return;
        }
        GH.confirm({
            title: 'Сдвинуть материал на ' + nText(Math.abs(days), 'день', 'дня', 'дней') + (days > 0 ? ' позже' : ' раньше') + '?',
            text: 'Дата темы и даты невышедших и неотменённых размещений «' + m.title + '» сдвинутся. ' +
                'Утверждение сохранится.',
            ok: 'Сдвинуть'
        }).then(function (ok) {
            if (!ok) return;
            mutate('POST', API + '/materials/' + enc(m.id) + '/shift', { days: days }).then(function (res) {
                if (res) { S.shiftDays = ''; if (current()) renderDrawer(); }
            });
        });
    }

    function repeatMaterial(m) {
        if (!S.repeatDays.length) return;
        mutate('POST', API + '/materials/' + enc(m.id) + '/repeat',
            { weekdays: S.repeatDays.slice().sort(), month: S.month }).then(function (res) {
            if (!res) return;
            var n = (res.created || []).length;
            if (n) GH.toast('Создано повторов: ' + n, 'success');
            else GH.toast('Новых дат нет: подходящие дни уже прошли или заняты этой серией', 'warning');
            S.repeatDays = [];
            if (current()) renderDrawer();
        });
    }

    function deleteMaterial(m) {
        GH.confirm({
            title: 'Удалить материал?',
            text: '«' + m.title + '» и все его размещения удаляются без возможности вернуть. Материал с вышедшими ' +
                'размещениями удалить нельзя: он остаётся для истории.',
            ok: 'Удалить материал', danger: true
        }).then(function (ok) {
            if (!ok) return;
            // Несохранённые правки этого материала больше не нужны.
            for (var k in S.dirty) {
                if (Object.prototype.hasOwnProperty.call(S.dirty, k) && k.indexOf('m:' + m.id + ':') === 0) {
                    delete S.dirty[k];
                    if (savers[k]) savers[k].cancel();
                }
            }
            GH.api('DELETE', API + '/materials/' + enc(m.id)).then(function () {
                GH.toast('Материал удалён', 'success');
                delete S.selected[m.id];
                GH.closeDrawer(el.drawer);
                reload();
            }, reportError);
        });
    }

    function deleteMedia(m, name) {
        var f = null;
        each(m.media, function (x) { if (x.name === name) f = x; });
        var locked = 0;
        each(m.placements, function (p) {
            if (locksOnContent(p) && (p.effective_media || []).indexOf(name) >= 0) locked++;
        });
        GH.confirm({
            title: 'Удалить файл?',
            text: '«' + (f ? f.original_name || f.name : name) + '» исчезнет из всех размещений этого материала.' +
                (locked ? '\nУтверждение снимется с ' + nText(locked, 'размещения', 'размещений', 'размещений') + '.' : ''),
            ok: 'Удалить файл', danger: true
        }).then(function (ok) {
            if (ok) mutate('DELETE', API + '/materials/' + enc(m.id) + '/media/' + enc(name));
        });
    }

    function uploadFiles(m, fileList) {
        var files = Array.prototype.slice.call(fileList || []);
        if (!files.length) return;
        var lim = (S.data && S.data.media_limits) || {};
        var ok = [];
        each(files, function (f) {
            var max = /^video\//.test(f.type) ? lim.video_bytes : lim.image_bytes;
            if (max && f.size > max) GH.toast('«' + f.name + '»: файл больше ' + mbText(max), 'danger');
            else ok.push(f);
        });
        if (!ok.length) return;
        S.uploading = { mid: m.id, total: ok.length, done: 0, failed: 0 };
        renderDrawer();
        // Размещения, с которых загрузка сняла утверждение (unapproved из
        // ответов по каждому файлу, без повторов), и последний материал из
        // ответа — по нему называем размещения в итоговом тосте.
        var unapproved = [];
        var lastMaterial = null;
        var chain = Promise.resolve();
        each(ok, function (f) {
            chain = chain.then(function () {
                var fd = new FormData();
                fd.append('file', f, f.name);
                return GH.api('POST', withMonth(API + '/materials/' + enc(m.id) + '/media'), fd).then(function (res) {
                    if (res && res.material) lastMaterial = res.material;
                    each(res && res.unapproved, function (id) { if (unapproved.indexOf(id) < 0) unapproved.push(id); });
                }, function (err) {
                    S.uploading.failed++;
                    GH.toast('«' + f.name + '»: ' + err.message, 'danger');
                    if (err.status === 503) reportError(err);
                }).then(function () {
                    S.uploading.done++;
                    var t = el.drawer.querySelector('[data-drop] .gh-cp-drop-t');
                    if (t && S.uploading.done < S.uploading.total) {
                        t.textContent = 'Загрузка: ' + (S.uploading.done + 1) + ' из ' + S.uploading.total + '…';
                    }
                });
            });
        });
        chain.then(function () {
            var up = S.uploading;
            S.uploading = null;
            var n = up.total - up.failed;
            if (n) GH.toast('Загружено: ' + nText(n, 'файл', 'файла', 'файлов'), 'success');
            if (unapproved.length) {
                // Тост не исчезает сам: снятое утверждение нельзя пропустить —
                // иначе публикация, которую считали утверждённой, не выйдет.
                var names = lastMaterial ? placementNames(lastMaterial, unapproved) : '';
                GH.toast('Утверждение снято с ' + nText(unapproved.length, 'размещения', 'размещений', 'размещений') +
                    (names ? ' (' + names + ')' : '') + ': новый файл вошёл в публикацию. Проверьте и утвердите ' +
                    'заново.', 'warning', { timeout: 0 });
            }
            if (n) reload({ material: lastMaterial });
            else load();
        });
    }

    // ----- обработчики карточки -----

    function onDrawerClick(e) {
        var t = e.target;
        var m = current();
        if (!m) return;
        var kindBtn = closest(t, '[data-kind-seg] [data-value]');
        if (kindBtn) { changeKind(m, kindBtn.getAttribute('data-value')); return; }
        var addSeg = closest(t, '[data-add-seg] [data-value]');
        if (addSeg) {
            var f = addFormState(m);
            var ch = addSeg.getAttribute('data-value');
            if (f.channel !== ch) {
                f.channel = ch;
                f.bars = [];
                f.bar = 'all';
                f.audience = '';
                renderDrawer();
            }
            return;
        }
        var act = closest(t, '[data-act]');
        if (!act || act.disabled || !el.drawer.contains(act)) return;
        var a = act.getAttribute('data-act');
        var pid = act.getAttribute('data-pid');
        var p = pid ? findPlacement(m, pid) : null;
        if (a === 'toggle-pl' && p) {
            S.expanded[pid] = !S.expanded[pid];
            renderDrawer();
        } else if (a.indexOf('pl-') === 0 && p) {
            var action = a.slice(3);
            if (action === 'approve') approveOne(m, p);
            else placementAction(m, p, action);
        } else if (a === 'token') {
            insertToken(act.getAttribute('data-token'));
        } else if (a === 'live-check') {
            runLiveCheck(m);
        } else if (a === 'media-del') {
            deleteMedia(m, act.getAttribute('data-name'));
        } else if (a === 'pick-files') {
            if (S.uploading) return;
            S.pickFor = m.id;
            el.file.value = '';
            el.file.click();
        } else if (a === 'add-pl') {
            addPlacements(m);
        } else if (a === 'ptab' && pid) {
            S.previewPid = pid;
            renderSection('preview');
            maybeLoadPreviewLive(m);
        } else if (a === 'shift') {
            shiftMaterial(m);
        } else if (a === 'repeat') {
            repeatMaterial(m);
        } else if (a === 'log-all') {
            if (S.log) S.log.all = true;
            renderSection('log');
        } else if (a === 'delete') {
            deleteMaterial(m);
        }
    }

    function onDrawerInput(e) {
        var t = e.target;
        var key = t.getAttribute && t.getAttribute('data-save-key');
        if (key) {
            if (/:title$/.test(key)) {
                // Перевод строки в названии не нужен (сервер всё равно склеит пробелы).
                if (/\n/.test(t.value)) t.value = t.value.replace(/\s*\n\s*/g, ' ');
                fitTitle();
            }
            S.dirty[key] = t.value;
            setSave('dirty');
            saver(key)();
            updateCounter(t);
            return;
        }
        if (t.getAttribute && t.getAttribute('data-rep') === 'days') S.shiftDays = t.value;
    }

    // Дата и время размещения сюда не попадают: их сохраняет dtChange/dtCommit.
    function placementFieldChange(m, p, pf, t) {
        if (pf === 'bar') { patchPlacement(p.id, { bar: t.value }); return; }
        if (pf === 'audience') { patchPlacement(p.id, { audience: t.value ? { segment: t.value } : null }); return; }
        if (pf === 'own') {
            if (t.checked) { patchPlacement(p.id, { text: p.effective_text || '' }); return; }
            GH.confirm({
                title: 'Вернуть общий текст?',
                text: 'Своя версия текста этого размещения будет удалена, размещение возьмёт общий текст материала.',
                ok: 'Вернуть общий текст'
            }).then(function (ok) {
                if (!ok) { t.checked = true; return; }
                var key = 'p:' + p.id + ':text';
                delete S.dirty[key];
                if (savers[key]) savers[key].cancel();
                patchPlacement(p.id, { text: null });
            });
            return;
        }
        if (pf === 'media-all') {
            var names = [];
            each(m.media, function (f) { names.push(f.name); });
            patchPlacement(p.id, { media: t.checked ? null : names });
            return;
        }
        if (pf === 'media-item') {
            var boxes = el.drawer.querySelectorAll('[data-pf="media-item"][data-pid="' + p.id + '"]');
            var chosen = [];
            for (var i = 0; i < boxes.length; i++) if (boxes[i].checked) chosen.push(boxes[i].value);
            patchPlacement(p.id, { media: chosen });
        }
    }

    function onDrawerChange(e) {
        var t = e.target;
        var m = current();
        if (!m || !t.getAttribute) return;
        // Дата темы, дата и время размещения и формы добавления — только целым
        // значением (раздел «дата и время»).
        if (isDT(t)) { dtChange(t); return; }
        var mf = t.getAttribute('data-mf');
        if (mf === 'media_required') { patchMaterial(m.id, { media_required: t.checked }); return; }
        if (mf === 'live_source') { patchMaterial(m.id, { live_source: t.value || null }); return; }
        var pf = t.getAttribute('data-pf');
        var pid = t.getAttribute('data-pid');
        if (pf && pid) {
            var p = findPlacement(m, pid);
            if (p) placementFieldChange(m, p, pf, t);
            return;
        }
        var add = t.getAttribute('data-add');
        if (add) {
            var f = addFormState(m);
            if (add === 'allbars') {
                f.bars = [];
                if (t.checked) each(GH.BARS, function (b) { f.bars.push(b.key); });
            } else if (add === 'bar') {
                var at = f.bars.indexOf(t.value);
                if (t.checked && at < 0) f.bars.push(t.value);
                if (!t.checked && at >= 0) f.bars.splice(at, 1);
            } else if (add === 'barsel') {
                f.bar = t.value;
            } else if (add === 'audience') {
                f.audience = t.value;
            }
            renderDrawer();
            return;
        }
        var rep = t.getAttribute('data-rep');
        if (rep === 'days') { S.shiftDays = t.value; return; }
        if (rep === 'wd') {
            var d = parseInt(t.value, 10);
            var i = S.repeatDays.indexOf(d);
            if (t.checked && i < 0) S.repeatDays.push(d);
            if (!t.checked && i >= 0) S.repeatDays.splice(i, 1);
            var btn = el.drawer.querySelector('[data-act="repeat"]');
            if (btn) btn.disabled = !S.repeatDays.length;
            return;
        }
        if (t.getAttribute('data-live') === 'bar') { S.liveBar = t.value; }
    }

    // Выбор файлов в постоянном поле #cpFile (вне карточки, см. mediaHtml).
    function onFilePicked() {
        var files = Array.prototype.slice.call(el.file.files || []);
        el.file.value = '';
        var m = S.pickFor ? findMaterial(S.pickFor) : null;
        S.pickFor = null;
        if (!files.length) return;
        if (!m) { GH.toast('Материал удалён или не найден — файлы не загружены', 'warning'); return; }
        if (S.uploading) { GH.toast('Идёт загрузка других файлов — дождитесь её и добавьте эти ещё раз', 'warning'); return; }
        uploadFiles(m, files);
    }

    function onDrawerFocusOut(e) {
        var t = e.target;
        if (isDT(t)) {
            var fk = t.getAttribute('data-fk');
            if (S.dtPending[fk]) { dtCommit(t); return; }
            delete S.dtKeyAt[fk];
            if (S.drawerStale) renderDrawerSoon();
            return;
        }
        var key = t.getAttribute && t.getAttribute('data-save-key');
        if (!key) return;
        var hasDirty = Object.prototype.hasOwnProperty.call(S.dirty, key);
        if (/:title$/.test(key) && hasDirty && !String(S.dirty[key]).trim()) {
            delete S.dirty[key];
            delete S.savedVal[key];
            if (savers[key]) savers[key].cancel();
            setSave('');
            GH.toast('Название не может быть пустым — оставлено прежнее', 'warning');
            renderDrawer();
            return;
        }
        if (savers[key] && savers[key].pending()) {
            savers[key].flush();
        } else if (Object.prototype.hasOwnProperty.call(S.savedVal, key)) {
            // Сохранено, пока поле было в фокусе (saveKey): теперь поле
            // показывает значение сервера.
            if (S.dirty[key] === S.savedVal[key]) delete S.dirty[key];
            delete S.savedVal[key];
        }
        // Название при уходе из поля — таким, каким его сохранит сервер
        // (пробелы по краям и двойные пробелы убираются); во время набора поле
        // не переписывается.
        if (/:title$/.test(key)) {
            var norm = normTitle(t.value);
            if (norm !== t.value) { t.value = norm; fitTitle(); }
        }
    }

    function onDrawerKey(e) {
        var t = e.target;
        if (isDT(t)) {
            if (e.key === 'Enter') { e.preventDefault(); dtCommit(t); return; }
            // Tab/Shift — переход между полями, Escape — закрытие карточки: не набор.
            if (e.key !== 'Tab' && e.key !== 'Shift' && e.key !== 'Escape') S.dtKeyAt[t.getAttribute('data-fk')] = Date.now();
            return;
        }
        if (e.key === 'Enter' && t.classList && t.classList.contains('gh-cp-title')) {
            e.preventDefault();
            t.blur();
        }
    }

    function bindDrop() {
        el.drawer.addEventListener('dragover', function (e) {
            var zone = closest(e.target, '[data-drop]');
            if (!zone) return;
            e.preventDefault();
            zone.classList.add('is-drag');
        });
        el.drawer.addEventListener('dragleave', function (e) {
            var zone = closest(e.target, '[data-drop]');
            if (zone && !zone.contains(e.relatedTarget)) zone.classList.remove('is-drag');
        });
        el.drawer.addEventListener('drop', function (e) {
            var zone = closest(e.target, '[data-drop]');
            if (!zone) return;
            e.preventDefault();
            zone.classList.remove('is-drag');
            var m = current();
            if (m && !S.uploading && e.dataTransfer) uploadFiles(m, e.dataTransfer.files);
        });
    }

    // ==================== диалог «Утвердить готовые» ====================

    function approveScope() {
        return GH.monthLabel(S.month) + ' · ' + (S.bar ? GH.barName(S.bar) : 'все бары') + ' · ' +
            (S.channel ? chName(S.channel) : 'все площадки') + (S.origin ? ' · только от ИИ' : '');
    }
    function apWhen(it) {
        return (it.date ? GH.fmtDateShort(it.date) : 'без даты') + (it.time ? ' ' + it.time : '');
    }
    // Строки диалога группируются: один материал в одно время на нескольких
    // барах — одна строка со списком баров (20 одинаковых строк «Таплист
    // пятницы» не читаются). Число в заголовке блока — по-прежнему размещения.
    function barOrder(key) {
        if (key === 'all') return -1;
        for (var i = 0; i < GH.BARS.length; i++) if (GH.BARS[i].key === key) return i;
        return GH.BARS.length;
    }
    function apGroups(items, withReasons) {
        var list = [];
        var index = {};
        each(items, function (it) {
            var why = [];
            if (withReasons) each(it.missing, function (x) { why.push(x.text); });
            var key = [it.material_id, it.date || '', it.time || '', it.channel, why.join(', ')].join('|');
            if (!index[key]) {
                index[key] = { date: it.date, time: it.time, title: it.title, channel: it.channel,
                               why: why.join(', '), bars: [], kind: itemKind(it), origin: it.origin };
                list.push(index[key]);
            }
            index[key].bars.push(it.bar);
        });
        each(list, function (g) { g.bars.sort(function (a, b) { return barOrder(a) - barOrder(b); }); });
        return list;
    }
    // Тип материала строки: kind из ответа approve-preview, если сервер его
    // даёт, иначе — из загруженного плана (диалог показывает тот же месяц).
    function itemKind(it) {
        if (it.kind) return it.kind;
        var m = findMaterial(it.material_id);
        return m ? m.kind : '';
    }
    var LIVE_AP_TIP = 'Материал с актуальными данными: утверждается шаблон, а таплист подставляется в момент ' +
        'выхода. Если данных не будет или они не проверены, публикация остановится.';
    function liveTag(kind) {
        return kind === 'live' ? ' <span class="gh-badge gh-tone-accent gh-cp-ap-live"' + tip(LIVE_AP_TIP) + '>' +
            'шаблон · данные при выходе</span>' : '';
    }
    function apRow(g, extra) {
        var bars = [];
        each(g.bars, function (b) { bars.push(GH.barShort(b)); });
        return '<li class="gh-cp-ap-i"><span class="gh-cp-ap-when">' + esc(apWhen(g)) + '</span>' +
            '<span class="gh-cp-ap-what">' + aiMark(g, true) + esc(g.title) + ' <b>' + esc(bars.join(' · ')) + '</b>' +
                liveTag(g.kind) + '</span>' +
            (extra || '') + '</li>';
    }

    function openApprove() {
        flushAll();
        S.approve = { loading: true, bots: {} };
        renderApprove();
        GH.openModal(el.approveModal);
        // Под фильтром «Только от ИИ» окно утверждает только материалы агента
        // (сервер: ?origin=), как бар и площадка — только отфильтрованное.
        var q = '?month=' + enc(S.month) + (S.bar ? '&bar=' + enc(S.bar) : '') +
            (S.channel ? '&channel=' + enc(S.channel) : '') + (S.origin ? '&origin=' + enc(S.origin) : '');
        GH.api('GET', API + '/approve-preview' + q).then(function (res) {
            if (!S.approve) return;
            S.approve = { data: res || {}, bots: {} };
            renderApprove();
        }, function (err) {
            if (!S.approve) return;
            S.approve = { error: err.message, bots: {} };
            renderApprove();
        });
    }

    function renderApprove() {
        var a = S.approve || {};
        var html = '<p class="gh-cp-scope">' + esc(approveScope()) + '</p><p>' + esc(APPROVE_TEXT) + '</p>';
        if (a.loading) {
            html += '<div class="gh-cp-loading"><span class="gh-spin"></span>Собираю список…</div>';
        } else if (a.error) {
            html += '<p class="gh-field-err">' + esc(a.error) + '</p>';
        } else {
            var d = a.data || {};
            var will = d.will_approve || [];
            var bots = d.bot || [];
            var stays = d.stays_draft || [];
            html += sub('Уйдут в публикацию', String(will.length));
            if (!will.length) {
                html += '<p class="gh-cp-explain">Готовых публикаций под эти фильтры нет.</p>';
            } else {
                each(CHANNEL_KEYS, function (ch) {
                    var items = [];
                    each(will, function (it) { if (it.channel === ch) items.push(it); });
                    if (!items.length) return;
                    html += '<div class="gh-cp-ap-g"><div class="gh-cp-ap-gh">' + esc(chName(ch)) + ' · ' +
                        esc(nText(items.length, 'размещение', 'размещения', 'размещений')) +
                        '</div><ul class="gh-cp-ap-list">';
                    each(apGroups(items, false), function (g) { html += apRow(g); });
                    html += '</ul></div>';
                });
            }
            if (bots.length) {
                html += sub('Рассылки через бота', String(bots.length));
                html += '<p class="gh-cp-explain">Рассылка утверждается, только если её отметить. Проверьте аудиторию: ' +
                    'разосланное сообщение не отзовёшь.</p>';
                each(bots, function (it) {
                    html += '<label class="gh-cb gh-cp-ap-bot"><input type="checkbox" data-bot="' + esc(it.placement_id) + '"' +
                        (a.bots[it.placement_id] ? ' checked' : '') + '><span>' + aiMark(it, true) + '<b>' + esc(it.title) + '</b> · ' +
                        esc(apWhen(it)) + ' · ' + esc(GH.barName(it.bar)) + liveTag(itemKind(it)) + '<br>Аудитория: ' +
                        esc(it.audience ? it.audience.name : 'не выбрана') + ' · размер: ' + esc(SIZE_UNKNOWN) +
                        '</span></label>';
                });
            }
            if (stays.length) {
                html += sub('Останутся черновиками', String(stays.length));
                html += '<ul class="gh-cp-ap-list is-stay">';
                each(apGroups(stays, true), function (g) {
                    html += apRow(g, '<span class="gh-cp-ap-why">' + esc(chName(g.channel)) + ' · не хватает: ' +
                        esc(g.why) + '</span>');
                });
                html += '</ul>';
            }
        }
        el.approveBody.innerHTML = html;
        updateApproveBtn();
    }

    function approveIds() {
        var a = S.approve || {};
        var d = a.data || {};
        var ids = [];
        var bots = 0;
        each(d.will_approve, function (it) { ids.push(it.placement_id); });
        each(d.bot, function (it) { if (a.bots && a.bots[it.placement_id]) { ids.push(it.placement_id); bots++; } });
        return { ids: ids, bots: bots };
    }
    function updateApproveBtn() {
        var x = approveIds();
        var busy = S.approve && S.approve.busy;
        el.approveGo.disabled = !x.ids.length || !!busy || !!(S.approve && S.approve.loading);
        el.approveGo.textContent = x.ids.length ? 'Утвердить ' + x.ids.length : 'Утвердить';
    }
    function submitApprove() {
        var x = approveIds();
        if (!x.ids.length) return;
        S.approve.busy = true;
        updateApproveBtn();
        GH.api('POST', API + '/approve', { placement_ids: x.ids, confirm_bot: x.bots > 0 }).then(function (res) {
            var approved = (res && res.approved) || [];
            var skipped = (res && res.skipped) || [];
            GH.closeModal(el.approveModal);
            GH.toast('Утверждено: ' + nText(approved.length, 'размещение', 'размещения', 'размещений'), 'success');
            if (skipped.length) {
                GH.toast('Не утверждено: ' + skipped.length + ' — ' + ((skipped[0].reasons || []).join(', ') ||
                    'изменились данные'), 'warning');
            }
            reload();
        }, function (err) {
            if (S.approve) S.approve.busy = false;
            updateApproveBtn();
            reportError(err);
        });
    }

    // ==================== диалог «Скопировать прошлый месяц» ====================

    function openCopy() {
        flushAll();
        var from = GH.addMonths(S.month, -1);
        S.copy = { from: from, to: S.month, past: S.month < currentMonth(), content: false, count: null,
                   result: null, error: '', busy: false };
        renderCopy();
        GH.openModal(el.copyModal, { onClose: function () { S.copy = null; } });
        GH.api('GET', API + '?month=' + enc(from)).then(function (res) {
            if (!S.copy || S.copy.from !== from) return;
            S.copy.count = res && res.stats ? res.stats.materials || 0 : 0;
            renderCopy();
        }, function () {
            if (!S.copy || S.copy.from !== from) return;
            S.copy.count = -1;
            renderCopy();
        });
    }

    // Правила переноса дат в диалоге берутся с сервера (meta copy_rules =
    // core/content_plan.COPY_RULES), а не пишутся здесь своим текстом: copy_month
    // переносит по n-му дню недели только опорную дату, остальные даты материала
    // сдвигает вместе с ней, а серию собирает из размещений всех её дней. Свой
    // список в JS уже однажды разошёлся с кодом (описывал перенос каждой даты
    // отдельно), а правило на экране обязано совпадать с расчётом (принцип
    // проекта). Запасной список — пока план не загрузился: только утверждения,
    // верные при любом из этих правил.
    var COPY_RULES_FALLBACK = [
        'Даты переносятся на тот же день недели; порядок и интервалы размещений материала сохраняются.',
        'Материалы без даты копируются без даты. Отменённые размещения не копируются.',
        'Все копии — черновики: ничего не утверждается и не публикуется.'
    ];
    function copyRules() {
        var rules = S.data && S.data.copy_rules;
        return rules && rules.length ? rules.slice() : COPY_RULES_FALLBACK.slice();
    }

    function renderCopy() {
        var c = S.copy;
        if (!c) return;
        var html;
        if (c.result) {
            html = '<p class="gh-cp-scope">«' + esc(GH.monthLabel(c.from)) + '» → «' + esc(GH.monthLabel(c.to)) + '»</p>' +
                '<p><b>Скопировано: ' + esc(nText(c.result.created || 0, 'материал', 'материала', 'материалов')) +
                '.</b> Все копии — черновики: ничего не утверждено и не опубликовано.</p>';
            if ((c.result.notes || []).length) {
                html += sub('Обратите внимание', String(c.result.notes.length)) + '<ul class="gh-cp-rules">';
                each(c.result.notes, function (n) { html += '<li>' + esc(n) + '</li>'; });
                html += '</ul>';
            }
            el.copyBody.innerHTML = html;
            el.copyGo.textContent = 'Готово';
            el.copyGo.disabled = false;
            return;
        }
        var countText = c.count === null ? 'Считаю материалы…'
            : c.count < 0 ? 'Не удалось прочитать план прошлого месяца.'
            : 'В плане «' + GH.monthLabel(c.from) + '»: ' + nText(c.count, 'материал', 'материала', 'материалов') + '.';
        html = '<p class="gh-cp-scope">Из «' + esc(GH.monthLabel(c.from)) + '» в «' + esc(GH.monthLabel(c.to)) + '»</p>' +
            '<p>' + esc(countText) + '</p>';
        if (c.past) {
            html += '<div class="gh-cp-warn">«' + esc(GH.monthLabel(c.to)) + '» уже прошёл: копировать можно только ' +
                'в текущий или будущий месяц.</div>';
        }
        html += '<label class="gh-cb gh-cp-copyopt"><input type="checkbox" data-copy="content"' +
                (c.content ? ' checked' : '') + '><span>Копировать тексты и фото</span></label>' +
            '<div class="gh-field-hint">Выключено: у готовых публикаций копируются названия и размещения, тексты и ' +
                'фото пишутся заново. Шаблоны материалов с актуальными данными копируются всегда — это ' +
                'утверждённый дизайн.</div>' +
            sub('Как переносятся даты', '') +
            '<ul class="gh-cp-rules">';
        each(copyRules(), function (r) { html += '<li>' + esc(r) + '</li>'; });
        html += '<li>Если дата копии уже прошла, черновик покажет «время выхода уже прошло» — его нужно перенести.</li>' +
            '</ul>';
        if (c.error) html += '<p class="gh-field-err">' + esc(c.error) + '</p>';
        el.copyBody.innerHTML = html;
        el.copyGo.textContent = c.busy ? 'Копирую…' : 'Скопировать';
        el.copyGo.disabled = c.busy || c.past || c.count === 0;
    }

    function submitCopy() {
        var c = S.copy;
        if (!c) return;
        if (c.result) { GH.closeModal(el.copyModal); return; }
        c.busy = true;
        c.error = '';
        renderCopy();
        GH.api('POST', API + '/copy-month', { from: c.from, to: c.to, with_content: !!c.content }).then(function (res) {
            if (S.copy !== c) return;
            c.busy = false;
            c.result = res || { created: 0, notes: [] };
            renderCopy();
            reload();
        }, function (err) {
            if (S.copy !== c) return;
            c.busy = false;
            c.error = err.message;
            renderCopy();
            if (err.status === 503) reportError(err);
        });
    }

    // ==================== черновики ИИ ====================

    // «Удалить черновики ИИ»: материалы агента плана этого месяца, у которых
    // все размещения — черновики или отменены (agent_draft считает сервер).
    // Подтверждение называет число и материалы; на сервер уходят ровно эти id
    // (POST /agent-drafts/delete): если план успел измениться, сервер удалит
    // только то, что всё ещё черновик ИИ, и вернёт остальное в skipped.
    function deleteAgentDrafts() {
        if (S.scope) return;
        var list = agentStats().drafts;
        if (!list.length) return;
        flushAll();
        var names = [];
        each(list.slice(0, AGENT_DEL_SHOWN), function (m) { names.push('— «' + m.title + '»'); });
        if (list.length > AGENT_DEL_SHOWN) names.push('и ещё ' + (list.length - AGENT_DEL_SHOWN));
        var what = nText(list.length, 'черновик', 'черновика', 'черновиков');
        GH.confirm({
            title: 'Удалить черновики ИИ: ' + list.length + '?',
            text: 'Удаляются материалы плана «' + GH.monthLabel(S.month) + '», которые создал ИИ-агент и у ' +
                'которых ни одно размещение не утверждено и не вышло (все — черновики или отменены). Вернуть ' +
                'их нельзя. Материалы людей и утверждённое не трогаются.\n\n' + names.join('\n'),
            ok: 'Удалить ' + what, danger: true
        }).then(function (ok) {
            if (!ok) return;
            var ids = [];
            each(list, function (m) { ids.push(m.id); });
            GH.api('POST', API + '/agent-drafts/delete', { month: S.month, material_ids: ids }).then(function (res) {
                var deleted = (res && res.deleted) || [];
                var skipped = (res && res.skipped) || [];
                each(deleted, function (id) {
                    delete S.selected[id];
                    // Несохранённые правки удалённого материала больше не нужны.
                    for (var k in S.dirty) {
                        if (Object.prototype.hasOwnProperty.call(S.dirty, k) && k.indexOf('m:' + id + ':') === 0) {
                            delete S.dirty[k];
                            if (savers[k]) savers[k].cancel();
                        }
                    }
                });
                if (S.openId && deleted.indexOf(S.openId) >= 0) GH.closeDrawer(el.drawer);
                GH.toast('Удалено черновиков ИИ: ' + deleted.length, deleted.length ? 'success' : 'muted');
                if (skipped.length) {
                    GH.toast('Не удалено: ' + skipped.length + ' — ' + (skipped[0].reason || ''), 'warning');
                }
                reload();
            }, function (err) { reportError(err); reload(); });
        });
    }

    // ==================== бриф для агента ====================
    // Поля, подписи, подсказки и пределы приходят с сервера (schema в ответе
    // GET /api/content-plan/brief, core/content_brief.py) — экран их не
    // дублирует. Каждое поле сохраняется само через AUTOSAVE_MS после
    // последнего нажатия и сразу при уходе из поля: PUT {sections: {...}} с
    // одним полем (сервер сливает переданное с остальным). Карточка после
    // сохранения не перерисовывается (набранное остаётся в поле); отклонённое
    // значение (400: длиннее предела) остаётся в поле с красным счётчиком,
    // чтобы его можно было сократить.

    // Ключи полей брифа: 's:<раздел>' — текстовый раздел; 'b:<бар>:<поле>' —
    // поле бара; 'e' — весь список примеров (examples заменяется целиком).
    function briefBody(key, value) {
        var parts = String(key).split(':');
        var sections = {};
        if (parts[0] === 's') {
            sections[parts[1]] = value;
        } else if (parts[0] === 'b') {
            var fields = {};
            fields[parts[2]] = value;
            sections.bars = {};
            sections.bars[parts[1]] = fields;
        } else if (parts[0] === 'e') {
            sections.examples = value;
        }
        return { sections: sections };
    }

    function briefSchema() { return (S.brief && S.brief.data && S.brief.data.schema) || {}; }
    function briefSections() {
        var d = S.brief && S.brief.data;
        return (d && d.brief && d.brief.sections) || {};
    }
    function briefDirtyOr(key, value) {
        return Object.prototype.hasOwnProperty.call(S.briefDirty, key) ? S.briefDirty[key] : value;
    }

    function openBrief() {
        flushAll();
        S.brief = { loading: true };
        S.briefDirty = {};
        setBriefSave('');
        renderBrief();
        GH.openDrawer(el.briefDrawer, { onClose: onBriefClose });
        GH.setParams({ brief: '1' });
        loadBrief();
    }

    function loadBrief() {
        GH.api('GET', API + '/brief').then(function (res) {
            if (!S.brief) return;
            var sections = (res && res.brief && res.brief.sections) || {};
            S.brief = { data: res || {}, examples: (sections.examples || []).slice() };
            renderBrief();
        }, function (err) {
            if (!S.brief) return;
            S.brief = { error: err.status === 503
                ? 'Бриф недоступен: ' + err.message + '. Файл не перезаписывается — сообщите администратору.'
                : 'Бриф не загрузился: ' + err.message };
            renderBrief();
        });
    }

    function onBriefClose() {
        flushBrief();
        S.brief = null;
        GH.setParams({ brief: null });
    }

    function briefStatus() {
        var d = S.brief && S.brief.data;
        if (!d || !d.brief) return 'Правила сети для ИИ-агента';
        if (!d.stored) return 'Ещё не сохранён: показана затравка из справочника баров';
        var b = d.brief;
        return 'Сохранён ' + GH.fmtDateTime(b.updated_at) + (b.updated_by ? ', ' + b.updated_by : '');
    }

    function briefCounter(id, text, max) {
        var n = charLen(text);
        return '<span class="gh-counter' + (max && n > max ? ' is-over' : '') + '" data-bcounter="' + esc(id) +
            '" data-limit="' + (max || 0) + '"' + tip('Предел поля — ' + max + ' знаков. Длина считается в ' +
                'символах, как на сервере.') + '>' + n + ' / ' + max + '</span>';
    }

    // Поле брифа: textarea + подсказка + счётчик. key — ключ сохранения,
    // cid — ключ счётчика (у примеров — 'e:<номер>': ключ сохранения общий).
    function briefArea(key, cid, value, max, label, rows, extra) {
        var text = key === 'e' ? value : briefDirtyOr(key, value || '');
        return '<textarea class="gh-textarea gh-cp-brief-ta" rows="' + rows + '" data-bkey="' + esc(key) + '"' +
            ' data-bc="' + esc(cid) + '" data-fk="brief:' + esc(cid) + '"' + (extra || '') +
            ' aria-label="' + esc(label) + '">' + esc(text) + '</textarea>' +
            '<div class="gh-cp-textfoot">' + briefCounter(cid, text, max) + '</div>';
    }

    function briefTextHtml(spec, sections) {
        var key = 's:' + spec.key;
        return '<section class="gh-cp-sec" data-bsec="' + esc(spec.key) + '">' + sub(spec.label, '') +
            (spec.hint ? '<p class="gh-field-hint">' + esc(spec.hint) + '</p>' : '') +
            briefArea(key, key, sections[spec.key], spec.max, spec.label, 4) + '</section>';
    }

    function briefExamplesHtml(spec) {
        var list = S.brief.examples || [];
        var html = '<section class="gh-cp-sec" data-bsec="examples">' +
            sub(spec.label, list.length + ' из ' + spec.max_items) +
            (spec.hint ? '<p class="gh-field-hint">' + esc(spec.hint) + '</p>' : '');
        each(list, function (text, i) {
            html += '<div class="gh-cp-brief-ex">' +
                '<div class="gh-cp-brief-ex-h"><span>Пример ' + (i + 1) + '</span>' +
                    '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-bact="del-example" data-ei="' + i +
                    '" data-fk="brief:del:' + i + '">Убрать</button></div>' +
                briefArea('e', 'e:' + i, text, spec.max, 'Пример ' + (i + 1), 5, ' data-ei="' + i + '"') +
                '</div>';
        });
        html += '<button type="button" class="gh-btn gh-btn-sm" data-bact="add-example" data-fk="brief:add"' +
            (list.length >= spec.max_items ? ' disabled' : '') + '>' + PLUS_SVG + 'Добавить пример</button>';
        return html + '</section>';
    }

    function briefBarsHtml(spec, sections) {
        var schema = briefSchema();
        var bars = sections.bars || {};
        var html = '<section class="gh-cp-sec" data-bsec="bars">' + sub(spec.label, '') +
            (spec.hint ? '<p class="gh-field-hint">' + esc(spec.hint) + '</p>' : '');
        // Порядок баров — список schema.bars (в объекте ответа ключи отсортированы).
        each(schema.bars, function (bar) {
            var fields = bars[bar.key] || {};
            var facts = [];
            if (bar.address) facts.push(bar.address);
            if (bar.taps) facts.push('кранов: ' + bar.taps);
            html += '<div class="gh-cp-brief-bar">' +
                '<div class="gh-cp-brief-bar-h"><b>' + esc(bar.name) + '</b>' +
                    (facts.length ? '<span>' + esc(facts.join(' · ')) + '</span>' : '') + '</div>';
            each(schema.bar_fields, function (f) {
                var key = 'b:' + bar.key + ':' + f.key;
                html += '<div class="gh-field"><span class="gh-field-cap"' + tip(f.hint) + '>' + esc(f.label) +
                    '</span>' + briefArea(key, key, fields[f.key], f.max, bar.name + ' — ' + f.label, 2) + '</div>';
            });
            html += '</div>';
        });
        return html + '</section>';
    }

    function briefBodyHtml() {
        var d = S.brief.data || {};
        var schema = d.schema || {};
        var sections = briefSections();
        var html = '<div class="gh-cp-brief-intro">' +
            '<p class="gh-cp-brief-purpose">' + esc(schema.purpose || '') + '</p>' +
            '<p class="gh-cp-explain">' + esc(schema.limits_note || '') + '</p>' +
            (d.stored ? '' : '<div class="gh-cp-warn">Бриф ещё не сохранён: в разделе «О сети» — затравка из ' +
                'справочника баров сервиса (названия, адреса, краны). Он сохранится с первой правкой.</div>') +
            '</div>';
        each(schema.sections, function (spec) {
            if (spec.type === 'text') html += briefTextHtml(spec, sections);
            else if (spec.type === 'list') html += briefExamplesHtml(spec);
            else if (spec.type === 'bars') html += briefBarsHtml(spec, sections);
        });
        return html;
    }

    function renderBrief() {
        var b = S.brief;
        if (!b) return;
        var focus = captureFocus(el.briefDrawer);
        var oldBody = el.briefDrawer.querySelector('.gh-drawer-body');
        var scroll = oldBody ? oldBody.scrollTop : 0;
        var body;
        if (b.loading) {
            body = '<div class="gh-cp-loading"><span class="gh-spin"></span>Загружаю бриф…</div>';
        } else if (b.error) {
            body = '<p class="gh-field-err">' + esc(b.error) + '</p>' +
                '<button type="button" class="gh-btn gh-btn-sm" data-bact="retry">Повторить</button>';
        } else {
            body = briefBodyHtml();
        }
        el.briefDrawer.innerHTML = '<div class="gh-drawer-head">' +
                '<div class="gh-drawer-h"><div class="gh-drawer-t">Бриф для агента</div>' +
                    '<div class="gh-drawer-s" data-bstatus>' + esc(briefStatus()) + '</div></div>' +
                '<button type="button" class="gh-x" data-gh-close aria-label="Закрыть бриф">' + X_SVG + '</button>' +
            '</div>' +
            '<div class="gh-drawer-body">' + body + '</div>' +
            '<div class="gh-drawer-foot">' +
                '<span class="gh-cp-brief-total" data-btotal></span>' +
                '<span class="gh-grow"></span>' +
                '<span class="gh-save" data-bsave></span>' +
                '<button type="button" class="gh-btn gh-btn-sm" data-gh-close>Закрыть</button>' +
            '</div>';
        fitBriefAreas();
        var newBody = el.briefDrawer.querySelector('.gh-drawer-body');
        if (newBody) newBody.scrollTop = scroll;
        restoreFocus(el.briefDrawer, focus);
        updateBriefTotal();
        updateBriefSave();
    }

    // «Всего: N / предел» — сумма длин всех полей на экране (как brief_total
    // на сервере, но с несохранённым): видно заранее, упрётся ли правка в
    // предел всего брифа (schema.total_max сервера).
    function updateBriefTotal() {
        var node = el.briefDrawer.querySelector('[data-btotal]');
        if (!node) return;
        var max = briefSchema().total_max;
        if (!max) { node.textContent = ''; return; }
        var areas = el.briefDrawer.querySelectorAll('[data-bkey]');
        var n = 0;
        for (var i = 0; i < areas.length; i++) n += charLen(areas[i].value);
        node.textContent = 'Всего: ' + GH.fmtNum(n, 0) + ' / ' + GH.fmtNum(max, 0);
        node.classList.toggle('is-over', n > max);
        node.setAttribute('data-tip', 'Длина всего брифа: все разделы, примеры и поля баров. Больше ' +
            GH.fmtNum(max, 0) + ' знаков сохранить нельзя (сокращать можно всегда): агент читает бриф целиком ' +
            'перед каждым черновиком.');
    }

    // Поле брифа растёт по тексту, но не выше BRIEF_AREA_MAX_PX (дальше —
    // прокрутка внутри поля): затравка «О сети» и длинные правила видны
    // целиком без ручного растягивания, а одно огромное поле не прячет
    // остальные. box-sizing: border-box (base.css) — к высоте текста
    // добавляются рамки.
    var BRIEF_AREA_MAX_PX = 420;
    function fitBriefArea(area) {
        area.style.height = 'auto';
        var h = area.scrollHeight;
        if (!h) return;     // карточка ещё скрыта: высоту подгонит следующая отрисовка
        var cs = window.getComputedStyle ? window.getComputedStyle(area) : null;
        var borders = cs ? (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0) : 0;
        area.style.height = Math.min(h + borders, BRIEF_AREA_MAX_PX) + 'px';
    }
    function fitBriefAreas() {
        var areas = el.briefDrawer.querySelectorAll('[data-bkey]');
        for (var i = 0; i < areas.length; i++) fitBriefArea(areas[i]);
    }

    function updateBriefCounter(area) {
        var cid = area.getAttribute('data-bc');
        var node = cid ? el.briefDrawer.querySelector('[data-bcounter="' + cid + '"]') : null;
        if (!node) return;
        var n = charLen(area.value);
        var max = Number(node.getAttribute('data-limit')) || 0;
        node.textContent = n + ' / ' + max;
        node.classList.toggle('is-over', !!max && n > max);
    }

    function setBriefSave(stateName, message) {
        S.briefSave = stateName;
        S.briefError = message || '';
        updateBriefSave();
    }
    function updateBriefSave() {
        var node = el.briefDrawer.querySelector('[data-bsave]');
        if (!node) return;
        var st = S.briefSave;
        node.textContent = st === 'saving' || st === 'dirty' ? 'Сохраняется…' : st === 'saved' ? 'Сохранено'
            : st === 'error' ? 'Не сохранено: ' + (S.briefError || 'ошибка') : '';
        node.className = 'gh-save' + (st === 'saving' || st === 'dirty' ? ' is-saving' : st === 'saved' ? ' is-saved'
            : st === 'error' ? ' is-error' : '');
        var status = el.briefDrawer.querySelector('[data-bstatus]');
        if (status) status.textContent = briefStatus();
    }

    function briefSaver(key) {
        if (!briefSavers[key]) briefSavers[key] = GH.debounce(function () { return briefSaveKey(key); }, AUTOSAVE_MS);
        return briefSavers[key];
    }
    function briefPending() {
        for (var k in briefSavers) {
            if (Object.prototype.hasOwnProperty.call(briefSavers, k) && briefSavers[k].pending()) return true;
        }
        return false;
    }
    function flushBrief() {
        var out = [];
        for (var k in briefSavers) {
            if (Object.prototype.hasOwnProperty.call(briefSavers, k) && briefSavers[k].pending()) {
                out.push(briefSavers[k].flush());
            }
        }
        return Promise.all(out);
    }

    function briefSaveKey(key) {
        if (!Object.prototype.hasOwnProperty.call(S.briefDirty, key)) return Promise.resolve(null);
        var value = S.briefDirty[key];
        S.briefSaving++;
        setBriefSave('saving');
        return GH.api('PUT', API + '/brief', briefBody(key, value), apiOpts()).then(function (res) {
            S.briefSaving--;
            if (S.briefDirty[key] === value) delete S.briefDirty[key];
            var d = S.brief && S.brief.data;
            if (d && res && res.brief) {
                d.brief = res.brief;
                d.stored = res.stored;
                d.total = res.total;
            }
            setBriefSave(S.briefSaving || briefPending() ? 'saving' : 'saved');
            return res;
        }, function (err) {
            S.briefSaving--;
            setBriefSave('error', err.message);
            if (err.status === 503) {
                GH.toast('Бриф недоступен: ' + err.message + '. Файл не перезаписывается — сообщите администратору.',
                    'danger');
            } else {
                GH.toast(err.message, 'danger');
            }
            return null;
        });
    }

    function onBriefInput(e) {
        var t = e.target;
        var key = t.getAttribute && t.getAttribute('data-bkey');
        if (!key || !S.brief || !S.brief.data) return;
        if (key === 'e') {
            var i = parseInt(t.getAttribute('data-ei'), 10);
            if (i >= 0 && i < S.brief.examples.length) S.brief.examples[i] = t.value;
            S.briefDirty.e = S.brief.examples.slice();
        } else {
            S.briefDirty[key] = t.value;
        }
        setBriefSave('dirty');
        briefSaver(key)();
        updateBriefCounter(t);
        updateBriefTotal();
        fitBriefArea(t);
    }

    function onBriefFocusOut(e) {
        var key = e.target && e.target.getAttribute && e.target.getAttribute('data-bkey');
        if (key && briefSavers[key] && briefSavers[key].pending()) briefSavers[key].flush();
    }

    function addExample() {
        var spec = null;
        each(briefSchema().sections, function (s) { if (s.type === 'list') spec = s; });
        if (!spec || S.brief.examples.length >= spec.max_items) return;
        S.brief.examples.push('');
        renderBrief();
        var areas = el.briefDrawer.querySelectorAll('[data-bkey="e"]');
        var last = areas[areas.length - 1];
        if (last) {
            try { last.focus({ preventScroll: false }); } catch (err) { /* фокус не критичен */ }
        }
    }

    function removeExample(i) {
        var text = S.brief.examples[i];
        var run = function () {
            S.brief.examples.splice(i, 1);
            S.briefDirty.e = S.brief.examples.slice();
            renderBrief();
            briefSaver('e')();
            briefSaver('e').flush();
        };
        if (!String(text || '').trim()) { run(); return; }
        GH.confirm({
            title: 'Убрать пример ' + (i + 1) + '?',
            text: 'Пример удалится из брифа, агент больше не будет брать его за образец.',
            ok: 'Убрать', danger: true
        }).then(function (ok) { if (ok) run(); });
    }

    function onBriefClick(e) {
        var act = closest(e.target, '[data-bact]');
        if (!act || act.disabled || !S.brief) return;
        var a = act.getAttribute('data-bact');
        if (a === 'retry') {
            S.brief = { loading: true };
            renderBrief();
            loadBrief();
        } else if (a === 'add-example' && S.brief.data) {
            addExample();
        } else if (a === 'del-example' && S.brief.data) {
            removeExample(parseInt(act.getAttribute('data-ei'), 10));
        }
    }

    // ==================== пауза ====================

    function menuItem(attr, value, label, hint, on) {
        return '<button type="button" class="gh-menu-item' + (on ? ' is-on' : '') + '" ' + attr + '="' + esc(value) + '">' +
            '<span>' + esc(label) + '</span>' + (hint ? '<span class="gh-menu-hint">' + esc(hint) + '</span>' : '') +
            '</button>';
    }

    function renderPauseMenu() {
        var html = '<div class="gh-menu-grab" aria-hidden="true"></div><div class="gh-menu-cap">Поставить на паузу</div>' +
            menuItem('data-pause', 'pause|all', 'Вся сеть', 'все бары и сеть');
        each(GH.BARS, function (b) { html += menuItem('data-pause', 'pause|' + b.key, b.name, b.short); });
        html += '<div class="gh-menu-sep"></div><div class="gh-menu-cap">Снять паузу</div>' +
            menuItem('data-pause', 'resume|all', 'Вся сеть', 'все бары и сеть');
        each(GH.BARS, function (b) { html += menuItem('data-pause', 'resume|' + b.key, b.name, b.short); });
        html += '<div class="gh-cp-menu-note">Касается утверждённых публикаций, время которых ещё впереди. Пауза одного ' +
            'бара не останавливает публикации на всю сеть (например, общий Instagram).</div>';
        el.pauseMenu.innerHTML = html;
    }

    function bulkPause(action, bar) {
        var scope = bar === 'all' ? 'всей сети' : 'бара «' + GH.barName(bar) + '»';
        var text;
        if (action === 'pause') {
            text = 'Утверждённые публикации ' + scope + ', время которых ещё впереди, встанут на паузу и не выйдут, ' +
                'пока паузу не снимут.' + (bar === 'all' ? '' : ' Публикации на всю сеть пауза одного бара не трогает.');
        } else {
            text = 'Публикации ' + scope + ' на паузе снова станут утверждёнными. Те, чьё время выхода уже прошло, ' +
                'останутся на паузе — их нужно перенести.';
        }
        GH.confirm({
            title: action === 'pause' ? 'Поставить на паузу: ' + (bar === 'all' ? 'вся сеть' : GH.barName(bar)) + '?'
                : 'Снять паузу: ' + (bar === 'all' ? 'вся сеть' : GH.barName(bar)) + '?',
            text: text,
            ok: action === 'pause' ? 'Поставить на паузу' : 'Снять паузу'
        }).then(function (ok) {
            if (!ok) return;
            GH.api('POST', API + '/bulk-pause', { bar: bar, action: action }).then(function (res) {
                var n = (res && res.changed) || 0;
                var skipped = (res && res.skipped) || [];
                GH.toast((action === 'pause' ? 'На паузу поставлено: ' : 'Пауза снята: ') +
                    nText(n, 'публикация', 'публикации', 'публикаций'), n ? 'success' : 'muted');
                if (skipped.length) {
                    GH.toast('Остались на паузе: ' + skipped.length + ' — время выхода прошло. ' +
                        (skipped[0].reason || ''), 'warning');
                }
                reload();
            }, reportError);
        });
    }

    // ==================== меню фильтров ====================

    function renderBarMenu() {
        var html = '<div class="gh-menu-grab" aria-hidden="true"></div><div class="gh-menu-cap">Бар</div>' +
            menuItem('data-bar', '', 'Все бары', 'вся сеть', S.bar === '');
        each(GH.BARS, function (b) { html += menuItem('data-bar', b.key, b.name, b.short, S.bar === b.key); });
        html += '<div class="gh-cp-menu-note">Показываются размещения бара и размещения на всю сеть. Фильтр общий ' +
            'для контент-плана и отзывов.</div>';
        el.barMenu.innerHTML = html;
    }
    function renderChMenu() {
        var hints = { telegram: 'канал каждого бара', instagram: 'аккаунт сети', bot: 'рассылка' };
        var html = '<div class="gh-menu-grab" aria-hidden="true"></div><div class="gh-menu-cap">Площадка</div>' +
            menuItem('data-ch', '', 'Все площадки', '', S.channel === '');
        each(CHANNEL_KEYS, function (k) { html += menuItem('data-ch', k, chName(k), hints[k], S.channel === k); });
        el.chMenu.innerHTML = html;
    }

    // ==================== месяц и вид ====================

    function switchMonth(mon) {
        if (!mon || !MONTH_RE.test(mon)) return;
        // Стрелки и кнопка месяца выводят из сквозного вида в месяц; фильтр
        // состояния остаётся — можно пройти по месяцам с тем же фильтром.
        if (S.scope) { leaveScope(mon, S.stateFilter); return; }
        if (mon === S.month) return;
        flushAll();
        S.month = mon;
        S.selected = {};
        S.calOpen = {};
        GH.setParams({ month: mon });
        renderChrome();
        load();
        if (S.reviewsOn) loadReviews();
    }

    function setView(v) {
        S.view = v === 'calendar' ? 'calendar' : 'table';
        GH.setParams({ view: S.view === 'table' ? null : S.view });
        // Календарь — сетка одного месяца: сквозной вид в нём не показать,
        // поэтому переход в календарь открывает текущий месяц с тем же фильтром.
        if (S.view === 'calendar' && S.scope) { leaveScope(S.month, S.stateFilter); return; }
        if (S.view === 'calendar' && S.reviewsOn) loadReviews();
        renderChrome();
        renderView();
        renderBulk();
    }

    // ==================== обработчики страницы ====================

    function onViewClick(e) {
        var t = e.target;
        var act = closest(t, '[data-act]');
        if (act && !el.drawer.contains(act)) {
            var a = act.getAttribute('data-act');
            if (a === 'add') { addMaterial(null); return; }
            if (a === 'copy') { openCopy(); return; }
            if (a === 'leave-scope') { leaveScope(S.month, ''); return; }
            if (a === 'origin-off') { setOrigin(''); return; }
            if (a === 'reset-filters') {
                S.bar = GH.setBar('');
                S.channel = '';
                S.origin = '';
                GH.setParams({ origin: null });
                renderOrigin();
                setStateFilter('');
                renderChrome();
                if (S.reviewsOn) loadReviews();
                return;
            }
        }
        var more = closest(t, '[data-cal-more]');
        if (more) {
            var day = more.getAttribute('data-cal-more');
            S.calOpen[day] = !S.calOpen[day];
            renderView();
            return;
        }
        var addDay = closest(t, '[data-add-day]');
        if (addDay) { addMaterial(addDay.getAttribute('data-add-day')); return; }
        var open = closest(t, '[data-open]');
        if (open) { openMaterial(open.getAttribute('data-open'), open.getAttribute('data-pid')); return; }
        if (closest(t, '.gh-cp-c-sel') || closest(t, 'input, label, button, a, .gh-cp-day-rv')) return;
        var row = closest(t, 'tr[data-mid]');
        if (row) { openMaterial(row.getAttribute('data-mid')); return; }
        var cell = closest(t, '.gh-cp-day.is-add');
        if (cell) addMaterial(cell.getAttribute('data-day'));
    }

    function onViewChange(e) {
        var t = e.target;
        if (t.hasAttribute('data-sel')) {
            var id = t.getAttribute('data-sel');
            if (t.checked) S.selected[id] = true;
            else delete S.selected[id];
            var row = closest(t, 'tr');
            if (row) row.classList.toggle('is-sel', t.checked);
            var head = el.table.querySelector('[data-selall]');
            if (head) {
                var list = tableMaterials();
                var n = 0;
                each(list, function (m) { if (S.selected[m.id]) n++; });
                head.checked = n > 0 && n === list.length;
                head.indeterminate = n > 0 && n < list.length;
            }
            renderBulk();
            return;
        }
        if (t.hasAttribute('data-selall')) {
            var on = t.checked;
            each(tableMaterials(), function (m) {
                if (on) S.selected[m.id] = true;
                else delete S.selected[m.id];
            });
            renderTable();
            renderBulk();
            return;
        }
        if (t.getAttribute('data-cal') === 'reviews') {
            S.reviewsOn = t.checked;
            if (S.reviewsOn) loadReviews();
            renderView();
        }
    }

    function bind() {
        el.prev.addEventListener('click', function () { switchMonth(GH.addMonths(S.month, -1)); });
        el.next.addEventListener('click', function () { switchMonth(GH.addMonths(S.month, 1)); });
        el.monthBtn.addEventListener('click', function () { switchMonth(GH.mskNow().month); });

        el.barBtn.addEventListener('click', function () { renderBarMenu(); GH.toggleMenu(el.barMenu, el.barBtn); });
        el.barMenu.addEventListener('click', function (e) {
            var item = closest(e.target, '[data-bar]');
            if (!item) return;
            S.bar = GH.setBar(item.getAttribute('data-bar'));
            renderChrome();
            renderView();
            if (S.reviewsOn) loadReviews();
        });
        el.chBtn.addEventListener('click', function () { renderChMenu(); GH.toggleMenu(el.chMenu, el.chBtn); });
        el.chMenu.addEventListener('click', function (e) {
            var item = closest(e.target, '[data-ch]');
            if (!item) return;
            S.channel = item.getAttribute('data-ch');
            renderChrome();
            renderView();
        });
        GH.bindSeg(el.viewSeg, setView);

        el.approveBtn.addEventListener('click', openApprove);
        el.addBtn.addEventListener('click', function () { addMaterial(null); });
        el.copyBtn.addEventListener('click', openCopy);
        el.briefBtn.addEventListener('click', openBrief);
        el.originBtn.addEventListener('click', function () { setOrigin(S.origin ? '' : ORIGIN_AGENT); });
        el.agentDel.addEventListener('click', deleteAgentDrafts);
        el.briefDrawer.addEventListener('input', onBriefInput);
        el.briefDrawer.addEventListener('click', onBriefClick);
        el.briefDrawer.addEventListener('focusout', onBriefFocusOut);
        el.pauseBtn.addEventListener('click', function () { renderPauseMenu(); GH.toggleMenu(el.pauseMenu, el.pauseBtn); });
        el.pauseMenu.addEventListener('click', function (e) {
            var item = closest(e.target, '[data-pause]');
            if (!item) return;
            var parts = item.getAttribute('data-pause').split('|');
            bulkPause(parts[0], parts[1]);
        });
        el.retry.addEventListener('click', function () { load(); });

        el.sum.addEventListener('click', function (e) {
            var item = closest(e.target, '[data-state]');
            if (!item) return;
            var key = item.getAttribute('data-state');
            // В сквозном виде любой выбор возвращает план текущего месяца —
            // с выбранным фильтром или без него (setStateFilter -> leaveScope).
            setStateFilter(S.stateFilter === key ? '' : key);
        });
        el.stateBar.addEventListener('click', function (e) {
            // В сквозном виде крестик возвращает план текущего месяца
            // (setStateFilter -> leaveScope).
            if (closest(e.target, '[data-act="clear-state"]')) setStateFilter('');
        });

        el.table.addEventListener('click', onViewClick);
        el.cal.addEventListener('click', onViewClick);
        el.table.addEventListener('change', onViewChange);
        el.cal.addEventListener('change', onViewChange);

        el.bulk.addEventListener('click', function (e) {
            var b = closest(e.target, '[data-bulk]');
            if (b) bulkAction(b.getAttribute('data-bulk'));
        });

        el.drawer.addEventListener('click', onDrawerClick);
        el.drawer.addEventListener('input', onDrawerInput);
        el.drawer.addEventListener('change', onDrawerChange);
        el.drawer.addEventListener('focusout', onDrawerFocusOut);
        el.drawer.addEventListener('keydown', onDrawerKey);
        // Нажатие на подстановку не должно уводить фокус из шаблона.
        el.drawer.addEventListener('mousedown', function (e) {
            if (closest(e.target, '[data-act="token"]')) e.preventDefault();
        });
        bindDrop();
        el.file.accept = MEDIA_ACCEPT;
        el.file.addEventListener('change', onFilePicked);

        el.approveBody.addEventListener('change', function (e) {
            var t = e.target;
            var pid = t.getAttribute && t.getAttribute('data-bot');
            if (!pid || !S.approve) return;
            if (t.checked) S.approve.bots[pid] = true;
            else delete S.approve.bots[pid];
            updateApproveBtn();
        });
        el.approveGo.addEventListener('click', submitApprove);
        el.approveModal.addEventListener('gh:close', function () { S.approve = null; });

        el.copyBody.addEventListener('change', function (e) {
            if (e.target.getAttribute && e.target.getAttribute('data-copy') === 'content' && S.copy) {
                S.copy.content = e.target.checked;
            }
        });
        el.copyGo.addEventListener('click', submitCopy);

        // Уход со страницы с несохранённым: отправить сразу и с keepalive —
        // обычный fetch браузер обрывает вместе со страницей. flushAll шлёт
        // запросы синхронно, поэтому флаг S.keepalive действует ровно на них.
        // Вкладка ушла в фон (на телефоне её могут выгрузить без pagehide) —
        // сохраняются тексты; набор даты не трогаем: человек может вернуться
        // и дописать.
        window.addEventListener('pagehide', function () {
            S.keepalive = true;
            try { flushAll(); } finally { S.keepalive = false; }
        });
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState !== 'hidden') return;
            S.keepalive = true;
            try { flushSavers(); } finally { S.keepalive = false; }
        });
    }

    function init() {
        el = {
            prev: byId('cpPrev'),
            next: byId('cpNext'),
            monthBtn: byId('cpMonthBtn'),
            monthLabel: byId('cpMonthLabel'),
            barBtn: byId('cpBarBtn'),
            barLabel: byId('cpBarLabel'),
            barMenu: byId('cpBarMenu'),
            chBtn: byId('cpChBtn'),
            chLabel: byId('cpChLabel'),
            chMenu: byId('cpChMenu'),
            viewSeg: byId('cpViewSeg'),
            approveBtn: byId('cpApproveBtn'),
            addBtn: byId('cpAddBtn'),
            delivery: byId('cpDelivery'),
            err: byId('cpErr'),
            errText: byId('cpErrText'),
            retry: byId('cpRetry'),
            sum: byId('cpSum'),
            copyBtn: byId('cpCopyBtn'),
            pauseBtn: byId('cpPauseBtn'),
            pauseMenu: byId('cpPauseMenu'),
            stateBar: byId('cpStateBar'),
            msg: byId('cpMsg'),
            table: byId('cpTable'),
            cal: byId('cpCal'),
            bulk: byId('cpBulk'),
            bulkN: byId('cpBulkN'),
            drawer: byId('cpDrawer'),
            approveModal: byId('cpApproveModal'),
            approveBody: byId('cpApproveBody'),
            approveGo: byId('cpApproveGo'),
            copyModal: byId('cpCopyModal'),
            copyBody: byId('cpCopyBody'),
            copyGo: byId('cpCopyGo'),
            file: byId('cpFile'),
            origin: byId('cpOrigin'),
            originBtn: byId('cpOriginBtn'),
            originN: byId('cpOriginN'),
            agentDel: byId('cpAgentDelBtn'),
            briefBtn: byId('cpBriefBtn'),
            briefDrawer: byId('cpBriefDrawer')
        };
        if (!GH) {
            if (el.msg) {
                el.msg.textContent = 'Не загрузился общий модуль раздела (common.js). Обновите страницу.';
                el.msg.classList.add('is-err');
            }
            return;
        }
        var params = GH.params();
        var mon = params.get('month');
        var monthGiven = MONTH_RE.test(mon || '');
        S.month = monthGiven ? mon : GH.mskNow().month;
        S.view = params.get('view') === 'calendar' ? 'calendar' : 'table';
        var st = params.get('state');
        S.stateFilter = STATE_FILTERS.indexOf(st) >= 0 ? st : '';
        // Сквозной вид — ?state=overdue|failed без ?month= (ссылки полосы
        // «Требует внимания»). С календарём не сочетается: календарь — сетка
        // одного месяца, там остаётся обычный фильтр состояния.
        S.scope = !monthGiven && SCOPE_STATES.indexOf(S.stateFilter) >= 0 && S.view === 'table' ? 'state' : '';
        S.origin = params.get('origin') === ORIGIN_AGENT ? ORIGIN_AGENT : '';
        S.bar = GH.getBar();
        S.pendingOpen = params.get('open') || null;
        // ?brief=1 — открыть бриф для агента (ссылка «откройте бриф»); если в
        // адресе есть и ?open=, главнее карточка материала.
        var wantBrief = params.get('brief') === '1';
        bind();
        renderChrome();
        load().then(function (ok) {
            if (ok && S.pendingOpen) {
                var id = S.pendingOpen;
                S.pendingOpen = null;
                openMaterial(id);
                return;
            }
            if (wantBrief) openBrief();
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();

    // Для отладки в консоли и проверок (tests/test_content_plan_render.mjs
    // исполняет файл в vm и вызывает чистые правила отсюда).
    window.__contentPlan = {
        state: S, load: load, openMaterial: openMaterial, setView: setView,
        openApprove: openApprove, openCopy: openCopy, charLen: charLen, parseDays: parseDays,
        dayStats: dayStats, dtValue: dtValue, dtChange: dtChange, dtCommit: dtCommit,
        stateCls: stateCls, stateLabel: stateLabel, placementFiles: placementFiles, listUrl: listUrl,
        inTable: inTable, normTitle: normTitle, copyRules: copyRules,
        materialVisible: materialVisible, agentStats: agentStats, aiMark: aiMark, briefBody: briefBody,
        deleteAgentDrafts: deleteAgentDrafts, openBrief: openBrief
    };
})();
