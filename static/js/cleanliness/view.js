/* Страница «Чистота» — журнал приёмок бара за месяц.

   Всё считает сервер (core/bar_acceptance.build_journal): строки, пробелы,
   итоги. Здесь только показ, фильтры и просмотр фото. Ни одного правила («кто
   отвечает», «что считать пробелом») в этом файле нет и быть не должно — вторая
   версия правила разъехалась бы с первой.

   Фильтрация — на клиенте: месяц это ~120 строк (4 точки x 30 дней), гонять
   запрос на каждый щелчок фильтра незачем (тот же приём, что в блоке «Касса за
   месяц»). */
(function () {
    'use strict';

    var MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль',
                  'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    var DOW = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

    var state = { year: 0, month: 0, data: null };

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

    // ==================== Загрузка ====================

    function load() {
        var url = '/api/cleanliness/month/' + state.year + '/' + state.month;
        return api(url)
            .then(function (data) {
                state.data = data;
                document.getElementById('clNotice').innerHTML = '';
                renderMonthLabel();
                renderRule();
                renderTiles();
                fillVenues();
                renderRows();
                renderFoot();
            })
            .catch(function (err) {
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

    function renderMonthLabel() {
        document.getElementById('clMonthLabel').textContent =
            MONTHS[state.month - 1] + ' ' + state.year;
    }

    function renderRule() {
        var d = state.data || {};
        var el = document.getElementById('clRule');
        if (!d.rule_from) { el.textContent = ''; return; }
        var p = d.rule_from.split('-');
        el.textContent = 'вопрос задаётся с ' + p[2] + '.' + p[1] + '.' + p[0];
    }

    function renderTiles() {
        var t = (state.data || {}).totals || {};
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

    function fillVenues() {
        var sel = document.getElementById('clVenue');
        var prev = sel.value;
        var locs = (state.data || {}).locations || [];
        sel.innerHTML = '<option value="">Все точки</option>'
            + locs.map(function (l) {
                return '<option value="' + esc(l.id) + '">' + esc(l.short || l.name) + '</option>';
            }).join('');
        // Точка сохраняется при переходе между месяцами, если она там есть.
        if (prev && sel.querySelector('option[value="' + prev + '"]')) sel.value = prev;
    }

    function visibleRows() {
        var rows = (state.data || {}).rows || [];
        var venue = document.getElementById('clVenue').value;
        var status = document.getElementById('clStatus').value;
        var q = (document.getElementById('clSearch').value || '').trim().toLowerCase();
        return rows.filter(function (r) {
            if (venue && String(r.location_id) !== venue) return false;
            if (status === 'not_marked') {
                if (r.problems.indexOf('not_marked') === -1) return false;
            } else if (status && r.status !== status) return false;
            if (q) {
                var hay = (r.employee_name + ' ' + (r.note || '')).toLowerCase();
                if (hay.indexOf(q) === -1) return false;
            }
            return true;
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
        document.getElementById('clCount').textContent =
            rows.length + ' из ' + (((state.data || {}).rows || []).length);

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

    function shiftMonth(delta) {
        var d = new Date(state.year, state.month - 1 + delta, 1);
        state.year = d.getFullYear();
        state.month = d.getMonth() + 1;
        load();
    }

    document.addEventListener('DOMContentLoaded', function () {
        var now = new Date();
        state.year = now.getFullYear();
        state.month = now.getMonth() + 1;

        document.getElementById('clPrev').addEventListener('click', function () { shiftMonth(-1); });
        document.getElementById('clNext').addEventListener('click', function () { shiftMonth(1); });
        ['clVenue', 'clStatus'].forEach(function (id) {
            document.getElementById(id).addEventListener('change', renderRows);
        });
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
