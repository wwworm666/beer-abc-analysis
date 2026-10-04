/* Страница /taps/<bar>: краны бара, подключение, замена и снятие кег, уточнение сорта.

   API — routes/taps.py, документация — docs/taps.md. Данные в DOM попадают только
   через textContent (без innerHTML).

   Каждое действие отправляет expected — состояние крана, которое видел бармен
   (status, current_beer, started_at). Если кран за это время изменили (второй
   бармен, вторая вкладка, двойное нажатие), сервер отвечает 409 и ничего не пишет. */
(function () {
    'use strict';

    const root = document.getElementById('tp');
    const BAR = { id: root.dataset.bar, name: root.dataset.barName, taps: Number(root.dataset.taps) };
    const REFRESH_MS = 30000;
    const HISTORY_STEP = 30;
    const RESULTS_LIMIT = 30;

    const state = {
        taps: [],
        stats: null,
        events: [],
        historyShown: HISTORY_STEP,
        beers: null,
        filter: 'all',
        query: '',
        sheet: null,
        busy: false,
    };

    const $ = (id) => document.getElementById(id);

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function svg(paths) {
        const ns = 'http://www.w3.org/2000/svg';
        const node = document.createElementNS(ns, 'svg');
        node.setAttribute('viewBox', '0 0 24 24');
        node.setAttribute('aria-hidden', 'true');
        for (const d of paths) {
            const path = document.createElementNS(ns, 'path');
            path.setAttribute('d', d);
            node.appendChild(path);
        }
        return node;
    }

    const norm = (value) => String(value || '').toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();

    async function getJson(url, options) {
        const response = await fetch(url, Object.assign({ cache: 'no-store', headers: { Accept: 'application/json' } }, options || {}));
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        return { ok: response.ok, status: response.status, data };
    }

    function postJson(url, body) {
        return getJson(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(body || {}),
        });
    }

    // ---------- уведомление ----------

    let toastTimer = null;
    function toast(text, bad) {
        const node = $('tp-toast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { node.hidden = true; }, bad ? 8000 : 4000);
    }

    // ---------- как показывать кран ----------

    function info(tap) {
        const beer = tap.beer_info || {};
        const verified = beer.mapping_status === 'verified';
        const facts = [];
        if (verified) {
            if (beer.style) facts.push(beer.style);
            if (beer.abv !== null && beer.abv !== undefined && beer.abv !== '') facts.push(String(beer.abv).replace('.', ',') + '%');
            if (beer.ibu !== null && beer.ibu !== undefined && beer.ibu !== '') facts.push(beer.ibu + ' IBU');
        }
        const article = tap.current_keg_id && !/^AUTO-/.test(tap.current_keg_id) ? tap.current_keg_id : '';
        return {
            active: tap.status === 'active' && Boolean(tap.current_beer),
            verified,
            // кега из iiko выбрана, но карточки Untappd у неё ещё нет — это не дело бармена:
            // связь предлагает ИИ-агент, подтверждает администратор (/taps/untappd)
            noCard: beer.mapping_status === 'unverified',
            title: verified ? beer.beer_name : (tap.current_beer || ''),
            brewery: verified ? (beer.brewery || '') : '',
            facts: facts.join(' · '),
            keg: tap.current_beer || '',
            article,
        };
    }

    function needsIdentity(tap) {
        const view = info(tap);
        return view.active && !view.verified;
    }

    function since(iso) {
        if (!iso) return '';
        const start = new Date(iso);
        if (Number.isNaN(start.getTime())) return '';
        const days = Math.floor((Date.now() - start.getTime()) / 86400000);
        if (days <= 0) return 'сегодня';
        if (days === 1) return '1 день';
        const mod10 = days % 10;
        const mod100 = days % 100;
        const word = mod10 === 1 && mod100 !== 11 ? 'день'
            : (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'дня' : 'дней');
        return days + ' ' + word;
    }

    function dateText(iso) {
        const moment = new Date(iso);
        if (Number.isNaN(moment.getTime())) return '';
        return moment.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', ' в');
    }

    function expectedOf(tap) {
        return { status: tap.status, current_beer: tap.current_beer || null, started_at: tap.started_at || null };
    }

    // ---------- загрузка ----------

    function tapByNumber(number) {
        return state.taps.find((tap) => tap.tap_number === number)
            || { tap_number: number, status: 'empty', current_beer: null, current_keg_id: null, started_at: null };
    }

    async function loadTaps() {
        const result = await getJson('/api/taps/' + encodeURIComponent(BAR.id));
        if (!result.ok || !Array.isArray(result.data.taps)) {
            $('tp-error').textContent = result.data.error || 'Не удалось загрузить краны. Проверьте связь и обновите страницу.';
            $('tp-error').hidden = false;
            return false;
        }
        $('tp-error').hidden = true;
        state.taps = result.data.taps;
        renderStrip();
        renderChips();
        renderGrid();
        return true;
    }

    async function loadStats() {
        const result = await getJson('/api/taps/' + encodeURIComponent(BAR.id) + '/stats');
        state.stats = result.ok ? result.data : null;
        renderStrip();
    }

    async function loadHistory() {
        const result = await getJson('/api/taps/events/all?bar_id=' + encodeURIComponent(BAR.id) + '&limit=300');
        if (!result.ok) return;
        state.events = pairEvents(result.data.events || []);
        renderHistory();
    }

    async function loadBeers(force) {
        if (state.beers && !force) return state.beers;
        const result = await getJson('/api/beers/draft');
        if (!result.ok || !Array.isArray(result.data.beers)) throw new Error(result.data.error || 'Не удалось загрузить список кег');
        state.beers = result.data.beers.map((beer) => Object.assign({}, beer, {
            haystack: norm([beer.name, beer.beer_name, beer.brewery, beer.num].filter(Boolean).join(' ')),
        }));
        return state.beers;
    }

    async function refreshAll() {
        const ok = await loadTaps();
        if (ok) {
            loadStats();
            loadHistory();
        }
    }

    // ---------- сводка и фильтры ----------

    function counts() {
        const all = [];
        for (let number = 1; number <= BAR.taps; number++) all.push(tapByNumber(number));
        const active = all.filter((tap) => info(tap).active);
        return {
            all: all.length,
            active: active.length,
            empty: all.length - active.length,
            unverified: active.filter((tap) => !info(tap).verified).length,
        };
    }

    function renderStrip() {
        const box = $('tp-strip');
        box.textContent = '';
        const c = counts();
        const cell = (value, label, extra, options) => {
            const node = el(options && options.onClick ? 'button' : 'div', 'tp-stat' + (options && options.warn ? ' is-warn' : ''));
            if (options && options.onClick) {
                node.type = 'button';
                node.addEventListener('click', options.onClick);
            }
            if (options && options.title) node.title = options.title;
            const number = el('b', null, String(value));
            if (extra) number.appendChild(el('small', null, ' ' + extra));
            node.appendChild(number);
            node.appendChild(el('span', null, label));
            box.appendChild(node);
        };
        cell(c.active, 'Активных кранов', 'из ' + c.all);
        cell(c.empty, 'Пустых', null, c.empty ? { onClick: () => setFilter('empty'), title: 'Показать пустые краны' } : null);
        cell(c.unverified, 'Без карточки Untappd', null, c.unverified ? {
            warn: true, onClick: () => setFilter('unverified'),
            title: 'Краны без проверенной карточки Untappd: в таплисте без ссылки и стиля, в фид Яндекса не попадают',
        } : null);
        const activity = state.stats && typeof state.stats.activity_7d === 'number' ? state.stats.activity_7d.toFixed(1).replace('.', ',') + '%' : '—';
        cell(activity, 'Активность за 7 дней', null, {
            title: 'Доля кран-дней с подключённой кегой за последние 7 дней, включая сегодня: '
                + 'сумма активных дней всех кранов / (кранов × 7) × 100',
        });
    }

    const FILTERS = [
        { key: 'all', label: 'Все' },
        { key: 'active', label: 'Активные' },
        { key: 'empty', label: 'Пустые' },
        { key: 'unverified', label: 'Без карточки Untappd', warn: true },
    ];

    function matchesFilter(tap, filter) {
        const view = info(tap);
        if (filter === 'active') return view.active;
        if (filter === 'empty') return !view.active;
        if (filter === 'unverified') return view.active && !view.verified;
        return true;
    }

    function setFilter(key) {
        state.filter = key;
        renderChips();
        renderGrid();
    }

    function renderChips() {
        const box = $('tp-chips');
        box.textContent = '';
        for (const filter of FILTERS) {
            let size = 0;
            for (let number = 1; number <= BAR.taps; number++) if (matchesFilter(tapByNumber(number), filter.key)) size += 1;
            if (filter.key === 'unverified' && !size && state.filter !== 'unverified') continue;
            const chip = el('button', 'tp-chip' + (filter.warn ? ' is-warn' : ''));
            chip.type = 'button';
            chip.setAttribute('aria-pressed', String(state.filter === filter.key));
            chip.appendChild(document.createTextNode(filter.label));
            chip.appendChild(el('span', 'tp-num', String(size)));
            chip.addEventListener('click', () => setFilter(filter.key));
            box.appendChild(chip);
        }
    }

    // ---------- сетка кранов ----------

    function renderGrid() {
        const grid = $('tp-grid');
        grid.textContent = '';
        const query = norm(state.query);
        let shown = 0;
        for (let number = 1; number <= BAR.taps; number++) {
            const tap = tapByNumber(number);
            if (!matchesFilter(tap, state.filter)) continue;
            const view = info(tap);
            if (query) {
                const text = norm([number, view.title, view.brewery, view.keg, view.article].join(' '));
                if (!query.split(' ').every((part) => text.includes(part))) continue;
            }
            grid.appendChild(card(tap, view));
            shown += 1;
        }
        if (!shown) grid.appendChild(el('div', 'tp-empty-list', 'Нет кранов по этому условию.'));
    }

    function card(tap, view) {
        const node = el('button', 'tp-card' + (view.active ? '' : ' is-empty') + (view.active && !view.verified ? ' is-warn' : ''));
        node.type = 'button';
        const head = el('span', 'tp-card-head');
        head.appendChild(el('span', 'tp-tapno', String(tap.tap_number)));
        head.appendChild(el('span', 'tp-when', view.active ? since(tap.started_at) : 'свободен'));
        node.appendChild(head);
        if (view.active) {
            node.appendChild(el('span', 'tp-card-title', view.title));
            const sub = [view.brewery, view.facts].filter(Boolean).join(' · ');
            if (sub) node.appendChild(el('span', 'tp-card-sub', sub));
            if (!view.verified) node.appendChild(el('span', 'tp-badge is-warn', view.noCard ? 'Нет карточки Untappd' : 'Уточните сорт'));
            if (view.verified) node.appendChild(el('span', 'tp-card-keg', view.keg));
            node.setAttribute('aria-label', `Кран ${tap.tap_number}: ${view.title}`);
        } else {
            node.appendChild(el('span', 'tp-card-title', 'Пусто'));
            node.appendChild(el('span', 'tp-card-sub', 'Нажмите, чтобы подключить кегу'));
            node.setAttribute('aria-label', `Кран ${tap.tap_number}: пусто, подключить кегу`);
        }
        node.addEventListener('click', () => openSheet(tap.tap_number, view.active ? 'view' : 'start'));
        return node;
    }

    // ---------- история ----------

    // Замена пишет два события с одним временем: «остановлено X» и «замена на Y».
    // Для экрана это одна строка «X → Y». В старых событиях замены (до 2026-09-27)
    // нет old_beer — берём его из парного «остановлено».
    function pairEvents(events) {
        const list = events.slice().sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
        const used = new Set();
        const result = [];
        list.forEach((event, index) => {
            if (used.has(index)) return;
            if (event.action === 'replace') {
                const time = Date.parse(event.timestamp);
                const pairIndex = list.findIndex((other, otherIndex) => !used.has(otherIndex) && otherIndex !== index
                    && other.action === 'stop' && other.tap_number === event.tap_number
                    && Math.abs(Date.parse(other.timestamp) - time) < 5000);
                const copy = Object.assign({}, event);
                if (pairIndex >= 0) {
                    used.add(pairIndex);
                    if (!copy.old_beer) copy.old_beer = list[pairIndex].beer_name;
                }
                result.push(copy);
            } else {
                result.push(event);
            }
            used.add(index);
        });
        return result;
    }

    function dayTitle(iso) {
        const moment = new Date(iso);
        const today = new Date();
        const key = (value) => value.toDateString();
        const yesterday = new Date(today.getTime() - 86400000);
        if (key(moment) === key(today)) return 'Сегодня';
        if (key(moment) === key(yesterday)) return 'Вчера';
        return moment.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    }

    function renderHistory() {
        const box = $('tp-history');
        box.textContent = '';
        const events = state.events;
        $('tp-history-count').textContent = events.length ? 'последние ' + Math.min(events.length, state.historyShown) + ' из ' + events.length : '';
        if (!events.length) {
            box.appendChild(el('div', 'tp-empty-list', 'Пока нет событий. Здесь появятся подключения, замены и снятия кег.'));
            $('tp-history-more').hidden = true;
            return;
        }
        let day = null;
        for (const event of events.slice(0, state.historyShown)) {
            const title = dayTitle(event.timestamp);
            if (title !== day) {
                day = title;
                box.appendChild(el('div', 'tp-day', title));
            }
            const row = el('div', 'tp-event');
            const moment = new Date(event.timestamp);
            row.appendChild(el('span', 'tp-event-time', moment.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })));
            row.appendChild(el('span', 'tp-event-tap', 'Кран ' + event.tap_number));
            const text = el('span', 'tp-event-text');
            text.appendChild(el('span', 'tp-event-kind is-' + event.action));
            if (event.action === 'start') {
                text.appendChild(document.createTextNode('Подключена '));
                text.appendChild(el('b', null, event.beer_name || ''));
            } else if (event.action === 'stop') {
                text.appendChild(document.createTextNode('Закончилась '));
                text.appendChild(el('b', null, event.beer_name || ''));
            } else {
                text.appendChild(document.createTextNode('Замена: '));
                text.appendChild(el('b', null, event.old_beer || 'прежняя кега'));
                text.appendChild(document.createTextNode(' на '));
                text.appendChild(el('b', null, event.beer_name || ''));
            }
            row.appendChild(text);
            box.appendChild(row);
        }
        $('tp-history-more').hidden = events.length <= state.historyShown;
    }

    // ---------- окно крана ----------

    function openSheet(number, mode) {
        state.sheet = { number, mode, selected: null, query: '' };
        $('tp-sheet-wrap').hidden = false;
        document.documentElement.classList.add('tp-lock');
        renderSheet();
    }

    function closeSheet() {
        if (state.busy) return;
        state.sheet = null;
        $('tp-sheet-wrap').hidden = true;
        document.documentElement.classList.remove('tp-lock');
    }

    function setMode(mode) {
        state.sheet.mode = mode;
        state.sheet.selected = null;
        state.sheet.query = '';
        renderSheet();
    }

    function renderSheet() {
        const sheet = state.sheet;
        if (!sheet) return;
        const tap = tapByNumber(sheet.number);
        const view = info(tap);
        $('tp-sheet-title').textContent = 'Кран ' + tap.tap_number;
        $('tp-sheet-status').textContent = view.active ? 'подключён ' + (tap.started_at ? dateText(tap.started_at) : '') : 'пустой';
        const body = $('tp-sheet-body');
        body.textContent = '';
        if (sheet.mode === 'view') renderView(body, tap, view);
        else if (sheet.mode === 'confirm-stop') renderConfirmStop(body, tap, view);
        else renderPicker(body, tap, view);
    }

    function beerBlock(view) {
        const block = el('div', 'tp-beer');
        block.appendChild(el('div', 'tp-beer-title', view.title));
        const sub = [view.brewery, view.facts].filter(Boolean).join(' · ');
        if (sub) block.appendChild(el('div', 'tp-beer-sub', sub));
        block.appendChild(el('div', 'tp-beer-keg', [view.keg, view.article ? 'артикул ' + view.article : ''].filter(Boolean).join(' · ')));
        return block;
    }

    function button(label, className, onClick, icon) {
        const node = el('button', 'tp-btn ' + (className || ''));
        node.type = 'button';
        if (icon) node.appendChild(svg(icon));
        node.appendChild(document.createTextNode(label));
        node.addEventListener('click', onClick);
        return node;
    }

    function renderView(body, tap, view) {
        body.appendChild(beerBlock(view));
        if (view.noCard) {
            const note = el('div', 'tp-note is-warn',
                'У этой кеги ещё нет проверенной карточки Untappd: в таплисте она без ссылки и стиля, '
                + 'а «Таплист пятницы» бара не уйдёт. Карточку подбирает ИИ-агент, подтверждает администратор — ');
            const more = el('a', null, 'Связи с Untappd');
            more.href = '/taps/untappd';
            note.appendChild(more);
            note.appendChild(document.createTextNode('.'));
            body.appendChild(note);
        } else if (!view.verified) {
            body.appendChild(el('div', 'tp-note is-warn',
                'Сорт не сопоставлен с проверенной карточкой: этого пива нет в таплисте и в фиде Яндекса. '
                + 'Выберите точную кегу из iiko — время подключения сохранится.'));
        }
        const needsKeg = !view.verified && !view.noCard;
        const actions = el('div', 'tp-actions');
        if (needsKeg) actions.appendChild(button('Уточнить сорт', 'tp-btn-primary tp-btn-block', () => setMode('identify')));
        actions.appendChild(button('Заменить кегу', (view.verified ? 'tp-btn-primary ' : '') + 'tp-btn-block', () => setMode('replace')));
        actions.appendChild(button('Кега закончилась', 'tp-btn-danger tp-btn-block', () => setMode('confirm-stop')));
        body.appendChild(actions);
        if (!needsKeg) {
            const fix = el('button', 'tp-link-btn', 'Сорт указан неверно? Уточнить без замены кеги');
            fix.type = 'button';
            fix.addEventListener('click', () => setMode('identify'));
            body.appendChild(fix);
        }
    }

    function renderConfirmStop(body, tap, view) {
        body.appendChild(el('p', 'tp-question', `Кега «${view.title}» на кране ${tap.tap_number} закончилась? Кран станет пустым.`));
        const row = el('div', 'tp-actions-row');
        row.appendChild(button('Отмена', '', () => setMode('view')));
        const confirm = button('Да, закончилась', 'tp-btn-danger-solid', () => submitStop(tap, confirm));
        row.appendChild(confirm);
        body.appendChild(row);
    }

    const PICKER_TEXT = {
        start: { question: 'Какую кегу подключаете?', submit: 'Подключить' },
        replace: { question: 'На какую кегу меняете?', submit: 'Заменить' },
        identify: { question: 'Какой сорт сейчас на кране? Кега не меняется, время подключения сохранится.', submit: 'Сохранить сорт' },
    };

    function renderPicker(body, tap, view) {
        const sheet = state.sheet;
        const text = PICKER_TEXT[sheet.mode];
        if (view.active) {
            const back = el('button', 'tp-link-btn tp-back', 'Назад');
            back.type = 'button';
            back.addEventListener('click', () => setMode('view'));
            body.appendChild(back);
            if (sheet.mode === 'replace') body.appendChild(el('div', 'tp-hint', 'Сейчас: ' + view.title));
        }
        body.appendChild(el('p', 'tp-question', text.question));

        const search = el('label', 'tp-search');
        search.appendChild(svg(['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'm20 20-3.5-3.5']));
        const input = el('input');
        input.type = 'search';
        input.placeholder = 'Название, пивоварня или артикул';
        input.autocomplete = 'off';
        input.setAttribute('aria-label', 'Найти кегу');
        input.value = sheet.query;
        search.appendChild(input);
        body.appendChild(search);

        const results = el('div', 'tp-results');
        results.setAttribute('role', 'listbox');
        body.appendChild(results);

        const submit = button(text.submit, 'tp-btn-primary tp-btn-block', () => submitPicked(tap, submit));
        submit.disabled = !sheet.selected;
        body.appendChild(submit);

        const hint = el('div', 'tp-hint');
        hint.appendChild(document.createTextNode('Нет нужной кеги? '));
        const refresh = el('button', 'tp-link-btn', 'Обновить список кег из iiko');
        refresh.type = 'button';
        refresh.addEventListener('click', () => refreshKegs(true));
        hint.appendChild(refresh);
        body.appendChild(hint);

        const draw = () => {
            results.textContent = '';
            if (!state.beers) {
                results.appendChild(el('div', 'tp-hint', 'Загружаю список кег…'));
                return;
            }
            const query = norm(input.value);
            if (!query) {
                results.appendChild(el('div', 'tp-hint', 'Начните вводить название — по-русски, как в iiko, или как на этикетке.'));
                return;
            }
            const parts = query.replace(/^кег\s+/, '').split(' ');
            const found = state.beers.filter((beer) => parts.every((part) => beer.haystack.includes(part)));
            found.sort((a, b) => (b.mapped - a.mapped) || a.name.localeCompare(b.name, 'ru'));
            if (!found.length) {
                results.appendChild(el('div', 'tp-hint', 'Ничего не найдено. Проверьте название или обновите список кег из iiko.'));
                return;
            }
            for (const beer of found.slice(0, RESULTS_LIMIT)) {
                const item = el('button', 'tp-result');
                item.type = 'button';
                item.setAttribute('role', 'option');
                item.setAttribute('aria-selected', String(Boolean(sheet.selected && sheet.selected.id === beer.id)));
                const title = beer.mapped && beer.beer_name ? [beer.brewery, beer.beer_name].filter(Boolean).join(' — ') : beer.name;
                item.appendChild(el('span', 'tp-result-title', title));
                const sub = el('span', 'tp-result-sub', [beer.mapped ? beer.name : '', beer.num ? 'артикул ' + beer.num : ''].filter(Boolean).join(' · '));
                if (!beer.mapped) {
                    if (sub.textContent) sub.appendChild(document.createTextNode(' · '));
                    sub.appendChild(el('em', null, 'нет карточки сорта — в таплист не попадёт'));
                }
                item.appendChild(sub);
                item.addEventListener('click', () => {
                    sheet.selected = beer;
                    submit.disabled = false;
                    submit.lastChild.textContent = text.submit + ': ' + (beer.mapped && beer.beer_name ? beer.beer_name : beer.name);
                    for (const other of results.querySelectorAll('.tp-result')) other.setAttribute('aria-selected', String(other === item));
                });
                results.appendChild(item);
            }
            if (found.length > RESULTS_LIMIT) results.appendChild(el('div', 'tp-hint', `Показаны первые ${RESULTS_LIMIT} из ${found.length}. Уточните запрос.`));
        };
        input.addEventListener('input', () => {
            sheet.query = input.value;
            sheet.selected = null;
            submit.disabled = true;
            submit.lastChild.textContent = text.submit;
            draw();
        });
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                const first = results.querySelector('.tp-result');
                if (first && results.querySelectorAll('.tp-result').length === 1) first.click();
                else if (sheet.selected) submit.click();
            }
        });
        draw();
        if (!state.beers) {
            loadBeers().then(draw).catch((error) => {
                results.textContent = '';
                results.appendChild(el('div', 'tp-note is-bad', error.message));
            });
        }
        setTimeout(() => input.focus(), 50);
    }

    // ---------- действия ----------

    async function act(buttonNode, run) {
        if (state.busy) return;
        state.busy = true;
        if (buttonNode) {
            buttonNode.disabled = true;
            buttonNode.classList.add('is-busy');
        }
        try {
            await run();
        } finally {
            state.busy = false;
            if (buttonNode && buttonNode.isConnected) {
                buttonNode.disabled = false;
                buttonNode.classList.remove('is-busy');
            }
        }
    }

    async function handleResult(result, successText) {
        if (result.ok) {
            closeSheetAfterAction();
            toast(successText);
            await refreshAll();
            return;
        }
        if (result.status === 409) {
            toast(result.data.error || 'Кран уже изменили. Данные обновлены.', true);
            await loadTaps();
            loadHistory();
            if (state.sheet) setMode(info(tapByNumber(state.sheet.number)).active ? 'view' : 'start');
            return;
        }
        toast(result.data.error || 'Не получилось. Проверьте связь и повторите.', true);
    }

    function closeSheetAfterAction() {
        state.sheet = null;
        $('tp-sheet-wrap').hidden = true;
        document.documentElement.classList.remove('tp-lock');
    }

    function submitPicked(tap, buttonNode) {
        const sheet = state.sheet;
        const beer = sheet && sheet.selected;
        if (!beer) return;
        const label = beer.mapped && beer.beer_name ? beer.beer_name : beer.name;
        if (sheet.mode === 'identify') {
            act(buttonNode, async () => {
                const expected = {};
                for (const key of ['current_beer', 'current_keg_id', 'started_at', 'iiko_product_id']) expected[key] = tap[key] === undefined ? null : tap[key];
                const result = await postJson(`/api/taps/${encodeURIComponent(BAR.id)}/identify`, {
                    tap_number: tap.tap_number, iiko_product_id: beer.id, expected,
                });
                await handleResult(result, `Кран ${tap.tap_number}: сорт уточнён — ${label}`);
            });
            return;
        }
        const path = sheet.mode === 'start' ? 'start' : 'replace';
        act(buttonNode, async () => {
            const result = await postJson(`/api/taps/${encodeURIComponent(BAR.id)}/${path}`, {
                tap_number: tap.tap_number,
                beer_name: beer.name,
                keg_id: beer.num || '',
                iiko_product_id: beer.id,
                expected: expectedOf(tap),
            });
            await handleResult(result, path === 'start'
                ? `Кран ${tap.tap_number}: подключена ${label}`
                : `Кран ${tap.tap_number}: заменена на ${label}`);
        });
    }

    function submitStop(tap, buttonNode) {
        act(buttonNode, async () => {
            const result = await postJson(`/api/taps/${encodeURIComponent(BAR.id)}/stop`, {
                tap_number: tap.tap_number, expected: expectedOf(tap),
            });
            await handleResult(result, `Кран ${tap.tap_number} пустой`);
        });
    }

    async function refreshKegs(fromSheet) {
        const topButton = $('tp-refresh-kegs');
        topButton.disabled = true;
        topButton.classList.add('is-busy');
        toast('Забираю список кег из iiko…');
        try {
            const result = await postJson('/api/update-nomenclature', {});
            if (!result.ok) throw new Error(result.data.error || 'iiko не ответил');
            await loadBeers(true);
            toast('Список кег обновлён');
            if (fromSheet && state.sheet) renderSheet();
        } catch (error) {
            toast('Не удалось обновить список кег: ' + error.message, true);
        } finally {
            topButton.disabled = false;
            topButton.classList.remove('is-busy');
        }
    }

    async function downloadCsv() {
        const node = $('tp-csv');
        node.disabled = true;
        node.classList.add('is-busy');
        try {
            const response = await fetch(`/api/taps/export-taplist-full?bar_id=${encodeURIComponent(BAR.id)}`, { cache: 'no-store' });
            if (!response.ok) {
                let message = 'Не удалось получить таплист';
                try { message = (await response.json()).error || message; } catch (error) { /* не JSON */ }
                throw new Error(message);
            }
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement('a');
            link.href = url;
            link.download = `taplist_${BAR.id}.csv`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) {
            toast(error.message, true);
        } finally {
            node.disabled = false;
            node.classList.remove('is-busy');
        }
    }

    // ---------- запуск ----------

    function bind() {
        $('tp-sheet-close').addEventListener('click', closeSheet);
        $('tp-sheet-wrap').addEventListener('click', (event) => {
            if (event.target.id === 'tp-sheet-wrap') closeSheet();
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && state.sheet) closeSheet();
        });
        $('tp-csv').addEventListener('click', downloadCsv);
        $('tp-refresh-kegs').addEventListener('click', () => refreshKegs(false));
        $('tp-history-more-btn').addEventListener('click', () => {
            state.historyShown += HISTORY_STEP;
            renderHistory();
        });
        let timer = null;
        $('tp-filter').addEventListener('input', (event) => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                state.query = event.target.value;
                renderGrid();
            }, 100);
        });
        // Пока открыто окно крана или вкладка скрыта, страница не перерисовывается.
        setInterval(() => {
            if (!state.sheet && !state.busy && document.visibilityState === 'visible') refreshAll();
        }, REFRESH_MS);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && !state.sheet) refreshAll();
        });
    }

    bind();
    refreshAll();
})();
