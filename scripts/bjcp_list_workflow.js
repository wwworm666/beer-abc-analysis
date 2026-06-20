export const meta = {
  name: 'bjcp-2021-list',
  description: 'Полный список стилей BJCP 2021 (RU/EN/код + rec-дескрипторы) по категориям 1..34',
  phases: [{ title: 'BJCP-list', detail: 'один агент на категорию' }],
}
const RULES = "ПРАВИЛА ДЕСКРИПТОРОВ (для rec каждого стиля):\n1. Ровно ТРИ отдельных СЛОВА, не фразы. 2. Честность состава (без фантомных фруктов;\nдля хефевайцена «гвоздичный» можно, «банановый» нельзя). 3. Названия солодов/процессов\nчестны (карамельный/шоколадный/жжёный/ореховый/бисквитный). 4. Характер хмеля можно\nзвать фруктом (цитрусовый/тропический). 5. Без брак-слов («спиртовой»->ликёрный),\nодинокий «кислый»->«кисло-сладкий», но «горький»(IPA)/«жжёный»(стаут) — желанны.\n6. Без воды («яркий»); «чистый/питкий/освежающий/мягкий» ок. 7. Не переобещать.\n8. Три РАЗНЫЕ оси, без дублей. 9. Лагер ведёт «чистый». 10. Стаут — плотный набор\nкофе/шоколад/жжёный ок. 11. Порядок = акцент, главное слово вперёд.";
const CATS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34];
const SCHEMA = {"type": "object", "additionalProperties": false, "properties": {"category_num": {"type": "integer"}, "category_ru": {"type": "string", "description": "русское имя категории BJCP"}, "category_en": {"type": "string"}, "styles": {"type": "array", "items": {"type": "object", "additionalProperties": false, "properties": {"code": {"type": "string", "description": "код, напр. 1A, 21B, 27"}, "en": {"type": "string"}, "ru": {"type": "string", "description": "русское имя стиля (перевод Profibeer)"}, "rec": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3}}, "required": ["code", "en", "ru", "rec"]}}}, "required": ["category_num", "category_ru", "styles"]};

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
  ].join('\n');
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
