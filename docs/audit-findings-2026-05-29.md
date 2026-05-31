# Аудит стабильности и скорости — 2026-05-29

Лог реализации правок по итогам аудита (workflow + измерение прод-логов) и
опортунистических находок, замеченных в процессе. Scope A: точечные код-фиксы +
deploy-config + безопасные perf-микрооптимизации. Крупные переписывания отложены.

## Что исправлено (по тирам)

### Tier 1 — измеренная первопричина тормозов
- **Двойной запрос фронта** — убран дублирующий триггер `loadAnalytics()` + in-flight guard. [static/js/dashboard/modules/analytics.js](../static/js/dashboard/modules/analytics.js)
- **Single-flight на бэке** — `cached_olap()` (per-key lock + double-checked locking + мягкий bound кэша). [extensions.py](../extensions.py)
- **Удалён `DASHBOARD_OLAP_CACHE.clear()`** из `revenue_metrics`; оба хендлера переведены на `cached_olap`. [routes/dashboard.py](../routes/dashboard.py)

### Tier 2 — устойчивость iiko
- `timeout=DEFAULT_TIMEOUT (5,60)` на 4 вызова без таймаута; `logout()` bare `except` → лог; кэш `get_groups_with_pos`; guard `authenticate()` при пустых кредах. [core/iiko_api.py](../core/iiko_api.py)
- Retry-бюджет OLAP: `timeout=60`, 2 попытки, ретрай на ConnectTimeout/ConnectionError, backoff. [core/olap_reports.py](../core/olap_reports.py)
- `try/finally` + `logout()` в [routes/schedule.py](../routes/schedule.py) и [routes/taps.py](../routes/taps.py) (утечка слотов лицензии).
- Валидация конфигурации на старте. [app.py](../app.py)

### Tier 3 — конкурентность и долговечность
- Новый общий хелпер [core/json_store.py](../core/json_store.py): `atomic_write_json` + `file_lock`.
- Применён к [core/meeting_notes.py](../core/meeting_notes.py) (atomic + cross-worker RMW + свежее чтение), [core/open_check_subscribers.py](../core/open_check_subscribers.py) (atomic write), [core/taps_manager.py](../core/taps_manager.py) (cross-worker lock + reload перед мутацией + тримминг истории).
- `fsync` перед `os.replace` в [core/plans_manager.py](../core/plans_manager.py).
- `try/except` вокруг тела циклов шедулеров. [core/chz_scheduler.py](../core/chz_scheduler.py), [core/open_check_scheduler.py](../core/open_check_scheduler.py)

### Tier 4 — таймауты Telegram
- `api_call` default timeout 20→8. [core/open_check_telegram.py](../core/open_check_telegram.py)
- aiogram `Bot` с `AiohttpSession(timeout=15)`. [telegram_webhook.py](../telegram_webhook.py)

### Tier 5 — deploy-config (вступит в силу ТОЛЬКО после редеплоя на Selectel)
- gunicorn: `--worker-class gthread --threads 4`, `--timeout 180`, `--max-requests 800 --max-requests-jitter 100`. [Dockerfile](../Dockerfile)
- `Cache-Control` для `/static/*`. [Caddyfile](../Caddyfile)

### Tier 6 — безопасные perf-микрооптимизации (проверены на эквивалентность)
- Мемоизация `prepare_waiter_data`. [core/waiter_analysis.py](../core/waiter_analysis.py)
- Мемоизация `perform_xyz_analysis_by_bar` по бару. [core/xyz_analysis.py](../core/xyz_analysis.py)
- Убран лишний `self.data.copy()` на каждую категорию. [core/category_analysis.py](../core/category_analysis.py)

## Опортунистические находки (замечены при реализации)

| Находка | Файл | Статус |
|---|---|---|
| `revenue_metrics` кэшировал `None`-результат OLAP и шёл в `calculate_metrics(None)` (потенциальный краш) | routes/dashboard.py | Исправлено (cached_olap кэширует только truthy + ранний возврат 500) |
| `get_groups_with_pos` перечитывал статичный XML на каждый employee-запрос | core/iiko_api.py | Исправлено (module-level кэш 10 мин) |
| Инвариант «все mutable JSON пишутся atomic» из overview.md был задекларирован, но не выполнялся (taps/meeting_notes/subscribers) | core/* | Исправлено — теперь выполняется, overview.md стал корректным без правки |
| `_OLAP_INFLIGHT_LOCKS` мог расти без границ | extensions.py | Учтено в helper (лёгкая уборка локов вне кэша) |

## Отложено (крупное/рискованное — НЕ делалось, по решению Scope A)

- Cross-worker дисковый/Redis OLAP-кэш (шаринг между воркерами).
- Шедулер прогрева кэша частых периодов.
- Вынос обработки Telegram-webhook в фоновый поток/очередь.
- Унификация хардкода `/kultura` в 4 файлах ([подводный камень №1](../../C:/KULT/ctr) — отдельная задача).
- [server/chz_receiver.py](../server/chz_receiver.py) — не подключён (мёртвый код), без обработки ошибок.
- `get_git_commit_hash()` в Dockerfile не работает (`.git` в `.dockerignore`) — версия = timestamp старта.

## Проверка (offline, без сети/iiko)

- `import app` — OK
- `python -m unittest tests.test_logic_audit_regressions` — `OK (expected failures=3)` (идентично baseline до правок)
- `python tests/test_draft_analysis.py` — 30 passed, 0 failed
- `python -m compileall core routes extensions.py app.py config.py telegram_webhook.py` — без ошибок
- `node --check analytics.js` — OK
- Эквивалентность Tier 6 (waiter/xyz мемоизация == свежий расчёт) — OK
- Smoke json_store / meeting_notes / taps_manager — OK

`test_all_iiko_apis.py` и `test_weihenstephan_data.py` требуют живого iiko — из offline-гейта исключены.

---

## Запись для docs/CHANGELOG.md

> Добавлена в `docs/CHANGELOG.md` отдельным коммитом (после того как параллельная
> doc-работа по iiko-api была закоммичена в `1985053`). Текст ниже — копия записи.

```markdown
### 2026-05-29 — Аудит стабильности/скорости: дедуп фронта, single-flight, atomic-write, таймауты iiko/Telegram

Измерение прод-логов вскрыло первопричину тормозов дашборда: фронт слал
`/api/dashboard-analytics` дважды, пара попадала на оба gunicorn-воркера
одновременно, оба мимо кэша (стампед), оба на 16-17с заняты одним OLAP — на это
время весь сайт без свободных воркеров. Hit-rate кэша был ~17%.

**Что:**
- Tier 1: убран двойной запрос фронта + in-flight guard; backend single-flight
  (`cached_olap`); удалён отладочный `DASHBOARD_OLAP_CACHE.clear()`.
- Tier 2: таймауты на 4 iiko-вызовах, retry-бюджет OLAP под gunicorn timeout,
  try/finally+logout (утечка слотов), кэш groups, валидация конфига.
- Tier 3: общий `core/json_store.py` (atomic_write + cross-worker lock), применён
  к taps/meeting_notes/subscribers; fsync в plans_manager; try/except в шедулерах.
- Tier 4: таймауты Telegram (api_call 8с, aiogram session 15с).
- Tier 5 (нужен редеплой): gunicorn gthread/threads=4, timeout=180,
  max-requests=800; Caddy Cache-Control для /static.
- Tier 6: мемоизация waiter/xyz, убран лишний df.copy в category.

**Почему:** устранить блокировку пула из 2 воркеров (главная причина тормозов) и
закрыть реальные риски доступности под gunicorn 2 workers.

**Файлы:** static/js/dashboard/modules/analytics.js, extensions.py,
routes/dashboard.py, core/iiko_api.py, core/olap_reports.py, routes/schedule.py,
routes/taps.py, app.py, core/json_store.py (new), core/meeting_notes.py,
core/open_check_subscribers.py, core/taps_manager.py, core/plans_manager.py,
core/chz_scheduler.py, core/open_check_scheduler.py, core/open_check_telegram.py,
telegram_webhook.py, Dockerfile, Caddyfile, core/waiter_analysis.py,
core/xyz_analysis.py, core/category_analysis.py, docs/lessons.md.
```
