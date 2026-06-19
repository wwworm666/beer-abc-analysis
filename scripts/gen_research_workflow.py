"""
Генерирует самодостаточный workflow-скрипт (JS) для веб-ресёрча вкусов/тегов и шкал
(горечь/плотность/цвет) по сортам из data/menu_research_input.json. Данные о пиве
вшиваются в скрипт (workflow не имеет доступа к ФС), поэтому запускать Workflow нужно
через scriptPath на сгенерированный файл.

Выход: scripts/_research_workflow.js
Запуск: py -3 scripts/gen_research_workflow.py
"""
import os
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "data", "menu_research_input.json")
OUT = os.path.join(ROOT, "scripts", "_research_workflow.js")

beers = json.load(open(IN, encoding="utf-8"))
# компактные поля для подсказки
slim = [{
    "id": b["id"], "name": b.get("name", ""), "latin": b.get("latin", ""),
    "brewery": b.get("brewery", ""), "country": b.get("country", ""),
    "style": b.get("style", ""), "abv": b.get("abv", ""),
} for b in beers]

BEERS_JSON = json.dumps(slim, ensure_ascii=False)

SCRIPT = r'''export const meta = {
  name: 'menu-taste-research',
  description: 'Web-research beer styles to fill taste tags + bitterness/body/color ratings (1-5)',
  phases: [
    { title: 'Research', detail: 'per-beer web search -> 3 tags + gor/plot/cvet' },
    { title: 'Verify', detail: 'sanity-check medium/low confidence ratings vs style' },
  ],
}

const BEERS = __BEERS__;

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    id: { type: 'integer' },
    tags: { type: 'array', items: { type: 'string' }, minItems: 3, maxItems: 3 },
    gor: { type: 'integer', minimum: 1, maximum: 5 },
    plot: { type: 'integer', minimum: 1, maximum: 5 },
    cvet: { type: 'integer', minimum: 1, maximum: 5 },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    sources: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['id', 'tags', 'gor', 'plot', 'cvet', 'confidence'],
}

const VSCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    id: { type: 'integer' },
    tags: { type: 'array', items: { type: 'string' }, minItems: 3, maxItems: 3 },
    gor: { type: 'integer', minimum: 1, maximum: 5 },
    plot: { type: 'integer', minimum: 1, maximum: 5 },
    cvet: { type: 'integer', minimum: 1, maximum: 5 },
    issues: { type: 'string' },
  },
  required: ['id', 'tags', 'gor', 'plot', 'cvet'],
}

const researchPrompt = (b) => `Ты пивной эксперт. Исследуй КОНКРЕТНЫЙ сорт пива и верни данные для меню-карточки.

Сорт:
- Название (рус): ${b.name}
- Латиница/бренд: ${b.latin}
- Пивоварня: ${b.brewery}
- Страна: ${b.country}
- Стиль: ${b.style}
- Крепость: ${b.abv}%

ОБЯЗАТЕЛЬНО используй веб-поиск: найди инструмент WebSearch через ToolSearch (query "select:WebSearch") и вызови его. Сделай 1-3 запроса (название + пивоварня; полезны untappd, ratebeer, сайт пивоварни, profibeer) и найди РЕАЛЬНЫЕ характеристики именно этого пива: стиль, IBU (горечь), цвет (SRM/EBC), начальную плотность (OG), дескрипторы вкуса/аромата. Если точный продукт не находится — опирайся на типичные характеристики указанного стиля и снизь confidence.

Верни строго по схеме:
1) tags — РОВНО 3 слова вкуса/аромата на русском, нижний регистр, по одному прилагательному/существительному (напр. "цитрусовый", "карамельный", "хвойный", "сливочный"). НЕ названия стиля, не общие слова ("вкусный","приятный"). Три РАЗНЫХ самых характерных дескриптора.
2) gor (горечь 1-5 по IBU): 1=<10 (пшеничные/сауэр/фруктовые/медовухи), 2=10-20 (лагеры/блонды/витбиры), 3=20-40 (пэйл-эли/амберы/портеры/стауты), 4=40-60 (IPA), 5=60+ (имперские IPA/DIPA).
3) plot (плотность/тело 1-5 по OG/крепости): 1=лёгкое (OG<1.040, ≤4.5%), 2=лёгкое-среднее, 3=среднее (OG~1.045-1.055, 5-6%), 4=полное (OG 1.060-1.075, 7-9%), 5=очень полное (OG 1.080+, 10%+, имперские/квадрупели).
4) cvet (цвет 1-5 по SRM): 1=соломенный (SRM<4: пилс/витбир/блонд/гозе), 2=золотистый (4-7), 3=янтарный/медный (8-14: амбер/мэрцен/трипель), 4=коричневый (15-24: дюббель/браун/портер), 5=чёрный (25+: стаут).
5) confidence: high=нашёл точные данные сорта; medium=часть данных или по бренду/линейке; low=только по стилю.
6) sources: использованные URL/площадки.
echo id=${b.id}.`

const verifyPrompt = (b, r) => `Проверь черновую оценку пивной карточки на непротиворечивость и правильность сорта.
Сорт: ${b.name} / ${b.latin} / ${b.brewery} / стиль "${b.style}" / ${b.abv}%.
Черновик: tags=${JSON.stringify(r.tags)}, gor=${r.gor}, plot=${r.plot}, cvet=${r.cvet} (confidence=${r.confidence}).
Сверь шкалы со стилем; при сомнении сделай 1 веб-поиск (WebSearch через ToolSearch). Исправь явные ошибки:
- цвет: стаут/портер 4-5, дюббель/браун 4, амбер/трипель 3, лагер/блонд/витбир/гозе 1-2;
- горечь: IPA 4 (имперский 5), пэйл-эль/портер 3, лагер/блонд 2, сауэр/пшеничное/фруктовое 1-2;
- плотность: имперские/квадрупели 5, крепкие (8-9%) 4, средние (5-6%) 3, сессионные (≤4.5%) 1-2.
Теги — РОВНО 3 разных русских слова вкуса, соответствующих стилю.
Верни ИТОГОВЫЕ id=${b.id}, tags(3), gor, plot, cvet, issues (что поправил, кратко; "" если ок).`

const results = await pipeline(
  BEERS,
  (b) => agent(researchPrompt(b), {
    label: `research:${b.id} ${b.name}`.slice(0, 48),
    phase: 'Research', schema: SCHEMA, agentType: 'general-purpose',
  }),
  (r, b) => {
    if (!r) return null
    if (r.confidence === 'high') return r
    return agent(verifyPrompt(b, r), {
      label: `verify:${b.id} ${b.name}`.slice(0, 48),
      phase: 'Verify', schema: VSCHEMA, agentType: 'general-purpose',
    }).then(v => v ? { ...r, tags: v.tags, gor: v.gor, plot: v.plot, cvet: v.cvet, _issues: v.issues } : r)
  }
)

const out = results.filter(Boolean).map(r => ({
  id: r.id, tags: r.tags, gor: r.gor, plot: r.plot, cvet: r.cvet,
  confidence: r.confidence, sources: (r.sources || []).slice(0, 4),
}))
log(`research done: ${out.length}/${BEERS.length} beers`)
return out
'''

script = SCRIPT.replace("__BEERS__", BEERS_JSON)
open(OUT, "w", encoding="utf-8").write(script)
print(f"[ok] {len(slim)} beers baked -> {OUT}")
