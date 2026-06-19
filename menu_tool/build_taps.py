"""
Собирает отдельный набор карточек по текущим кранам (НЕ трогает menu_items.json).

Вход:
  data/menu_taps_cards.json   — результат воркфлоу-исследования (name_ru, latin,
                                brewery, country, style_ru, abv, tags, gor/plot/cvet)
  data/menu_tap_prices.json   — цены из iiko (p025/p04/p05 по номеру крана)
Выход:
  menu_tool/data/menu_taps.json — карточки в формате menu_card.html (id, n, name,
                                latin, brewery, country, style, abv, tags, ratings,
                                p025/p03/p04/p05)
  menu_tool/taps_print.html   — одна печатная HTML-страница со всеми карточками A4
                                (тот же шаблон menu_card.html; открыть в браузере ->
                                Печать/Сохранить как PDF, A4 100%, без полей).

Запуск: py -3 menu_tool/build_taps.py
"""
import os
import re
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)  # для import menu_routes / app

CARDS_IN = os.path.join(ROOT, "data", "menu_taps_cards.json")
PRICES_IN = os.path.join(ROOT, "data", "menu_tap_prices.json")
DATA_OUT = os.path.join(HERE, "data", "menu_taps.json")
PRINT_OUT = os.path.join(HERE, "taps_print.html")
EDIT_OUT = os.path.join(HERE, "taps_edit.html")
FONT_CSS = os.path.join(HERE, "fonts", "ptserif.css")  # PT Serif, base64 (offline)

# Ссылки на Google Fonts CDN из menu_card.html — выкидываем и встраиваем шрифт
# локально (base64), чтобы taps_*.html работали без сети и без CORS на file://.
GF_LINK_RE = re.compile(r"\s*<link[^>]+fonts\.(?:googleapis|gstatic)\.com[^>]*>", re.I)


def _embedded_font_style():
    if os.path.exists(FONT_CSS):
        with open(FONT_CSS, encoding="utf-8") as f:
            return "<style>\n" + f.read() + "\n</style>"
    return ""  # запасной вариант: CDN-ссылки останутся


# Точечные правки под формат печатной карточки: заголовок = ПРОДУКТ, пивоварня
# уходит в строку происхождения; слишком длинные заголовки переполняют A4 (авто-
# уменьшение упирается в 38pt на 23+ символах). Сырое исследование с источниками —
# в data/menu_taps_cards.json, здесь только косметика под вёрстку.
OVERRIDES = {
    5:  {"style": "Хейзи ИПА"},                                    # было "НЕ ИПА" — двусмысленно
    8:  {"name": "Мёд и Абрикос", "latin": "Honey & Apricot"},     # бренд -> в brewery
    9:  {"name": "Морнинг Маня", "latin": "Morning Manya"},
    10: {"name": "Рустик", "latin": "Rustiq"},
    15: {"name": "Клюквенная Пастила", "latin": "Cranberry Pastila"},
    16: {"name": "Сигнал Файр", "latin": "Signal Fire"},
    22: {"name": "Хартлесс Бич 2.0", "latin": "Heartless Bitch 2.0", "style": "Сидр"},
    23: {"name": "Коммерциенрат Приват", "latin": "Commerzienrat Privat"},
}
# Короткая форма пивоварни для строки происхождения (без "Brewery/Brauhaus/скобок").
BREWERY = {
    1: "ФестХаус", 2: "Van Steenberge", 3: "ФестХаус", 5: "Plan B", 6: "Островица",
    7: "Brewlok", 8: "Степь и Ветер", 9: "Zavod", 10: "Bullevie",
    12: "Bourgogne des Flandres", 13: "Rewort", 14: "Omer Vander Ghinste",
    15: "Black Cat", 16: "Polnochnyj Project", 17: "Konix", 18: "Palm",
    20: "Alaska", 21: "Островица", 22: "Gravity Project", 23: "Riegele", 24: "Brewlok",
}


def load_cards():
    raw = json.load(open(CARDS_IN, encoding="utf-8"))
    # воркфлоу мог вернуть {"cards":[...]} или просто [...]
    return raw["cards"] if isinstance(raw, dict) and "cards" in raw else raw


def build_items():
    cards = load_cards()
    prices = json.load(open(PRICES_IN, encoding="utf-8"))
    items = []
    for c in cards:
        tap = int(c["tap"])
        ov = OVERRIDES.get(tap, {})
        pr = prices.get(str(tap), {}).get("prices", {})
        items.append({
            "id": tap,
            "n": tap,
            "name": ov.get("name", c.get("name_ru", "").strip()),
            "latin": ov.get("latin", c.get("latin", "").strip()),
            "brewery": BREWERY.get(tap, c.get("brewery", "").strip()),
            "country": c.get("country", "").strip(),
            "style": ov.get("style", c.get("style_ru", "").strip()),
            "abv": str(c.get("abv", "")).strip(),
            "tags": [str(t).strip() for t in (c.get("tags") or [])][:3],
            "ratings": {
                "gor": int(c.get("gor") or 0),
                "plot": int(c.get("plot") or 0),
                "cvet": int(c.get("cvet") or 0),
            },
            "p025": pr.get("p025"),
            "p03": pr.get("p03"),
            "p04": pr.get("p04"),
            "p05": pr.get("p05"),
        })
    items.sort(key=lambda x: x["n"])
    os.makedirs(os.path.dirname(DATA_OUT), exist_ok=True)
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return items


def render_print(items):
    """Одна HTML со всеми карточками: тот же шаблон menu_card.html (single source)."""
    from app import create_app
    from menu_routes import _decorate, _resolve_variant
    app = create_app()
    art_re = re.compile(r"<article\b.*?</article>", re.S)
    with app.test_request_context():
        from flask import render_template
        variant = _resolve_variant()
        shell = None
        articles = []
        for it in items:
            html = render_template("menu_card.html", item=_decorate(it),
                                   variant=variant, standalone=True)
            if shell is None:
                shell = html                      # полный документ (head/style/script)
                articles.append(art_re.search(html).group(0))
            else:
                articles.append(art_re.search(html).group(0))
    # все <article> подряд перед служебным <script> (fitTags) в shell
    body = "\n".join(articles)
    combined = art_re.sub(lambda m: "", shell, count=1)        # убрать одиночный article из shell
    combined = combined.replace("<body>", "<body>\n" + body + "\n", 1)
    # Шаблон рассчитан на ОДНУ карточку (body=flex-строка, центрирование одной .page).
    # Для буклета из 21 карточки складываем их вертикально, каждая на своей A4-странице.
    stack = ("<style>body{display:block!important}"
             ".page{margin:0 auto!important}</style>")
    combined = GF_LINK_RE.sub("", combined)                    # убрать CDN-ссылки шрифта
    combined = combined.replace("</head>", _embedded_font_style() + stack + "</head>", 1)
    with open(PRINT_OUT, "w", encoding="utf-8") as f:
        f.write(combined)


# Самодостаточная страница-редактор (открывается из файла, без сервера): правка
# тегов/вкусов/шкал с живым превью, экспорт menu_taps.json, печать в PDF. Карточки
# рендерятся тем же markup/CSS, что menu_card.html (включая авто-уменьшение заголовка).
EDITOR_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Меню кранов - правка вкусов и тегов</title>
__FONTS__
__STYLE__
<style>
  body{display:block!important;background:#2a2824;color:#e8e3d8;
       font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:0 0 90px}
  /* Карточки — всегда PT Serif: не наследовать sans-serif редактора (иначе и превью,
     и печать из редактора рендерятся системным шрифтом, хотя PT Serif загружен). */
  .page{font-family:"PT Serif",Georgia,serif}
  #toolbar{position:sticky;top:0;z-index:10;background:#1c1a17;border-bottom:1px solid #3a362f;
           padding:14px 22px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
  #toolbar h1{font-size:16px;margin:0 auto 0 0;font-weight:600}
  .btn{background:#0e7c5a;color:#fff;border:0;border-radius:8px;padding:10px 16px;
       font-size:14px;font-weight:600;cursor:pointer}
  .btn.sec{background:#3a362f}
  .hint{padding:12px 22px;color:#9a948a;font-size:13px;max-width:1000px;line-height:1.55}
  .row{display:flex;gap:24px;align-items:flex-start;padding:18px 22px;border-bottom:1px solid #2c2924}
  .prev{width:270px;height:382px;flex:0 0 270px;overflow:hidden;background:#fff;
        border-radius:4px;box-shadow:0 2px 14px rgba(0,0,0,.4)}
  .scaler{width:794px;transform:scale(.34);transform-origin:top left}
  .form{flex:1;min-width:0;max-width:660px}
  .rowhead{font-size:15px;margin-bottom:12px;color:#cfc9bd}
  .form label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#9a948a;margin-bottom:10px}
  .form input{background:#211f1b;border:1px solid #3a362f;border-radius:6px;color:#ece7dc;
              padding:9px 10px;font-size:14px;font-family:inherit}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}
  .tagrow{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
  .meterrow{display:grid;grid-template-columns:auto 1fr;gap:8px 12px;align-items:center;margin-top:8px}
  .meterrow>span{font-size:13px;color:#cfc9bd}
  .dots{display:flex;gap:6px}
  .dotbtn{width:26px;height:16px;border:1px solid #6a6459;background:transparent;border-radius:3px;cursor:pointer;padding:0}
  .dotbtn.on{background:#d8cdb8;border-color:#d8cdb8}
  #print{display:none}
  @media print{
    #toolbar,.hint,#editor{display:none!important}
    body{background:#fff!important;padding:0}
    #print{display:block!important}
    .page{page-break-after:always;break-after:page;margin:0 auto}
  }
</style></head><body>
<div id="toolbar">
  <h1>Меню кранов - правка вкусов и тегов</h1>
  <button class="btn" onclick="downloadJSON()">Скачать menu_taps.json</button>
  <button class="btn sec" onclick="window.print()">Печать / PDF</button>
</div>
<div class="hint">Меняй <b>теги</b> (3 слова вкуса), стиль, крепость и шкалы
(горечь / плотность / цвет) - превью обновляется сразу. <b>Печать / PDF</b> печатает все
карточки A4 (масштаб 100%, без полей). <b>Скачать</b> сохраняет правки в menu_taps.json -
заменишь им файл в menu_tool/data/ (или пришли мне), чтобы пересобрать общий PDF.</div>
<div id="editor"></div>
<div id="print"></div>
<script>
const CARDS = __DATA__;
const esc = s => (s==null?"":String(s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const fmt = v => (v===null||v===undefined||v==="")?"—":String(v).replace(".",",");
const pad2 = n => String(n).padStart(2,"0");
function nameClass(n){const l=(n||"").length;if(l>22)return"len-xl";if(l>16)return"len-lg";if(l>11)return"len-md";return"";}
function dotsHTML(n){let h="";for(let i=1;i<=5;i++)h+=`<span class="d${i<=n?" on":""}"></span>`;return h;}
function cardInner(it){
  const trans=it.latin?`<div class="trans">[ ${esc(it.latin)} ]</div>`:"";
  const op=[];if(it.country)op.push(`<span class="accent">${esc(it.country)}</span>`);if(it.brewery)op.push(esc(it.brewery));
  const tags=(it.tags||[]).map((t,i)=>`${i?'<span class="dot">·</span>':""}<span>${esc(t)}</span>`).join("");
  const r=it.ratings||{};
  return `<span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
    <header class="eyebrow"><span class="num">№ ${pad2(it.n||0)}</span></header>
    <section class="hero">${trans}<h1 class="name ${nameClass(it.name)}">${esc(it.name)}</h1>
      <div class="origin">${op.join(" · ")}</div></section>
    <section class="facts"><span class="style">${esc(it.style)}</span>
      <span class="abv">${esc(it.abv)}<span class="pct">%</span></span></section>
    <section class="tags">${tags}</section>
    <section class="meters">
      <div class="meter"><span class="k">горечь</span><div class="scale">${dotsHTML(r.gor)}</div></div>
      <div class="meter"><span class="k">плотность</span><div class="scale">${dotsHTML(r.plot)}</div></div>
      <div class="meter"><span class="k">цвет</span><div class="scale">${dotsHTML(r.cvet)}</div></div></section>
    <section class="prices v3">
      <div class="price"><span class="vol">0,25</span><span class="num">${fmt(it.p025)}</span></div>
      <div class="price"><span class="vol">0,4</span><span class="num">${fmt(it.p04)}</span></div>
      <div class="price"><span class="vol">0,5</span><span class="num">${fmt(it.p05)}</span></div></section>`;
}
function fitName(el){if(!el)return;el.style.fontSize="";let s=parseFloat(getComputedStyle(el).fontSize);while(el.scrollHeight>140&&s>36){s-=1;el.style.fontSize=s+"px";}}
function fitTags(el){if(!el)return;el.style.fontSize="";let s=parseFloat(getComputedStyle(el).fontSize);while(el.scrollWidth>el.clientWidth+1&&s>14){s-=1;el.style.fontSize=s+"px";}}
function paint(i){
  [document.getElementById("prev-"+i),document.getElementById("print-"+i)].forEach(a=>{
    if(!a)return;a.innerHTML=cardInner(CARDS[i]);fitName(a.querySelector(".name"));fitTags(a.querySelector(".tags"));
  });
}
function setTag(i,j,v){const t=(CARDS[i].tags||["","",""]).slice();while(t.length<3)t.push("");t[j]=v;CARDS[i].tags=t.map(x=>x).slice(0,3);paint(i);}
function setField(i,k,v){CARDS[i][k]=v;paint(i);}
function setRating(i,k,v){CARDS[i].ratings=CARDS[i].ratings||{};CARDS[i].ratings[k]=v;paint(i);renderDots(i,k);}
function renderDots(i,only){
  ["gor","plot","cvet"].forEach(k=>{
    if(only&&only!==k)return;
    const box=document.getElementById(`dots-${i}-${k}`);if(!box)return;
    const val=(CARDS[i].ratings||{})[k]||0;box.innerHTML="";
    for(let n=1;n<=5;n++){const b=document.createElement("button");b.type="button";
      b.className="dotbtn"+(n<=val?" on":"");b.onclick=()=>setRating(i,k,(val===n?n-1:n));box.appendChild(b);}
  });
}
function downloadJSON(){
  const blob=new Blob([JSON.stringify(CARDS,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="menu_taps.json";
  document.body.appendChild(a);a.click();a.remove();
}
function build(){
  const ed=document.getElementById("editor"),pr=document.getElementById("print");
  CARDS.forEach((it,i)=>{
    const tg=it.tags||[];
    const row=document.createElement("div");row.className="row";
    row.innerHTML=`
      <div class="prev"><div class="scaler"><article class="page" id="prev-${i}"></article></div></div>
      <div class="form">
        <div class="rowhead">Кран №${it.n} — <b>${esc(it.name)}</b></div>
        <div class="grid2">
          <label>Стиль<input value="${esc(it.style)}" oninput="setField(${i},'style',this.value)"></label>
          <label>Крепость, %<input value="${esc(it.abv)}" oninput="setField(${i},'abv',this.value)"></label>
        </div>
        <div class="tagrow">
          <label>Тег 1<input value="${esc(tg[0]||"")}" oninput="setTag(${i},0,this.value)"></label>
          <label>Тег 2<input value="${esc(tg[1]||"")}" oninput="setTag(${i},1,this.value)"></label>
          <label>Тег 3<input value="${esc(tg[2]||"")}" oninput="setTag(${i},2,this.value)"></label>
        </div>
        <div class="meterrow">
          <span>Горечь</span><div class="dots" id="dots-${i}-gor"></div>
          <span>Плотность</span><div class="dots" id="dots-${i}-plot"></div>
          <span>Цвет</span><div class="dots" id="dots-${i}-cvet"></div>
        </div>
      </div>`;
    ed.appendChild(row);
    const a=document.createElement("article");a.className="page";a.id="print-"+i;pr.appendChild(a);
  });
  CARDS.forEach((_,i)=>{paint(i);renderDots(i);});
}
build();
if(document.fonts&&document.fonts.ready){document.fonts.ready.then(()=>{CARDS.forEach((_,i)=>paint(i));});}
</script></body></html>
"""


def render_editor(items):
    """Самодостаточная страница-редактор taps_edit.html (данные встроены)."""
    from app import create_app
    from menu_routes import _decorate, _resolve_variant
    app = create_app()
    with app.test_request_context():
        from flask import render_template
        one = render_template("menu_card.html", item=_decorate(items[0]),
                              variant=_resolve_variant(), standalone=True)
    style = re.search(r"<style>.*?</style>", one, re.S).group(0)
    # шрифт — локальный base64 (offline), без Google Fonts CDN
    cdn = "\n".join(re.findall(r'<link[^>]+rel="(?:preconnect|stylesheet)"[^>]*>', one))
    font_head = _embedded_font_style() or cdn
    html = (EDITOR_HTML
            .replace("__FONTS__", font_head)
            .replace("__STYLE__", style)
            .replace("__DATA__", json.dumps(items, ensure_ascii=False)))
    with open(EDIT_OUT, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    items = build_items()
    render_print(items)
    render_editor(items)
    print(f"[ok] {len(items)} карточек -> {DATA_OUT}")
    print(f"[ok] печать -> {PRINT_OUT}")
    print(f"[ok] редактор -> {EDIT_OUT}")
    for it in items:
        r = it["ratings"]
        pr = f"{it['p025']}/{it['p04']}/{it['p05']}"
        print(f"  #{it['n']:>2} {it['name'][:24]:24s} {it['style'][:16]:16s} "
              f"{it['abv']:>4}%  гор{r['gor']} пл{r['plot']} цв{r['cvet']}  {pr}  "
              f"{', '.join(it['tags'])}")


if __name__ == "__main__":
    main()
