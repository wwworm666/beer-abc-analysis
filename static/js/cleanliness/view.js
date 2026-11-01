/* Страница «Чистота» — журнал приёмок бара за месяц.

   Всё считает сервер (core/bar_acceptance.build_journal): строки, пробелы,
   итоги. Здесь только показ, фильтры и просмотр фото. Ни одного правила («кто
   отвечает», «что считать пробелом») в этом файле нет и быть не должно — вторая
   версия правила разъехалась бы с первой.

   Фильтрация — на клиенте: месяц это ~120 строк (4 точки x 30 дней), гонять
   запрос на каждый щелчок фильтра незачем (тот же приём, что в блоке «Касса за
   месяц»).

   Месяц и бар — из полосы «Бар и период» (window.KStrip; с 2026-11-01, план единого
   виджета, этап 5): своих стрелок месяца и списка «Все точки» больше нет. Месяц — показанный
   в полосе (помесячный режим, данные с 24.08.2026 — раньше стрелка выключена). Бар — точка
   графика с тем же ключом (locations.venue_key из /api/schedule/locations): строки и плитки
   этой точки (плитки — totals_by_location с сервера, правило «что считать» не дублируется).
   «Все бары» — все точки. */
(function () {
    'use strict';

    var DOW = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

    var strip = window.KStrip || null;
    var K = window.KPeriod || null;
    // places — точки графика (id, venue_key) для сопоставления с баром полосы.
    var state = { year: 0, month: 0, data: null, places: null };
    var loadSeq = 0;   // номер последней загрузки: ответ за прежний месяц не рисуется

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function pad2(n) { return n < 10 ? '0' + n : '' + n; }

    function api(url) {
        return fetch(url, { credentials: 'same-origin' }).then(function (res) {
            if (!res.ok) {
                return res.json().catch(function () { return {}; })
                    .then(function (d) { throw new Error(d.error || ('HTTP ' + res.status)); });
            }
            return res.json();
        });
    }

    function fmtDate(ds) {
        var p = String(ds).split('-');
        var dow = new Date(+p[0], +p[1] - 1, +p[2]).getDay();
        return '<span class="cl-dow">' + DOW[dow] + '</span> ' + p[2] + '.' + p[1];
    }

    function fmtTime(iso) {
        var m = String(iso || '').match(/T(\d{2}):(\d{2})/);
        return m ? m[1] + ':' + m[2] : '';
    }

    // ==================== Бар и месяц из полосы ====================

    // Точка графика бара: venue_key = ключ бара сайта. «Все бары» ('') — null; бара нет среди
    // точек графика — undefined (страница пишет это и показывает все точки).
    function locationIdForBar(bar, places) {
        if (!bar) return null;
        for (var i = 0; i < (places || []).length; i++) {
            if (places[i].venue_key === bar) return places[i].id;
        }
        return undefined;
    }

    // Строки под фильтры: точка (id или null — все), ответ, поиск по бармену и тексту.
    function filterRows(rows, f) {
        f = f || {};
        var q = (f.q || '').trim().toLowerCase();
        return (rows || []).filter(function (r) {
            if (f.locationId != null && String(r.location_id) !== String(f.locationId)) return false;
            if (f.status === 'not_marked') {
                if (r.problems.indexOf('not_marked') === -1) return false;
            } else if (f.status && r.status !== f.status) return false;
            if (q) {
                var hay = (r.employee_name + ' ' + (r.note || '')).toLowerCase();
                if (hay.indexOf(q) === -1) return false;
            }
            return true;
        });
    }

    function stripMonth() {
        var p = strip ? strip.get().period : (K ? K.currentPeriod('month') : null);
        if (p && p.granularity !== 'month' && K) p = K.monthOf(p);
        return p ? { year: Number(p.start.slice(0, 4)), month: Number(p.start.slice(5, 7)) } : null;
    }

    function selectedLocation() {
        var bar = strip ? strip.get().bar : '';
        var id = locationIdForBar(bar, state.places);
        return id === undefined ? null : id;
    }

    // Бар выбран, но такой точки в графике нет — видно, почему в журнале все точки.
    function barNote() {
        var bar = strip ? strip.get().bar : '';
        if (!bar || !state.places || locationIdForBar(bar, state.places) !== undefined) return '';
        return 'Точки этого бара нет в графике — показаны все точки.';
    }

    // ==================== Загрузка ====================

    function load() {
        var seq = ++loadSeq;
        var url = '/api/cleanliness/month/' + state.year + '/' + state.month;
        var places = state.places ? Promise.resolve(state.places)
            : api('/api/schedule/locations').catch(function () { return null; });
        return Promise.all([api(url), places])
            .then(function (res) {
                if (seq !== loadSeq) return;
                state.data = res[0];
                state.places = res[1] || state.places;
                document.getElementById('clNotice').innerHTML = '';
                render();
            })
            .catch(function (err) {
                if (seq !== loadSeq) return;
                // Ошибку показываем НА МЕСТЕ таблицы, а не тостом: тост живёт
                // пару секунд, а причина пустого экрана нужна дольше.
                console.error('[CLEAN]', err);
                document.getElementById('clNotice').innerHTML =
                    '<div class="cl-error">Не удалось загрузить журнал приёмок. '
                    + esc(err.message)
                    + ' <button type="button" data-retry>повторить</button></div>';
                var btn = document.querySelector('#clNotice [data-retry]');
                if (btn) btn.addEventListener('click', load);
                document.getElementById('clRows').innerHTML = '';
            });
    }

    // ==================== Рендер ====================

    function render() {
        renderRule();
        renderTiles();
        renderRows();
        renderFoot();
    }

    function renderRule() {
        var d = state.data || {};
        var el = document.getElementById('clRule');
        if (!d.rule_from) { el.textContent = ''; return; }
        var p = d.rule_from.split('-');
        el.textContent = 'вопрос задаётся с ' + p[2] + '.' + p[1] + '.' + p[0];
    }

    function renderTiles() {
        var d = state.data || {};
        var loc = selectedLocation();
        // Плитки выбранного бара — итоги его точки с сервера; нет строк точки — нули.
        var t = loc == null ? (d.totals || {}) : ((d.totals_by_location || {})[String(loc)] || {});
        var gap = t.not_marked || 0;
        var tiles = [
            { k: 'смен с приёмкой', v: (t.answered || 0) + ' / ' + (t.shifts || 0), cls: '' },
            { k: 'чисто', v: t.clean || 0, cls: 'is-clean' },
            { k: 'замечания', v: t.issues || 0, cls: 'is-issues' },
            { k: 'плохо', v: t.bad || 0, cls: 'is-bad' },
            { k: 'не отмечено', v: gap, cls: 'is-gap' + (gap ? ' has-gap' : '') }
        ];
        document.getElementById('clTiles').innerHTML = tiles.map(function (x) {
            return '<div class="cl-tile ' + x.cls + '">'
                + '<div class="cl-tile-k">' + esc(x.k) + '</div>'
                + '<div class="cl-tile-v">' + esc(x.v) + '</div></div>';
        }).join('');
    }

    // Строки бара полосы (все — при «Все бары») с фильтрами ответа и поиска.
    function visibleRows() {
        return filterRows((state.data || {}).rows, {
            locationId: selectedLocation(),
            status: document.getElementById('clStatus').value,
            q: document.getElementById('clSearch').value
        });
    }

    function statusCell(r) {
        if (r.status) {
            return '<span class="cl-badge is-' + esc(r.status) + '">'
                + esc(r.status_label) + '</span>'
                + (r.edited ? '<span class="cl-edited">изменено</span>' : '');
        }
        if (r.problems.indexOf('not_marked') !== -1) {
            return '<span class="cl-badge is-gap">не отмечено</span>';
        }
        // Ответа нет, но и пробелом это не считается. Две разные причины, и
        // путать их нельзя: «ещё успеет» против «тогда этого вопроса не было».
        // Без второй формулировки вся история до даты отсечки навсегда осталась
        // бы в состоянии «ждём ответа».
        if (r.expected === false && r.date < (state.data || {}).today) {
            return '<span class="cl-pend">вопрос не задавался</span>';
        }
        return '<span class="cl-pend">ждём ответа</span>';
    }

    function renderRows() {
        var rows = visibleRows();
        var body = document.getElementById('clRows');
        // «из» — строки бара полосы (все точки при «Все бары»), а не всей сети.
        var base = filterRows((state.data || {}).rows, { locationId: selectedLocation() });
        document.getElementById('clCount').textContent = rows.length + ' из ' + base.length;
        var note = barNote();
        var noteEl = document.getElementById('clBarNote');
        if (noteEl) { noteEl.textContent = note; noteEl.hidden = !note; }

        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="6"><div class="cl-empty">'
                + 'За этот месяц открывающих смен с такими условиями нет.'
                + '</div></td></tr>';
            return;
        }

        // Классы на каждой ячейке — не для красоты: на телефоне строка таблицы
        // превращается в карточку (cleanliness.css), и раскладка адресует
        // ячейки по смыслу, а не по nth-child.
        body.innerHTML = rows.map(function (r) {
            var hasPhoto = !!r.photo;
            var photo = hasPhoto
                ? '<img class="cl-thumb" src="/api/cleanliness/photo/' + esc(r.photo)
                    + '" alt="Фото приёмки" data-photo="' + esc(r.photo)
                    + '" data-cap="' + esc(r.employee_name + ' · ' + r.date
                        + ' · ' + (r.location_short || '')) + '">'
                : '<span class="cl-nophoto">&mdash;</span>';
            var when = fmtTime(r.answered_at);
            return '<tr>'
                + '<td class="cl-td-date">' + fmtDate(r.date)
                + (when ? ' <span class="cl-dow">' + esc(when) + '</span>' : '') + '</td>'
                + '<td class="cl-td-venue">' + esc(r.location_short || r.location_name) + '</td>'
                + '<td class="cl-td-who">' + esc(r.employee_name) + '</td>'
                + '<td class="cl-td-st">' + statusCell(r) + '</td>'
                + '<td class="cl-td-note">' + esc(r.note || '') + '</td>'
                + '<td class="cl-td-photo' + (hasPhoto ? '' : ' is-empty') + '">'
                + photo + '</td>'
                + '</tr>';
        }).join('');

        body.querySelectorAll('.cl-thumb[data-photo]').forEach(function (img) {
            img.addEventListener('click', function () {
                openLightbox(img.dataset.photo, img.dataset.cap);
            });
        });
    }

    function renderFoot() {
        document.getElementById('clFoot').textContent =
            'Строка на каждую открывающую смену: бар принимает тот, кто выходит '
            + 'первым. Ответить можно только в день смены — незакрытый день '
            + 'остаётся «не отмечено».';
    }

    // ==================== Просмотр фото ====================

    function openLightbox(name, caption) {
        var box = document.getElementById('clLightbox');
        document.getElementById('clLbImg').src =
            '/api/cleanliness/photo/' + encodeURIComponent(name);
        document.getElementById('clLbCap').textContent = caption || '';
        box.hidden = false;
    }

    function closeLightbox() {
        var box = document.getElementById('clLightbox');
        box.hidden = true;
        document.getElementById('clLbImg').src = '';
    }

    // ==================== Старт ====================

    // Месяц state — из полосы. true — сменился (надо загрузить журнал).
    function syncMonth() {
        var m = stripMonth();
        if (!m) return false;
        var changed = m.year !== state.year || m.month !== state.month;
        state.year = m.year;
        state.month = m.month;
        return changed;
    }

    // Чистые помощники — для Node-проверки (tests/test_cleanliness_strip_runtime.mjs).
    window.CleanlinessView = { locationIdForBar: locationIdForBar, filterRows: filterRows,
                               stripMonth: stripMonth };

    if (typeof document === 'undefined' || !document.getElementById) return;

    document.addEventListener('DOMContentLoaded', function () {
        syncMonth();
        if (strip) {
            // Месяц — другой журнал; бар — те же строки, другая точка (без запроса).
            strip.onChange(function (e) {
                if (e.type === 'period') {
                    if (syncMonth()) load();
                } else if (state.data) {
                    renderTiles();
                    renderRows();
                }
            });
        }
        document.getElementById('clStatus').addEventListener('change', renderRows);
        document.getElementById('clSearch').addEventListener('input', renderRows);

        document.getElementById('clLbClose').addEventListener('click', closeLightbox);
        document.getElementById('clLightbox').addEventListener('click', function (e) {
            if (e.target.id === 'clLightbox') closeLightbox();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeLightbox();
        });

        load();
    });
})();
