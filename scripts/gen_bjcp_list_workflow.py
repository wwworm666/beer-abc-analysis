"""Генератор workflow: перечислить ПОЛНЫЙ список стилей BJCP 2021 (один агент на
категорию 1..34). Каждый агент возвращает стили категории: код, EN, RU (перевод
Profibeer-стиля), 3 рекомендованных дескриптора по правилам владельца из BJCP-профиля.
Это источник для выпадающего списка стилей в редакторе.

Запуск: py -3 scripts/gen_bjcp_list_workflow.py -> scripts/bjcp_list_workflow.js
"""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

RULES = """ПРАВИЛА ДЕСКРИПТОРОВ (для rec каждого стиля):
1. Ровно ТРИ отдельных СЛОВА, не фразы. 2. Честность состава (без фантомных фруктов;
для хефевайцена «гвоздичный» можно, «банановый» нельзя). 3. Названия солодов/процессов
честны (карамельный/шоколадный/жжёный/ореховый/бисквитный). 4. Характер хмеля можно
звать фруктом (цитрусовый/тропический). 5. Без брак-слов («спиртовой»->ликёрный),
одинокий «кислый»->«кисло-сладкий», но «горький»(IPA)/«жжёный»(стаут) — желанны.
6. Без воды («яркий»); «чистый/питкий/освежающий/мягкий» ок. 7. Не переобещать.
8. Три РАЗНЫЕ оси, без дублей. 9. Лагер ведёт «чистый». 10. Стаут — плотный набор
кофе/шоколад/жжёный ок. 11. Порядок = акцент, главное слово вперёд."""

CATS = list(range(1, 35))  # BJCP 2021: категории 1..34

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "category_num": {"type": "integer"},
        "category_ru": {"type": "string", "description": "русское имя категории BJCP"},
        "category_en": {"type": "string"},
        "styles": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "code": {"type": "string", "description": "код, напр. 1A, 21B, 27"},
                    "en": {"type": "string"},
                    "ru": {"type": "string", "description": "русское имя стиля (перевод Profibeer)"},
                    "rec": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["code", "en", "ru", "rec"],
            },
        },
    },
    "required": ["category_num", "category_ru", "styles"],
}

js = """export const meta = {
  name: 'bjcp-2021-list',
  description: 'Полный список стилей BJCP 2021 (RU/EN/код + rec-дескрипторы) по категориям 1..34',
  phases: [{ title: 'BJCP-list', detail: 'один агент на категорию' }],
}
const RULES = __RULES__;
const CATS = __CATS__;
const SCHEMA = __SCHEMA__;

function promptFor(n) {
  return [
    'Ты эксперт BJCP 2021 Style Guidelines. Перечисли ВСЕ пивные стили категории № ' + n,
    'из руководства BJCP 2021 (если не уверен в составе категории — кратко сверься в вебе,',
    'bjcp.org). Для КАЖДОГО стиля категории верни: code (напр. ' + n + 'A), en (английское',
    'имя), ru (русское имя в стиле перевода Profibeer), rec (3 слова-дескриптора вкуса,',
    'выведенные из BJCP-профиля стиля по правилам ниже). Также имя категории ru/en.',
    'Если категория специальная/открытая (напр. 27 историческое, 28 дикий эль, 29 фруктовое,',
    '34 специальное) — перечисли её перечисленные/типовые подстили.',
    '',
    RULES,
    '',
    'Верни строго JSON по схеме (StructuredOutput).',
  ].join('\\n');
}

phase('BJCP-list')
log('Собираю BJCP 2021 по ' + CATS.length + ' категориям')
const out = (await pipeline(
  CATS,
  n => agent(promptFor(n), { label: 'cat:' + n, phase: 'BJCP-list', schema: SCHEMA })
        .then(r => r ? { ...r, category_num: n } : null)
)).filter(Boolean)
const total = out.reduce((s, c) => s + (c.styles ? c.styles.length : 0), 0)
log('Готово: ' + out.length + ' категорий, ' + total + ' стилей')
return out
"""
js = (js.replace("__RULES__", json.dumps(RULES, ensure_ascii=False))
        .replace("__CATS__", json.dumps(CATS))
        .replace("__SCHEMA__", json.dumps(SCHEMA, ensure_ascii=False)))
(ROOT / "scripts/bjcp_list_workflow.js").write_text(js, encoding="utf-8")
print("written: scripts/bjcp_list_workflow.js  (cats:", len(CATS), ")")
