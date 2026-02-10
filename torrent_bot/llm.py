"""
Claude API — определение фильма/сериала (текст + картинки) и ранжирование раздач.
"""
import json
import base64
import anthropic
from torrent_bot.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

IDENTIFY_PROMPT = """Ты — эксперт по кино и сериалам. Определи фильм или сериал по описанию/скриншоту пользователя.

ВАЖНО:
- Ты отлично знаешь кино и сериалы до мая 2025
- Думай шире: если описание расплывчатое, подбери НАИБОЛЕЕ ВЕРОЯТНЫЙ вариант
- Учитывай: актёров, режиссёров, сюжет, жанр, год, страну
- Если пользователь пишет "от создателя X" — ищи последние работы этого создателя
- Если отправлен скриншот — анализируй кадр: актёры, стиль, обстановка, субтитры, UI плеера
- Для сериалов обязательно определи тип "series"

Верни JSON:
{
  "title_en": "English title",
  "title_ru": "Русское название",
  "year": 2024,
  "type": "movie" или "series",
  "season": null,
  "episode": null,
  "search_queries": ["запрос1", "запрос2", "запрос3"],
  "confidence": 0.9,
  "reasoning": "Почему я так решил (кратко)"
}

Правила для search_queries:
- 2-3 варианта на русском (для трекеров)
- Для сериалов: "Название сериал", "Название сезон X"
- Для фильмов: "Название год", "Оригинальное название год"
- НЕ используй слишком длинные запросы

confidence:
- > 0.9 — точное название или узнал по скриншоту
- 0.7-0.9 — уверен по описанию
- 0.5-0.7 — вероятный вариант
- < 0.5 — не уверен

Верни ТОЛЬКО JSON, без пояснений."""


def _parse_json(text):
    """Извлечь JSON из ответа Claude (может быть обёрнут в ```json)."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(text)


def identify_content(user_text=None, image_data=None, media_type="image/jpeg"):
    """
    Определяет фильм/сериал по тексту и/или картинке.
    user_text — текст от пользователя (может быть None если только картинка)
    image_data — bytes картинки (может быть None если только текст)
    media_type — MIME тип картинки
    """
    content = []

    if image_data:
        b64 = base64.standard_b64encode(image_data).decode('utf-8')
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64
            }
        })

    prompt_parts = [IDENTIFY_PROMPT]
    if user_text:
        prompt_parts.append(f'\nОписание пользователя: "{user_text}"')
    if image_data and not user_text:
        prompt_parts.append('\nПользователь отправил скриншот. Определи что это за фильм/сериал по кадру.')
    if image_data and user_text:
        prompt_parts.append('\nПользователь также приложил скриншот — используй и текст, и картинку.')

    content.append({"type": "text", "text": "\n".join(prompt_parts)})

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}]
    )

    try:
        return _parse_json(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return None


def identify_from_results(user_text, results):
    """
    Fallback: когда Claude не смог определить контент напрямую,
    ищем на трекере и просим Claude выбрать из результатов.
    """
    if not results:
        return None

    results_text = "\n".join([
        f"{i+1}. {r.get('title', '?')} | {r.get('size', '?')} | Сиды: {r.get('seeds', 0)}"
        for i, r in enumerate(results[:15])
    ])

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": f"""Пользователь ищет: "{user_text}"

Вот результаты поиска на трекере:
{results_text}

Определи, какие из результатов подходят под запрос пользователя.

Верни JSON:
{{
  "matched_indices": [1, 3],
  "title_en": "English title",
  "title_ru": "Русское название",
  "year": 2024,
  "type": "movie" или "series",
  "confidence": 0.8
}}

matched_indices — номера (1-based) подходящих раздач.
Если ничего не подходит — matched_indices: [], confidence: 0.
Верни ТОЛЬКО JSON."""}]
    )

    try:
        return _parse_json(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return None


def rank_releases(movie, releases):
    """
    Получает список раздач, возвращает отсортированный по качеству.
    Claude выбирает лучшие на основе качества, сидов, размера.
    """
    if not releases:
        return []

    if len(releases) <= 3:
        return _enrich_quality(releases)

    content_type = movie.get('type', 'movie')
    is_series = content_type == 'series'

    releases_text = "\n".join([
        f"{i+1}. {r.get('title', '?')} | "
        f"Размер: {r.get('size', '?')} | "
        f"Сиды: {r.get('seeds', 0)} | "
        f"Трекер: {r.get('tracker', '?')}"
        for i, r in enumerate(releases[:20])
    ])

    series_criteria = ""
    if is_series:
        season = movie.get('season')
        episode = movie.get('episode')
        if season:
            series_criteria = f"\n5. Нужен сезон {season}" + (f", серия {episode}" if episode else " (полный)")
        else:
            series_criteria = "\n5. Предпочтительно полные сезоны"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": f"""Отранжируй раздачи для "{movie.get('title_ru', '')}" ({movie.get('title_en', '')}, {movie.get('year', '')}).
Тип: {"сериал" if is_series else "фильм"}

Раздачи:
{releases_text}

Критерии (по приоритету):
1. Качество: 2160p > 1080p > 720p. Remux > BluRay/BDRip > WEB-DL > HDRip
2. Сиды >= 3 (без сидов — не скачается)
3. Русская дорожка (озвучка/субтитры)
4. Разумный размер (1080p ~4-15GB){series_criteria}

Верни JSON:
{{"ranked": [3, 1, 7], "top_reason": "почему топ-1 лучший"}}

Индексы 1-based, от лучшего к худшему. Максимум 5. Только JSON."""}]
    )

    try:
        result = _parse_json(response.content[0].text)
        ranked_indices = result.get('ranked', [])

        ranked = []
        for idx in ranked_indices:
            if 1 <= idx <= len(releases):
                ranked.append(releases[idx - 1])

        return _enrich_quality(ranked) if ranked else _enrich_quality(releases[:5])
    except (json.JSONDecodeError, IndexError):
        return _enrich_quality(releases[:5])


def _enrich_quality(releases):
    """Добавить поле quality если его нет, извлекая из title."""
    for r in releases:
        if not r.get('quality'):
            r['quality'] = _extract_quality(r.get('title', ''))
    return releases


def _extract_quality(title):
    """Извлечь качество из названия раздачи."""
    t = title.lower()

    quality = ''
    for q in ['2160p', '1080p', '720p', '480p']:
        if q in t:
            quality = q
            break

    release_type = ''
    for rt in ['remux', 'blu-ray', 'bluray', 'bdrip', 'bdremux',
               'web-dl', 'webdl', 'webrip', 'hdrip', 'dvdrip', 'hdtvrip']:
        if rt in t:
            release_type = rt.upper()
            break

    result = f"{quality} {release_type}".strip()
    return result or 'Unknown'
