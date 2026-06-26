* [Сценарии использования](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h2__1656648227)
* [Алгоритм работы](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h2_1914292404)
* [Настройка внешнего меню](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h3_339060030)
* [Настройка учетных записей для работы с API](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h3__573143767)
* [Работа с API](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h2_846952416)
* [Примечания](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h2__2054049413)
* [Работа с КБЖУ](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h3_304087314)
* [Маркировка товара](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h3_1241019820)
* [НДС](/articles/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/a/h3__641981842)

В Cloud API ver.2 реализованы методы, которые позволяют гибко работать с внешним меню. Преимущество новых методов в том, что внешняя система при запросе меню получит актуальные цены и доступность блюд в ресторане на момент выполнения запроса.

Работа с внешним меню iikoWeb через API iikoCloud доступна только для пользователей **облачной версии iiko**.

В рамках данной статьи приведены шаги по настройке API-ключа для работы с внешним меню и непосредственное выполнение запросов.

Методы для работы с внешним меню:
* [/api/2/menu](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu/post) - метод, позволяющий получить список доступных для апи-логина внешних меню и ценовых категорий,
* [/api/2/menu/by_id](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu~1by_id/post) - метод, позволяющий получить внешнее меню (в теле запроса передается id доступного внешнего меню).

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Внешние меню не работают с приказами по времени. |
| --- | --- |

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Для работы с лояльностью iikoCard нужно по-прежнему использовать внешнее меню, созданное в iikoOffice. Достаточно просто продублировать позиции из внешнего меню iikoWeb, добавив те же самые блюда в iikoOffice, без дополнительных настроек структуры меню. |
| --- | --- |

## Сценарии использования

1. Ресторан хочет настроить разный состав блюд во внешнем меню для разных типов заказа. Например, часть блюд нельзя доставлять курьерскими сервисами, но данные блюда должны быть доступны во внешнем меню для самовывоза. Также могут быть разные цены на самовывоз и доставку.
2. Ресторан имеет отдельное приложение для заказов доставки и отдельное - для заказов в стол. Меню одно, но могут различаться цены или набор ресторанов, с которыми работают приложения.
3. Разные цены на блюда и различная доступность блюд в различных ресторанах сети. Например, в "Ресторане 1" Салат стоит 100 рублей, в "Ресторане 2" - 150 рублей, а в "Ресторане 3" блюдо снято с продажи.
4. Ресторан хочет на своем сайте размещать информацию об аллергенах, которые присутствуют в блюде.
5. Ресторан использует размеры блюд и и хочет отображать информацию о калорийности и весе с учетом размера блюда.
6. Ресторан использует размеры блюд и хочет, чтобы на сайте фотографии блюда отличались в зависимости от размера.
7. Меню ресторана (набор блюд, цены) отлично для разных внешних сервисов.
8. Ресторан хочет ограничить внешнему сервису работу с ресторанной сетью и предоставить доступ только к определенным ресторанам в сети.

## Алгоритм работы

### **Настройка внешнего меню**

Детальные шаги по настройке внешнего меню, описаны в пользовательской документации iikoWeb [здесь](/articles/iikoweb/external-menu).

###  Настройка учетных записей для работы с API

Для работы с внешними меню через API, необходимо привязать их к учетной записи iikoTransport.

Авторизуйтесь в личном кабинете iikoWeb, перейдите в раздел "Настройка Cloud API". Нажать на кнопку "Добавить интеграцию".

### ![](/resources/Storage/api-documentations/external-menu/external-menu-2024-04-04.png)

Задайте имя учетной записи и при необходимости укажите источник заказа:
![](/resources/Storage/api-documentations/external-menu/external-menu-2024-04-04-1.png)

**Источник заказа** предназначен одновременно как для маркировки заказов приходящих через API, так и для ограничения видимости заказов.

* Если "Источник заказа" не указан, то через API можно получить информацию **по всем заказам ресторана**.
* Если "Источник заказа" указан, то создаваемым через API заказам будет проставляться "Источник", а **доступ к заказам будет ограничен фильтром**.

Выберите внешнее меню из выпадающего списка (можно выбрать несколько вариантов):![](/resources/Storage/api-documentations/external-menu/external-menu-2024-04-04-2.png)

Выберите значение поля "**Источник цен**". Цены во внешнем меню могут быть:

- из внешнего меню - цены на блюда подставляются из внешнего меню, созданного в iikoWeb,
- из выбранной ценовой категории - цены берутся из конкретного ресторана для заданной ценовой категории, внешнее меню iikoWeb определяет только структуру меню.
Если в "Источнике цен" выбрана "Ценовая категория", то из выпадающего списка выберете одну или несколько ценовых категорий, с которыми будет работать внешняя система:![](/resources/Storage/api-documentations/external-menu/external-menu-2024-04-04-3.png)

**Вкладка "Подключенные точки"** - должны быть добавлены все точки, с которыми требуется работа, иначе будет выводиться сообщение (пример): "*Passed organization(s) 21ca011b-e26b-4d98-b612-322be8a3b11e doesn't belong to your api login included organization list.*"

Сохраните изменения.

## Работа с API

Для получения списка внешних меню, с которыми может работать внешняя система, необходимо запросить все имеющиеся у учетной записи внешние меню, в дальнейшем для получения информации по конкретному меню, будет использоваться поле id из ответа на запрос. Для этого используйте **/api/2/menu.**

Body пустое, на выходе структура:


```json
{
    "externalMenus": [
        {"id": 42, "name": "Menu 1"},
        {"id": 43, "name": "Menu 2"}
    ],
    "priceCategories": [ // будет null, если в UI был выбран источник "Внешнее меню"
        {"id": guid1, "name": "PC 1"},
        {"id": guid2, "name": "PC 2"}
    ],
}
```

Затем, используя полученный идентификатор внешнего меню, запросите позиции по нему через **/api/2/menu/by\_id** с body:


```json
{
    "externalMenuId": 73,
    "organizationIds": ["c0a959b8-7ba0-4763-a297-eda830672cca"],
    "priceCategoryId": guid или null
}
```


| ![Information](/resources/Storage/api-documentations/info.png) | null в данном методе можно отправить только если получение цен настроено из внешнего меню. В случае получения цен из ценовых категорий обязательно указание ценовой категории, даже если она всего одна (базовая). |
| --- | --- |

В ответ приходит структура внешнего меню:

[+] [Show More](javascript:void%280%29)
 [-] [Hide](javascript:void%280%29)
 
```json
{
  "id": 73,
  "name": "Menu rest",
  "description": "",
  "itemCategories": [
    {
      "id": "39bdc944-82d0-462a-982d-591326cef59c",
      "name": "Coffee",
      "description": "",
      "buttonImageUrl": "",
      "headerImageUrl": null,
      "items": [
        {
          "itemId": "2f9f071d-f8d0-4d91-9674-21044abaea42",
          "sku": "00064",
          "name": "Сappuccino",
          "description": "Tasty classic cappuccino

          ",
          "allergenGroups": [
          {
          "id": "d15c3f77-8dcd-3cb9-27b8-99363c7fba6a",
          "code": "7",
          "name": "Milk"

        }

      ],
      "tags": [
      ],
      "labels": [
      ],
      "taxCategory": null,
      "itemSizes": [
        {
          "sizeId": "865522ee-3104-4579-8c12-47de103193fa",
          "sku": "00064-S",
          "sizeCode": "S",
          "sizeName": "Small",
          "isDefault": true,
          "nutritionPerHundredGrams": {
            "fats": 2,
            "carbs": 5,
            "proteins": 4,
            "energy": 54

          },
          "prices": [
            {
              "price": 170,
              "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

            },
            {
              "price": 150,
              "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

            }

          ],
          "portionWeightGrams": 400,
          "itemModifierGroups": [
            {
              "name": "Milk",
              "description": "",
              "restrictions": {
                "minQuantity": 1,
                "maxQuantity": 1,
                "freeQuantity": 0,
                "byDefault": 0

              },
              "items": [
                {
                  "id": "44d44fa6-5676-443c-9b01-84c239b3c7f9",
                  "sku": "00059",
                  "name": "Almond milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "820b9018-6797-48df-892b-875306e792b5"

                },
                {
                  "id": "80e4c7a6-da3f-4548-8233-d4615a304436",
                  "sku": "00060",
                  "name": "Coconut milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "495ef4d6-8c52-40fb-8f50-96bd8e486af9"

                },
                {
                  "id": "4f80ab6b-4031-4a74-a4c6-07df66a45491",
                  "sku": "00058",
                  "name": "Standard milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 1

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 1,
                    "carbs": 6,
                    "proteins": 4,
                    "energy": 49

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "6fffa208-704f-43b9-b028-37da372f81ec"

                }

              ],
              "canBeDivided": true,
              "itemGroupId": "7bb36295-54f1-4940-8b05-0e4dd618733a",
              "sku": "0025",
              "childModifiersHaveMinMaxRestrictions": false

            },
            {
              "name": "Syrup",
              "description": "",
              "restrictions": {
                "minQuantity": 0,
                "maxQuantity": 9,
                "freeQuantity": 0,
                "byDefault": 0

              },
              "items": [
                {
                  "id": "dfb877ef-15f6-4dd9-aa30-24177530b04e",
                  "sku": "00094",
                  "name": "Chocolate syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "2818f2de-5717-4f88-b65a-d1d8309357f6"

                },
                {
                  "id": "809be120-a0f5-4f56-8182-451aa9201ef6",
                  "sku": "00095",
                  "name": "Strawberry syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "39b64a14-723d-46ed-8efc-b0b4a4f6a44b"

                },
                {
                  "id": "5353d3c0-0531-465c-8104-40b419a3a403",
                  "sku": "00096",
                  "name": "Banana syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "52fef420-04a9-49de-bfd0-0c7c5e5b299c"

                },
                {
                  "id": "de9f5029-e52c-411a-a700-e9619d43b349",
                  "sku": "00093",
                  "name": "Vanila syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "c170c89a-a868-49c6-9787-91b7197ab869"

                },
                {
                  "id": "e3726c2c-6c3b-4fba-b704-a703a5b56e56",
                  "sku": "00092",
                  "name": "Coconut syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "869c8404-7a97-48c6-a7f4-13d965f2dac5"

                }

              ],
              "canBeDivided": false,
              "itemGroupId": "b4d096b3-4c52-49f6-8f66-f75260c1f55c",
              "sku": "0020",
              "childModifiersHaveMinMaxRestrictions": false

            }

          ],
          "buttonImageUrl": null,
          "buttonImageCroppedUrl": [
          ]

        },
        {
          "sizeId": "1a636556-e844-4abf-a95a-ff8e57226ade",
          "sku": "00064-L",
          "sizeCode": "L",
          "sizeName": "Large",
          "isDefault": false,
          "nutritionPerHundredGrams": {
            "fats": 2,
            "carbs": 5,
            "proteins": 4,
            "energy": 54

          },
          "prices": [
            {
              "price": 240,
              "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

            },
            {
              "price": 240,
              "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

            }

          ],
          "portionWeightGrams": 400,
          "itemModifierGroups": [
            {
              "name": "Milk",
              "description": "",
              "restrictions": {
                "minQuantity": 1,
                "maxQuantity": 1,
                "freeQuantity": 0,
                "byDefault": 0

              },
              "items": [
                {
                  "id": "99ff4826-cb6a-4bcb-9f9b-b7a8fef5ed68",
                  "sku": "00059",
                  "name": "Almond milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "820b9018-6797-48df-892b-875306e792b5"

                },
                {
                  "id": "513c8e13-9f80-4b38-af0f-5b1b3fb53dc4",
                  "sku": "00060",
                  "name": "Coconut milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "495ef4d6-8c52-40fb-8f50-96bd8e486af9"

                },
                {
                  "id": "21aa708c-5808-479e-89b8-35fb46864983",
                  "sku": "00058",
                  "name": "Standard milk",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 0,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 0,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 1,
                    "carbs": 6,
                    "proteins": 4,
                    "energy": 49

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "6fffa208-704f-43b9-b028-37da372f81ec"

                }

              ],
              "canBeDivided": true,
              "itemGroupId": "7bb36295-54f1-4940-8b05-0e4dd618733a",
              "sku": "0025",
              "childModifiersHaveMinMaxRestrictions": false

            },
            {
              "name": "Syrup",
              "description": "",
              "restrictions": {
                "minQuantity": 0,
                "maxQuantity": 9,
                "freeQuantity": 0,
                "byDefault": 0

              },
              "items": [
                {
                  "id": "a03682d2-fb15-423f-88de-0260feba6e3d",
                  "sku": "00094",
                  "name": "Chocolate syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "2818f2de-5717-4f88-b65a-d1d8309357f6"

                },
                {
                  "id": "629d50fe-172b-4bbd-b0b9-af51cf105139",
                  "sku": "00095",
                  "name": "Strawberry syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "39b64a14-723d-46ed-8efc-b0b4a4f6a44b"

                },
                {
                  "id": "e1b3bfea-2888-40ba-a89c-b3d18a8a394e",
                  "sku": "00096",
                  "name": "Banana syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "52fef420-04a9-49de-bfd0-0c7c5e5b299c"

                },
                {
                  "id": "93ec800f-f3ec-4636-a318-3f3cca90e5bd",
                  "sku": "00093",
                  "name": "Vanila syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "c170c89a-a868-49c6-9787-91b7197ab869"

                },
                {
                  "id": "9e1bcf1a-8c8b-4a9d-9b94-c2772fc05e90",
                  "sku": "00092",
                  "name": "Coconut syrup",
                  "description": "",
                  "buttonImageUrl": null,
                  "prices": [
                    {
                      "price": 20,
                      "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

                    },
                    {
                      "price": 20,
                      "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

                    }

                  ],
                  "restrictions": {
                    "minQuantity": 0,
                    "maxQuantity": 0,
                    "freeQuantity": 0,
                    "byDefault": 0

                  },
                  "allergenGroups": [
                  ],
                  "nutritionPerHundredGrams": {
                    "fats": 0,
                    "carbs": 0,
                    "proteins": 0,
                    "energy": 0

                  },
                  "portionWeightGrams": 0,
                  "tags": [
                  ],
                  "labels": [
                  ],
                  "itemId": "869c8404-7a97-48c6-a7f4-13d965f2dac5"

                }

              ],
              "canBeDivided": false,
              "itemGroupId": "b4d096b3-4c52-49f6-8f66-f75260c1f55c",
              "sku": "0020",
              "childModifiersHaveMinMaxRestrictions": false

            }

          ],
          "buttonImageUrl": null,
          "buttonImageCroppedUrl": [
          ]

        }

      ],
      "orderItemType": "Compound",
      "modifierSchemaId": "71fbd193-d99b-4168-ac17-da664493400e",
      "modifierSchemaName": {
        "id": "71fbd193-d99b-4168-ac17-da664493400e",
        "deleted": false,
        "name": "Coffee",
        "productScale": "54840d34-2855-4080-9eb9-96dfcd1b040d",
        "modifiers": [
          {
            "modifier": "7bb36295-54f1-4940-8b05-0e4dd618733a",
            "defaultAmount": 0,
            "freeOfChargeAmount": 0,
            "minimumAmount": 1,
            "maximumAmount": 1,
            "hideIfDefaultAmount": false,
            "childModifiersHaveMinMaxRestrictions": false,
            "splittable": true,
            "required": true,
            "childModifiers": [
              {
                "modifier": "820b9018-6797-48df-892b-875306e792b5",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": true,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "495ef4d6-8c52-40fb-8f50-96bd8e486af9",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": true,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "6fffa208-704f-43b9-b028-37da372f81ec",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": true,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              }

            ],
            "cls": ""

          },
          {
            "modifier": "b4d096b3-4c52-49f6-8f66-f75260c1f55c",
            "defaultAmount": 0,
            "freeOfChargeAmount": 0,
            "minimumAmount": 0,
            "maximumAmount": 9,
            "hideIfDefaultAmount": false,
            "childModifiersHaveMinMaxRestrictions": false,
            "splittable": false,
            "required": false,
            "childModifiers": [
              {
                "modifier": "52fef420-04a9-49de-bfd0-0c7c5e5b299c",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": false,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "2818f2de-5717-4f88-b65a-d1d8309357f6",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": false,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "869c8404-7a97-48c6-a7f4-13d965f2dac5",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": false,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "39b64a14-723d-46ed-8efc-b0b4a4f6a44b",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": false,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              },
              {
                "modifier": "c170c89a-a868-49c6-9787-91b7197ab869",
                "defaultAmount": 0,
                "freeOfChargeAmount": 0,
                "minimumAmount": 0,
                "maximumAmount": 0,
                "hideIfDefaultAmount": false,
                "childModifiersHaveMinMaxRestrictions": false,
                "splittable": false,
                "required": false,
                "childModifiers": [
                ],
                "cls": ""

              }

            ],
            "cls": ""

          }

        ],
        "splittableProduct": true

      }

    }

  ]

},
{
  "id": "3f5388f0-54aa-466e-993c-dbb824a9f730",
  "name": "Pizza",
  "description": "",
  "buttonImageUrl": "",
  "headerImageUrl": null,
  "items": [
    {
      "itemId": "9d28f14c-2ef4-48eb-b0c3-3e2ab9ffa7e7",
      "sku": "00017",
      "name": "Pepperoni",
      "description": "mozarella cheese, tomato sauce, pepperoni ham",
      "allergenGroups": [
      ],
      "tags": [
      ],
      "labels": [
      ],
      "taxCategory": null,
      "itemSizes": [
        {
          "sizeId": null,
          "sku": "00017",
          "sizeCode": null,
          "sizeName": null,
          "isDefault": true,
          "nutritionPerHundredGrams": {
            "fats": 0,
            "carbs": 0,
            "proteins": 0,
            "energy": 0

          },
          "prices": [
            {
              "price": 480,
              "organizationId": "7eb96c48-c234-46d2-86bb-42034aa113c7"

            },
            {
              "price": 480,
              "organizationId": "9fab92f9-774c-4b10-a6b5-876346815092"

            }

          ],
          "portionWeightGrams": 0,
          "itemModifierGroups": [
          ],
          "buttonImageUrl": null,
          "buttonImageCroppedUrl": [
          ]

        }

      ],
      "orderItemType": "Product",
      "modifierSchemaId": null,
      "modifierSchemaName": null

    }

  ]

}

]
}
```


## Примечания

* При запросе внешнего меню по нескольким организациям в блоке prices возвращается информация по ценам запрошенных организаций. Если price = 0, то данное блюдо доступно для продажи по нулевой цене, если price = null, то данное блюдо запрещено к продаже в данной организации.
* У модификаторов есть значения минимального и максимального количества для группы и для каждого модификатора в частности. Если minQuality &gt; 0, то данная группа модификаторов является обязательной. maxQuality отвечает за максимально возможное количество модификаторов, добавляемых к блюду. Если параметр childModifiersHaveMinMaxRestrictions = false, то берутся ограничения по количеству модификаторов из значений группы модификаторов. Если childModifiersHaveMinMaxRestrictions = true, то берутся ограничения по количеству модификаторов из каждого модификатора (items).
```json
"itemModifierGroups": [
{
"name": "Add check",
"description": "",
"restrictions": {
"minQuantity": 0,
"maxQuantity": 4,
"freeQuantity": 0,
"byDefault": 0
},
"items": [
{
"sku": "00116",
"name": "Option 5",
"description": "",
"buttonImageUrl": null,
"prices": [ ... ],
"restrictions": {
"minQuantity": 0,
"maxQuantity": 1,
"freeQuantity": 0,
"byDefault": 0
},
"allergenGroups": [ ... ],
"nutritionPerHundredGrams": { ... },
"portionWeightGrams": 0,
"tags": [],
"labels": [],
"itemId": "c2b7fd30-4db5-4f64-adc5-b4fc8501e795"
},
{
"sku": "00098",
"name": "Option 2",
"description": "",
"buttonImageUrl": null,
"prices": [ ... ],
"restrictions": {
"minQuantity": 0,
"maxQuantity": 1,
"freeQuantity": 0,
"byDefault": 0
},
"allergenGroups": [],
"nutritionPerHundredGrams": { ... },
"portionWeightGrams": 0,
"tags": [],
"labels": [],
"itemId": "1b1590e3-5df0-4325-b746-8f24c97e0652"
}
],
"canBeDivided": false,
"itemGroupId": "58212c59-7ef3-4b40-a0a8-e904924c3f04",
"sku": "0037",
"childModifiersHaveMinMaxRestrictions": true
}
]
```

* Если itemGroupId = null, то модификаторы в данной группе считаются простыми, одиночными.

* Если параметр itemSize содержит один элемент, и внутри этого элемента sizeId и sizeName = null, то данное блюдо не имеет размеров. Если же элементов больше 1, то у данного блюда имеются размеры, за имя и идентификатор размера отвечают поля sizeName , sizeId.
* Параметр sizeCode отвечает за название размера для кухни.


```json
"itemSizes": [
{
"sizeId": null,
"sku": "00115",
"sizeCode": null,
"sizeName": null,
"isDefault": true,
"nutritionPerHundredGrams": { ... },
"prices": [ ... ],
"portionWeightGrams": 0,
"itemModifierGroups": [ ... ],
"buttonImageUrl": null,
"buttonImageCroppedUrl": []
}
]
```

### **Работа с КБЖУ**

Есть два варианта работы с КБЖУ:
1) основной метод: указать в iikoOffice или в iikoChain (если это сеть, то в чейн!). Затем эта информация уйдет в iikoWeb, где следует принудительно обновить внешнее меню (если источник цен внешнее меню), после чего КБЖУ будет отображаться.
2) напрямую ввести в iikoWeb, но это будет работать только в рамках выгрузки внешнего меню, синхронизация с РМС/Чейн не произойдет. **Важно!** Если в последствии в РМС/Чейн будет внесена информация по КБЖУ или будет выполнено ручное обновление меню в вебе, то данные, внесенные в iikoWeb обновятся данными из РМС/Чейн.

В ответе метода [/api/2/menu/by_id](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu~1by_id/post) присутствуют две переменные, отвечающие за вывод данных пищевой ценности: **nutritionPerHundredGrams** – пищевая ценность 100 грамм продукта и **nutritions** – пищевая ценность 100 грамм продукта в организации (сколько организаций, столько раз будет выводить информация).

Также следует обратить внимание на значение поля «Источник цен» в настройках апи-ключа, если установлено значение **«Ценовая категория»**, то для nutritions будут использоваться данные из РМС/Чейн, nutritionPerHundredGrams – данные из внешнего меню, если **«Внешнее меню»**, то nutritionPerHundredGrams и nutritions будут заполняться данными из внешнего меню.

### Маркировка товара

Для понимания, является данная номенклатурная единица маркированным товаром, в ответ внешнего меню добавлена переменная **isMarked** (true/false).

Переменная **isMarked** возвращает **true**, если в iikoOffice/iikoChain или в iikoWeb в справочнике кодов ТН ВЭД в карточке кода проставлена галочка "Запрашивать ввод марки при продаже". Примеры ниже:

![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-11-24.png)

![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-11-24-1.png)

### НДС

Для передачи ставки НДС внешним интеграторам и внешним ФР: рассмотрим пример где ставки НДС разные для организаций внутри сети и заданы через переопределение в настройках ТП.

В карточке блюда для всей сети задана одна ставка (например 5%)

![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-12-26-1.png)

В Настройках ТП по определенным точкам сети проставлено переопределение 5% --&gt; 7%

![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-12-26.png)

В таких случаях [запрос внешнего меню](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu~1by_id/post) нужно выполнять с версией 3 и выше (**"version": 3**). В ответе параметр **taxCategoryId** - ставка НДС из карточки блюда 
![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-12-26-5.png)

Если в ответе внешнего меню есть заполненный блок **overrideTaxCategories** - значит в этом РМС есть переопределенные налоговые категории
![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-12-26-3.png)

Если блок overrideTaxCategories не заполнен, то ставка НДС берется из блока **taxCategories**
![](/resources/Storage/api-documentations/metody-polucheniya-vneshnego-menyu-iikoweb/metody-polucheniya-vneshnego-menyu-iikoweb-2025-12-26-4.png)
