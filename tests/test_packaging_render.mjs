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
    // Урезание — это .slice(0, N) БЕЗ продолжения. Пара `rows.slice(0, 8)` +
    // `rows.slice(8)` — раскрывашка «первые восемь, остальные под details», как на
    // /draft: показаны все строки, просто не сразу. Такая пара разрешена.
    const cuts = [];
    for (const m of js.matchAll(/\.slice\(0,\s*(\d+)\)/g)) {
        const n = m[1];
        if (!js.includes(`.slice(${n})`)) cuts.push(m[0]);
    }
    assert.deepEqual(cuts, [],
        `остались урезания списков: ${cuts.join(', ')} — «все категории» сломаны`);
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

test('расшифровка букв на экране и совпадает с порогами ядра', () => {
    // Владелец просил видеть значение каждой буквы прямо на странице. Числа в
    // расшифровке обязаны быть теми же, что в core/abc_thresholds.py — иначе
    // страница объясняет одно, а считает другое.
    const key = html.match(/<div class="pk-key" id="pkKey">([\s\S]*?)<\/div>\s*<div class="pk-legend">/);
    assert.ok(key, 'нет блока расшифровки букв под таблицей позиций');
    const rows = (key[1].match(/class="pk-key-row"/g) || []).length;
    assert.equal(rows, 3, `в коде три буквы, строк расшифровки ${rows}`);
    for (const letter of ['a', 'b', 'c', 'x', 'y', 'z', 'none']) {
        assert.ok(key[1].includes(`pk-abc-ltr ${letter}"`), `нет таблетки для ${letter}`);
    }
    const a = thresholds.match(/PARETO_A_MAX_CUM_PERCENT = (\d+)/)[1];
    const b = thresholds.match(/PARETO_B_MAX_CUM_PERCENT = (\d+)/)[1];
    assert.ok(key[1].includes(`первые ${a}%`), `в расшифровке не ${a}% для A`);
    assert.ok(key[1].includes(`следующие ${b - a}%`), `в расшифровке не ${b - a}% для B`);
    assert.ok(key[1].includes(`последние ${100 - b}%`), `в расшифровке не ${100 - b}% для C`);
    const mA = Math.round(parseFloat(thresholds.match(/MARKUP_A_MIN = ([\d.]+)/)[1]) * 100);
    const mB = Math.round(parseFloat(thresholds.match(/MARKUP_B_MIN = ([\d.]+)/)[1]) * 100);
    assert.ok(key[1].includes(`от ${mA}%`), `порог наценки A не ${mA}%`);
    assert.ok(key[1].includes(`от ${mB}% до ${mA}%`), `порог наценки B не ${mB}–${mA}%`);
    assert.ok(key[1].includes(`ниже ${mB}%`), `порог наценки C не ${mB}%`);
    const x = Math.round(parseFloat(thresholds.match(/XYZ_X_MAX_CV = ([\d.]+)/)[1]));
    const y = Math.round(parseFloat(thresholds.match(/XYZ_Y_MAX_CV = ([\d.]+)/)[1]));
    assert.ok(key[1].includes(`до ${x}%`), `порог X не ${x}%`);
    assert.ok(key[1].includes(`от ${x}% до ${y}%`), `порог Y не ${x}–${y}%`);
    assert.ok(key[1].includes(`свыше ${y}%`), `порог Z не ${y}%`);
    const minWeeks = thresholds.match(/MIN_XYZ_WEEKS = (\d+)/)[1];
    assert.ok(key[1].includes(`меньше ${minWeeks} недель`), `минимум недель не ${minWeeks}`);
    // Таблетки буквы XYZ должны быть раскрашены и в CSS.
    for (const letter of ['x', 'y', 'z']) {
        assert.ok(css.includes(`.pk-abc-ltr.${letter} {`), `нет цвета для буквы ${letter}`);
    }
});

test('секция баланса и расхождений — зеркало /draft, в штуках', () => {
    assert.match(html, /БАЛАНС И РАСХОЖДЕНИЯ/, 'нет секции баланса');
    assert.match(html, /всё в штуках/, 'единица не названа');
    for (const id of ['pkBalance', 'pkLosses', 'pkDiag', 'pkUpdated']) {
        assert.ok(html.includes(`id="${id}"`), `нет узла ${id}`);
    }
    for (const cls of ['pk-two', 'pk-card', 'pk-bal-row', 'pk-bal-total', 'pk-loss-row',
                       'pk-more', 'pk-cell-row', 'pk-note']) {
        assert.ok(css.includes(`.${cls}`), `класс .${cls} не описан в CSS`);
    }
    // Пороги плашек взяты с /draft временно — это должно быть сказано в коде.
    assert.match(js, /Пороги те же, что на \/draft/, 'происхождение порогов 10\/30 не объяснено');
    assert.match(js, /function lossTone/, 'нет lossTone');
    assert.ok(js.includes('percent >= 30') && js.includes('percent >= 10'), 'пороги не 10/30');
    // Формула баланса печатается словами и числами.
    assert.ok(js.includes("' − расход '"), 'формула баланса не выводится на экран');
});

test('зеркальные заголовки двух страниц', () => {
    const draft = read('templates/draft.html');
    const nav = read('templates/shared/nav.html');
    assert.match(html, /<title>Фасовка — ABC\/XYZ и потери — Пивная культура<\/title>/);
    assert.match(draft, /<title>Розлив — ABC\/XYZ и потери — Пивная культура<\/title>/);
    assert.match(html, /pk-title-n">Фасовка — ABC\/XYZ и потери</);
    assert.match(draft, /dr-title-n">Розлив — ABC\/XYZ и потери</);
    assert.ok(nav.includes('Фасовка\n') && nav.includes('Розлив\n'), 'пункты меню не переименованы');
    assert.ok(!/ABC\/XYZ анализ\n|Анализ проливов\n/.test(nav), 'в меню остались старые названия');
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
