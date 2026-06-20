"""Генератор workflow-скрипта: по каждому СТИЛЮ вывести 3 дескриптора вкуса из
официального профиля BJCP 2021 (aroma/flavor/mouthfeel) по правилам владельца, и
сравнить с прежним набором (мода пер-сорт тегов). Плюс агент даёт BJCP код + RU/EN имя.

Запуск: py -3 scripts/gen_style_taste_workflow.py -> scripts/style_taste_workflow.js
"""
import json, pathlib
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
cards = json.load(open(ROOT / "data/menu_cards.json", encoding="utf-8"))

by = defaultdict(list)
ex = defaultdict(list)
for c in cards:
    by[c["style"]].append(c.get("tags") or [])
    if len(ex[c["style"]]) < 3:
        ex[c["style"]].append(f'{c.get("name","")} ({c.get("abv","")}%)')

styles = []
for st, taglists in by.items():
    triples = Counter(tuple(t) for t in taglists if len(t) == 3)
    words = Counter(w for t in taglists for w in t)
    prior = list(triples.most_common(1)[0][0]) if triples else [w for w, _ in words.most_common(3)]
    styles.append({
        "style": st,
        "n": len(taglists),
        "prior": prior,
        "freq": [w for w, _ in words.most_common(5)],
        "examples": ex[st],
    })
styles.sort(key=lambda s: (-s["n"], s["style"].lower()))

RULES = """ПРАВИЛА ДЕСКРИПТОРОВ ВКУСА (соблюдай строго):
1. Ровно ТРИ отдельных СЛОВА-дескриптора, НЕ фразы.
2. Честность состава: опора на реальные солод/хмель/дрожжи/процесс, без фантомных
   фруктов (банан/слива из дрожжевого эфира — нельзя). Для хефевайцена допускается
   «гвоздичный» как подпись стиля (решение владельца), но НЕ «банановый».
3. Названия солодов/процессов честны (карамельный, шоколадный, бисквитный, жжёный,
   ореховый — это сами солода).
4. Характер ХМЕЛЯ можно звать его фруктовым дескриптором (цитрусовый, тропический) —
   это характер хмеля, не добавленный фрукт.
5. Не писать брак-слова: «спиртовой»->ликёрный/согревающий; «смолистый» убрать; но
   «горький» для IPA и «жжёный» для стаута — желанный характер; одинокий «кислый»->
   «кисло-сладкий».
6. Без маркетинговой воды («яркий»). «чистый/питкий/освежающий/мягкий» — ОК.
7. Не переобещать интенсивность.
8. Без дублей — три РАЗНЫЕ оси (солод/хмель/финиш и т.п.); «горький+хмелевой» = дубль.
9. Лагер — веди «чистый», максимум один вкусовой якорь.
10. Плотность вкусов под стиль: у стаута кофе/шоколад/жжёный уместны вместе.
11. Порядок = АКЦЕНТ, главное слово вперёд."""

EXAMPLES = """ЭТАЛОНЫ владельца:
- Тёмный трипель (Gulden Draak) -> карамельный, бисквитный, ликёрный
- Фландрский эль (Bourgogne des Flandres) -> винный, бархатистый, кисло-сладкий
- Чешский лагер (Ferdinand 10) -> чистый, хлебный, питкий
- Хеллес -> чистый, солодовый, мягкий
- Овсяный стаут (Brewlok) -> кофейный, шоколадный, жжёный
- ДИПА -> горький, сухой, цитрусовый"""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "style": {"type": "string", "description": "входное русское имя стиля (эхо)"},
        "bjcp_code": {"type": "string", "description": "код BJCP 2021, напр. 10A, 21B, 16C; X1 если вне BJCP"},
        "bjcp_ru": {"type": "string", "description": "русское имя стиля по BJCP 2021 (перевод Profibeer-стиля)"},
        "bjcp_en": {"type": "string", "description": "оригинальное английское имя стиля BJCP"},
        "bjcp_desc": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                      "description": "3 слова, выведенные ИЗ профиля BJCP (aroma/flavor/mouthfeel) по правилам"},
        "prior_desc": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                       "description": "прежний набор (эхо входа)"},
        "final": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                  "description": "итоговый лучший набор (можно смешать BJCP и прежний)"},
        "better": {"type": "string", "enum": ["bjcp", "prior", "mixed"],
                   "description": "что в итоге лучше"},
        "note": {"type": "string", "description": "кратко: что взял из BJCP, чем лучше/хуже прежнего"},
    },
    "required": ["style", "bjcp_code", "bjcp_ru", "bjcp_en", "bjcp_desc", "prior_desc", "final", "better"],
}

js = """export const meta = {
  name: 'style-taste-bjcp',
  description: 'По каждому стилю вывести 3 дескриптора из профиля BJCP 2021 и сравнить с прежним набором',
  phases: [{ title: 'BJCP', detail: 'один агент на стиль' }],
}

const RULES = __RULES__;
const EXAMPLES = __EXAMPLES__;
const STYLES = __STYLES__;
const SCHEMA = __SCHEMA__;

function promptFor(s) {
  return [
    'Ты эксперт BJCP. Задача: для пивного стиля вывести РОВНО 3 слова-дескриптора вкуса',
    'из ОФИЦИАЛЬНОГО профиля BJCP 2021 (разделы Aroma / Flavor / Mouthfeel / Overall',
    'Impression), переведя сенсорику в честные русские слова по правилам владельца.',
    '',
    RULES,
    '',
    EXAMPLES,
    '',
    'СТИЛЬ (русское имя из каталога): ' + s.style,
    'примеры сортов этого стиля: ' + (s.examples.join('; ') || '—'),
    'ПРЕЖНИЙ набор (выведен из пер-сорт тегов): ' + (s.prior.join(', ') || '—'),
    '',
    'ШАГИ:',
    '1) Определи, какому стилю BJCP 2021 это соответствует: дай код (напр. 10A, 21B, 16C),',
    '   английское имя и русское имя (как в переводе Profibeer). Если стиль вне BJCP',
    '   (томатный гозе, сидр, медовуха, рисовый ИПА и т.п.) — код "X1" и ближайшее имя.',
    '   Если не уверен в профиле конкретного стиля — кратко проверь в вебе (bjcp.org).',
    '2) Из профиля BJCP (солод, хмель, дрожжи, брожение, тело, финиш) выведи РОВНО 3',
    '   честных слова по правилам -> bjcp_desc (главное слово первым).',
    '3) Сравни bjcp_desc с ПРЕЖНИМ набором и выбери ИТОГ (final): можно взять BJCP,',
    '   оставить прежнее или СМЕШАТЬ лучшее из обоих. Укажи better и краткий note',
    '   (чем итог лучше). Цель — самый честный и точный набор для меню.',
    'Верни строго JSON по схеме (StructuredOutput).',
  ].join('\\n');
}

phase('BJCP')
log('BJCP-дескрипторы для ' + STYLES.length + ' стилей (сравнение с прежним набором)')
const out = (await pipeline(
  STYLES,
  s => agent(promptFor(s), { label: 'style:' + s.style, phase: 'BJCP', schema: SCHEMA })
        .then(r => r ? { ...r, style: s.style, prior_desc: s.prior } : null)
)).filter(Boolean)
log('Готово: ' + out.length + ' стилей')
return out
"""
js = (js
      .replace("__RULES__", json.dumps(RULES, ensure_ascii=False))
      .replace("__EXAMPLES__", json.dumps(EXAMPLES, ensure_ascii=False))
      .replace("__STYLES__", json.dumps(styles, ensure_ascii=False))
      .replace("__SCHEMA__", json.dumps(SCHEMA, ensure_ascii=False)))

out_path = ROOT / "scripts/style_taste_workflow.js"
out_path.write_text(js, encoding="utf-8")
print(f"styles: {len(styles)}")
print(f"written: {out_path}")
