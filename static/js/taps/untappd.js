/* Страница /taps/untappd: связи кег iiko с карточками Untappd.

   ИИ-агент присылает предложения (черновики), администратор нажимает «Верно» или
   «Не то»; связь, подтверждённая здесь, действует сразу — таплист, «Таплист пятницы»,
   бот, фиды. API — routes/taps.py (/api/untappd/*), правила — docs/untappd-links.md.
   Данные в DOM попадают только через textContent (без innerHTML): тексты карточек и
   причины агента — данные, не разметка. */
(function (root) {
    'use strict';

    // ---------- строка таплиста (чистые функции: их сверяет с Python tests/test_taps_untappd_page.py) ----------

    const clean = (value) => String(value || '').split(/\s+/).filter(Boolean).join(' ');

    // Имя и строка — как в core/taplist_post (post_name, beer_text): короткое имя
    // пивоварни + название; пивоварню не пишем, если имя пустое или уже есть в названии.
    // Сервер прислал готовую строку (preview.line); здесь она пересобирается, только
    // когда администратор правит стиль по-русски или имя пивоварни.
    function composeName(beerName, short) {
        const name = clean(beerName);
        const brewery = clean(short);
        if (!brewery || name.toLowerCase().includes(brewery.toLowerCase())) return name;
        return brewery + ' ' + name;
    }

    function composeLine(preview, styleRu, short) {
        const fixedName = preview.name_from_dictionary || preview.brewery_from_dictionary;
        const name = (fixedName || short === null) ? preview.name : composeName(preview.beer_name, short);
        const parts = [];
        const style = (preview.style_from_dictionary || styleRu === null) ? preview.style_ru : clean(styleRu);
        if (style) parts.push(style);
        if (preview.abv) parts.push(preview.abv + '%');
        return name + (parts.length ? ' — ' + parts.join(', ') : '');
    }

    const api = { clean: clean, composeName: composeName, composeLine: composeLine };
    root.TpUntappd = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof document === 'undefined') return;

    const TABS = [
        { key: 'review', label: 'На проверке' },
        { key: 'queue', label: 'Ждут агента' },
        { key: 'done', label: 'Подтверждены здесь' },
    ];
    // Статусы встроенного реестра (scripts/build_untappd_registry.py, STATUS_LABELS) и новая карточка iiko.
    const REGISTRY_STATUS = {
        new: 'новая карточка iiko',
        needs_source: 'нужна точная карточка',
        needs_identity: 'уточнить сорт или пивоварню',
        needs_variant: 'уточнить версию',
        not_found: 'карточка не найдена',
        approximate: 'есть только примерная связь',
        skipped: 'пропущено при сборке реестра',
    };
    const VERIFIED_LIMIT = 100;
    const NOTE_MAX = 500;

    // edits — что администратор уже ввёл в поля имён ({id: {style, brewery}}): переживает
    // перерисовку («Не то» → «Отмена», обновление списка).
    const state = { tab: null, pending: null, queue: null, verified: null, canReview: false,
                    busy: false, open: null, edits: {} };

    const $ = (id) => document.getElementById(id);

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    // Ссылка наружу (http/https) открывается в новой вкладке, своя страница (/taps/bar2) — здесь же.
    function link(url, text, className) {
        const value = String(url || '');
        const inside = /^\/(?!\/)/.test(value);
        if (!inside && !/^https?:\/\//i.test(value)) return el('span', className, text || value);
        const node = el('a', className, text || value);
        node.href = value;
        if (!inside) {
            node.target = '_blank';
            node.rel = 'noopener noreferrer';
        }
        return node;
    }

    function shortUrl(url) {
        return String(url || '').replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '');
    }

    function stamp(value) {
        const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(String(value || ''));
        return match ? match[3] + '.' + match[2] + ' ' + match[4] : '';
    }

    function abvText(value) {
        if (value === null || value === undefined || value === '') return '';
        const number = Number(value);
        return Number.isFinite(number) ? String(Math.round(number * 100) / 100).replace('.', ',') + '%' : '';
    }

    function where(onTap) {
        return (onTap || []).map((tap) => (tap.bar || tap.bar_id) + ', кран ' + tap.tap_number).join('; ');
    }

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

    let toastTimer = null;
    function toast(text, bad) {
        const node = $('tp-toast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { node.hidden = true; }, bad ? 8000 : 4000);
    }

    // ---------- загрузка ----------

    async function load() {
        const [pending, queue, verified] = await Promise.all([
            getJson('/api/untappd/proposals?status=proposed'),
            getJson('/api/untappd/queue?scope=all'),
            getJson('/api/untappd/proposals?status=verified&limit=' + VERIFIED_LIMIT),
        ]);
        const failed = [pending, queue, verified].find((answer) => !answer.ok);
        const error = $('tp-links-error');
        if (failed) {
            error.textContent = 'Не удалось загрузить связи: ' + (failed.data.error || 'ошибка ' + failed.status);
            error.hidden = false;
        } else {
            error.hidden = true;
        }
        state.pending = pending.ok ? pending.data : null;
        state.queue = queue.ok ? queue.data : null;
        state.verified = verified.ok ? verified.data : null;
        state.canReview = Boolean(state.pending && state.pending.can_review);
        if (!state.tab) state.tab = (state.pending && state.pending.items.length) ? 'review' : 'queue';
        render();
    }

    function waiting() {
        if (!state.queue) return [];
        return state.queue.items.filter((row) => !(row.proposal && row.proposal.status === 'proposed'));
    }

    function counts() {
        return {
            review: state.pending ? state.pending.items.length : 0,
            queue: waiting().length,
            done: state.pending ? state.pending.counts.verified : 0,
            onTap: state.queue ? state.queue.counts.on_tap : 0,
        };
    }

    // ---------- сводка и вкладки ----------

    function render() {
        renderStrip();
        renderTabs();
        const list = $('tp-links-list');
        list.textContent = '';
        if (state.tab === 'review') renderReview(list);
        else if (state.tab === 'queue') renderQueue(list);
        else renderDone(list);
    }

    function renderStrip() {
        const strip = $('tp-links-strip');
        strip.textContent = '';
        const c = counts();
        const cell = (value, label, tab, warn) => {
            const node = el('button', 'tp-stat' + (warn ? ' is-warn' : ''));
            node.type = 'button';
            node.appendChild(el('b', null, String(value)));
            node.appendChild(el('span', null, label));
            node.addEventListener('click', () => setTab(tab));
            strip.appendChild(node);
        };
        cell(c.review, 'ждут решения', 'review', c.review > 0);
        cell(c.onTap, 'на кранах без связи', 'queue', c.onTap > 0);
        cell(c.queue, 'ждут агента', 'queue', false);
        cell(c.done, 'подтверждено здесь', 'done', false);
    }

    function renderTabs() {
        const box = $('tp-links-tabs');
        box.textContent = '';
        const c = counts();
        for (const tab of TABS) {
            const chip = el('button', 'tp-chip' + (tab.key === 'review' && c.review ? ' is-warn' : ''));
            chip.type = 'button';
            chip.setAttribute('role', 'tab');
            chip.setAttribute('aria-pressed', String(state.tab === tab.key));
            chip.setAttribute('aria-selected', String(state.tab === tab.key));
            chip.appendChild(document.createTextNode(tab.label + ' '));
            chip.appendChild(el('span', 'tp-num', String(c[tab.key])));
            chip.addEventListener('click', () => setTab(tab.key));
            box.appendChild(chip);
        }
    }

    function setTab(key) {
        state.tab = key;
        state.open = null;
        render();
    }

    // ---------- «На проверке» ----------

    function renderReview(list) {
        if (!state.pending) return;
        if (!state.pending.items.length) {
            list.appendChild(el('div', 'tp-empty-list',
                'Новых предложений нет. Агент присылает их по расписанию; что ждёт связи — во вкладке «Ждут агента».'));
            return;
        }
        for (const item of state.pending.items) list.appendChild(proposalCard(item));
    }

    function kegHead(item, onTap, statusText) {
        const head = el('div', 'tp-link-head');
        const title = el('div', 'tp-link-keg');
        title.appendChild(el('b', null, item.iiko_name || 'Кега без названия'));
        const meta = [item.iiko_article ? 'арт. ' + item.iiko_article : '', statusText || ''].filter(Boolean).join(' · ');
        if (meta) title.appendChild(el('span', 'tp-link-meta', meta));
        head.appendChild(title);
        if (onTap && onTap.length) head.appendChild(el('span', 'tp-badge is-warn', 'На кране: ' + where(onTap)));
        return head;
    }

    // Карточка, которая пойдёт в таплист: если этот id Untappd уже есть в реестре — его
    // проверенные данные (preview.card), иначе — данные из предложения.
    function beerBlock(item) {
        const card = (item.preview && item.preview.card) || item.card || {};
        const block = el('div', 'tp-link-beer');
        if (card.photo_url && /^https:\/\//.test(card.photo_url)) {
            const img = el('img', 'tp-link-photo');
            img.src = card.photo_url;
            img.alt = '';
            img.loading = 'lazy';
            img.referrerPolicy = 'no-referrer';
            block.appendChild(img);
        }
        const text = el('div', 'tp-link-beer-text');
        text.appendChild(el('div', 'tp-beer-title', card.beer_name || ''));
        text.appendChild(el('div', 'tp-beer-sub', card.brewery || ''));
        const facts = [card.style || '', abvText(card.abv_percent),
                       card.ibu !== null && card.ibu !== undefined ? card.ibu + ' IBU' : ''].filter(Boolean).join(' · ');
        if (facts) text.appendChild(el('div', 'tp-beer-sub', facts));
        text.appendChild(link(item.url, shortUrl(item.url), 'tp-link-url'));
        block.appendChild(text);
        return block;
    }

    function field(labelText, value, hint) {
        const label = el('label', 'tp-link-field');
        label.appendChild(el('span', null, labelText));
        const input = el('input', 'tp-input tp-input-plain');
        input.type = 'text';
        input.value = value || '';
        input.maxLength = 200;
        input.autocomplete = 'off';
        label.appendChild(input);
        if (hint) label.appendChild(el('small', 'tp-hint', hint));
        return { label, input };
    }

    function proposalCard(item) {
        const preview = item.preview || {};
        const node = el('article', 'tp-panel tp-link');
        node.appendChild(kegHead(item, item.on_tap));
        node.appendChild(beerBlock(item));
        if (preview.known_card) {
            node.appendChild(el('p', 'tp-hint', 'Эта карточка уже есть в реестре: в таплист пойдут её проверенные данные.'));
        }
        const card = preview.card || item.card || {};
        if (card.description) node.appendChild(el('p', 'tp-link-desc', card.description));

        const line = el('div', 'tp-link-line');
        line.appendChild(el('span', 'tp-link-line-label', 'В таплисте'));
        const lineText = el('span', 'tp-link-line-text', preview.line || '');
        line.appendChild(lineText);
        node.appendChild(line);

        const fields = el('div', 'tp-link-fields');
        const edits = state.edits[item.id] || (state.edits[item.id] = {});
        let styleInput = null;
        let breweryInput = null;
        if (state.canReview && preview.style && !preview.style_from_dictionary) {
            const f = field('Стиль по-русски', 'style' in edits ? edits.style : preview.style_ru,
                'В словаре нет стиля «' + preview.style + '». Пусто — стиль в пост не попадёт.');
            styleInput = f.input;
            fields.appendChild(f.label);
        }
        if (state.canReview && !preview.name_from_dictionary && !preview.brewery_from_dictionary && card.brewery) {
            const f = field('Пивоварня в посте', 'brewery' in edits ? edits.brewery : preview.brewery_short,
                'Пусто — без пивоварни (если марка уже в названии).');
            breweryInput = f.input;
            fields.appendChild(f.label);
        }
        const update = () => {
            if (styleInput) edits.style = styleInput.value;
            if (breweryInput) edits.brewery = breweryInput.value;
            lineText.textContent = composeLine(preview, styleInput ? styleInput.value : null,
                                               breweryInput ? breweryInput.value : null);
        };
        if (styleInput) styleInput.addEventListener('input', update);
        if (breweryInput) breweryInput.addEventListener('input', update);
        if ('style' in edits || 'brewery' in edits) update();
        if (fields.childNodes.length) node.appendChild(fields);

        node.appendChild(whyBlock(item));

        if (!state.canReview) {
            node.appendChild(el('p', 'tp-hint', 'Подтверждает администратор.'));
            return node;
        }
        if (state.open === 'reject:' + item.id) {
            node.appendChild(rejectForm(item));
            return node;
        }
        const actions = el('div', 'tp-actions-row tp-link-actions');
        const confirm = button('Верно', 'tp-btn-primary', () => {
            const body = {};
            if (styleInput) body.style_ru = styleInput.value;
            if (breweryInput) body.brewery_short = breweryInput.value;
            act(confirm, '/api/untappd/proposals/' + encodeURIComponent(item.id) + '/confirm', body,
                'Связь подтверждена: «' + (item.iiko_name || '') + '» уже в таплисте.');
        });
        actions.appendChild(confirm);
        actions.appendChild(button('Не то', '', () => { state.open = 'reject:' + item.id; render(); }));
        node.appendChild(actions);
        return node;
    }

    function whyBlock(item) {
        const details = el('details', 'tp-how tp-link-why');
        details.appendChild(el('summary', null, 'Почему эта карточка'));
        const body = el('div', 'tp-how-body');
        if (item.reason) body.appendChild(el('p', null, item.reason));
        const sources = (item.evidence_urls || []).filter((url) => url !== item.url);
        if (sources.length) {
            const listNode = el('ul', 'tp-link-sources');
            for (const url of sources) {
                const li = el('li');
                li.appendChild(link(url, shortUrl(url)));
                listNode.appendChild(li);
            }
            body.appendChild(listNode);
        }
        for (const warning of item.warnings || []) body.appendChild(el('p', 'tp-hint', warning));
        body.appendChild(el('p', 'tp-hint', 'Предложил: ' + (item.created_by || 'неизвестно') + ', ' + stamp(item.created_at)));
        details.appendChild(body);
        return details;
    }

    function rejectForm(item) {
        const form = el('div', 'tp-link-reject');
        const label = el('label', 'tp-link-field');
        label.appendChild(el('span', null, 'Что не так'));
        const note = el('textarea', 'tp-input tp-input-plain');
        note.rows = 2;
        note.maxLength = NOTE_MAX;
        note.placeholder = 'Другой сорт, год, пивоварня — агент учтёт и поищет снова';
        label.appendChild(note);
        form.appendChild(label);
        const row = el('div', 'tp-actions-row');
        row.appendChild(button('Отмена', '', () => { state.open = null; render(); }));
        const reject = button('Отклонить', 'tp-btn-danger', () => act(reject,
            '/api/untappd/proposals/' + encodeURIComponent(item.id) + '/reject', { note: note.value },
            'Отклонено: кега вернулась в очередь агента.'));
        row.appendChild(reject);
        form.appendChild(row);
        setTimeout(() => note.focus(), 0);
        return form;
    }

    // ---------- «Ждут агента» ----------

    function renderQueue(list) {
        if (!state.queue) return;
        const rows = waiting();
        if (!rows.length) {
            list.appendChild(el('div', 'tp-empty-list', 'Все кеги на кранах и новые карточки iiko связаны с Untappd.'));
        }
        const panel = rows.length ? el('section', 'tp-panel tp-link-rows') : null;
        for (const row of rows) {
            const item = el('div', 'tp-link-row');
            item.appendChild(kegHead(row, row.on_tap, REGISTRY_STATUS[row.registry_status] || ''));
            const proposal = row.proposal;
            if (proposal && proposal.status === 'rejected') {
                item.appendChild(el('p', 'tp-hint', 'Отклонено' + (proposal.review_note ? ': «' + proposal.review_note + '»' : '')
                    + ' — агент поищет другую карточку.'));
            } else if (proposal && proposal.status === 'revoked') {
                item.appendChild(el('p', 'tp-hint', 'Связь отменена' + (proposal.review_note ? ': «' + proposal.review_note + '»' : '') + '.'));
            }
            panel.appendChild(item);
        }
        if (panel) list.appendChild(panel);
        const loose = state.queue.unidentified_taps || [];
        if (loose.length) {
            const box = el('section', 'tp-panel tp-link-rows');
            box.appendChild(el('h2', 'tp-link-subhead', 'Краны без товара iiko'));
            box.appendChild(el('p', 'tp-hint tp-link-subnote',
                'Здесь нужна не связь, а точная кега: бармен нажимает «Уточнить сорт» на странице бара.'));
            for (const tap of loose) {
                const row = el('div', 'tp-link-row');
                row.appendChild(link('/taps/' + encodeURIComponent(tap.bar_id), (tap.bar || tap.bar_id) + ', кран ' + tap.tap_number));
                row.appendChild(el('span', 'tp-link-meta', tap.current_beer || ''));
                box.appendChild(row);
            }
            list.appendChild(box);
        }
    }

    // ---------- «Подтверждены здесь» ----------

    function renderDone(list) {
        if (!state.verified) return;
        if (!state.verified.items.length) {
            list.appendChild(el('div', 'tp-empty-list', 'Здесь пока ничего не подтверждали.'));
            return;
        }
        const panel = el('section', 'tp-panel tp-link-rows');
        for (const item of state.verified.items) {
            const row = el('div', 'tp-link-row');
            row.appendChild(kegHead(item, item.on_tap));
            const line = el('div', 'tp-link-line');
            line.appendChild(link(item.url, (item.preview || {}).line || shortUrl(item.url), 'tp-link-line-text'));
            row.appendChild(line);
            row.appendChild(el('p', 'tp-hint', 'Подтвердил: ' + (item.reviewed_by || '') + ', ' + stamp(item.reviewed_at)
                + ' · предложил: ' + (item.created_by || '')));
            if (state.canReview) {
                if (state.open === 'revoke:' + item.id) {
                    row.appendChild(el('p', 'tp-question', 'Отменить связь? Ссылка и данные Untappd пропадут из таплиста, поста и бота, кега вернётся в очередь агента.'));
                    const actions = el('div', 'tp-actions-row');
                    actions.appendChild(button('Нет', '', () => { state.open = null; render(); }));
                    const revoke = button('Да, отменить', 'tp-btn-danger', () => act(revoke,
                        '/api/untappd/proposals/' + encodeURIComponent(item.id) + '/revoke', {},
                        'Связь отменена: кега вернулась в очередь.'));
                    actions.appendChild(revoke);
                    row.appendChild(actions);
                } else {
                    const open = el('button', 'tp-link-btn', 'Отменить связь');
                    open.type = 'button';
                    open.addEventListener('click', () => { state.open = 'revoke:' + item.id; render(); });
                    row.appendChild(open);
                }
            }
            panel.appendChild(row);
        }
        list.appendChild(panel);
        if (state.pending && state.pending.counts.verified > state.verified.items.length) {
            list.appendChild(el('p', 'tp-hint', 'Показаны последние ' + state.verified.items.length + ' из '
                + state.pending.counts.verified + '.'));
        }
    }

    // ---------- действия ----------

    function button(label, className, onClick) {
        const node = el('button', 'tp-btn ' + (className || ''), label);
        node.type = 'button';
        node.addEventListener('click', onClick);
        return node;
    }

    async function act(control, url, body, done) {
        if (state.busy) return;
        state.busy = true;
        control.classList.add('is-busy');
        control.disabled = true;
        try {
            const answer = await postJson(url, body);
            if (!answer.ok) {
                toast(answer.data.error || 'Не получилось: ошибка ' + answer.status, true);
                if (answer.status === 409) await load();
                return;
            }
            state.open = null;
            toast(done);
            await load();
        } catch (error) {
            toast('Нет связи с сервером. Попробуйте ещё раз.', true);
        } finally {
            state.busy = false;
            control.classList.remove('is-busy');
            control.disabled = false;
        }
    }

    load().catch(() => {
        const error = $('tp-links-error');
        error.textContent = 'Не удалось загрузить связи. Обновите страницу.';
        error.hidden = false;
    });
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && !state.busy && !state.open) load().catch(() => {});
    });
})(typeof window !== 'undefined' ? window : this);
