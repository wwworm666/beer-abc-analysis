Сам факт успешного получения токена еще не означает возможность работы с API Delivery. API-логин должен быть привязан к одной или нескольким организациям, [зарегистрированным в iiko.biz](/articles/api-documentations/kak-podkluchit-api). Для этого зайдите в **Приложения → Список,** нажмите кнопку **Обновить подключения** и убедитесь, что приложение API Delivery подключено к вашей организации.

![](/resources/Storage/api-documentations/podkluchenie-organizacii-2019-05-15-1.png)

| ![Information](/resources/Storage/api-documentations/info.png) | Если приложение API Delivery остается не подключенным, значит вы не оплатили ежемесячную лицензию, обратитесь к своему менеджеру. |
| --- | --- |

В этом случае GET-запрос на получения списка организаций


```json
https://iiko.biz:9900/api/0/organization/list?access_token=jc-fv_OUMRLZObHJqHy_4J3koKGYKwhwl10jZVwaEmss4Zfjz1GHzyWbr0QlE6Hw2BSYzfE4XcHs9jqfOavzJg2&request_timeout=00%3A01%3A00
```

```json
https://iiko.biz:9900/api/0/organization/list?access_token=jc-fv_OUMRLZObHJqHy_4J3koKGYKwhwl10jZVwaEmss4Zfjz1GHzyWbr0QlE6Hw2BSYzfE4XcHs9jqfOavzJg2&request_timeout=00%3A01%3A00
```


вернет ответ:


```json
[]
```

```json
[]
```


Успешным ответом от API является информация по организации и получение ее уникального идентификатора (id). Этот id постоянный для каждой организации.

Этот id можно получить также из адресной строки браузера. Для этого в iiko.biz откройте карточку организации: **Организации → Точки продаж.**

Например: 
 https://iiko.biz/ru-RU/Settings/IikoBizSettings/f20594c6-2da7-11e8-80e0-d8d38565926f

где f20594c6-2da7-11e8-80e0-d8d38565926f — id организации.
