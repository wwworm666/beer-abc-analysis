# Деплой на прод

## Что это

Как код из репозитория попадает на https://beerkultura.ru. Документ для того, кто
выполняет деплой руками (человек или агент с доступом к машине и к серверу):
автодеплоя по пушу в проекте НЕТ, прод обновляется двумя командами на сервере.

Legacy-документы про Render (`DEPLOYMENT_GUIDE.md`, `RENDER_DISK_SETUP.md`) описывают
старый хостинг и оставлены как rollback-страховка — по ним деплоить не нужно.

## Файлы

- [`Dockerfile`](../../Dockerfile) — образ приложения, `COPY . .` + gunicorn (gthread, 2 воркера, 4 потока)
- [`docker-compose.yml`](../../docker-compose.yml) — сервисы `app` (beer-app) и `caddy` (beer-caddy), маунты, `env_file: .env`
- [`Caddyfile`](../../Caddyfile) — TLS и reverse proxy на `localhost:10000`
- [`.env.example`](../../.env.example) — шаблон переменных; боевой `.env` живёт только на сервере
- [`core/storage_paths.py`](../../core/storage_paths.py) — резолв путей к постоянным данным (`PERSISTENT_DATA_DIR=/kultura`)

## Как работает

### Куда деплоим

| Что | Значение |
|---|---|
| Прод | https://beerkultura.ru |
| Сервер | Selectel VPS, `139.100.200.92` |
| Вход | `ssh root@139.100.200.92` |
| Репозиторий на сервере | `/opt/beer` (владелец `deploy:deploy`) |
| Ветка деплоя | `main` |
| Контейнеры | `beer-app` (gunicorn:10000), `beer-caddy` (80/443) |
| Постоянные данные | host `/srv/kultura` → `/kultura` |
| Данные приложения | host `/srv/beer/data` → `/app/data` |
| Секреты | `/opt/beer/.env`, `/srv/beer/secrets` → `/app/secrets:ro` |

Схема: ветка разработчика → `main` на GitHub → `git pull` на сервере → пересборка
образа → рестарт контейнера. Ни GitHub Actions, ни вебхуков в проекте нет.

### Шаг 1. Код попадает в main

Разработка идёт в ветке, прод тянет только `main`. История линейная, мержи делаются
fast-forward:

```bash
git fetch origin
git checkout main && git pull --ff-only
git merge --ff-only origin/<ветка>
git push origin main
```

Перед этим — тесты на машине разработчика:

```bash
python -m pytest -q tests          # ожидается «passed», ошибки в tests/debug/ — штатные
```

### Шаг 2. Сервер забирает код и пересобирает образ

```bash
ssh root@139.100.200.92
cd /opt/beer && git pull --ff-only
docker compose up -d --build app
docker compose logs --tail=50 app
```

`--build` обязателен: код запекается в образ (`COPY . .` в Dockerfile). Без пересборки
контейнер поднимется на старом коде, а `git pull` останется бесполезным.

### Когда пересборка НЕ нужна

| Что изменилось | Команда |
|---|---|
| Код (py, html, js, css) | `docker compose up -d --build app` |
| Только `.env` на сервере | `docker compose up -d app` — env читается заново при старте |
| `Caddyfile` | `docker compose up -d caddy` — файл примонтирован, образ не наш |
| Только `docs/` | ничего, деплой не нужен |

### Проверка после деплоя

```bash
docker compose ps                                  # beer-app и beer-caddy — Up
docker compose logs --tail=50 app                  # без traceback, есть строки шедулеров
curl -sS -o /dev/null -w '%{http_code}\n' https://beerkultura.ru/login    # 200
```

Плюс открыть в браузере страницу, которую меняли, и проверить сам сценарий: логи
покажут, что приложение живо, но не что фича работает.

### Что НЕ доезжает через git pull

`docker-compose.yml` монтирует host-каталоги ПОВЕРХ каталогов образа, поэтому
изменения репозитория в `data/` на прод не попадают:

- `/srv/beer/data` → `/app/data` — затеняет repo-копию `data/`;
- `/srv/kultura` → `/kultura` — постоянное хранилище, единственный источник правды
  для изменяемых JSON и баз (`kpi_targets.json`, `taps_data.json`,
  `plansdashboard.json`, `shifts.db`, `secret_key` и т.д.).

Логика сидирования (`core/storage_paths.py`): если файла на `/kultura` нет, а в
`/app/data` есть — он копируется на диск ОДИН раз. Дальше диск никогда не
перезаписывается из репозитория. Поэтому новый или изменённый файл данных кладётся
руками:

```bash
cd /opt/beer && git pull --ff-only
cp data/<файл>.json /srv/beer/data/<файл>.json     # источник сидирования
# ИЛИ сразу на постоянный диск, минуя сидирование:
# cp data/<файл>.json /srv/kultura/<файл>.json
docker compose up -d --build app
```

Правка боевых данных, которые редактируются через интерфейс (планы, цели KPI, краны),
делается на сайте, а не файлами: диск — источник правды, и ручная правка файла может
быть перетёрта приложением.

### Секреты

`.env` и ключ Google в git не хранятся (`.dockerignore` исключает `.env`). Живут
только на сервере: `/opt/beer/.env` и `/srv/beer/secrets/google-sa.json`
(маунт `:ro`). При добавлении переменной — дописать в `.env` на сервере И в
`.env.example` в репозитории (без значения).

### Шедулеры и рестарт

В контейнере крутятся ночные задачи (`app.py`): ЧЗ 03:00, open-check 14:59, выгрузка
ЗП в Google-таблицу 04:00, снимок `/me`, месячный отчёт, температура, синк гостей.
Рестарт при деплое их просто поднимает заново; у задач есть atomic-локи и
`_catch_up_if_missed`, поэтому деплой поверх окна запуска не ломает день. Но если
деплой приходится ровно на минуту запуска — стоит проверить логи, отработала ли задача.

Отдельно: месяц у ночных задач ЗП и `/me` закрывается 7-го числа
(`SALARY_SYNC_PREV_UNTIL_DAY`, `ME_SNAPSHOT_PREV_UNTIL_DAY`). Если правка расчёта
касается прошлого месяца и деплой позже 7-го — данные сами не пересчитаются:
Google-вкладку обновляют кнопкой «Google» на `/salary`, снимок `/me` за тот месяц
остаётся замороженным.

### Откат

Образ всегда пересобирается в один тег `beer-abc-analysis:latest`, отдельных версий
нет. Откат — по git:

```bash
cd /opt/beer
git log --oneline -5
git checkout <хороший-коммит>        # или git reset --hard <коммит>, если main откатили
docker compose up -d --build app
```

Данные откат не затрагивает: они на `/kultura`, а не в образе.

### Грабли

- **`git pull` падает с `Permission denied`.** Часть файлов принадлежит `root`
  (наследие первой установки). Лечится `sudo chown -R deploy:deploy /opt/beer`; после
  прерванного pull дерево выровнять `git reset --hard origin/main`, предварительно
  убедившись, что в изменённых файлах нет чьей-то ручной работы.
- **Задеплоили, а на сайте старое.** Забыт `--build`, либо браузер держит старую
  статику: ассеты версионируются `?v=<hash>` и Caddy отдаёт `max-age` 30 дней —
  проверять hard-reload.
- **Изменили JSON в `data/` и ждёте эффекта на проде.** Не сработает, см. «Что не
  доезжает через git pull».
- **`menu_tool/`** на прод не деплоится (Chromium тяжёлый), это локальное приложение
  на порту 5050. **`chz_test/`** живёт на бар-ПК, обновляется отдельно через Tailscale
  (см. [remote-sync.md](../remote-sync.md)).

## Changelog

### 2026-09-06 — Документ создан

Актуальный деплой был описан кусками: `README.md` (кратко), `menu-editor.md` (маунты
и сидирование), `google-sheets-export.md` (секреты), `CHANGELOG.md` (инцидент с
правами на `/opt/beer`), а `DEPLOYMENT_GUIDE.md` описывал мёртвый Render-флоу. Собрано
в один документ: путь кода до прода, когда нужна пересборка, что не доезжает через
`git pull`, проверка, откат, грабли.
