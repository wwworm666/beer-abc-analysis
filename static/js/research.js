/* Страница kultura.research (/research, routes/research.py, kultura_bot/web.py).
 *
 * Беседы человека слева, беседа справа, поле вопроса внизу. Вопрос уходит в очередь сайта; отвечает
 * сервер бота в Амстердаме тем же кодом, что в Telegram. Пока вопрос в работе, страница раз в
 * POLL_MS спрашивает его состояние: строки хода работы («Отвечаю · 0:40», «Сейчас: …») и кнопка
 * «Остановить»; готов — ответ, свёрнутое «Как считается», графики (TgChart, как «Открыть
 * интерактивно»), отчёт (TgReport, как страница отчёта), кнопки следующего шага и строка цены.
 *
 * Тексты — только textContent; HTML вставляется лишь из полей *_html, которые сервер собрал сам
 * (kultura_bot/engine/formatting.to_html: всё экранировано, разметка своя — b, i, code, pre, a, blockquote).
 * Беседа в адресе — ?t=<id>: ссылку можно открыть снова. */
(function () {
  'use strict';

  const POLL_MS = 2000;
  const LIST_EVERY_MS = 15000;
  const root = document.getElementById('rsRoot');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const els = {
    side: $('rsSide'), sideToggle: $('rsSideToggle'), threads: $('rsThreads'), threadsEmpty: $('rsThreadsEmpty'),
    newBtn: $('rsNew'), head: $('rsHead'), title: $('rsTitle'), headActions: $('rsHeadActions'), del: $('rsDelete'),
    start: $('rsStart'), suggest: $('rsSuggest'), feed: $('rsFeed'), form: $('rsForm'), engine: $('rsEngine'),
    input: $('rsInput'), mode: $('rsMode'), fast: $('rsFast'), send: $('rsSend'), error: $('rsError'),
    toast: $('rsToast'),
  };

  const state = {
    threads: [], current: null, questions: [], mode: 'answer', sending: false,
    pollTimer: 0, listAt: 0, mounted: [], fonts: null,
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
      if (resp.status === 401) { window.location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); }
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
  function when(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const now = new Date();
    const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' });
    const sameDay = d.toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' }) ===
      now.toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' });
    if (sameDay) return time;
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', timeZone: 'Europe/Moscow' }) + ' ' + time;
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

  /* ---------------- беседы ---------------- */

  function renderThreads() {
    els.threads.textContent = '';
    for (const t of state.threads) {
      const b = el('button', 'rs-thread');
      b.type = 'button';
      b.setAttribute('aria-current', t.id === state.current ? 'true' : 'false');
      b.append(el('span', 'rs-thread-title', t.title || 'Без вопроса'));
      const meta = el('span', 'rs-thread-meta');
      meta.append(el('span', null, when(t.last_at)));
      meta.append(el('span', null, t.questions + ' ' + plural(t.questions, ['вопрос', 'вопроса', 'вопросов'])));
      if (t.reports) meta.append(el('span', null, 'Research: ' + t.reports));
      if (t.active) meta.append(el('span', 'rs-live', 'идёт ответ'));
      b.append(meta);
      b.addEventListener('click', () => { openThread(t.id, true); closeSide(); });
      els.threads.append(b);
    }
    els.threadsEmpty.hidden = state.threads.length > 0;
    els.sideToggle.textContent = 'Беседы' + (state.threads.length ? ' (' + state.threads.length + ')' : '');
  }
  function plural(n, forms) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  }
  function closeSide() {
    els.side.dataset.open = 'false';
    els.sideToggle.setAttribute('aria-expanded', 'false');
  }

  function renderEngine(engine) {
    const text = engine && !engine.ok ? engine.text : '';
    els.engine.textContent = text || '';
    els.engine.hidden = !text;
  }

  function renderSuggest(sections) {
    els.suggest.textContent = '';
    for (const s of sections || []) {
      const group = el('div', 'rs-suggest-group');
      group.append(el('div', 'rs-suggest-title', s.title));
      const chips = el('div', 'rs-chips');
      for (const q of s.questions || []) {
        const chip = el('button', 'rs-chip', q);
        chip.type = 'button';
        chip.addEventListener('click', () => ask(q));
        chips.append(chip);
      }
      group.append(chips);
      els.suggest.append(group);
    }
  }

  function loadThreads() {
    state.listAt = Date.now();
    return API.threads().then(data => {
      state.threads = data.threads || [];
      renderThreads();
      renderEngine(data.engine);
      if (!els.suggest.childElementCount) renderSuggest(data.sections);
      return data;
    }).catch(err => showError(err.message));
  }

  /* ---------------- беседа ---------------- */

  function clearFeed() {
    for (const m of state.mounted) { try { if (m.destroy) m.destroy(); } catch (e) { /* уже убран */ } }
    state.mounted = [];
    els.feed.textContent = '';
  }

  function newThread(push, focus) {
    state.current = null;
    state.questions = [];
    clearFeed();
    els.head.hidden = true;
    els.start.hidden = false;
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
    els.start.hidden = state.questions.length > 0;
    els.head.hidden = !state.current;
    const first = state.questions[0];
    els.title.textContent = first ? first.question.replace(/\s+/g, ' ').slice(0, 200) : '';
    resetDelete();
    for (const q of state.questions) els.feed.append(renderQuestion(q));
    syncComposer();
    const last = els.feed.lastElementChild;
    if (last) last.scrollIntoView({ block: 'start' });
  }

  function renderQuestion(q) {
    const art = el('article', 'rs-q');
    art.dataset.id = q.id;
    const askBox = el('div', 'rs-ask');
    const meta = el('div', 'rs-ask-meta');
    meta.append(el('span', 'rs-badge' + (q.mode === 'report' ? ' rs-badge-report' : ''),
      q.mode === 'report' ? 'Research' : 'Ответ'));
    if (q.fast) meta.append(el('span', 'rs-badge', 'быстро'));
    meta.append(el('span', null, when(q.asked_at)));
    askBox.append(meta, el('div', 'rs-ask-text', q.question));
    art.append(askBox);
    const answer = el('div', 'rs-answer');
    art.append(answer);
    fillAnswer(answer, q);
    return art;
  }

  function fillAnswer(box, q) {
    box.textContent = '';
    if (q.active) {
      const wait = el('div', 'rs-wait');
      if (q.status === 'queued' || q.status === 'taken') {
        wait.append(el('p', 'rs-progress', q.status === 'queued'
          ? 'В очереди: сервер бота возьмёт вопрос, когда освободится.' : 'Сервер бота взял вопрос — начинаю…'));
      } else {
        wait.append(el('p', 'rs-progress', q.progress || 'Отвечаю…'));
      }
      const actions = el('div', 'rs-wait-actions');
      if (q.stopping) {
        actions.append(el('span', 'rs-muted', 'Останавливаю: шаг, который уже идёт, дойдёт до конца…'));
      } else {
        const stop = el('button', 'mcp-btn mcp-btn-ghost mcp-btn-sm', 'Остановить');
        stop.type = 'button';
        stop.addEventListener('click', () => {
          stop.disabled = true;
          API.stop(q.id).then(data => updateQuestion(data.question)).catch(err => { stop.disabled = false; toast(err.message); });
        });
        actions.append(stop);
      }
      wait.append(actions);
      box.append(wait);
      return;
    }
    if (q.status !== 'done') {
      box.append(el('div', 'rs-fail' + (q.status === 'error' ? ' rs-fail-error' : ''),
        q.shown || (q.status === 'stopped' ? 'Остановлено.' : 'Ответа нет.')));
      if (q.cost && q.cost.line) box.append(el('div', 'rs-cost', q.cost.line));
      return;
    }
    if (q.notice) box.append(el('div', 'rs-notice', q.notice));
    const later = [];
    for (const card of q.cards || []) {
      if (card.kind === 'chart') box.append(chartCard(card, later));
      else if (card.kind === 'report') box.append(reportCard(card, later));
    }
    if (q.answer_html) box.append(html('div', 'rs-text', q.answer_html));
    if (q.how_html) {
      const fold = el('details', 'rs-fold');
      fold.append(el('summary', null, 'Как считается'), html('div', 'rs-text', q.how_html));
      box.append(fold);
    }
    const asks = [].concat(q.ask || [], ...(q.cards || []).map(c => c.ask || []));
    if (asks.length) {
      const chips = el('div', 'rs-chips');
      for (const text of [...new Set(asks)]) {
        const chip = el('button', 'rs-chip', text);
        chip.type = 'button';
        chip.addEventListener('click', () => ask(text, q.thread_id));
        chips.append(chip);
      }
      box.append(chips);
    }
    if (q.cost && q.cost.line) box.append(el('div', 'rs-cost', q.cost.line));
    if (later.length) fontsReady().then(() => later.forEach(fn => fn()));
  }

  function chartCard(card, later) {
    const wrap = el('div', 'rs-card');
    if (card.caption_html) wrap.append(html('div', 'rs-card-caption rs-text', card.caption_html));
    const box = el('div');
    wrap.append(box);
    later.push(() => {
      if (!window.TgChart) { box.append(el('p', 'rs-muted', 'График не загрузился.')); return; }
      const howNode = card.how_html ? html('div', 'rep-text', card.how_html) : null;
      state.mounted.push(window.TgChart.mount(box, card.spec, { mode: 'app', toast, howNode }));
    });
    return wrap;
  }

  function reportCard(card, later) {
    const wrap = el('div', 'rs-report');
    const box = el('div');
    wrap.append(box);
    const actions = el('div', 'rs-report-actions');
    if (card.page) {
      const a = el('a', null, 'Открыть отдельной страницей');
      a.href = card.page;
      a.target = '_blank';
      a.rel = 'noopener';
      actions.append(a);
      actions.append(el('span', 'rs-muted', 'там же — ссылка для браузера'));
    }
    if (actions.childElementCount) wrap.append(actions);
    later.push(() => {
      if (!window.TgReport) { box.append(el('p', 'rs-muted', 'Отчёт не загрузился.')); return; }
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
    const art = els.feed.querySelector('article[data-id="' + CSS.escape(q.id) + '"]');
    if (!art) return;
    const box = art.querySelector('.rs-answer');
    const changed = before.status !== q.status || before.progress !== q.progress || before.stopping !== q.stopping;
    if (changed) fillAnswer(box, q);
    if (before.active && !q.active) {
      syncComposer();
      loadThreads();
      art.scrollIntoView({ block: 'nearest' });
    }
  }

  /* ---------------- опрос ---------------- */

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    if (!state.questions.some(q => q.active)) return;
    state.pollTimer = setTimeout(poll, POLL_MS);
  }
  function poll() {
    const active = state.questions.filter(q => q.active);
    if (!active.length) return;
    if (document.hidden) { schedulePoll(); return; }
    Promise.all(active.map(q => API.question(q.id).then(d => updateQuestion(d.question)).catch(() => {})))
      .then(() => {
        if (Date.now() - state.listAt > LIST_EVERY_MS) loadThreads();
        schedulePoll();
      });
  }

  /* ---------------- вопрос ---------------- */

  function syncComposer() {
    const busy = state.sending || state.questions.some(q => q.active);
    els.send.disabled = busy;
    els.send.textContent = state.sending ? 'Отправляю…' : (busy ? 'Бот отвечает…' : 'Спросить');
    for (const chip of document.querySelectorAll('.rs-chip')) chip.disabled = busy;
  }

  function ask(text, threadId) {
    const question = (text || '').trim();
    if (!question) { els.input.focus(); return; }
    if (state.sending || state.questions.some(q => q.active)) { toast('Бот ещё отвечает на прошлый вопрос'); return; }
    showError('');
    state.sending = true;
    syncComposer();
    const body = { question, mode: state.mode, fast: !!(els.fast && els.fast.checked) };
    const thread = threadId || state.current;
    if (thread) body.thread_id = thread;
    API.ask(body).then(data => {
      const q = data.question;
      if (q.thread_id !== state.current) {
        state.current = q.thread_id;
        state.questions = [];
        clearFeed();
        setUrl(q.thread_id, true);
      }
      state.questions.push(q);
      els.start.hidden = true;
      els.head.hidden = false;
      if (state.questions.length === 1) els.title.textContent = q.question.replace(/\s+/g, ' ').slice(0, 200);
      const art = renderQuestion(q);
      els.feed.append(art);
      art.scrollIntoView({ block: 'start', behavior: 'smooth' });
      els.input.value = '';
      if (els.fast) els.fast.checked = false;            // быстрый режим — только для этого вопроса
      loadThreads();
      schedulePoll();
    }).catch(err => showError(err.message)).finally(() => {
      state.sending = false;
      syncComposer();
    });
  }

  /* ---------------- удаление беседы ---------------- */

  function resetDelete() {
    els.headActions.textContent = '';
    els.headActions.append(els.del);
  }
  els.del.addEventListener('click', () => {
    const id = state.current;
    if (!id) return;
    els.headActions.textContent = '';
    els.headActions.append(el('span', 'rs-muted', 'Удалить беседу со всеми ответами?'));
    const yes = el('button', 'mcp-btn mcp-btn-danger mcp-btn-sm', 'Удалить');
    yes.type = 'button';
    const no = el('button', 'mcp-btn mcp-btn-ghost mcp-btn-sm', 'Отмена');
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

  for (const b of els.mode.querySelectorAll('button[data-mode]')) {
    b.addEventListener('click', () => {
      state.mode = b.dataset.mode;
      for (const o of els.mode.querySelectorAll('button[data-mode]')) {
        o.setAttribute('aria-checked', o === b ? 'true' : 'false');
      }
    });
  }
  els.form.addEventListener('submit', e => { e.preventDefault(); ask(els.input.value); });
  els.input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(els.input.value); }
  });
  els.newBtn.addEventListener('click', () => { newThread(true, true); closeSide(); });
  els.sideToggle.addEventListener('click', () => {
    const open = els.side.dataset.open !== 'true';
    els.side.dataset.open = open ? 'true' : 'false';
    els.sideToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  window.addEventListener('popstate', () => {
    const id = new URLSearchParams(location.search).get('t');
    if (id) openThread(id, false); else newThread(false);
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) schedulePoll(); });

  // Тема сайта сменилась — графики перерисовать в новых цветах.
  new MutationObserver(() => state.mounted.forEach(m => { try { m.retheme(); } catch (e) { /* убран */ } }))
    .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  /* ---------------- старт ---------------- */

  loadThreads().then(() => {
    const id = new URLSearchParams(location.search).get('t');
    if (id) openThread(id, false); else newThread(false);
  });
})();
