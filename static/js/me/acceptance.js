/* Карточка «Как принял бар?» на личной странице /me.

   Один вопрос на открытии смены: Чисто / Замечания / Плохо. «Чисто» — один тап
   и всё; «Замечания» — строка; «Плохо» — строка и фото. Правила, кто и когда
   отвечает, живут на сервере (core/bar_acceptance.py) — здесь только экран.

   Карточка НЕ знает про window.Schedule и график: она грузит собственный
   /api/cleanliness/today, где сервер сам решает, чья сегодня открывающая смена.
   Продублировать это правило в JS означало бы завести вторую версию «кто
   отвечает за день» — а первая уже решает, кто сдаёт кассу.

   Сбой этой загрузки не гасит остальную страницу и наоборот: тот же принцип
   независимых блоков, что у живой части и снимка (см. view.js).

   Фото уменьшается ЗДЕСЬ, перед отправкой: в прод-образе нет Pillow, а снимок с
   телефона — это 3-5 МБ, из которых для «видно, что бар грязный» нужно 300 КБ.
   canvas отдаёт JPEG независимо от того, что дал телефон (в том числе HEIC),
   поэтому серверу достаточно принимать один формат.

   Подключать ПОСЛЕ common.js (нужен S.escapeHtml / S.showToast). */
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

    var HOST_ID = 'meAcceptance';

    // Уменьшение фото перед отправкой. 1600 px по длинной стороне — на телефоне
    // это всё ещё «видно грязь на кране», а вес падает на порядок.
    var MAX_SIDE = 1600;
    var JPEG_QUALITY = 0.82;

    var data = null;      // последний ответ /api/cleanliness/today
    var draft = null;     // {shiftId, status, photoBlob, photoUrl, keepPhoto}
    var sending = false;

    function esc(s) { return S.escapeHtml(s == null ? '' : String(s)); }

    // ==================== Уменьшение фото ====================

    // Файл -> Blob (JPEG). Если браузер не смог (нет canvas, не декодировал
    // формат) — отдаём исходный файл: пусть решает сервер, он всё равно
    // проверяет сигнатуру и размер. Молча терять фото нельзя.
    function shrinkPhoto(file) {
        return loadBitmap(file).then(function (img) {
            var w = img.width, h = img.height;
            var k = Math.min(1, MAX_SIDE / Math.max(w, h));
            var cw = Math.max(1, Math.round(w * k));
            var ch = Math.max(1, Math.round(h * k));
            var canvas = document.createElement('canvas');
            canvas.width = cw;
            canvas.height = ch;
            canvas.getContext('2d').drawImage(img, 0, 0, cw, ch);
            if (img.close) img.close();
            return new Promise(function (resolve) {
                canvas.toBlob(function (blob) {
                    resolve(blob || file);
                }, 'image/jpeg', JPEG_QUALITY);
            });
        }).catch(function (err) {
            console.warn('[ME/ACC] фото не уменьшилось, шлём как есть', err);
            return file;
        });
    }

    // createImageBitmap с imageOrientation — единственный способ гарантировать,
    // что снимок с телефона не ляжет на бок: EXIF-поворот применяется при
    // декодировании. Где его нет — обычный <img> (современные браузеры
    // применяют ориентацию и к нему).
    function loadBitmap(file) {
        if (window.createImageBitmap) {
            try {
                return createImageBitmap(file, { imageOrientation: 'from-image' })
                    .catch(function () { return loadViaImg(file); });
            } catch (e) { /* старая сигнатура без options — вниз, на <img> */ }
        }
        return loadViaImg(file);
    }

    function loadViaImg(file) {
        return new Promise(function (resolve, reject) {
            var url = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
            img.src = url;
        });
    }

    // ==================== Отправка ====================

    // Своя отправка, а не S.api: там тело всегда JSON, а здесь multipart с файлом.
    // Разбор ошибки — тот же (поле error), чтобы бармен видел серверный текст.
    function postForm(url, formData) {
        return fetch(url, { method: 'POST', body: formData, credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) {
                    return res.json().catch(function () { return {}; })
                        .then(function (d) { throw new Error(d.error || ('HTTP ' + res.status)); });
                }
                return res.json();
            });
    }

    function submit(shiftId, status, note, photoBlob, keepPhoto) {
        if (sending) return;
        sending = true;
        setBusy(true);
        var fd = new FormData();
        fd.append('status', status);
        if (note) fd.append('note', note);
        if (photoBlob) fd.append('photo', photoBlob, 'photo.jpg');
        if (keepPhoto) fd.append('keep_photo', '1');
        postForm('/api/cleanliness/shift/' + shiftId, fd)
            .then(function () {
                draft = null;
                S.showToast('Приёмка отмечена');
                return load();
            })
            .catch(function (err) {
                setBusy(false);
                showError(err.message);
            })
            .then(function () { sending = false; });
    }

    // ==================== Разметка ====================

    function fmtTime(iso) {
        if (!iso) return '';
        var m = String(iso).match(/T(\d{2}):(\d{2})/);
        return m ? m[1] + ':' + m[2] : '';
    }

    function shiftMeta(shift) {
        var parts = [];
        if (shift.location_short || shift.location_name) {
            parts.push(shift.location_short || shift.location_name);
        }
        if (shift.start_time) parts.push('старт ' + shift.start_time);
        return parts.join(' · ');
    }

    // Уже отвечено: компактная строка. Она остаётся на экране весь день —
    // и как подтверждение «я отметил», и как вход в правку.
    function answeredHtml(item) {
        var acc = item.acceptance;
        var shift = item.shift;
        var photo = acc.photo
            ? '<a class="me-acc-thumb" href="/api/cleanliness/photo/' + esc(acc.photo)
                + '" target="_blank" rel="noopener">'
                + '<img src="/api/cleanliness/photo/' + esc(acc.photo) + '" alt="Фото приёмки"></a>'
            : '';
        return '<div class="me-acc-card is-done is-' + esc(acc.status) + '">'
            + '<div class="me-acc-done-row">'
            + '<span class="me-acc-st is-' + esc(acc.status) + '">' + esc(acc.status_label) + '</span>'
            + '<span class="me-acc-when">' + esc(shiftMeta(shift))
            + (fmtTime(acc.answered_at) ? ' · ' + esc(fmtTime(acc.answered_at)) : '')
            + (acc.edited ? ' · изменено' : '') + '</span>'
            + '</div>'
            + (acc.note ? '<div class="me-acc-note-txt">' + esc(acc.note) + '</div>' : '')
            + photo
            + '<button type="button" class="me-acc-edit" data-edit="' + esc(shift.id) + '">изменить</button>'
            + '</div>';
    }

    // Ещё не отвечено: сам вопрос. Три кнопки — один тап на «Чисто», остальные
    // раскрывают форму.
    function questionHtml(item) {
        var shift = item.shift;
        return '<div class="me-acc-card">'
            + '<div class="me-acc-q">Как принял бар?</div>'
            + '<div class="me-acc-meta">' + esc(shiftMeta(shift)) + '</div>'
            + '<div class="me-acc-btns" data-shift="' + esc(shift.id) + '">'
            + '<button type="button" class="me-acc-b is-clean" data-st="clean">Чисто</button>'
            + '<button type="button" class="me-acc-b is-issues" data-st="issues">Замечания</button>'
            + '<button type="button" class="me-acc-b is-bad" data-st="bad">Плохо</button>'
            + '</div>'
            + '<div class="me-acc-form" hidden></div>'
            + '</div>';
    }

    // Форма под кнопкой: строка «что не так» + фото (обязательное у «Плохо»).
    function formHtml(status, keepPhoto) {
        var isBad = status === 'bad';
        var maxLen = (data && data.note_max_len) || 200;
        var photoHint = isBad
            ? 'Фото обязательно: без него это слово против слова'
            : 'Фото по желанию';
        return '<label class="me-acc-flbl" for="meAccNote">'
            + (isBad ? 'Что не так' : 'Что не так — одной строкой') + '</label>'
            + '<input type="text" id="meAccNote" class="me-acc-note" maxlength="' + maxLen + '"'
            + ' autocomplete="off" placeholder="напр. краны не промыты, стойка липкая">'
            + '<div class="me-acc-photo">'
            + '<label class="me-acc-file">'
            + '<input type="file" id="meAccPhoto" accept="image/*" hidden>'
            + '<span class="me-acc-file-t">' + (keepPhoto ? 'Заменить фото' : 'Добавить фото') + '</span>'
            + '</label>'
            + '<span class="me-acc-photo-h">' + photoHint + '</span>'
            + '</div>'
            + '<div class="me-acc-preview" id="meAccPreview"' + (keepPhoto ? '' : ' hidden') + '></div>'
            + '<div class="me-acc-err" id="meAccErr" hidden></div>'
            + '<div class="me-acc-acts">'
            + '<button type="button" class="me-acc-send" id="meAccSend">Отправить</button>'
            + '<button type="button" class="me-acc-cancel" id="meAccCancel">Отмена</button>'
            + '</div>';
    }

    // ==================== Рендер и события ====================

    function host() { return document.getElementById(HOST_ID); }

    function render() {
        var el = host();
        if (!el) return;
        if (!data || data.status !== 'ok' || !data.items.length) {
            el.innerHTML = '';
            return;
        }
        var html = '<div class="me-acc">'
            + '<div class="me-acc-lbl">ПРИЁМКА БАРА</div>';
        data.items.forEach(function (item) {
            html += item.acceptance ? answeredHtml(item) : questionHtml(item);
        });
        el.innerHTML = html + '</div>';
        wire();
    }

    function wire() {
        var el = host();
        el.querySelectorAll('.me-acc-b[data-st]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var shiftId = btn.parentNode.dataset.shift;
                var st = btn.dataset.st;
                // «Чисто» — ничего вводить не надо, отправляем сразу: вопрос на
                // открытии смены должен закрываться одним тапом.
                if (st === 'clean') { submit(shiftId, 'clean', '', null, false); return; }
                openForm(shiftId, st);
            });
        });
        el.querySelectorAll('.me-acc-edit[data-edit]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = itemById(btn.dataset.edit);
                if (!item) return;
                // Правка: карточку возвращаем в состояние вопроса, а прежние
                // ответ и фото подставляем — переснимать из-за опечатки не надо.
                var acc = item.acceptance;
                item.acceptance = null;
                render();
                if (acc.status !== 'clean') {
                    openForm(item.shift.id, acc.status, acc.note, acc.photo);
                }
            });
        });
    }

    function itemById(shiftId) {
        var found = null;
        (data.items || []).forEach(function (i) {
            if (String(i.shift.id) === String(shiftId)) found = i;
        });
        return found;
    }

    // keptPhoto — имя УЖЕ сохранённого файла (правка прежнего ответа): его
    // показываем в превью и досылаем флагом keep_photo, чтобы правка опечатки в
    // тексте не требовала переснимать фотографию.
    function openForm(shiftId, status, note, keptPhoto) {
        var card = host().querySelector('.me-acc-btns[data-shift="' + shiftId + '"]');
        if (!card) return;
        var wrap = card.parentNode.querySelector('.me-acc-form');
        var same = draft && draft.shiftId === String(shiftId);
        var prevBlob = same ? draft.photoBlob : null;
        var keptName = same ? draft.keptPhoto : (keptPhoto || null);
        var prevKeep = !prevBlob && !!keptName;
        draft = { shiftId: String(shiftId), status: status, photoBlob: prevBlob,
                  keepPhoto: prevKeep, keptPhoto: keptName };
        wrap.innerHTML = formHtml(status, prevKeep);
        wrap.hidden = false;

        card.querySelectorAll('.me-acc-b').forEach(function (b) {
            b.classList.toggle('is-on', b.dataset.st === status);
        });

        var noteEl = document.getElementById('meAccNote');
        if (note) noteEl.value = note;
        noteEl.focus();

        document.getElementById('meAccPhoto').addEventListener('change', onPhotoPick);
        document.getElementById('meAccSend').addEventListener('click', onSend);
        document.getElementById('meAccCancel').addEventListener('click', function () {
            draft = null;
            load();
        });
        if (prevBlob) showPreview(URL.createObjectURL(prevBlob));
        else if (prevKeep) showPreview('/api/cleanliness/photo/' + encodeURIComponent(keptName));
    }

    function onPhotoPick(e) {
        var file = e.target.files && e.target.files[0];
        if (!file) return;
        showError('');
        showPreviewText('готовлю фото…');
        shrinkPhoto(file).then(function (blob) {
            if (!draft) return;
            draft.photoBlob = blob;
            draft.keepPhoto = false;   // новое фото заменяет прежнее
            showPreview(URL.createObjectURL(blob));
        });
    }

    function showPreview(url) {
        var el = document.getElementById('meAccPreview');
        if (!el) return;
        el.hidden = false;
        el.innerHTML = '<img src="' + url + '" alt="Фото приёмки">';
    }

    function showPreviewText(text) {
        var el = document.getElementById('meAccPreview');
        if (!el) return;
        el.hidden = false;
        el.innerHTML = '<span class="me-acc-prev-t">' + esc(text) + '</span>';
    }

    function onSend() {
        if (!draft) return;
        var note = (document.getElementById('meAccNote').value || '').trim();
        if (!note) { showError('Напишите одной строкой, что не так'); return; }
        if (draft.status === 'bad' && !draft.photoBlob && !draft.keepPhoto) {
            showError('Для ответа «Плохо» нужно фото');
            return;
        }
        submit(draft.shiftId, draft.status, note, draft.photoBlob, draft.keepPhoto);
    }

    function showError(text) {
        var el = document.getElementById('meAccErr');
        if (!el) return;
        el.hidden = !text;
        el.textContent = text || '';
    }

    function setBusy(on) {
        var el = host();
        if (el) el.classList.toggle('is-busy', !!on);
        var send = document.getElementById('meAccSend');
        if (send) { send.disabled = on; send.textContent = on ? 'отправляю…' : 'Отправить'; }
    }

    // ==================== Загрузка ====================

    function load() {
        return S.api('/api/cleanliness/today')
            .then(function (res) {
                data = res;
                setBusy(false);
                render();
            })
            .catch(function (err) {
                // Карточка — не единственное на странице: молча гасим блок и
                // пишем в консоль, вместо того чтобы пугать бармена ошибкой про
                // приёмку, когда он пришёл смотреть смену.
                console.error('[ME/ACC] не загрузилось', err);
                var el = host();
                if (el) el.innerHTML = '';
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!host()) return;   // страница без блока — молча ничего не делаем
        load();
        // Вернулся в таб — перечитываем: приёмку мог отметить он же с другого
        // устройства, и два «Чисто» подряд выглядели бы как поломка.
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden && !draft) load();
        });
    });

    window.Me = window.Me || {};
    window.Me.acceptance = { load: load };
})();
