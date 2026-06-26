* [Процесс создания API-ключа](/articles/api-documentations/podklyuchenie-poluchenie-api-klyucha/a/h2__84618915)
* [Как проверить, что ресторан на Cloud-тарифе](/articles/api-documentations/podklyuchenie-poluchenie-api-klyucha/a/h2__938265538)
 
Для работы c iikoCloud API нужно создать **API-ключ**, который в дальнейшем используется в запросах.

## Процесс создания API-ключа

Для создания API-ключа:

1. Перейдите в ЛК iikoWeb по ссылке *https://xxx-xxx-xxx.iikoweb.ru/navigator/ru-RU/index.html#/main* (дается при [получении демо-стенда](/articles/api-documentations/~kak-poluchit-demo-stend)) или из iikoOffice (Обмен данными - iikoTransport: Настройка iikoTransport)![](/resources/Storage/api-documentations/connect-to-iiko-cloud-2023-01-30.png)
2. Перейдите в раздел "**Настройки Cloud API**"![](/resources/Storage/api-documentations/connect-to-iiko-cloud/connect-to-iiko-cloud-2024-02-26.png) ****
3. Вы открывшемся окне нажмите на кнопку **"Добавить интеграцию"![](/resources/Storage/api-documentations/connect-to-iiko-cloud/connect-to-iiko-cloud-2024-02-26-1.png)**
4. Введите **Имя api логина и Email .** В **Имя api логина**можно указать, для чего он используется — для сайта или мобильного приложения Driver App. Автоматически сгенерируется сам **Api-ключ** и установится галочка **Активный**. Заполните **Email** - на него будут приходить важные уведомления системы.![](/resources/Storage/api-documentations/connect-to-iiko-cloud/connect-to-iiko-cloud-2024-02-26-2.png)
5. Подключите рестораны, для этого перейдите на вкладку **"ПОДКЛЮЧЕННЫЕ ТОЧКИ"**, которые работают с этим API-ключом: нажмите **Добавить точку,** установите галочки напротив нужных ресторанов**.**
6. ![](/resources/Storage/api-documentations/connect-to-iiko-cloud/connect-to-iiko-cloud-2024-02-26-4.png)
7. Нажмите кнопку **Сохранить.**
8. Настройка завершена.

После создания ключа необходимо перейти на вкладку "Организации"

![](/resources/Storage/api-documentations/podklyuchenie-poluchenie-api-klyucha/podklyuchenie-poluchenie-api-klyucha-2026-04-14.png)

Далее нужно выбрать точку, где необходимо включить работу транспорта.

![](/resources/Storage/api-documentations/podklyuchenie-poluchenie-api-klyucha/podklyuchenie-poluchenie-api-klyucha-2026-04-14-1.png)

Далее ставим галочки напротив терминалов:

![](/resources/Storage/api-documentations/connect-to-iiko-cloud/connect-to-iiko-cloud-2024-04-04-2.png)

Нажмите кнопку **Сохранить.**

**[Подробнее о проверке и работы через Cloud API](/articles/iikoweb/iikocloudapi/a/h3_129714767)**

## Как проверить, что ресторан на Cloud-тарифе

Выполните метод получения данных [организации](https://api-ru.iiko.services/docs#tag/Organizations/paths/~1api~11~1organizations/post), в ответе метода будет выведена переменная "isCloud" со значением true/false.
