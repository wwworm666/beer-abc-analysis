/**
 * ТЕКСТОВЫЕ проверки страницы «ABC/XYZ анализ» фасовки (/packaging).
 *
 *     node tests/test_packaging_render.mjs
 *
 * Здесь проверяется согласованность трёх файлов между собой: шаблон объявляет
 * узлы, JS их ищет, CSS описывает классы, которые JS пишет в разметку. Такие
 * расхождения не ловятся ни юнит-тестами расчёта, ни глазами на одном экране:
 * страница просто молча не рисует блок.
 *
 * Устроено так же, как tests/test_draft_render.mjs — это соседняя страница в том
 * же оформлении, и проверять их надо одинаково.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/packaging.html');
const css = read('static/packaging/packaging.css');
const js = read('static/js/packaging/packaging.js');
const routes = read('routes/pages.py');
const analysisPy = read('routes/analysis.py');
const thresholds = read('core/abc_thresholds.py');

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

test('маршрут рендерит новый шаблон и отдаёт app_version', () => {
    assert.match(routes, /render_template\('packaging\.html', bars=BARS, app_version=APP_VERSION\)/,
        'маршрут /packaging не отдаёт packaging.html с app_version');
});

test('шаблон подключает свои стили и скрипт с кэш-бастингом', () => {
    assert.match(html, /static\/packaging\/packaging\.css\?v=\{\{ app_version \}\}/,
        'packaging.css без ?v — правки вёрстки не доедут до браузеров');
    assert.match(html, /static\/js\/packaging\/packaging\.js\?v=\{\{ app_version \}\}/,
        'packaging.js без ?v');
    assert.match(html, /body class="packaging-page"/, 'нет класса страницы для токенов');
});

test('все id, которые ищет JS, объявлены в шаблоне', () => {
    const wanted = new Set();
    for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) wanted.add(m[1]);
    // sidebar-toggle приходит из общего shared/nav.html, а не из этого шаблона.
    wanted.delete('sidebar-toggle');
    // Поля «своего периода» JS сам же и рисует внутри меню.
    wanted.delete('pkFrom');
    wanted.delete('pkTo');
    const missing = [...wanted].filter((id) => !html.includes(`id="${id}"`));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
});

test('страница берёт данные из /api/packaging и только оттуда', () => {
    assert.match(js, /fetch\('\/api\/packaging'/, 'нет запроса к новому эндпоинту');
    assert.ok(!/api\/analyze|api\/categories|weekly-chart/.test(js),
        'остался вызов удалённого эндпоинта');
    const fetches = [...js.matchAll(/fetch\(/g)].length;
    assert.equal(fetches, 1, `запросов должно быть ровно один, найдено ${fetches}`);
});

test('удалённых эндпоинтов больше нет в роутах', () => {
    assert.ok(!/route\('\/api\/analyze'/.test(analysisPy), 'остался /api/analyze');
    assert.ok(!/route\('\/api\/categories'/.test(analysisPy), 'остался /api/categories');
    assert.ok(!/route\('\/api\/weekly-chart/.test(analysisPy), 'остался /api/weekly-chart');
    assert.match(analysisPy, /route\('\/api\/packaging', methods=\['POST'\]\)/,
        'нет нового эндпоинта');
});

test('список баров приходит из шаблона, а не захардкожен в JS', () => {
    assert.match(html, /id="pkBars"[^>]*>\{\{ bars \| tojson \}\}/,
        'бары не отдаются страницей');
    assert.ok(!/Большой пр|Лиговский|Кременчугская|Варшавская/.test(js),
        'названия баров зашиты в скрипт');
});

test('все классы, которые пишет JS, описаны в CSS', () => {
    const used = new Set();
    for (const m of js.matchAll(/class="(pk-[a-z0-9 -]+)"/g)) {
        m[1].split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
    }
    // Классы-модификаторы собираются конкатенацией и проверяются ниже отдельно.
    const missing = [...used].filter((c) => !css.includes(`.${c}`));
    assert.deepEqual(missing, [], `нет в CSS: ${missing.join(', ')}`);
});

test('обе таблицы и обе секции объявлены в шаблоне', () => {
    assert.match(html, /id="pkCats"/, 'нет таблицы категорий');
    assert.match(html, /id="pkPos"/, 'нет таблицы позиций');
    assert.match(html, /id="pkBuckets"/, 'нет корзин действий');
    assert.match(html, /id="pkSum"/, 'нет сводки');
    assert.match(html, /id="pkDrawer"/, 'нет выдвижной карточки');
});

test('вкладок режима больше нет: категории и позиции на одном экране', () => {
    assert.ok(!/setAnalysisMode|mode-beers|mode-categories/.test(html + js),
        'остался переключатель режима — данные снова прячутся за вкладку');
});

test('категории не урезаются: в коде нет slice по спискам данных', () => {
    const slices = js.match(/\.slice\(0,\s*\d+\)/g) || [];
    assert.deepEqual(slices, [],
        `остались урезания списков: ${slices.join(', ')} — «все категории» сломаны`);
    assert.ok(!/Топ-10|топ-10/.test(html + js), 'остался заголовок про топ-10');
});

test('названия не обрезаются символьно, обрезка — задача CSS', () => {
    assert.ok(!/substring\(0,\s*\d+\)|slice\(0,\s*\d+\)\s*\+\s*'\.\.\./.test(js),
        'имя категории режется в JS: длинные названия станут неразличимы');
    assert.match(css, /\.pk-name\s*\{[^}]*text-overflow:\s*ellipsis/,
        'нет многоточия по CSS для длинных имён');
});

test('обработчики кликов не подставляют данные в атрибуты', () => {
    // На апострофе в «O'Hara's» ломался прежний onclick с именем внутри.
    assert.ok(!/onclick=/.test(js), 'в разметке появился инлайновый onclick');
    assert.ok(!/onclick=/.test(html), 'в шаблоне появился инлайновый onclick');
    assert.match(js, /data-cat="' \+ esc\(/, 'имя категории пишется без экранирования');
    assert.match(js, /data-bucket="' \+ bucket\.key/, 'ключ корзины пишется не из словаря');
});

test('имена из данных экранируются везде, где попадают в разметку', () => {
    // Опасна только склейка данных С РАЗМЕТКОЙ: `'<span>' + p.Beer`. Передача
    // того же поля в хелпер, который экранирует весь аргумент целиком
    // (drawerHead, abcLine, cell, band), безопасна, а двойное экранирование
    // выдало бы на экран «&amp;» вместо «&».
    const bare = [];
    js.split('\n').forEach((line, i) => {
        const hits = line.match(/\+\s*\w+\.(Beer|Category|Bar|Country)\b/g) || [];
        if (!hits.length) return;
        // Разметка именно в этой строке — значит поле клеится с HTML здесь же.
        const touchesMarkup = /['"][^'"]*[<>]/.test(line);
        if (touchesMarkup && !/esc\(/.test(line)) {
            bare.push(`стр. ${i + 1}: ${hits.join(', ')}`);
        }
    });
    assert.deepEqual(bare, [], `склейка с разметкой без esc(): ${bare.join(' | ')}`);
    // И контрольная проверка, что экранирование вообще применяется.
    assert.ok(/esc\(p\.Beer\)/.test(js), 'имя фасовки нигде не экранируется');
    assert.ok(/esc\(cat\.Category\)/.test(js), 'имя категории нигде не экранируется');
});

test('корзины действий на фронте совпадают с ядром', () => {
    const buckets = read('core/abc_buckets.py');
    for (const key of ['stars', 'workhorses', 'price_up', 'premium', 'background', 'remove']) {
        assert.ok(buckets.includes(`'${key}'`), `в ядре нет корзины ${key}`);
        assert.ok(js.includes(`key: '${key}'`), `на фронте нет корзины ${key}`);
    }
    for (const name of ['Звёзды', 'Рабочие лошадки', 'Недооценённые', 'Премиум-ниша',
                        'Фон', 'Удалить']) {
        assert.ok(js.includes(name), `подпись «${name}» разошлась с ядром`);
    }
});

test('пороги в подписях совпадают с константами ядра', () => {
    assert.match(thresholds, /XYZ_X_MAX_CV = 30\.0/, 'порог X съехал');
    assert.match(thresholds, /XYZ_Y_MAX_CV = 60\.0/, 'порог Y съехал');
    assert.match(thresholds, /MARKUP_A_MIN = 1\.2/, 'порог наценки A съехал');
    // Те же числа обязаны стоять в текстах на экране, иначе страница объясняет
    // одно, а считает другое.
    assert.ok(js.includes('разброс до 30%'), 'в подписи XYZ не тот порог X');
    assert.ok(js.includes('свыше 60%'), 'в подписи XYZ не тот порог Y');
    assert.ok(html.includes('от 120%'), 'в легенде не тот порог наценки');
});

test('формула наценки показана пользователю, а не только в документации', () => {
    // Требование .claude/CLAUDE.md пункт 1: расчёт виден на экране.
    assert.match(html, /\(выручка − себестоимость\) \/ себестоимость/,
        'формулы наценки нет в сводке');
    assert.match(js, /pk-formula/, 'в карточке нет строки с расчётом буквы');
    assert.ok(js.includes('база: весь ассортимент разреза'),
        'не подписана база, от которой считается буква по выручке');
});

test('объяснено, что такое «Общая» и откуда берутся категории', () => {
    assert.match(html, /бары складываются в одну сеть/, 'не объяснено сведение в тотал');
    assert.match(html, /Без категории \(Ф\)/, 'не объяснено, куда деваются позиции без стиля');
    assert.match(html, /третий уровень дерева групп/, 'не объяснено, что такое категория');
});

test('прочерк вместо буквы объяснён, а не выдан за оценку', () => {
    assert.match(html, /Прочерк вместо буквы означает, что данных не хватило/,
        'в легенде не сказано, что прочерк — это не «плохо»');
    assert.ok(js.includes('Прочерк честнее буквы'), 'в карточке нет объяснения прочерка');
});

test('без эмодзи в разметке и скрипте', () => {
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u;
    assert.ok(!emoji.test(html), 'эмодзи в шаблоне — запрещено Style Rules проекта');
    assert.ok(!emoji.test(js), 'эмодзи в скрипте');
    assert.ok(!emoji.test(css), 'эмодзи в стилях');
});

test('ни одного HEX вне блока токенов', () => {
    // Токены объявлены в двух местах: светлая тема и тёмная. Всё остальное
    // обязано ссылаться на переменные, иначе тёмная тема разъедется.
    const withoutTokens = css
        .replace(/body\.packaging-page\s*\{[\s\S]*?\n\}/, '')
        .replace(/\[data-theme="dark"\][\s\S]*?\n\}/, '');
    const hexes = withoutTokens.match(/#[0-9A-Fa-f]{3,8}\b/g) || [];
    assert.deepEqual(hexes, [], `HEX вне токенов: ${hexes.join(', ')}`);
});

test('тёмная тема переопределяет те же токены, что объявлены в светлой', () => {
    const light = new Set();
    const lightBlock = css.match(/body\.packaging-page\s*\{([\s\S]*?)\n\}/);
    for (const m of lightBlock[1].matchAll(/(--pk-[a-z0-9-]+):/g)) light.add(m[1]);
    const dark = new Set();
    const darkBlock = css.match(/\[data-theme="dark"\][\s\S]*?\{([\s\S]*?)\n\}/);
    for (const m of darkBlock[1].matchAll(/(--pk-[a-z0-9-]+):/g)) dark.add(m[1]);
    // Радиусы, шрифты и сетки в тёмной теме не меняются — сравниваем только цвета.
    const colourish = [...light].filter((t) => !/--pk-(r-|sans|mono)/.test(t));
    const missing = colourish.filter((t) => !dark.has(t));
    assert.deepEqual(missing, [], `в тёмной теме не переопределены: ${missing.join(', ')}`);
});

test('запрещённые имена классов из уроков проекта не используются', () => {
    // Глобальный mobile.css перебивает их на <=480px (уроки /me и /draft).
    // Комментарии вырезаем: в шапке файла эти имена перечислены как раз как
    // предупреждение, и ловить собственное предупреждение смысла нет.
    const cssCode = css.replace(/\/\*[\s\S]*?\*\//g, '');
    const jsCode = js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    for (const banned of ['metric-card', 'metric-value', 'stat-value']) {
        assert.ok(!cssCode.includes(`.${banned}`), `использовано опасное имя .${banned}`);
        assert.ok(!jsCode.includes(banned), `использовано опасное имя ${banned} в JS`);
    }
});

test('страница не ломается на периоде, где XYZ не считается', () => {
    assert.match(js, /xyz_available/, 'фронт не читает признак доступности XYZ');
    assert.match(html, /id="pkXyzChip"/, 'нет плашки о недоступности XYZ');
    assert.ok(js.includes('без XYZ'), 'в меню периодов не помечены короткие периоды');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
