/* kultura.research — страница вопросов боту (/research, routes/research.py, kultura_bot/web.py).
 *
 * Свой минималистичный дизайн (решение владельца 2026-11-09, static/research.css): беседы — панелью, которая
 * выезжает слева по кнопке; пустая беседа — логотип, который набирается (static/logo.js, вид research), поле
 * и три сложных готовых вопроса с подсказками (нажатие задаёт вопрос сразу); в беседе поле прижато книзу.
 * В поле: скрепка (файлы: картинки, PDF, Excel, CSV, текст — ещё перетаскиванием на поле и вставкой картинки)
 * и молния быстрого режима слева (подсказка — при наведении, на телефоне — сообщением), глубина ответа справа —
 * «Ответ» или «Исследование», меню как выбор усилия у моделей. Файлы уходят вместе с вопросом (base64 в JSON),
 * их хранит сайт и показывает только тому, кто их приложил. Вопрос уходит в очередь сайта; отвечает сервер бота в Амстердаме тем же кодом,
 * что в Telegram. Пока вопрос в работе, страница раз в POLL_MS спрашивает его состояние: переливающаяся
 * строка, шкала и «что делаю сейчас» (строки хода работы сервера бота), а кнопка «Спросить» становится
 * «Остановить». Готов — ответ, свёрнутое «Как считается», графики (TgChart, как «Открыть интерактивно»),
 * отчёт (TgReport) и расход. Кнопок следующего шага («[[…]]» под ответом) нет — решение владельца.
 *
 * Тексты — только textContent; HTML вставляется лишь из полей *_html, которые собрал сервер
 * (kultura_bot/engine/formatting.to_html: всё экранировано, разметка своя — b, i, code, pre, a, blockquote).
 * Беседа в адресе — ?t=<id>. */
(function () {
  'use strict';

  const POLL_MS = 2000;
  const LIST_EVERY_MS = 15000;
  const root = document.getElementById('rsRoot');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const els = {
    side: $('rsSide'), sideClose: $('rsSideClose'), sideToggle: $('rsSideToggle'), scrim: $('rsScrim'),
    threads: $('rsThreads'), threadsEmpty: $('rsThreadsEmpty'), newBtn: $('rsNew'), newTop: $('rsNewTop'),
    main: $('rsMain'), title: $('rsTitle'), headActions: $('rsHeadActions'), del: $('rsDelete'),
    feed: $('rsFeed'), form: $('rsForm'), engine: $('rsEngine'), input: $('rsInput'),
    effortBtn: $('rsEffortBtn'), effortMenu: $('rsEffortMenu'), effortLabel: $('rsEffortLabel'),
    fast: $('rsFast'), fastTip: $('rsFastTip'), send: $('rsSend'), error: $('rsError'), info: $('rsInfo'), infoOpen: $('rsInfoOpen'),
    infoClose: $('rsInfoClose'), toast: $('rsToast'), suggest: $('rsSuggest'),
    files: $('rsFiles'), attach: $('rsAttach'), fileInput: $('rsFileInput'),
    logo: document.querySelector('#rsStart [data-kultura-logo]'),
  };
  const state = {
    threads: [], current: null, questions: [], mode: 'answer', sending: false, pollTimer: 0, listAt: 0, files: [],
    mounted: [], fonts: null,
  };

  /* ---------------- запросы ---------------- */

  function request(method, url, body) {
    const opts = { method, cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(async resp => {
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 401) window.location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search);
      if (!resp.ok) throw new Error(data.error || ('Ошибка сервера ' + resp.status));
      return data;
    });
  }
  const API = {
    threads: () => request('GET', '/api/research/threads'),
    thread: id => request('GET', '/api/research/threads/' + encodeURIComponent(id)),
    remove: id => request('DELETE', '/api/research/threads/' + encodeURIComponent(id)),
    ask: body => request('POST', '/api/research/ask', body),
    question: id => request('GET', '/api/research/questions/' + encodeURIComponent(id)),
    stop: id => request('POST', '/api/research/questions/' + encodeURIComponent(id) + '/stop', {}),
  };

  /* ---------------- мелочи ---------------- */

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function html(tag, cls, markup) {
    // Только HTML, собранный сервером (formatting.to_html): ссылки — в новой вкладке.
    const e = el(tag, cls);
    e.innerHTML = (markup || '').replace(/(<\/blockquote>|<\/pre>)\n/g, '$1');
    for (const a of e.querySelectorAll('a[href]')) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    return e;
  }
  function svg(paths, cls) {
    const ns = 'http://www.w3.org/2000/svg';
    const s = document.createElementNS(ns, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('aria-hidden', 'true');
    if (cls) s.setAttribute('class', cls);
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', paths);
    s.append(p);
    return s;
  }
  let toastTimer = 0;
  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 2600);
  }
  function showError(msg) {
    els.error.textContent = msg || '';
    els.error.hidden = !msg;
  }
  function plural(n, forms) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  }
  const MSK = { timeZone: 'Europe/Moscow' };
  function dayKey(d) { return d.toLocaleDateString('ru-RU', MSK); }
  function when(iso) {
    const d = new Date(iso || '');
    if (isNaN(d)) return '';
    const time = d.toLocaleTimeString('ru-RU', Object.assign({ hour: '2-digit', minute: '2-digit' }, MSK));
    if (dayKey(d) === dayKey(new Date())) return time;
    return d.toLocaleDateString('ru-RU', Object.assign({ day: 'numeric', month: 'short' }, MSK)) + ', ' + time;
  }
  function group(iso) {
    const d = new Date(iso || '');
    if (isNaN(d)) return 'Ранее';
    const now = new Date();
    if (dayKey(d) === dayKey(now)) return 'Сегодня';
    if (dayKey(d) === dayKey(new Date(now.getTime() - 864e5))) return 'Вчера';
    if (now - d < 7 * 864e5) return 'Последние 7 дней';
    return 'Ранее';
  }
  function fontsReady() {
    if (!state.fonts) state.fonts = window.TgChart ? window.TgChart.fontsReady() : Promise.resolve();
    return state.fonts;
  }
  function setUrl(threadId, push) {
    const url = threadId ? '/research?t=' + encodeURIComponent(threadId) : '/research';
    if (url === location.pathname + location.search) return;
    (push ? history.pushState : history.replaceState).call(history, { t: threadId || null }, '', url);
  }
  function active() { return state.questions.find(q => q.active) || null; }

  /* ---------------- беседы ---------------- */

  function renderThreads() {
    els.threads.textContent = '';
    let last = '';
    for (const t of state.threads) {
      const g = group(t.last_at);
      if (g !== last) { els.threads.append(el('div', 'rx-group', g)); last = g; }
      const b = el('button', 'rx-thread');
      b.type = 'button';
      b.title = t.title || '';
      b.setAttribute('aria-current', t.id === state.current ? 'true' : 'false');
      b.append(el('span', 'rx-thread-title', t.title || 'Без вопроса'));
      if (t.active) b.append(el('span', 'rx-thread-live'));
      b.addEventListener('click', () => { closeSide(); if (t.id !== state.current) openThread(t.id, true); });
      els.threads.append(b);
    }
    els.threadsEmpty.hidden = state.threads.length > 0;
  }
  function sideOpen() { return root.classList.contains('is-side-open'); }
  function openSide() {
    root.classList.add('is-side-open');
    els.scrim.hidden = false;
    els.sideToggle.setAttribute('aria-expanded', 'true');
    // Фокус — в панель: на открытую беседу, иначе на «Новая беседа» (клавиатура и экранный диктор).
    const target = els.threads.querySelector('[aria-current="true"]') || els.newBtn;
    requestAnimationFrame(() => target.focus({ preventScroll: true }));
  }
  function closeSide(back) {
    const was = sideOpen();
    root.classList.remove('is-side-open');
    els.scrim.hidden = true;
    els.sideToggle.setAttribute('aria-expanded', 'false');
    if (was && back) els.sideToggle.focus({ preventScroll: true });
  }
  function renderEngine(engine) {
    const text = engine && !engine.ok ? engine.text : '';
    els.engine.textContent = text || '';
    els.engine.hidden = !text;
  }
  function loadThreads() {
    state.listAt = Date.now();
    return API.threads().then(data => {
      state.threads = data.threads || [];
      renderThreads();
      renderEngine(data.engine);
      return data;
    }).catch(err => showError(err.message));
  }

  /* ---------------- беседа ---------------- */

  function clearFeed() {
    for (const m of state.mounted) { try { if (m.destroy) m.destroy(); } catch (e) { /* уже убран */ } }
    state.mounted = [];
    els.feed.textContent = '';
  }
  function setEmpty(empty) {
    const was = els.main.classList.contains('is-empty');
    els.main.classList.toggle('is-empty', empty);
    els.del.hidden = empty || !state.current;
    if (els.newTop) els.newTop.hidden = empty;
    // Беседа снова пустая — логотип набирается заново (при открытии страницы его начал static/logo.js).
    if (empty && !was && window.KulturaLogo && els.logo) window.KulturaLogo.play(els.logo);
  }
  function setTitle() {
    const first = state.questions[0];
    els.title.textContent = first ? first.question.replace(/\s+/g, ' ').slice(0, 160) : '';
    document.title = first ? els.title.textContent.slice(0, 60) + ' — kultura.research' : 'kultura.research';
  }

  function newThread(push, focus) {
    clearTimeout(state.pollTimer);
    state.current = null;
    state.questions = [];
    clearFeed();
    resetDelete();
    setTitle();
    setEmpty(true);
    setUrl(null, push);
    renderThreads();
    syncComposer();
    if (focus) els.input.focus();            // не при открытии страницы: на телефоне выскочила бы клавиатура
  }

  function openThread(id, push) {
    showError('');
    return API.thread(id).then(data => {
      state.current = id;
      state.questions = data.thread.questions || [];
      setUrl(id, push);
      renderThread();
      renderThreads();
      schedulePoll();
    }).catch(err => {
      showError(err.message);
      newThread(false);
    });
  }

  function renderThread() {
    clearFeed();
    resetDelete();
    setTitle();
    setEmpty(state.questions.length === 0);
    for (const q of state.questions) els.feed.append(renderTurn(q));
    syncComposer();
    // К началу последнего вопроса — когда графики уже нарисованы (они ждут те же шрифты, раньше в очереди).
    const last = els.feed.lastElementChild;
    if (last) fontsReady().then(() => requestAnimationFrame(() => last.scrollIntoView({ block: 'start' })));
  }

  // Файлы вопроса в ленте: картинка — миниатюрой, остальное — значком с именем; открываются в новой вкладке
  // (сайт отдаёт файл только тому, кто его приложил).
  function questionFiles(files) {
    const box = el('div', 'rx-q-files');
    for (const f of files) {
      const a = el('a', 'rx-q-file' + (f.kind === 'image' ? ' is-image' : ''));
      a.href = f.url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.title = f.name;
      if (f.kind === 'image') {
        const img = el('img');
        img.src = f.url;
        img.alt = f.name;
        img.loading = 'lazy';
        a.append(img);
      } else {
        a.append(el('span', 'rx-file-badge', badge(f.name)), el('span', 'rx-file-name', f.name),
          el('span', 'rx-file-size', bytes(f.size)));
      }
      box.append(a);
    }
    return box;
  }

  function renderTurn(q) {
    const turn = el('article', 'rx-turn');
    turn.dataset.id = q.id;
    const ask = el('div', 'rx-q');
    const tags = [q.mode === 'report' ? 'ИССЛЕДОВАНИЕ' : '', q.fast ? 'БЫСТРО' : ''].filter(Boolean);
    if (tags.length) ask.append(el('div', 'rx-q-meta', tags.join(' · ')));
    ask.append(el('div', 'rx-q-text', q.question));
    if (q.files && q.files.length) ask.append(questionFiles(q.files));
    turn.append(ask);
    const answer = el('div', 'rx-a');
    turn.append(answer);
    fillAnswer(answer, q);
    return turn;
  }

  // Строки хода работы сервера бота (kultura_bot/engine/progress.Tracker.render):
  // «Собираю отчёт · 0:42», «▰▰▰▱▱▱▱▱▱▱ ≈ 2 мин осталось», «Сейчас: …», «Сделано: …».
  function parseProgress(text) {
    const lines = String(text || '').split('\n').map(s => s.trim()).filter(Boolean);
    const out = { title: '', clock: '', fraction: null, left: '', rest: [] };
    if (!lines.length) return out;
    const head = lines[0].split(' · ');
    out.title = head[0];
    if (head.length > 1) out.clock = head[head.length - 1];
    for (const line of lines.slice(1)) {
      const m = out.fraction === null ? line.match(/^([▰▱]+)\s*(.*)$/) : null;
      if (m) {
        out.fraction = (m[1].match(/▰/g) || []).length / m[1].length;
        out.left = m[2];
      } else {
        out.rest.push(line);
      }
    }
    return out;
  }

  function runBox(q) {
    const box = el('div', 'rx-run');
    const head = el('div', 'rx-run-head');
    head.append(el('span', 'rx-dot'));
    let p = { title: '', clock: '', fraction: null, left: '', rest: [] };
    if (q.status === 'queued') {
      head.append(el('span', 'rx-shimmer', 'В очереди'));
      box.append(head, el('div', 'rx-run-line', 'Сервер бота возьмёт вопрос, когда освободится.'));
    } else if (q.status === 'taken' || !q.progress) {
      head.append(el('span', 'rx-shimmer', 'Начинаю…'));
      box.append(head);
    } else {
      p = parseProgress(q.progress);
      head.append(el('span', 'rx-shimmer', p.title || 'Отвечаю'));
      if (p.clock) head.append(el('span', 'rx-clock', p.clock));
      box.append(head);
      if (p.fraction !== null) {
        const meter = el('div', 'rx-meter');
        const fill = el('span');
        fill.style.width = Math.max(4, Math.round(p.fraction * 100)) + '%';
        meter.append(fill);
        box.append(meter);
      }
      if (p.left) box.append(el('div', 'rx-run-line', p.left));
      for (const line of p.rest) box.append(el('div', 'rx-run-line' + (/^Сделано:/.test(line) ? ' is-mono' : ''), line));
    }
    if (q.stopping) box.append(el('div', 'rx-run-line', 'Останавливаю: шаг, который уже идёт, дойдёт до конца…'));
    return box;
  }

  function costLine(cost) {
    if (!cost || !cost.steps) return '';
    let line = '$' + Number(cost.usd || 0).toFixed(2) + ' · ' + cost.steps + ' ' +
      plural(cost.steps, ['запрос', 'запроса', 'запросов']) + ' к модели';
    if (cost.fast_steps) line += ' · быстрых ' + cost.fast_steps + ', цена ×2';
    return line;
  }

  function fillAnswer(box, q) {
    box.textContent = '';
    if (q.active) { box.append(runBox(q)); return; }
    const meta = el('div', 'rx-meta-line');
    const cost = costLine(q.cost);
    if (cost) meta.append(el('span', null, cost));
    if (q.finished_at) meta.append(el('span', null, when(q.finished_at)));
    if (q.status !== 'done') {
      box.append(el('div', 'rx-fail' + (q.status === 'error' ? ' is-error' : ''),
        q.shown || (q.status === 'stopped' ? 'Остановлено.' : 'Ответа нет.')));
      if (meta.childElementCount) box.append(meta);
      return;
    }
    if (q.notice) box.append(el('div', 'rx-notice', q.notice));
    const later = [];
    for (const card of q.cards || []) {
      if (card.kind === 'chart') box.append(chartCard(card, later));
      else if (card.kind === 'report') box.append(reportCard(card, later));
    }
    if (q.answer_html) box.append(html('div', 'rx-prose', q.answer_html));
    if (q.how_html) {
      const fold = el('details', 'rx-how');
      const sum = el('summary');
      sum.append(svg('M9 6l6 6-6 6', 'rx-how-chev'), document.createTextNode('Как считается'));
      fold.append(sum, html('div', 'rx-prose rx-prose-sm', q.how_html));
      box.append(fold);
    }
    if (meta.childElementCount) box.append(meta);
    if (later.length) fontsReady().then(() => later.forEach(fn => fn()));
  }

  function chartCard(card, later) {
    const wrap = el('div', 'rx-card');
    if (card.caption_html) wrap.append(html('div', 'rx-prose', card.caption_html));
    const box = el('div');
    wrap.append(box);
    later.push(() => {
      if (!window.TgChart) { box.append(el('p', 'rx-notice', 'График не загрузился.')); return; }
      const howNode = card.how_html ? html('div', 'rep-text', card.how_html) : null;
      state.mounted.push(window.TgChart.mount(box, card.spec, { mode: 'app', toast, howNode }));
    });
    return wrap;
  }

  function reportCard(card, later) {
    const wrap = el('div', 'rx-report');
    const box = el('div');
    wrap.append(box);
    if (card.page) {
      const foot = el('div', 'rx-report-foot');
      const a = el('a', null, 'Открыть отдельной страницей');
      a.href = card.page;
      a.target = '_blank';
      a.rel = 'noopener';
      foot.append(a, el('span', null, 'там же — ссылка для браузера'));
      wrap.append(foot);
    }
    later.push(() => {
      if (!window.TgReport) { box.append(el('p', 'rx-notice', 'Отчёт не загрузился.')); return; }
      state.mounted.push(window.TgReport.mount(box, card.view, { toast }));
    });
    return wrap;
  }

  function updateQuestion(q) {
    if (!q) return;
    const i = state.questions.findIndex(x => x.id === q.id);
    if (i < 0) return;
    const before = state.questions[i];
    state.questions[i] = q;
    const turn = els.feed.querySelector('article[data-id="' + CSS.escape(q.id) + '"]');
    if (!turn) return;
    if (before.status !== q.status || before.progress !== q.progress || before.stopping !== q.stopping) {
      fillAnswer(turn.querySelector('.rx-a'), q);
    }
    if (before.active && !q.active) {
      loadThreads();
      turn.querySelector('.rx-a').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    syncComposer();
  }

  /* ---------------- опрос ---------------- */

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    if (!active()) return;
    state.pollTimer = setTimeout(poll, POLL_MS);
  }
  function poll() {
    const running = state.questions.filter(q => q.active);
    if (!running.length) return;
    if (document.hidden) { schedulePoll(); return; }
    Promise.all(running.map(q => API.question(q.id).then(d => updateQuestion(d.question)).catch(() => {})))
      .then(() => {
        if (Date.now() - state.listAt > LIST_EVERY_MS) loadThreads();
        schedulePoll();
      });
  }

  /* ---------------- вопрос ---------------- */

  function syncComposer() {
    const running = active();
    const stop = !!running;
    els.send.classList.toggle('is-stop', stop);
    els.send.setAttribute('aria-label', stop ? 'Остановить' : 'Спросить');
    els.send.title = stop ? 'Остановить' : 'Спросить';
    els.send.disabled = stop ? !!running.stopping : (state.sending || !els.input.value.trim());
  }

  function grow() {
    els.input.style.height = 'auto';
    els.input.style.height = Math.min(els.input.scrollHeight, Math.round(window.innerHeight * 0.4)) + 'px';
  }

  // typed — вопрос из поля: после отправки поле очищается; готовый вопрос набранный текст не трогает.
  async function ask(text, typed) {
    const question = (text || '').trim();
    if (!question || state.sending || active()) return;
    showError('');
    state.sending = true;
    syncComposer();
    const body = { question, mode: state.mode, fast: !!(els.fast && els.fast.getAttribute('aria-pressed') === 'true') };
    if (state.current) body.thread_id = state.current;
    const attached = typed ? state.files.slice() : [];         // готовый вопрос — без файлов: он о данных сети
    try {
      if (attached.length) body.files = await Promise.all(attached.map(async f => ({ name: f.name, data: await base64Of(f.file) })));
    } catch (err) {
      showError(err.message);
      state.sending = false;
      syncComposer();
      return;
    }
    return API.ask(body).then(data => {
      const q = data.question;
      if (q.thread_id !== state.current) {
        state.current = q.thread_id;
        state.questions = [];
        clearFeed();
        setUrl(q.thread_id, true);
      }
      state.questions.push(q);
      setTitle();
      setEmpty(false);
      const turn = renderTurn(q);
      els.feed.append(turn);
      requestAnimationFrame(() => turn.scrollIntoView({ block: 'start', behavior: 'smooth' }));
      if (typed) {
        els.input.value = '';
        grow();
        clearFiles(attached);                                   // ушедшие с вопросом; добавленные за это время — остаются
      }
      if (els.fast) els.fast.setAttribute('aria-pressed', 'false');     // быстрый режим — только для этого вопроса
      loadThreads();
      schedulePoll();
    }).catch(err => showError(err.message)).finally(() => {
      state.sending = false;
      syncComposer();
    });
  }

  function stop() {
    const running = active();
    if (!running || running.stopping) return;
    els.send.disabled = true;
    API.stop(running.id).then(data => updateQuestion(data.question)).catch(err => { toast(err.message); syncComposer(); });
  }

  /* ---------------- удаление беседы ---------------- */

  function resetDelete() {
    els.headActions.textContent = '';
    els.headActions.append(els.del);
    if (els.newTop) els.headActions.append(els.newTop);
    els.del.hidden = !state.current;
  }
  els.del.addEventListener('click', () => {
    const id = state.current;
    if (!id) return;
    els.headActions.textContent = '';
    els.headActions.append(el('span', 'rx-confirm', 'Удалить беседу?'));
    const yes = el('button', 'rx-pill rx-pill-danger', 'Удалить');
    yes.type = 'button';
    const no = el('button', 'rx-pill', 'Отмена');
    no.type = 'button';
    no.addEventListener('click', resetDelete);
    yes.addEventListener('click', () => {
      yes.disabled = true;
      API.remove(id).then(() => {
        state.threads = state.threads.filter(t => t.id !== id);
        newThread(true);
        toast('Беседа удалена');
      }).catch(err => { yes.disabled = false; toast(err.message); });
    });
    els.headActions.append(yes, no);
  });

  /* ---------------- поле вопроса ---------------- */

  /* глубина ответа: кнопка справа и меню, как выбор усилия у моделей */

  const effortItems = [...els.effortMenu.querySelectorAll('[data-mode]')];
  function effortOpen() { return !els.effortMenu.hidden; }
  function setMode(mode) {
    state.mode = mode;
    for (const item of effortItems) item.setAttribute('aria-checked', item.dataset.mode === mode ? 'true' : 'false');
    const current = effortItems.find(item => item.dataset.mode === mode);
    if (current) els.effortLabel.textContent = current.dataset.label;
    els.effortBtn.dataset.mode = mode;
  }
  function openEffort() {
    els.effortMenu.hidden = false;
    els.effortBtn.setAttribute('aria-expanded', 'true');
    // Вниз, если там хватает места (пустая беседа), иначе вверх (поле прижато к низу).
    const r = els.effortBtn.getBoundingClientRect();
    const h = els.effortMenu.offsetHeight;
    els.effortMenu.classList.toggle('is-up', window.innerHeight - r.bottom < h + 16 && r.top > h + 16);
    (effortItems.find(item => item.getAttribute('aria-checked') === 'true') || effortItems[0]).focus();
  }
  function closeEffort(back) {
    if (!effortOpen()) return;
    els.effortMenu.hidden = true;
    els.effortBtn.setAttribute('aria-expanded', 'false');
    if (back) els.effortBtn.focus();
  }
  els.effortBtn.addEventListener('click', () => (effortOpen() ? closeEffort() : openEffort()));
  effortItems.forEach((item, i) => {
    item.addEventListener('click', () => { setMode(item.dataset.mode); closeEffort(true); });
    item.addEventListener('keydown', e => {
      const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0;
      if (step) {
        e.preventDefault();
        effortItems[(i + step + effortItems.length) % effortItems.length].focus();
      } else if (e.key === 'Tab') {
        closeEffort();
      }
    });
  });
  document.addEventListener('click', e => {
    if (effortOpen() && !e.target.closest('#rsEffort')) closeEffort();
  });

  /* быстрый режим: молния; подсказка — при наведении, на телефоне (наведения нет) — сообщением */

  const noHover = window.matchMedia && window.matchMedia('(hover: none)').matches;
  if (els.fast) {
    els.fast.addEventListener('click', () => {
      const on = els.fast.getAttribute('aria-pressed') !== 'true';
      els.fast.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on && noHover && els.fastTip) toast(els.fastTip.textContent.replace(/\s+/g, ' ').trim());
    });
  }
  els.form.addEventListener('submit', e => {
    e.preventDefault();
    if (active()) stop(); else ask(els.input.value, true);
  });
  els.input.addEventListener('input', () => { grow(); syncComposer(); });
  els.input.addEventListener('keydown', e => {
    // Enter — отправить, Shift+Enter — новая строка (как в чатах моделей); во время набора иероглифов — нет.
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!active()) ask(els.input.value, true);
    }
  });

  /* ---------------- файлы к вопросу ---------------- */

  // Пределы — с сервера (kultura_bot/settings.py, WEB_FILES_*); тип сайт ещё раз проверит по содержимому.
  const LIMITS = { count: +root.dataset.filesMax || 5, file: +root.dataset.fileMax || 10485760,
    total: +root.dataset.filesTotal || 20971520 };
  const EXT_KIND = { jpg: 'image', jpeg: 'image', png: 'image', webp: 'image', gif: 'image', pdf: 'pdf',
    xlsx: 'table', csv: 'table', tsv: 'table', txt: 'text', md: 'text', json: 'text' };
  const ACCEPTED = 'Понимаю картинки (JPEG, PNG, WebP, GIF), PDF, Excel (.xlsx), CSV и текст.';
  const PLACEHOLDER = els.input.placeholder;
  let fileSeq = 0;

  function extOf(name) { const m = /\.([A-Za-z0-9]{1,5})$/.exec(name || ''); return m ? m[1].toLowerCase() : ''; }
  function badge(name) { return (extOf(name) || 'файл').toUpperCase().slice(0, 4); }
  function bytes(n) {
    if (n >= 1048576) return (n / 1048576).toFixed(1).replace('.', ',') + ' МБ';
    return Math.max(1, Math.round(n / 1024)) + ' КБ';
  }
  function kindOf(file) {
    const kind = EXT_KIND[extOf(file.name)];
    if (kind) return kind;
    if (/^image\/(jpeg|png|webp|gif)$/.test(file.type)) return 'image';
    return file.type === 'application/pdf' ? 'pdf' : '';
  }
  function base64Of(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',', 2)[1] || '');
      reader.onerror = () => reject(new Error('Файл «' + file.name + '» не прочитался — приложите его ещё раз'));
      reader.readAsDataURL(file);
    });
  }
  function addFiles(list) {
    showError('');
    const problems = [];
    for (const file of list) {
      const name = file.name || 'картинка.png';
      if (state.files.length >= LIMITS.count) { problems.push('Не больше ' + LIMITS.count + ' файлов к вопросу.'); break; }
      const kind = kindOf(file);
      if (!kind) { problems.push('Файл «' + name + '» я не читаю. ' + ACCEPTED); continue; }
      if (file.size > LIMITS.file) { problems.push('Файл «' + name + '» больше ' + bytes(LIMITS.file) + '.'); continue; }
      const total = state.files.reduce((sum, f) => sum + f.size, 0) + file.size;
      if (total > LIMITS.total) { problems.push('Все файлы вопроса вместе — не больше ' + bytes(LIMITS.total) + '.'); continue; }
      state.files.push({ id: ++fileSeq, file, name, size: file.size, kind,
        preview: kind === 'image' ? URL.createObjectURL(file) : '' });
    }
    if (problems.length) showError(problems.join(' '));
    renderFiles();
    syncComposer();
  }
  function removeFile(id) {
    const gone = state.files.find(f => f.id === id);
    if (gone && gone.preview) URL.revokeObjectURL(gone.preview);
    state.files = state.files.filter(f => f.id !== id);
    renderFiles();
    els.input.focus();
  }
  function clearFiles(sent) {
    const gone = sent || state.files;
    for (const f of gone) if (f.preview) URL.revokeObjectURL(f.preview);
    state.files = state.files.filter(f => !gone.includes(f));
    renderFiles();
  }
  function renderFiles() {
    els.files.textContent = '';
    els.files.hidden = !state.files.length;
    for (const f of state.files) {
      const chip = el('div', 'rx-file');
      chip.title = f.name;
      if (f.preview) {
        const img = el('img', 'rx-file-thumb');
        img.src = f.preview;
        img.alt = '';
        chip.append(img);
      } else {
        chip.append(el('span', 'rx-file-badge', badge(f.name)));
      }
      const meta = el('span', 'rx-file-meta');
      meta.append(el('span', 'rx-file-name', f.name), el('span', 'rx-file-size', bytes(f.size)));
      const x = el('button', 'rx-file-x');
      x.type = 'button';
      x.setAttribute('aria-label', 'Убрать файл ' + f.name);
      x.append(svg('M7 7l10 10M17 7L7 17'));
      x.addEventListener('click', () => removeFile(f.id));
      chip.append(meta, x);
      els.files.append(chip);
    }
    els.input.placeholder = state.files.length ? 'Что сделать с файлами? Например: сверь накладную с заказом' : PLACEHOLDER;
  }
  function hasFiles(e) { return !!(e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files')); }

  els.attach.addEventListener('click', () => els.fileInput.click());
  els.fileInput.addEventListener('change', () => {
    addFiles([...els.fileInput.files]);
    els.fileInput.value = '';                                  // тот же файл можно выбрать снова
    els.input.focus();
  });
  // Картинка из буфера (снимок экрана) — файлом; текст из Excel вставляется текстом, как обычно.
  els.input.addEventListener('paste', e => {
    const data = e.clipboardData;
    const files = data ? [...(data.files || [])] : [];
    if (files.length && !data.getData('text/plain')) {
      e.preventDefault();
      addFiles(files);
    }
  });
  // Перетаскивание: на поле — подсветка; файл, брошенный мимо поля, тоже ложится в вопрос (а не открывается).
  for (const type of ['dragenter', 'dragover']) {
    document.addEventListener(type, e => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      els.form.classList.add('is-drop');
    });
  }
  document.addEventListener('dragleave', e => { if (!e.relatedTarget) els.form.classList.remove('is-drop'); });
  document.addEventListener('drop', e => {
    els.form.classList.remove('is-drop');
    if (!hasFiles(e)) return;
    e.preventDefault();
    addFiles([...e.dataTransfer.files]);
  });

  /* ---------------- готовые вопросы ---------------- */

  // Готовый вопрос задаётся сразу — с выбранной глубиной («Ответ» или «Исследование») и молнией.
  if (els.suggest) {
    for (const b of els.suggest.querySelectorAll('.rx-sq')) b.addEventListener('click', () => ask(b.dataset.question, false));
  }
  els.newBtn.addEventListener('click', () => { closeSide(); newThread(true, true); });
  if (els.newTop) els.newTop.addEventListener('click', () => newThread(true, true));
  els.sideToggle.addEventListener('click', () => (sideOpen() ? closeSide() : openSide()));
  els.sideClose.addEventListener('click', () => closeSide(true));
  els.scrim.addEventListener('click', () => closeSide());
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (effortOpen()) closeEffort(true);
    else if (sideOpen()) closeSide(true);
  });
  els.infoOpen.addEventListener('click', () => {
    closeSide();
    if (els.info.showModal) els.info.showModal(); else els.info.setAttribute('open', '');
  });
  els.infoClose.addEventListener('click', () => els.info.close());
  els.info.addEventListener('click', e => { if (e.target === els.info) els.info.close(); });   // нажатие мимо окна
  window.addEventListener('popstate', () => {
    const id = new URLSearchParams(location.search).get('t');
    if (id) openThread(id, false); else newThread(false);
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) schedulePoll(); });

  /* ---------------- старт ---------------- */

  syncComposer();
  loadThreads().then(() => {
    const id = new URLSearchParams(location.search).get('t');
    if (id) openThread(id, false); else newThread(false);
  });
})();
