"""
Генерирует workflow-скрипт для веб-исследования НОВЫХ сортов (только имя из iiko):
заполняет название (рус), латиницу, пивоварню, страну, стиль, ABV, 3 тега и шкалы.
Данные вшиваются в скрипт (у workflow нет доступа к ФС) -> запускать через scriptPath.

Вход:  data/menu_new_sorts.json  (из scripts/add_csv_sorts.py)
Выход: scripts/_newsorts_workflow.js
Запуск: py -3 scripts/gen_newsorts_workflow.py
"""
import os
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "data", "menu_new_sorts.json")
OUT = os.path.join(ROOT, "scripts", "_newsorts_workflow.js")

sorts = json.load(open(IN, encoding="utf-8"))
slim = [{"id": s["id"], "name_src": s["name_src"]} for s in sorts]
BEERS_JSON = json.dumps(slim, ensure_ascii=False)

SCRIPT = r'''export const meta = {
  name: 'menu-newsorts-research',
  description: 'Web-research new beer sorts (name only) -> full card fields + tags + ratings',
  phases: [
    { title: 'Research', detail: 'per-sort web search -> name/brewery/style/abv/tags/ratings' },
    { title: 'Verify', detail: 'sanity-check medium/low confidence vs style' },
  ],
}

const BEERS = __BEERS__;

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    id: { type: 'integer' },
    name_ru: { type: 'string' },
    latin: { type: 'string' },
    brewery: { type: 'string' },
    country: { type: 'string' },
    style: { type: 'string' },
    abv: { type: 'string' },
    tags: { type: 'array', items: { type: 'string' }, minItems: 3, maxItems: 3 },
    gor: { type: 'integer', minimum: 1, maximum: 5 },
    plot: { type: 'integer', minimum: 1, maximum: 5 },
    cvet: { type: 'integer', minimum: 1, maximum: 5 },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    sources: { type: 'array', items: { type: 'string' } },
  },
  required: ['id', 'name_ru', 'style', 'abv', 'tags', 'gor', 'plot', 'cvet', 'confidence'],
}

const VSCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    id: { type: 'integer' },
    style: { type: 'string' },
    abv: { type: 'string' },
    tags: { type: 'array', items: { type: 'string' }, minItems: 3, maxItems: 3 },
    gor: { type: 'integer', minimum: 1, maximum: 5 },
    plot: { type: 'integer', minimum: 1, maximum: 5 },
    cvet: { type: 'integer', minimum: 1, maximum: 5 },
    issues: { type: 'string' },
  },
  required: ['id', 'style', 'abv', 'tags', 'gor', 'plot', 'cvet'],
}

const researchPrompt = (b) => `Ты пивной эксперт. По названию сорта из системы продаж бара собери данные для меню-карточки.

Название сорта (как в iiko, может включать пивоварню и объём): "${b.name_src}"

ОБЯЗАТЕЛЬНО используй веб-поиск: найди WebSearch через ToolSearch (query "select:WebSearch") и вызови. Определи КОНКРЕТНОЕ пиво: пивоварню, страну, стиль, крепость (ABV %), цвет (SRM), горечь (IBU), плотность (OG), дескрипторы вкуса. Сделай 1-3 запроса (untappd, сайт пивоварни, profibeer, craftbeer78, винные магазины). Если точно не находишь — опирайся на стиль и снизь confidence.

Верни строго по схеме:
- name_ru: КОРОТКОЕ отображаемое название НА РУССКОМ, ТОЛЬКО продукт (без пивоварни) — это заголовок карточки КАПСом. Латиницу транскрибируй: "Brewlok IPA" -> "Брюлок ИПА", "Velka Morava Пятипитие" -> "Пятипитие". Если в названии уже русский продукт — оставь как есть, убрав пивоварню/объём.
- latin: оригинальное/латинское название (бренд+продукт), напр. "Monk's Café", "Brewlok IPA". Если только русское — можно пусто.
- brewery: пивоварня коротко (без "Brewery/Brauhaus/Пивоварня").
- country: страна.
- style: стиль ПО-РУССКИ (напр. "Хейзи ИПА", "Чешский лагер", "Имперский стаут").
- abv: крепость числом с запятой ("5,2").
- tags: РОВНО 3 русских слова вкуса/аромата, нижний регистр, разные (напр. "цитрусовый","карамельный","хвойный"). Не названия стиля.
- gor (горечь 1-5 по IBU): 1=<10 (пшеничные/сауэр/фруктовые), 2=10-20 (лагеры/блонды), 3=20-40 (пэйл/амбер/портер), 4=40-60 (IPA), 5=60+ (имперские IPA/DIPA).
- plot (плотность 1-5): 1=лёгкое (<4.5%), 2, 3=среднее (5-6%), 4=полное (7-9%), 5=очень полное (10%+/имперские).
- cvet (цвет 1-5 по SRM): 1=соломенный (пилс/витбир/блонд), 2=золотистый, 3=янтарный/медный, 4=коричневый, 5=чёрный (стаут).
- confidence: high/medium/low. sources: URL.
echo id=${b.id}.`

const verifyPrompt = (b, r) => `Проверь черновик карточки пива на непротиворечивость.
Сорт iiko: "${b.name_src}". Черновик: стиль "${r.style}", ${r.abv}%, tags=${JSON.stringify(r.tags)}, gor=${r.gor}, plot=${r.plot}, cvet=${r.cvet} (confidence=${r.confidence}).
Сверь шкалы со стилем (при сомнении 1 веб-поиск). Правила: цвет стаут/портер 4-5, амбер/трипель 3, лагер/блонд/витбир/гозе 1-2; горечь IPA 4 (имперский 5), лагер/блонд 2, сауэр/пшеничное 1-2; плотность имперские 5, крепкие(8-9%) 4, средние(5-6%) 3, сессионные 1-2. Теги — 3 разных русских слова вкуса.
Верни ИТОГ id=${b.id}: style, abv, tags(3), gor, plot, cvet, issues (кратко; "" если ок).`

const results = await pipeline(
  BEERS,
  (b) => agent(researchPrompt(b), {
    label: `research:${b.id} ${b.name_src}`.slice(0, 52),
    phase: 'Research', schema: SCHEMA, agentType: 'general-purpose',
  }),
  (r, b) => {
    if (!r) return null
    if (r.confidence === 'high') return r
    return agent(verifyPrompt(b, r), {
      label: `verify:${b.id}`.slice(0, 40),
      phase: 'Verify', schema: VSCHEMA, agentType: 'general-purpose',
    }).then(v => v ? { ...r, style: v.style, abv: v.abv, tags: v.tags, gor: v.gor, plot: v.plot, cvet: v.cvet, _issues: v.issues } : r)
  }
)

const out = results.filter(Boolean).map(r => ({
  id: r.id, name_ru: r.name_ru, latin: r.latin || '', brewery: r.brewery || '',
  country: r.country || '', style: r.style, abv: r.abv,
  tags: r.tags, gor: r.gor, plot: r.plot, cvet: r.cvet,
  confidence: r.confidence, sources: (r.sources || []).slice(0, 4),
}))
log(`newsorts research done: ${out.length}/${BEERS.length}`)
return out
'''

open(OUT, "w", encoding="utf-8").write(SCRIPT.replace("__BEERS__", BEERS_JSON))
print(f"[ok] {len(slim)} new sorts baked -> {OUT}")
