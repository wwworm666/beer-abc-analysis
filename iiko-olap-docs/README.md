# iiko OLAP — локальный снапшот документации

Полный набор документации по **OLAP-отчётам iiko** (раздел `api-documentations` портала
`ru.iiko.help`), собранный локально 2026-05-29.

- **Источник истины — портал**, не эта папка. Здесь замороженный снапшот для офлайн-работы.
- Снапшот хранится в репозитории. Обновляется командой ниже.
- Полнота проверена: прогон по всем 158 статьям раздела + сверка внутренних ссылок +
  completeness-критик. Лишних кандидатов (`spravochniki`, `kody-bazovykh-tipov`, `scheta`,
  `sobytiya` и т.п.) отсеяно — они упоминают OLAP лишь вскользь. Пропущенных страниц нет.

## Файлы (9 страниц, ~767 КБ)

| Файл | О чём | Размер |
|------|-------|--------|
| [formirovanie-olap-otcheta-v-api.md](formirovanie-olap-otcheta-v-api.md) | **Главный гайд.** Как спроектировать отчёт в iikoOffice и перенести его в API iikoServer (reportType, поля строк/колонок/агрегаций, фильтры) | 109 КБ |
| [olap-otchety-v1.md](olap-otchety-v1.md) | OLAP-отчёт, **версия 1**: endpoint и параметры запроса | 40 КБ |
| [olap-otchety-v2.md](olap-otchety-v2.md) | OLAP-отчёт, **версия 2**: поля OLAP-отчёта и параметры запроса | 25 КБ |
| [otchety-v1.md](otchety-v1.md) | v1 — примеры: отчёт по складским операциям | 11 КБ |
| [otchety-dostavka-v1.md](otchety-dostavka-v1.md) | v1 — примеры: отчёты по доставке (сводный) | 15 КБ |
| [otchety-vv2.md](otchety-vv2.md) | v2 — примеры: балансы по счетам, контрагентам, подразделениям | 9 КБ |
| [primery-vyzova-olap-otchet-v2.md](primery-vyzova-olap-otchet-v2.md) | v2 — большой сборник примеров вызова OLAP-отчётов по продажам | 563 КБ |
| [prednastroennye-olap-otchety-vv2.md](prednastroennye-olap-otchety-vv2.md) | Список преднастроенных отчётов (конфигураций), отфильтрованных по типу OLAP | 6 КБ |
| [olap-otchety-po-dostavke.md](olap-otchety-po-dostavke.md) | OLAP-отчёты по доставке (создание предустановленного отчёта) | 5 КБ |

> Примечание: `olap-otchety-po-dostavke` отсутствовал в прежней локальной копии `docs/iiko-api/` —
> пробел закрыт этим снапшотом.

## Как обновить снапшот

Движок портала (ClickHelp) отдаёт чистый markdown по эндпоинту
`/helper/articles/{раздел}/{slug}/?action=getMarkdown`. Перекачать все 9 страниц:

```bash
DEST="iiko-olap-docs"
for s in formirovanie-olap-otcheta-v-api olap-otchety-po-dostavke olap-otchety-v1 \
         olap-otchety-v2 otchety-dostavka-v1 otchety-v1 otchety-vv2 \
         prednastroennye-olap-otchety-vv2 primery-vyzova-olap-otchet-v2; do
  curl -sL -A "Mozilla/5.0" \
    "https://ru.iiko.help/helper/articles/api-documentations/$s/?action=getMarkdown" \
    | sed '1s/^\xEF\xBB\xBF//' > "$DEST/$s.md"
done
```

Перепроверить полноту (вдруг на портале появились новые OLAP-страницы): взять список статей из
`https://ru.iiko.help/sitemaps/sitemap_publication_api-documentations.xml` и отфильтровать по
`olap|otchet`. Полный рецепт забора с портала — в `.claude/CLAUDE.md`.

## Веб-ссылки на оригиналы

Каждый файл соответствует странице `https://ru.iiko.help/articles/#!api-documentations/{slug}`,
например <https://ru.iiko.help/articles/#!api-documentations/formirovanie-olap-otcheta-v-api>.
