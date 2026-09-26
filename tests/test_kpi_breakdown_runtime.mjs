/**
 * Общий блок расчёта KPI (/me и страница ЗП): чек и линейки.
 *
 *     node tests/test_kpi_breakdown_runtime.mjs
 *
 * Настоящий static/js/shared/kpi_breakdown.js исполняется в Node на строках
 * расчёта в том виде, в каком их отдаёт core/kpi_calculator.py. Пример —
 * сентябрь 2026 (настоящие цели и фонд): 8 смен на Варшавской, 4 на
 * Кременчугской, доля розлива 60 %, 4 брискета и 2 щёчки. Числа строк сняты
 * прогоном KpiCalculator.calculate_employee на этих данных.
 *
 * Блок ничего не пересчитывает: деньги и множители берутся из строк расчёта.
 * Тест проверяет, что показ сходится с ними (чек, линейка, формулы, подсказка)
 * и что обе страницы подключают именно этот блок, а не свою копию.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

let passed = 0;
let failed = 0;
function test(name, fn) {
    try {
        fn();
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}

const sandbox = { Intl, Math, Number, String, Object, Array, JSON };
sandbox.window = sandbox;
vm.createContext(sandbox);
new vm.Script(read('static/js/shared/kpi_breakdown.js'), { filename: 'kpi_breakdown.js' })
    .runInContext(sandbox);
const KB = sandbox.KpiBreakdown;

const CATALOG = {
    draft_share: { name: 'Доля розлива', unit: '%', decimals: 1 },
    dish_count: { name: 'Продажи блюд', unit: 'шт', decimals: 0, extensive: true, dish_based: true },
    late_count: { name: 'Опоздания', unit: 'шт', decimals: 0, extensive: true },
};

// Строки — как в ответе /api/kpi-calculate (значения из calculate_employee).
function share() {
    return {
        name: 'Доля розлива', metric: 'draft_share', per_shift: false,
        fact: 60.0, target: 60.6667, min: 58.3333,
        ratio: 0.7143, capped_ratio: 0.7143, intermediate_premium: 5357.1,
        no_targets: false,
        location_targets: {
            'Варшавская': { target: 61, min: 59, shifts: 8 },
            'Кременчугская': { target: 60, min: 57, shifts: 4 },
        },
    };
}
function dishes() {
    return {
        name: 'Брискет блюдо + Щечки BBW блюдо', metric: 'dish_count', per_shift: true,
        fact: 0.5, fact_raw: 6.0, shifts_divisor: 12, target: 0.4667, min: 0.2667,
        ratio: 1.1665, capped_ratio: 1.1665, intermediate_premium: 8748.75,
        no_targets: false, no_dishes: false,
        dishes: ['Брискет блюдо', 'Щечки BBW блюдо'],
        dish_facts: { 'Брискет блюдо': 4, 'Щечки BBW блюдо': 2 },
        location_targets: {
            'Варшавская': { target: 0.4667, min: 0.2667, shifts: 8 },
            'Кременчугская': { target: 0.4667, min: 0.2667, shifts: 4 },
        },
    };
}
function model(over) {
    return Object.assign({
        title: 'KPI-премия', total: 11284.68, koef: 0.8, totalShifts: 12, allShifts: 12,
        norm: 15, pool: 15000, basePerKpi: 7500, maxRatio: 2,
        shiftsPerLocation: { 'Варшавская': 8, 'Кременчугская': 4 },
        catalog: CATALOG, dishesNotFound: [], plan: { open: true, shifts: 15 },
        items: [share(), dishes()],
    }, over || {});
}
function render(m) {
    const host = { innerHTML: '' };
    KB.render(host, m);
    return host.innerHTML.replace(/ /g, ' ');
}
const text = (html) => html.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ');

const html = render(model());
const plain = text(html);

// ---------------------------------------------------------------- чек
test('чек: строки показателей = множитель с 4 знаками × тариф = премия расчёта', () => {
    assert.match(plain, /Доля розлива×0,7143 × 7 500 ₽5 357 ₽/);
    assert.match(plain, /Брискет блюдо \+ Щечки BBW блюдо×1,1665 × 7 500 ₽8 749 ₽/);
});
test('чек: сумма, коэффициент одной строкой, итог — из расчёта', () => {
    assert.match(plain, /Сумма по показателям14 106 ₽/);
    assert.match(plain, /Коэффициент смен12 смен из нормы 1512 ÷ 15×0,80/);
    assert.match(plain, /KPI-премия14 106 ₽ × 0,8011 285 ₽/);
    assert.match(plain, /Фонд 15 000 ₽ делится поровну на 2 показателя: 7 500 ₽ за множитель ×1/);
});
test('чек: смены на точках без целей названы, а не спрятаны', () => {
    const p = text(render(model({ allShifts: 14 })));
    assert.match(p, /ещё 2 на точках без целей не считаются/);
});

// ---------------------------------------------------------------- линейка
test('линейка: ×0, ×1, ×2 всегда на 1/6, 1/2 и 5/6 ширины', () => {
    assert.equal(Math.round(KB._pos(0, 2) * 100) / 100, 16.67);
    assert.equal(KB._pos(1, 2), 50);
    assert.equal(Math.round(KB._pos(2, 2) * 100) / 100, 83.33);
    assert.equal(KB._pos(-10, 2), 0, 'далеко ниже минимума — к левому краю');
    assert.equal(KB._pos(10, 2), 100, 'далеко выше ×2 — к правому краю');
});
test('линейка доли: отметки 58,3 / 60,7 / 63 %, маркер на 60 %', () => {
    assert.match(html, /×0<\/span><span class="kb-lab-v">58,3 %/);
    assert.match(html, /×1<\/span><span class="kb-lab-v">60,7 %/);
    assert.match(html, /×2<\/span><span class="kb-lab-v">63 %/);
    assert.match(html, /class="kb-mark" style="left:40\.48%"/);
});
test('штучный KPI на норму 15 смен: 4 / 7 / 10 шт, факт 6 ÷ 12 × 15 = 7,5', () => {
    assert.match(html, /×0<\/span><span class="kb-lab-v">4 шт/);
    assert.match(html, /×1<\/span><span class="kb-lab-v">7 шт/);
    assert.match(html, /×2<\/span><span class="kb-lab-v">10 шт/);
    assert.match(plain, /Факт: 6 шт за 12 смен\. Цели заданы на 15 смен, поэтому факт пересчитан на 15: 6 ÷ 12 × 15 = 7,5 шт/);
    assert.match(html, /class="kb-mark" style="left:55\.5\d%"/);
});
test('масштаб не меняет множитель: на норму он тот же, что считал сервер', () => {
    const r = KB._rulerOf(dishes(), model());
    assert.ok(Math.abs(r.k - 1.1665) < 0.001, `k=${r.k}`);
    const s = KB._rulerOf(share(), model());
    assert.ok(Math.abs(s.k - 0.7143) < 0.001, `k=${s.k}`);
});
test('формулы с числами: множитель на карточке — из расчёта, 2 знака', () => {
    assert.match(plain, /\(60 − 58,33\) ÷ \(60,67 − 58,33\) = 0,71\./);
    assert.match(plain, /\(7,5 − 4\) ÷ \(7 − 4\) = 1,17\./);
    assert.match(html, /class="kb-mult">×0,71</);
    assert.match(html, /class="kb-mult is-ok">×1,17</);
});
test('ниже минимума — множитель 0 словами', () => {
    const it = Object.assign(share(), { fact: 55, capped_ratio: 0, ratio: 0, intermediate_premium: 0 });
    const p = text(render(model({ items: [it] })));
    assert.match(p, /Факт 55 % ниже 58,3 % — множитель 0\./);
});
test('выше ×2 — сказано, что множитель не больше 2', () => {
    const it = Object.assign(share(), { fact: 66, capped_ratio: 2, ratio: 3.29, intermediate_premium: 15000 });
    const p = text(render(model({ items: [it] })));
    assert.match(p, /= 3,29, но множитель не больше 2\./);
});

// ---------------------------------------------------------------- подсказка
test('подсказка по графику: ещё 3 смены, до ×1 ещё 1 шт, до ×2 ещё 4', () => {
    assert.match(plain, /Пока месяц идётПо графику у вас ещё 3 смены\. Чтобы к концу месяца было ×1, нужно ещё 1 шт \(всего 7 шт за 15 смен\), для ×2 — ещё 4 шт\./);
});
test('подсказки нет у закрытого месяца и без смен впереди', () => {
    assert.doesNotMatch(render(model({ plan: { open: false, shifts: 15 } })), /Пока месяц идёт/);
    assert.doesNotMatch(render(model({ plan: { open: true, shifts: 12 } })), /Пока месяц идёт/);
    assert.doesNotMatch(render(model({ plan: null })), /Пока месяц идёт/);
});

// ---------------------------------------------------------------- раскрытия
test('цели по точкам: взвешивание с числами', () => {
    assert.match(plain, /цель = \(8 × 61 \+ 4 × 60\) ÷ 12 = 60,67/);
    assert.match(plain, /минимум = \(8 × 59 \+ 4 × 57\) ÷ 12 = 58,33/);
    assert.match(plain, /Цели одинаковые на всех ваших точках\./);
});
test('блюда: разбивка факта и предупреждение о непроданном', () => {
    assert.match(plain, /Из чего 6Блюдо/);
    const p = text(render(model({ dishesNotFound: ['щечки bbw блюдо'] })));
    assert.match(p, /Щечки BBW блюдонет в продажах/);
    assert.match(p, /скорее всего, его переименовали в iiko/);
});
test('без целей и без блюд — премии нет, линейки нет', () => {
    const noT = Object.assign(share(), { no_targets: true, capped_ratio: 0, intermediate_premium: 0 });
    const p = text(render(model({ items: [noT] })));
    assert.match(p, /цели не заданы0 ₽/);
    assert.match(p, /цели по этому показателю не заданы/);
    assert.doesNotMatch(render(model({ items: [noT] })), /kb-ruler/);
    const noD = Object.assign(dishes(), { no_dishes: true, dishes: [], capped_ratio: 0, intermediate_premium: 0 });
    assert.match(text(render(model({ items: [noD] }))), /Блюда для этого показателя не выбраны/);
});
test('«меньше — лучше»: потолок и цель словами, недостижимая ×2 — прочерк', () => {
    const late = {
        name: 'Опоздания', metric: 'late_count', per_shift: true,
        fact: 0.0833, fact_raw: 1, shifts_divisor: 12, target: 0, min: 0.2,
        capped_ratio: 0.5835, intermediate_premium: 4376.25, no_targets: false,
    };
    const h = render(model({ items: [late] }));
    const p = text(h);
    assert.match(p, /Больше 3 шт на 15 смен — премии нет\. 0 шт — полные 7 500 ₽\./);
    assert.match(h, /×2<\/span><span class="kb-lab-v">—/);
    assert.doesNotMatch(h, /Пока месяц идёт/, 'у «меньше — лучше» не набирают');
});

// ---------------------------------------------------------------- страницы
test('обе страницы подключают общий блок и зовут KpiBreakdown.render', () => {
    const me = read('templates/me.html');
    const sal = read('templates/bonus.html');
    for (const [name, tpl] of [['me.html', me], ['bonus.html', sal]]) {
        assert.match(tpl, /static\/shared\/kpi_breakdown\.css\?v=\{\{ app_version \}\}/, name + ': нет стилей блока');
        assert.match(tpl, /static\/js\/shared\/kpi_breakdown\.js\?v=\{\{ app_version \}\}/, name + ': нет скрипта блока');
    }
    assert.match(read('static/js/me/snapshot.js'), /KpiBreakdown\.render\(/);
    assert.match(sal, /KpiBreakdown\.render\(/);
});
test('старые карточки KPI удалены с обеих страниц — второй подачи нет', () => {
    assert.doesNotMatch(read('static/js/me/snapshot.js'), /function kpiCard|me-kpi-num|me-scale/);
    assert.doesNotMatch(read('static/me/me.css'), /\.me-kpi-|\.me-scale/);
    assert.doesNotMatch(read('templates/bonus.html'), /kpi-detail-card|kpi-fund-banner|loc-breakdown|function periodVal/);
});
test('/me перекрашивает блок только токенами', () => {
    const css = read('static/me/me.css');
    assert.match(css, /body\.me-page \.kb \{[^}]*--kb-card: var\(--me-card\)/);
    const kb = read('static/shared/kpi_breakdown.css');
    assert.doesNotMatch(kb.replace(/\.kb \{[\s\S]*?\n\}/, ''), /#[0-9a-f]{3,6}\b/i,
        'цвет в правилах блока мимо токенов --kb-* — на одной из страниц поедет тема');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
