Статья объясняет особенности работы с методами `calculate `(расчет скидок и других условий лояльности для заказа) и `combo (получение всех доступных комбо)`. Эти методы позволяют эффективно рассчитывать стоимость заказов и управлять комбинированными предложениями, обеспечивая автоматизацию расчетов и упрощение процессов формирования заказов с учетом скидок и специальных предложений.

Методы  [calculate](https://api-ru.iiko.services/docs#tag/Discounts-and-promotions/paths/~1api~11~1loyalty~1iiko~1calculate/post) и [combo](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1combo/post) проксируются в iikoCard и работают по id блюд, которые имеются во внутренней номенклатуре iikoCard.

**Начиная с версии 8.3.х.х РМС**

Дублировать номенклатуру не требуется во внешнем меню бека. Поиск блюд идет по внутренней номенклатуре в карде. Выгружаются все блюда, находящиеся в продаже (выставлены места продаж или включены в приказы).

Выгрузка внутренней номенклатуры идет через */resto/service/import/forceNomenclatureImport.jsp* или вручную в беке (желательно выполнить полную перевыгрузку forceNomenclatureImport.jsp с соответствующей галкой если есть проблема) если это не происходит на автомате. В jms Логе будут записи вида:

| JSON |
| --- |
| 
```
2023-05-11 11:33:01,032  INFO <9cc4913f-936b-5cee-58bd-bbc3ab543f17><iikoUser><94.124.192.242>[h-8080-exec-0004](rin.NomenclatureExporter) JMS: Export nomenclature done
```
 |

Необходимо проверить наличие блюда в продаже в РМС в приказа

Если нет приказов - то должны быть выставлены галки включено в меню в РМС в карточке номенклатуры

После выгрузки номенклатуры блюдо обновится в кеше внутренней номенклатуры карда в течение 2х часов

**До версии 8.3.х.х РМС:**

Обязательное условие успешного расчета лояльности в транспорте - дублирование во внешнем меню iikoOffice каждой организации списка блюд.

Если блюдо не найдено во внешнем меню бека "errorDescription": "Product with Id 'a87d53e0-ab1e-485a-ac04-055e554c167e' not found"

iikoCard при расчете обращается за номенклатурой в transport ([метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1nomenclature/post)) по UOC id (убедиться, что UOC id актуальный) или по crmId. Далее получает список id блюд и переводит их в артикулы.

Для проверки что блюдо есть в номенклатуре транспорта - выполнить запрос https://api-ru.iiko.services/api/1/loyalty/iiko/calculate[метода получения номенклатуры](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1nomenclature/post) в теле id организации, по которой идет расчет лояльности или запрос комбо.
![](/resources/Storage/api-documentations/osobennosti-raboty-metodov-calculate-i-combo-v-cloud-api/osobennosti-raboty-metodov-calculate-i-combo-v-cloud-api-2024-04-25-2.png)

Из рекомендаций для клиентов - поднять ревизию внешнему меню любым способом (например, отредактировать и сохранить).

Далее дождаться обновление внутреннего кеша iikoCard (в течение часа) и проверить основной запрос (комбо или расчет лояльности).

![](/resources/Storage/api-documentations/osobennosti-raboty-metodov-calculate-i-combo-v-cloud-api/osobennosti-raboty-metodov-calculate-i-combo-v-cloud-api-2024-04-25-1.png)
