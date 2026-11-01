/**
 * Элемент «Период» в настоящем браузере (static/js/shared/period/period_picker.js).
 *
 *     node tests/test_period_picker_browser.mjs
 *
 * Нужен Playwright с Chromium (в облачной среде проекта он установлен); без него тест
 * пропускается с пометкой. Проверяет то, что владелец просил 2026-11-01: свой период вводится
 * цифрами любой длины, кварталов нет; плюс календарь на два месяца с прыжком к году, «Сбросить
 * выбор», режим страницы «на сейчас» и лист снизу на телефоне.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
let chromium;
try {
    ({ chromium } = require('playwright'));
} catch (e) {
    console.log('  skip  Playwright не установлен — тест элемента в браузере пропущен');
    process.exit(0);
}

const asset = (p) => pathToFileURL(path.join(ROOT, p)).href;
const html = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="${asset('static/dashboard/styles/variables.css')}">
<link rel="stylesheet" href="${asset('static/shared/period.css')}">
<style>body{font-family:sans-serif;background:var(--bg-primary);padding:16px}</style></head><body>
<div id="mount"></div><div id="now"></div>
<script src="${asset('static/js/shared/period/period_core.js')}"></script>
<script src="${asset('static/js/shared/period/period_picker.js')}"></script>
<script>
  KPeriod.configure({today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01', data_start: '2017-12-18'});
  window.changes = []; window.resets = 0;
  window.picker = KPeriodPicker.mount(document.getElementById('mount'), {
    value: KPeriod.currentPeriod('week'),
    onChange: function (p) { window.changes.push(p.start + '_' + p.end); },
    onReset: function () { window.resets++; },
    freshness: 'Данные iiko — по сегодня'
  });
  window.nowPicker = KPeriodPicker.mount(document.getElementById('now'), {disabled: true, disabledSub: 'данные на сейчас'});
</script></body></html>`;
const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'kp-')), 'picker.html');
fs.writeFileSync(file, html);

let passed = 0;
let failed = 0;
async function test(name, fn) {
    try {
        await fn();
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}

const browser = await chromium.launch();
async function openPage(width) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(pathToFileURL(file).href);
    page.errors = errors;
    return page;
}
const text = (page, sel) => page.$eval(sel, (el) => el.textContent.trim());

const page = await openPage(1280);

await test('без выбора — текущая неделя, в шапке «идёт»', async () => {
    assert.equal(await text(page, '#mount .kp-title'), '26 окт – 1 ноя 2026');
    assert.match(await text(page, '#mount .kp-sub'), /идёт, по 01\.11/);
});

await test('кварталов нет: шаги День, Неделя, Месяц, Год; в быстром выборе — 12 месяцев и всё время', async () => {
    await page.click('#mount .kp-trigger');
    const steps = await page.$$eval('#mount .kp-step', (els) => els.map((e) => e.textContent));
    assert.deepEqual(steps, ['День', 'Неделя', 'Месяц', 'Год']);
    const chips = await page.$$eval('#mount .kp-chip', (els) => els.map((e) => e.textContent));
    assert.ok(chips.includes('Последние 12 месяцев') && chips.includes('Всё время'), chips.join(', '));
    assert.ok(!chips.some((c) => /квартал/i.test(c)), chips.join(', '));
    const panel = await page.$eval('#mount .kp-panel', (el) => el.textContent);
    assert.ok(!/квартал/i.test(panel), 'слово «квартал» в панели');
});

await test('свой период цифрами: маска, «Показать», больше года — можно', async () => {
    await page.click('#mount .kp-custom[data-action="custom"]');
    await page.fill('#mount .kp-in[data-edge="from"]', '');
    await page.type('#mount .kp-in[data-edge="from"]', '01032024');
    assert.equal(await page.inputValue('#mount .kp-in[data-edge="from"]'), '01.03.2024', 'точки ставятся сами');
    await page.fill('#mount .kp-in[data-edge="to"]', '');
    await page.type('#mount .kp-in[data-edge="to"]', '31102026');
    await page.click('#mount .kp-apply');
    assert.equal(await page.evaluate(() => window.changes.at(-1)), '2024-03-01_2026-10-31');
    assert.equal(await text(page, '#mount .kp-title'), '1 мар 2024 – 31 окт 2026');
    assert.equal(await text(page, '#mount .kp-sub'), '975 дней');
    assert.equal(await page.$eval('#mount .kp-panel', (el) => el.hidden), true, 'панель закрылась');
});

await test('свой период открывается полями с его датами; ошибки — текстом', async () => {
    await page.click('#mount .kp-trigger');
    assert.equal(await page.inputValue('#mount .kp-in[data-edge="from"]'), '01.03.2024');
    await page.fill('#mount .kp-in[data-edge="from"]', '31.02.2026');
    await page.fill('#mount .kp-in[data-edge="to"]', '01.03.2026');
    assert.equal(await text(page, '#mount .kp-error'), 'Такой даты нет: 31.02.2026');
    await page.fill('#mount .kp-in[data-edge="from"]', '31.10.2026');
    await page.fill('#mount .kp-in[data-edge="to"]', '01.03.2024');
    assert.equal(await text(page, '#mount .kp-error'), 'Первая дата позже второй');
    const before = await page.evaluate(() => window.changes.length);
    await page.press('#mount .kp-in[data-edge="to"]', 'Enter');
    assert.equal(await page.evaluate(() => window.changes.length), before, 'с ошибкой не применяется');
    await page.fill('#mount .kp-in[data-edge="from"]', '01.10.2026');
    await page.fill('#mount .kp-in[data-edge="to"]', '05.11.2026');
    assert.equal(await text(page, '#mount .kp-error'), 'Позже последнего дня с данными: 01.11.2026');
});

await test('вставка «01.03.2024 – 31.10.2026» заполняет оба поля', async () => {
    await page.$eval('#mount .kp-in[data-edge="from"]', (el) => {
        const data = new DataTransfer();
        data.setData('text', '01.03.2025 – 30.09.2026');
        el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
    });
    assert.equal(await page.inputValue('#mount .kp-in[data-edge="from"]'), '01.03.2025');
    assert.equal(await page.inputValue('#mount .kp-in[data-edge="to"]'), '30.09.2026');
    assert.equal(await text(page, '#mount .kp-error'), '');
    const names = await page.$$eval('#mount .kp-month-name', (els) => els.map((e) => e.textContent));
    assert.deepEqual(names, ['Август 2026', 'Сентябрь 2026'], 'календарь показал набранный конец');
    assert.ok(await page.$('#mount .kp-day.edge[data-day="2026-09-30"]'), 'конец выделен');
});

await test('календарь: два месяца на компьютере, прыжок к году и месяцу в два нажатия', async () => {
    assert.equal(await page.$$eval('#mount .kp-month', (els) => els.length), 2);
    await page.click('#mount .kp-nav-title');
    for (let i = 0; i < 3; i++) await page.click('#mount [data-action="jump-year-back"]');
    assert.equal(await text(page, '#mount .kp-jump .kp-nav span'), '2023');
    await page.click('#mount [data-jump-month="2"]');
    const names = await page.$$eval('#mount .kp-month-name', (els) => els.map((e) => e.textContent));
    assert.deepEqual(names, ['Март 2023', 'Апрель 2023']);
});

await test('два нажатия по дням применяют период сразу', async () => {
    await page.click('#mount .kp-month:first-child .kp-day:not(.out)[data-day="2023-03-06"]');
    assert.equal(await page.inputValue('#mount .kp-in[data-edge="from"]'), '06.03.2023');
    await page.click('#mount .kp-day:not(.out)[data-day="2023-04-02"]');
    assert.equal(await page.evaluate(() => window.changes.at(-1)), '2023-03-06_2023-04-02');
    assert.equal(await text(page, '#mount .kp-title'), '6 мар – 2 апр 2023');
});

await test('стрелка у своего периода — на его длину; название едет в сторону стрелки', async () => {
    await page.click('#mount .kp-next');
    assert.ok(await page.$eval('#mount', (el) => el.classList.contains('kp--slide-next')));
    assert.equal(await text(page, '#mount .kp-title'), '3 – 30 апр 2023');
});

await test('«Сбросить выбор» — отдаёт сброс странице', async () => {
    await page.click('#mount .kp-trigger');
    await page.click('#mount .kp-reset');
    assert.equal(await page.evaluate(() => window.resets), 1);
    assert.equal(await page.$eval('#mount .kp-panel', (el) => el.hidden), true);
});

await test('страница «на сейчас»: серая надпись, без стрелок и панели', async () => {
    assert.equal(await text(page, '#now .kp-title'), 'Сейчас');
    assert.equal(await text(page, '#now .kp-sub'), 'данные на сейчас');
    assert.equal(await page.$eval('#now .kp-trigger', (el) => el.disabled), true);
    assert.equal(await page.$eval('#now .kp-prev', (el) => el.hidden), true);
    // Скрыты и на экране: .kp-arrow { display: flex } без правила [hidden] показывал бы стрелки,
    // которые ничего не делают (склад, сроки, температура — замечено на этапе 6).
    for (const sel of ['#now .kp-prev', '#now .kp-next']) {
        assert.equal(await page.$eval(sel, (el) => getComputedStyle(el).display), 'none', sel + ' видна');
    }
});

await test('ошибок страницы нет', async () => {
    assert.deepEqual(page.errors, []);
});

const phone = await openPage(390);
await test('телефон: один месяц календаря, лист снизу, поле 16 px', async () => {
    await phone.click('#mount .kp-trigger');
    await phone.click('#mount .kp-custom[data-action="custom"]');
    assert.equal(await phone.$$eval('#mount .kp-month', (els) => els.length), 1);
    const pos = await phone.$eval('#mount .kp-panel', (el) => getComputedStyle(el).position);
    assert.equal(pos, 'fixed');
    const size = await phone.$eval('#mount .kp-in', (el) => getComputedStyle(el).fontSize);
    assert.equal(size, '16px');
    const right = await phone.$$eval('#mount .kp-in', (els) => Math.max(...els.map((e) => e.getBoundingClientRect().right)));
    assert.ok(right <= 390, 'поле не вылезает за экран: правый край ' + right);
    assert.deepEqual(phone.errors, []);
});

await browser.close();
console.log(`\n${passed} ok, ${failed} failed`);
if (failed) process.exit(1);
