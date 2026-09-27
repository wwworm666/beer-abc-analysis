/* Страница /yandex «Фиды Яндекса»: редактор позиций в карточках баров на Картах.

   API — routes/yml_feeds.py, правила и формулы — docs/yandex-feeds.md.
   Данные в DOM попадают только через textContent и value (без innerHTML).

   Черновик: у каждой позиции поля hidden/name/price/description. Сохраняются
   только изменённые позиции, вместе с base — правкой, которую страница видела
   при загрузке. Если за это время позицию сохранил кто-то ещё, сервер отвечает
   409 и ничего не пишет. */
(function () {
    'use strict';

    // Яндекс показывает в карточке начало описания, примерно 250 символов.
    const CARD_DESCRIPTION = 250;
    const LIMITS = { name: 200, description: 3000 };
    const MAX_PRICE = 100000;
    const FILTERS = [
        { key: 'all', label: 'Все' },
        { key: 'edited', label: 'С правками' },
        { key: 'hidden', label: 'Скрытые' },
        { key: 'attention', label: 'Проверить' },
    ];

    const state = {
        feeds: [],
        barId: null,
        data: null,
        drafts: new Map(),
        open: new Set(),
        removeOrphans: new Set(),
        invalid: new Set(),
        filter: 'all',
        query: '',
        seq: 0,
        saving: false,
        morningTimer: null,
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

    // ---------- значения ----------

    const collapse = (value) => String(value || '').replace(/\s+/g, ' ').trim();
    const norm = (value) => collapse(value).toLowerCase().replace(/ё/g, 'е');

    function parsePrice(value) {
        const text = String(value === undefined || value === null ? '' : value).replace(/\s+/g, '').replace(',', '.');
        if (!text) return null;
        if (!/^\d+(\.\d+)?$/.test(text)) return NaN;
        return Math.round(Number(text) * 100) / 100;
    }

    function priceValid(value) {
        const number = parsePrice(value);
        return number === null || (!Number.isNaN(number) && number > 0 && number <= MAX_PRICE);
    }

    function samePrice(a, b) {
        const x = parsePrice(a);
        const y = parsePrice(b);
        return x !== null && y !== null && !Number.isNaN(x) && x === y;
    }

    function editablePrice(value) {
        const number = parsePrice(value);
        if (number === null || Number.isNaN(number)) return String(value || '');
        return Number.isInteger(number) ? String(number) : number.toFixed(2).replace('.', ',');
    }

    function money(value) {
        const number = parsePrice(value);
        if (number === null || Number.isNaN(number)) return '';
        return number.toLocaleString('ru-RU', {
            minimumFractionDigits: Number.isInteger(number) ? 0 : 2,
            maximumFractionDigits: 2,
        }) + ' ₽';
    }

    function when(iso) {
        if (!iso) return '';
        const moment = new Date(iso);
        if (Number.isNaN(moment.getTime())) return '';
        return moment.toLocaleString('ru-RU', {
            timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit',
            hour: '2-digit', minute: '2-digit',
        }).replace(',', ' в');
    }

    // ---------- черновик ----------

    function initial(offer) {
        return {
            hidden: Boolean(offer.hidden),
            name: offer.name || '',
            price: editablePrice(offer.price),
            description: offer.description || '',
            confirm: false,
        };
    }

    function draft(offer) {
        if (!state.drafts.has(offer.id)) state.drafts.set(offer.id, initial(offer));
        return state.drafts.get(offer.id);
    }

    function isDirty(offer) {
        const current = state.drafts.get(offer.id);
        if (!current) return false;
        const base = initial(offer);
        return current.confirm
            || current.hidden !== base.hidden
            || collapse(current.name) !== collapse(base.name)
            || !(collapse(current.price) === collapse(base.price) || samePrice(current.price, base.price))
            || collapse(current.description) !== collapse(base.description);
    }

    function offers() {
        return (state.data && state.data.offers) || [];
    }

    function dirtyCount() {
        return offers().filter(isDirty).length + state.removeOrphans.size;
    }

    function migratedFrom(offer) {
        return offer.override && offer.override.migrated_from_tap;
    }

    function needsAttention(offer) {
        return Boolean((offer.warnings && offer.warnings.length) || migratedFrom(offer) || offer.bar_only);
    }

    function shownName(offer) {
        return collapse(draft(offer).name) || offer.source_name || '';
    }

    function shownPrice(offer) {
        const value = draft(offer).price;
        return collapse(value) ? value : offer.source_price;
    }

    function shownDescription(offer) {
        return collapse(draft(offer).description) || offer.source_description || '';
    }

    function changeFor(offer) {
        const current = draft(offer);
        const name = collapse(current.name);
        const description = collapse(current.description);
        const price = collapse(current.price);
        return {
            hidden: current.hidden,
            name: name === collapse(offer.source_name) ? '' : name,
            price: !price || samePrice(price, offer.source_price) ? '' : price,
            description: description === collapse(offer.source_description) ? '' : description,
            base: offer.override || null,
            label: offer.source_name || offer.name,
        };
    }

    // ---------- уведомления ----------

    let toastTimer = null;
    function toast(text, bad) {
        const node = $('yf-toast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { node.hidden = true; }, bad ? 9000 : 4500);
    }

    // ---------- бары ----------

    function barTone(feed) {
        if (feed.error) return 'is-bad';
        if (feed.excluded) return 'is-warn';
        if (feed.beer !== null && feed.beer !== undefined) return 'is-ok';
        return '';
    }

    function renderBars() {
        const box = $('yf-bars');
        box.textContent = '';
        for (const feed of state.feeds) {
            const button = el('button', 'yf-bar');
            button.type = 'button';
            button.setAttribute('role', 'tab');
            button.setAttribute('aria-selected', String(feed.id === state.barId));
            button.dataset.id = feed.id;
            const dot = el('span', 'yf-dot ' + barTone(feed));
            dot.setAttribute('aria-hidden', 'true');
            button.appendChild(dot);
            button.appendChild(document.createTextNode(feed.title));
            if (feed.error) button.title = feed.error;
            else if (feed.excluded) button.title = 'Не попало в файл: ' + feed.excluded;
            button.addEventListener('click', () => switchBar(feed.id));
            box.appendChild(button);
        }
    }

    function switchBar(id) {
        if (id === state.barId) return;
        if (dirtyCount() && !window.confirm('Есть несохранённые правки. Перейти к другому бару без сохранения?')) return;
        openBar(id);
    }

    async function loadFeeds() {
        const response = await fetch('/api/yml/feeds', { headers: { Accept: 'application/json' } });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Не удалось загрузить список баров');
        state.feeds = data.feeds || [];
        renderBars();
        return data;
    }

    async function openBar(id) {
        const seq = ++state.seq;
        state.barId = id;
        state.data = null;
        state.drafts.clear();
        state.open.clear();
        state.removeOrphans.clear();
        state.invalid.clear();
        renderBars();
        const feed = state.feeds.find((item) => item.id === id);
        $('yf-url').value = feed ? feed.public_url : '';
        $('yf-open').href = feed ? feed.public_url : '#';
        $('yf-list').textContent = '';
        $('yf-list').appendChild(el('div', 'yf-loading', 'Загрузка…'));
        $('yf-phone').textContent = '';
        updateSavebar();
        try {
            const response = await fetch('/api/yml/feeds/' + encodeURIComponent(id), {
                headers: { Accept: 'application/json' },
            });
            const data = await response.json();
            if (seq !== state.seq) return;
            if (!response.ok) throw new Error(data.error || 'Не удалось прочитать фид');
            applyData(data);
        } catch (error) {
            if (seq !== state.seq) return;
            $('yf-list').textContent = '';
            $('yf-list').appendChild(el('div', 'yf-empty', error.message || 'Не удалось прочитать фид'));
            $('yf-snap-title').textContent = 'Не удалось прочитать фид';
            $('yf-snap-sub').textContent = 'Проверьте соединение и откройте бар ещё раз.';
        }
    }

    function applyData(data) {
        state.data = data;
        $('yf-url').value = data.feed.public_url;
        $('yf-open').href = data.feed.public_url;
        $('yf-preview-title').textContent = 'Пивная культура, ' + data.feed.title;
        renderStatus();
        renderBanners();
        renderChips();
        renderList();
        renderExtras();
        renderPreview();
        updateSavebar();
        scheduleMorningReload();
    }

    // ---------- состояние снимка ----------

    function renderStatus() {
        const data = state.data;
        const snap = data.snapshot || {};
        if (snap.source === 'snapshot') {
            $('yf-snap-title').textContent = 'Пиво из снимка от ' + when(snap.beer_updated_at || snap.updated_at);
        } else {
            $('yf-snap-title').textContent = 'Снимка ещё нет: пиво взято из iiko сейчас';
        }
        $('yf-snap-sub').textContent = 'Следующий снимок ' + when(snap.next_refresh)
            + '. Кухня и правки попадают в файл сразу.';
        const counts = data.counts || {};
        const box = $('yf-counts');
        box.textContent = '';
        const items = [
            ['В файле', counts.shown, false],
            ['Скрыто', counts.hidden, false],
            ['С правками', counts.edited, false],
            ['Не попало', counts.excluded, counts.excluded > 0],
        ];
        for (const [label, value, warn] of items) {
            const cell = el('div', 'yf-count' + (warn ? ' is-warn' : ''));
            cell.appendChild(el('b', null, String(value || 0)));
            cell.appendChild(el('span', null, label));
            box.appendChild(cell);
        }
    }

    function banner(tone, text, action) {
        const node = el('div', 'yf-banner ' + tone);
        const body = el('div');
        if (Array.isArray(text)) {
            body.appendChild(el('b', null, text[0]));
            body.appendChild(document.createTextNode(' ' + text[1]));
        } else {
            body.textContent = text;
        }
        node.appendChild(body);
        if (action) {
            const button = el('button', 'yf-btn yf-btn-sm', action.label);
            button.type = 'button';
            button.addEventListener('click', action.run);
            node.appendChild(button);
        }
        return node;
    }

    function showAttention() {
        state.filter = 'attention';
        renderChips();
        renderList();
        document.querySelector('.yf-editor').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function renderBanners() {
        const box = $('yf-banners');
        box.textContent = '';
        const data = state.data;
        const snap = data.snapshot || {};
        if (snap.error) box.appendChild(banner('is-bad', ['Снимок пива с ошибкой.', snap.error]));
        if (snap.stale) {
            box.appendChild(banner('is-warn', ['Снимок старше суток.',
                'В файле могут быть сорта, которых уже нет на кранах. Нажмите «Переснять пиво».']));
        }
        const migrated = offers().filter(migratedFrom).length;
        if (migrated) {
            box.appendChild(banner('is-warn', ['Правки пива теперь привязаны к сорту, а не к крану.',
                'Перенесено по текущему таплисту: ' + migrated + '. Проверьте, что правка относится к нужному пиву.'],
            { label: 'Показать', run: showAttention }));
        }
        const conflicts = offers().filter((offer) => offer.warnings && offer.warnings.length).length;
        if (conflicts) {
            box.appendChild(banner('is-warn', ['Проверить в iiko: ' + conflicts + '.',
                'Обычно это несколько блюд 0,5 л с разной ценой на одну кегу: в файл взята цена '
                + 'самого свежего приказа, лишние блюда уберите из техкарт.'],
            { label: 'Показать', run: showAttention }));
        }
    }

    // ---------- фильтры ----------

    function matches(offer, filter) {
        switch (filter) {
            case 'edited': return offer.edited || isDirty(offer);
            case 'hidden': return draft(offer).hidden;
            case 'attention': return needsAttention(offer);
            default: return true;
        }
    }

    function renderChips() {
        const box = $('yf-chips');
        box.textContent = '';
        for (const filter of FILTERS) {
            const count = offers().filter((offer) => matches(offer, filter.key)).length;
            if (filter.key === 'attention' && !count && state.filter !== 'attention') continue;
            const chip = el('button', 'yf-chip');
            chip.type = 'button';
            chip.setAttribute('aria-pressed', String(state.filter === filter.key));
            chip.appendChild(document.createTextNode(filter.label));
            chip.appendChild(el('span', 'yf-num', String(count)));
            chip.addEventListener('click', () => {
                state.filter = filter.key;
                renderChips();
                renderList();
            });
            box.appendChild(chip);
        }
    }

    function filtered() {
        const query = norm(state.query);
        return offers().filter((offer) => {
            if (query && !norm(shownName(offer)).includes(query) && !norm(offer.source_name).includes(query)) return false;
            return matches(offer, state.filter);
        });
    }

    // ---------- список ----------

    function metaText(offer) {
        if (offer.kind === 'beer') {
            const taps = (offer.taps || []).filter((tap) => tap !== null && tap !== undefined);
            const parts = [];
            if (taps.length) parts.push((taps.length > 1 ? 'Краны ' : 'Кран ') + taps.join(', '));
            parts.push(String(offer.portion || '0.5').replace('.', ',') + ' л');
            if (offer.vendor) parts.push(offer.vendor);
            return parts.join(' · ');
        }
        return offer.bar_only ? 'Кухня · правка только этого бара' : 'Кухня · общая для всех баров';
    }

    function badges(offer) {
        const list = [];
        if (isDirty(offer)) list.push(['Не сохранено', 'is-accent']);
        else if (offer.edited && !draft(offer).hidden) list.push(['С правкой', 'is-accent']);
        if (draft(offer).hidden) list.push(['Скрыто', '']);
        if (needsAttention(offer)) list.push(['Проверить', 'is-warn']);
        return list;
    }

    function thumb(offer) {
        const box = el('div', 'yf-thumb');
        const picture = /^https:\/\//i.test(offer.picture || '') ? offer.picture : '';
        if (picture) {
            const image = el('img');
            image.src = picture;
            image.alt = '';
            image.loading = 'lazy';
            image.referrerPolicy = 'no-referrer';
            box.appendChild(image);
        } else {
            box.appendChild(el('span', null, 'нет фото'));
        }
        return box;
    }

    function fillRow(item, offer) {
        const current = draft(offer);
        item.classList.toggle('is-hidden', current.hidden);
        item.querySelector('.yf-switch input').checked = !current.hidden;
        item.querySelector('.yf-row-name').textContent = shownName(offer);
        const meta = item.querySelector('.yf-row-meta');
        meta.textContent = '';
        meta.appendChild(document.createTextNode(metaText(offer)));
        for (const [label, tone] of badges(offer)) meta.appendChild(el('span', 'yf-badge ' + tone, label));
        const price = item.querySelector('.yf-row-price');
        price.textContent = money(shownPrice(offer));
        if (!samePrice(shownPrice(offer), offer.source_price) && offer.source_price) {
            const was = el('small', null, money(offer.source_price));
            was.title = 'Цена из источника';
            price.appendChild(was);
        }
    }

    function renderItem(offer) {
        const item = el('div', 'yf-item');
        item.dataset.id = offer.id;
        const row = el('div', 'yf-row');

        const toggle = el('label', 'yf-switch');
        toggle.title = 'Показывать в файле';
        const input = el('input');
        input.type = 'checkbox';
        input.setAttribute('role', 'switch');
        input.setAttribute('aria-label', 'Показывать в файле: ' + (offer.source_name || offer.name));
        input.addEventListener('change', () => {
            draft(offer).hidden = !input.checked;
            changed(offer, item);
        });
        toggle.appendChild(input);
        toggle.appendChild(el('span'));
        row.appendChild(toggle);
        row.appendChild(thumb(offer));

        const main = el('button', 'yf-row-main');
        main.type = 'button';
        main.setAttribute('aria-expanded', 'false');
        main.setAttribute('aria-controls', 'yf-edit-' + offer.id);
        main.appendChild(el('span', 'yf-row-name'));
        main.appendChild(el('span', 'yf-row-meta'));
        main.addEventListener('click', () => toggleOpen(offer, item));
        row.appendChild(main);

        row.appendChild(el('div', 'yf-row-price yf-num'));

        const chev = el('button', 'yf-chev');
        chev.type = 'button';
        chev.setAttribute('aria-label', 'Изменить позицию');
        chev.appendChild(svg(['M6 9l6 6 6-6']));
        chev.addEventListener('click', () => toggleOpen(offer, item));
        row.appendChild(chev);

        item.appendChild(row);
        fillRow(item, offer);
        if (state.open.has(offer.id)) openEditor(offer, item);
        return item;
    }

    function renderList() {
        const box = $('yf-list');
        box.textContent = '';
        const list = filtered();
        if (!list.length) {
            const empty = offers().length
                ? 'Ничего не найдено. Сбросьте поиск или фильтр.'
                : 'В файле этого бара пока нет позиций.';
            box.appendChild(el('div', 'yf-empty', empty));
            return;
        }
        let section = null;
        for (const offer of list) {
            if (offer.category_name !== section) {
                section = offer.category_name;
                const head = el('div', 'yf-section-head');
                head.appendChild(el('span', 'yf-section-title', section || 'Меню'));
                head.appendChild(el('span', 'yf-section-line'));
                const size = list.filter((item) => item.category_name === section).length;
                head.appendChild(el('span', 'yf-section-note yf-num', String(size)));
                box.appendChild(head);
            }
            box.appendChild(renderItem(offer));
        }
    }

    function toggleOpen(offer, item) {
        if (state.open.has(offer.id)) {
            state.open.delete(offer.id);
            const editor = item.querySelector('.yf-edit');
            if (editor) editor.remove();
            item.classList.remove('is-open');
            item.querySelector('.yf-row-main').setAttribute('aria-expanded', 'false');
        } else {
            state.open.add(offer.id);
            openEditor(offer, item);
            const first = item.querySelector('.yf-edit input, .yf-edit textarea');
            if (first) first.focus();
        }
    }

    // ---------- редактор позиции ----------

    function field(options) {
        const wrap = el('div', 'yf-field' + (options.wide ? ' yf-field-wide' : ''));
        const head = el('div', 'yf-field-head');
        const label = el('label', 'yf-field-label', options.label);
        const id = 'yf-f-' + options.key + '-' + options.offer.id;
        label.htmlFor = id;
        head.appendChild(label);
        const count = options.limit ? el('span', 'yf-field-count') : null;
        if (count) head.appendChild(count);
        wrap.appendChild(head);

        const input = options.multiline ? el('textarea', 'yf-textarea') : el('input', 'yf-input');
        if (!options.multiline) input.type = 'text';
        input.id = id;
        if (options.numeric) {
            input.classList.add('yf-num');
            input.inputMode = 'decimal';
        }
        input.value = draft(options.offer)[options.key];
        input.placeholder = options.placeholder || '';
        if (options.limit) input.maxLength = options.limit;
        wrap.appendChild(input);

        const source = el('div', 'yf-source');
        const sourceText = el('span', 'yf-source-text', options.sourceText);
        sourceText.title = options.sourceText;
        source.appendChild(sourceText);
        const reset = el('button', 'yf-link-btn', 'Вернуть исходное');
        reset.type = 'button';
        source.appendChild(reset);
        wrap.appendChild(source);
        const error = el('div', 'yf-error');
        error.hidden = true;
        wrap.appendChild(error);

        function refresh() {
            const value = input.value;
            const changedFromSource = options.isSource ? !options.isSource(value) : false;
            input.classList.toggle('is-changed', changedFromSource);
            reset.hidden = !changedFromSource;
            if (count) {
                const length = collapse(value).length;
                count.textContent = options.cardLimit
                    ? `${length} / ${options.limit} · в карточке ~${options.cardLimit}`
                    : `${length} / ${options.limit}`;
                count.classList.toggle('is-over', Boolean(options.cardLimit && length > options.cardLimit));
            }
            if (options.validate) {
                const message = options.validate(value);
                error.textContent = message || '';
                error.hidden = !message;
                input.classList.toggle('is-invalid', Boolean(message));
                input.setAttribute('aria-invalid', String(Boolean(message)));
                if (message) state.invalid.add(options.offer.id);
                else state.invalid.delete(options.offer.id);
            }
        }

        input.addEventListener('input', () => {
            draft(options.offer)[options.key] = input.value;
            refresh();
            changed(options.offer, options.item);
        });
        reset.addEventListener('click', () => {
            input.value = options.resetValue;
            draft(options.offer)[options.key] = input.value;
            refresh();
            changed(options.offer, options.item);
            input.focus();
        });
        refresh();
        return wrap;
    }

    function note(text, tone, actions) {
        const node = el('div', 'yf-note' + (tone ? ' ' + tone : ''));
        node.appendChild(el('div', null, text));
        if (actions && actions.length) {
            const box = el('div', 'yf-note-actions');
            for (const action of actions) {
                const button = el('button', 'yf-btn yf-btn-sm', action.label);
                button.type = 'button';
                button.addEventListener('click', action.run);
                box.appendChild(button);
            }
            node.appendChild(box);
        }
        return node;
    }

    function priceSource(offer) {
        if (offer.kind === 'beer') {
            const parts = ['Из iiko: ' + money(offer.source_price)];
            if (offer.price_source) parts.push(offer.price_source);
            if (offer.price_dish) parts.push('блюдо «' + offer.price_dish + '»');
            return parts.join(' · ');
        }
        return 'Из меню кухни: ' + money(offer.source_price);
    }

    function openEditor(offer, item) {
        const old = item.querySelector('.yf-edit');
        if (old) old.remove();
        item.classList.add('is-open');
        item.querySelector('.yf-row-main').setAttribute('aria-expanded', 'true');
        const editor = el('div', 'yf-edit');
        editor.id = 'yf-edit-' + offer.id;

        editor.appendChild(field({
            offer, item, key: 'name', label: 'Название', limit: LIMITS.name,
            placeholder: offer.source_name,
            sourceText: 'Исходное: ' + (offer.source_name || '—'),
            isSource: (value) => !collapse(value) || collapse(value) === collapse(offer.source_name),
            resetValue: offer.source_name || '',
        }));
        editor.appendChild(field({
            offer, item, key: 'price', label: 'Цена, ₽', numeric: true,
            placeholder: editablePrice(offer.source_price),
            sourceText: priceSource(offer),
            isSource: (value) => !collapse(value) || samePrice(value, offer.source_price),
            resetValue: editablePrice(offer.source_price),
            validate: (value) => (priceValid(value) ? '' : 'Цена — число от 0,01 до 100 000'),
        }));
        editor.appendChild(field({
            offer, item, key: 'description', label: 'Описание', wide: true, multiline: true,
            limit: LIMITS.description, cardLimit: CARD_DESCRIPTION,
            placeholder: offer.source_description,
            sourceText: 'Исходное: ' + (collapse(offer.source_description) || '—'),
            isSource: (value) => !collapse(value) || collapse(value) === collapse(offer.source_description),
            resetValue: offer.source_description || '',
        }));

        const notes = el('div', 'yf-notes');
        for (const warning of offer.warnings || []) notes.appendChild(note(warning, 'is-warn'));
        if (migratedFrom(offer)) {
            notes.appendChild(note(
                'Правка перенесена с крана ' + migratedFrom(offer) + ' при переходе на привязку к сорту. '
                + 'Проверьте, что она относится к этому пиву.', 'is-warn', [
                    { label: 'Всё верно', run: () => { draft(offer).confirm = true; changed(offer, item); toast('Подтверждение сохранится вместе с остальными правками'); } },
                    { label: 'Удалить правку', run: () => resetOffer(offer, item) },
                ]));
        }
        if (offer.kind === 'kitchen' && offer.bar_only) {
            notes.appendChild(note('Сейчас у этого бара своя правка блюда. После сохранения она станет общей для всех баров.', 'is-warn'));
        }
        if (notes.childNodes.length) editor.appendChild(notes);

        const foot = el('div', 'yf-edit-foot');
        foot.appendChild(el('span', null, offer.kind === 'kitchen'
            ? 'Меню кухни общее: правка блюда действует во всех четырёх барах.'
            : 'Правка действует в этом баре и остаётся за сортом, даже если его переставят на другой кран.'));
        if (offer.edited || isDirty(offer)) {
            const reset = el('button', 'yf-link-btn', 'Сбросить все правки позиции');
            reset.type = 'button';
            reset.addEventListener('click', () => resetOffer(offer, item));
            foot.appendChild(reset);
        }
        editor.appendChild(foot);
        item.appendChild(editor);
    }

    function resetOffer(offer, item) {
        state.drafts.set(offer.id, {
            hidden: false,
            name: offer.source_name || '',
            price: editablePrice(offer.source_price),
            description: offer.source_description || '',
            confirm: Boolean(offer.edited),
        });
        state.invalid.delete(offer.id);
        changed(offer, item);
        if (state.open.has(offer.id)) openEditor(offer, item);
    }

    function changed(offer, item) {
        if (item && item.isConnected) fillRow(item, offer);
        renderPreview();
        updateSavebar();
    }

    // ---------- не попали в файл, правки без позиций ----------

    function renderExtras() {
        const data = state.data;
        const excluded = data.excluded || [];
        $('yf-excluded').hidden = !excluded.length;
        $('yf-excluded-title').textContent = 'Не попали в файл: ' + excluded.length;
        const list = $('yf-excluded-list');
        list.textContent = '';
        for (const entry of excluded) {
            const row = el('li', 'yf-extra-item');
            const taps = (entry.taps || []).filter((tap) => tap !== null && tap !== undefined);
            row.appendChild(el('span', 'yf-extra-tap', taps.length ? 'Кран ' + taps.join(', ') : ''));
            const body = el('div');
            body.appendChild(el('div', 'yf-extra-name', entry.name));
            body.appendChild(el('div', 'yf-extra-reason', entry.reason));
            row.appendChild(body);
            row.appendChild(el('span'));
            list.appendChild(row);
        }

        const orphans = data.orphans || [];
        $('yf-orphans').hidden = !orphans.length;
        $('yf-orphans-title').textContent = 'Правки без позиции в файле: ' + orphans.length;
        const box = $('yf-orphans-list');
        box.textContent = '';
        for (const orphan of orphans) {
            const row = el('li', 'yf-extra-item' + (state.removeOrphans.has(orphan.id) ? ' is-removed' : ''));
            const match = /-u(\d+)-p05$/.exec(orphan.id);
            row.appendChild(el('span', 'yf-extra-tap', orphan.kitchen ? 'Кухня' : 'Пиво'));
            const body = el('div');
            const override = orphan.override || {};
            if (match && !override.name) {
                const link = el('a', 'yf-extra-name', 'Сорт Untappd ' + match[1]);
                link.href = 'https://untappd.com/beer/' + match[1];
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                body.appendChild(link);
            } else {
                body.appendChild(el('div', 'yf-extra-name', override.name || orphan.id));
            }
            const what = [];
            if (override.hidden) what.push('скрыт');
            if (override.name) what.push('своё название');
            if (override.price) what.push('своя цена ' + money(override.price));
            if (override.description) what.push('своё описание');
            body.appendChild(el('div', 'yf-extra-reason', what.join(', ') || 'пустая правка'));
            row.appendChild(body);
            const button = el('button', 'yf-btn yf-btn-sm',
                state.removeOrphans.has(orphan.id) ? 'Оставить' : 'Удалить');
            button.type = 'button';
            button.addEventListener('click', () => {
                if (state.removeOrphans.has(orphan.id)) state.removeOrphans.delete(orphan.id);
                else state.removeOrphans.add(orphan.id);
                renderExtras();
                updateSavebar();
            });
            row.appendChild(button);
            box.appendChild(row);
        }
    }

    // ---------- превью карточки ----------

    function renderPreview() {
        const box = $('yf-phone');
        box.textContent = '';
        let section = null;
        let shown = 0;
        for (const offer of offers()) {
            if (draft(offer).hidden) continue;
            if (offer.category_name !== section) {
                section = offer.category_name;
                box.appendChild(el('h3', 'yf-pv-cat', section || 'Меню'));
            }
            const card = el('article', 'yf-pv-item' + (isDirty(offer) ? ' is-changed' : ''));
            const picture = /^https:\/\//i.test(offer.picture || '') ? offer.picture : '';
            if (picture) {
                const image = el('img', 'yf-pv-photo');
                image.src = picture;
                image.alt = '';
                image.loading = 'lazy';
                image.referrerPolicy = 'no-referrer';
                card.appendChild(image);
            } else {
                card.appendChild(el('div', 'yf-pv-photo', 'нет фото'));
            }
            const main = el('div', 'yf-pv-main');
            const top = el('div', 'yf-pv-top');
            top.appendChild(el('div', 'yf-pv-name', shownName(offer)));
            top.appendChild(el('div', 'yf-pv-price', money(shownPrice(offer))));
            main.appendChild(top);
            main.appendChild(el('div', 'yf-pv-desc', shownDescription(offer)));
            card.appendChild(main);
            box.appendChild(card);
            shown += 1;
        }
        if (!shown) box.appendChild(el('div', 'yf-empty', 'В файле нет ни одной видимой позиции.'));
    }

    // ---------- сохранение ----------

    function updateSavebar() {
        const count = dirtyCount();
        $('yf-savebar').hidden = !count;
        $('yf-dirty-count').textContent = String(count);
        $('yf-save').disabled = state.saving;
    }

    async function save() {
        if (state.saving || !state.data) return;
        const changes = {};
        for (const offer of offers()) {
            if (!isDirty(offer)) continue;
            if (!priceValid(draft(offer).price)) {
                toast('«' + (offer.source_name || offer.name) + '»: цена — число от 0,01 до 100 000', true);
                return;
            }
            changes[offer.id] = changeFor(offer);
        }
        for (const orphan of state.data.orphans || []) {
            if (!state.removeOrphans.has(orphan.id)) continue;
            changes[orphan.id] = { hidden: false, name: '', price: '', description: '', base: orphan.override || null };
        }
        if (!Object.keys(changes).length) return;
        const barId = state.barId;
        const seq = state.seq;
        state.saving = true;
        $('yf-save').classList.add('is-busy');
        updateSavebar();
        try {
            const response = await fetch('/api/yml/feeds/' + encodeURIComponent(barId), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ changes }),
            });
            const data = await response.json();
            if (seq !== state.seq || barId !== state.barId) return;
            if (response.status === 409) {
                const conflicts = new Set(data.conflicts || []);
                const keep = new Map();
                for (const [id, value] of state.drafts) if (!conflicts.has(id)) keep.set(id, value);
                state.drafts = keep;
                for (const id of conflicts) state.removeOrphans.delete(id);
                applyData(data);
                toast(data.error || 'Позиции изменил кто-то ещё', true);
                return;
            }
            if (!response.ok) throw new Error(data.error || 'Не удалось сохранить правки');
            state.drafts.clear();
            state.removeOrphans.clear();
            state.invalid.clear();
            applyData(data);
            loadFeeds().catch(() => {});
            toast('Сохранено. Яндекс увидит правки при следующем чтении файла.');
        } catch (error) {
            toast(error.message || 'Не удалось сохранить правки', true);
        } finally {
            state.saving = false;
            $('yf-save').classList.remove('is-busy');
            updateSavebar();
        }
    }

    function discard() {
        if (!dirtyCount()) return;
        if (!window.confirm('Отменить все несохранённые правки этого бара?')) return;
        state.drafts.clear();
        state.removeOrphans.clear();
        state.invalid.clear();
        renderChips();
        renderList();
        renderExtras();
        renderPreview();
        updateSavebar();
    }

    // ---------- снимок по кнопке ----------

    async function refreshSnapshot() {
        if (dirtyCount()) {
            toast('Сначала сохраните или отмените правки: снимок перезагрузит список', true);
            return;
        }
        const button = $('yf-refresh');
        button.classList.add('is-busy');
        button.disabled = true;
        try {
            const response = await fetch('/api/yml/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: '{}',
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Снимок не снят');
            await loadFeeds();
            await openBar(state.barId);
            const bars = data.bars || {};
            const failed = Object.values(bars).filter((bar) => bar.error).length;
            toast(failed ? 'Снимок снят, у ' + failed + ' бар(ов) ошибка — см. сообщение вверху'
                : 'Снимок снят: сорта и цены обновлены во всех барах', Boolean(failed));
        } catch (error) {
            toast(error.message || 'Снимок не снят', true);
        } finally {
            button.classList.remove('is-busy');
            button.disabled = false;
        }
    }

    // Утром выходит новый снимок: открытая вкладка перечитывает бар сама,
    // если в ней нет несохранённых правок.
    function scheduleMorningReload() {
        clearTimeout(state.morningTimer);
        const next = state.data && state.data.snapshot && Date.parse(state.data.snapshot.next_refresh);
        if (!next) return;
        const delay = Math.max(60000, next - Date.now() + 90000);
        state.morningTimer = setTimeout(() => {
            if (dirtyCount()) {
                toast('Вышел новый снимок пива. Сохраните правки и обновите страницу.');
                return;
            }
            loadFeeds().then(() => openBar(state.barId)).catch(() => {});
        }, Math.min(delay, 2147483000));
    }

    // ---------- обработчики ----------

    function copyLink() {
        const input = $('yf-url');
        const done = () => toast('Ссылка скопирована');
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(input.value).then(done, () => {
                input.select();
                toast('Скопируйте ссылку из поля вручную', true);
            });
        } else {
            input.select();
            try {
                document.execCommand('copy');
                done();
            } catch (error) {
                toast('Скопируйте ссылку из поля вручную', true);
            }
        }
    }

    function bind() {
        $('yf-copy').addEventListener('click', copyLink);
        $('yf-help-toggle').addEventListener('click', () => {
            const help = $('yf-help');
            help.hidden = !help.hidden;
            $('yf-help-toggle').setAttribute('aria-expanded', String(!help.hidden));
        });
        $('yf-refresh').addEventListener('click', refreshSnapshot);
        $('yf-save').addEventListener('click', save);
        $('yf-discard').addEventListener('click', discard);
        let searchTimer = null;
        $('yf-search').addEventListener('input', (event) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                state.query = event.target.value;
                renderList();
            }, 120);
        });
        for (const button of document.querySelectorAll('.yf-view')) {
            button.addEventListener('click', () => {
                $('yf-main').dataset.view = button.dataset.view;
                for (const other of document.querySelectorAll('.yf-view')) {
                    other.setAttribute('aria-selected', String(other === button));
                }
                button.parentElement.scrollIntoView({ block: 'start', behavior: 'smooth' });
            });
        }
        document.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
                if (!dirtyCount()) return;
                event.preventDefault();
                save();
            }
        });
        window.addEventListener('beforeunload', (event) => {
            if (!dirtyCount()) return;
            event.preventDefault();
            event.returnValue = '';
        });
    }

    async function start() {
        bind();
        try {
            await loadFeeds();
            if (state.feeds.length) await openBar(state.feeds[0].id);
        } catch (error) {
            $('yf-list').textContent = '';
            $('yf-list').appendChild(el('div', 'yf-empty', error.message || 'Не удалось загрузить список баров'));
            $('yf-snap-title').textContent = 'Не удалось загрузить страницу';
        }
    }

    start();
})();
