"""
Unified search — ищет по всем трекерам параллельно.
"""
from concurrent.futures import ThreadPoolExecutor
from torrent_bot.trackers.rutracker import get_client as rutracker
from torrent_bot.trackers.kinozal import get_client as kinozal


def search_all_trackers(movie):
    """
    Ищет фильм по всем трекерам.
    movie — dict с полями search_queries, title_ru, title_en, year.
    Возвращает объединённый список раздач.
    """
    queries = movie.get('search_queries', [])
    if not queries:
        # Fallback: русское название + год
        queries = [f"{movie.get('title_ru', '')} {movie.get('year', '')}"]

    all_results = []

    # Ищем по первому запросу на обоих трекерах параллельно
    query = queries[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_safe_search, rutracker(), query): 'rutracker',
            executor.submit(_safe_search, kinozal(), query): 'kinozal',
        }
        for future in futures:
            try:
                results = future.result(timeout=20)
                all_results.extend(results)
            except Exception as e:
                print(f"Search error ({futures[future]}): {e}")

    # Если мало результатов — пробуем второй запрос
    if len(all_results) < 3 and len(queries) > 1:
        query2 = queries[1]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(_safe_search, rutracker(), query2): 'rutracker',
                executor.submit(_safe_search, kinozal(), query2): 'kinozal',
            }
            for future in futures:
                try:
                    results = future.result(timeout=20)
                    # Не дублируем уже найденные
                    existing_ids = {(r['tracker'], r['topic_id']) for r in all_results}
                    for r in results:
                        if (r['tracker'], r['topic_id']) not in existing_ids:
                            all_results.append(r)
                except Exception:
                    pass

    # Фильтруем раздачи без сидов
    all_results = [r for r in all_results if r.get('seeds', 0) >= 1]

    # Базовая сортировка по сидам (Claude потом переранжирует)
    all_results.sort(key=lambda r: r.get('seeds', 0), reverse=True)

    return all_results


def _safe_search(client, query):
    """Обёртка для отлова ошибок."""
    try:
        return client.search(query)
    except Exception as e:
        print(f"Tracker search error: {e}")
        return []
