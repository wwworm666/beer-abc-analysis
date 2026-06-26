* [Подключение веб-хуков](/articles/api-documentations/podklyuchenie-veb-khukov/a/h2_1962164077)

iikoCloud API позволяет работать с веб-хуками. Отличие веб-хука от API **заключается в инициации действия**: **в случае веб-хука сервер сам отправляет информацию при наступлении события, в то время как при работе с API запрос инициируется клиентом.**

Подписавшись на [веб-хуки](https://api-ru.iiko.services/docs#tag/Webhooks), есть возможность получать уведомления о всех следующих событиях:

* [об изменении статуса доставочного заказа](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.DeliveryOrderUpdateWebHookEventInfo/post),
* [об ошибке сохранения доставочного заказа](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.DeliveryOrderErrorWebHookEventInfo/post),
* [об изменении резерва](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.ReserveUpdateWebHookEventInfo/post),
* [об ошибке сохранения резерва](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.ReserveErrorWebHookEventInfo/post),
* [об изменении статуса заказа на стол](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.TableOrderUpdateWebHookEventInfo/post),
* [об ошибке сохранения заказа на стол](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.TableOrderErrorWebHookEventInfo/post),
* [об обновлении стоп-листа](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.StopListUpdateWebHookEventInfo/post),
* [об обновлении личной смены](https://api-ru.iiko.services/docs#tag/Webhooks/paths/iikoTransport.PublicApi.Contracts.WebHooks.PersonalShiftWebHookEventInfo/post).

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Для одного organizationId можно задать только один URL. |
| --- | --- |

##  Подключение веб-хуков

**Вариант 1. Выполните настройку веб-хуков в iikoWeb:** в разделе "Настройка Cloud API" выберите нужный API-ключ, перейдите во вкладку "Подключенные точки". Поставьте галочку напротив точки, по которой требуется получение веб-хуков, нажмите на "Настройка веб-хуков". ![](/resources/Storage/api-documentations/podklyuchenie-veb-khukov/podklyuchenie-veb-khukov-2025-08-12-1.png)

Далее в появившейся панели справа добавьте URI и токен авторизации (вкладка Основное), а во вкладке Фильтры - фильтры событий, по которым нужно получить веб-хук. Обязательно нажать на кнопку "Применить".

![](/resources/Storage/api-documentations/podklyuchenie-veb-khukov/podklyuchenie-veb-khukov-2025-08-12-2.png)![](/resources/Storage/api-documentations/podklyuchenie-veb-khukov/podklyuchenie-veb-khukov-2025-08-12-4.png)

**Вариант 2.** Задать настройки веб-хуков можно с помощью POST-запроса **[/api/1/webhooks/update_settings](https://api-ru.iiko.services/docs#tag/Webhooks/paths/~1api~11~1webhooks~1update_settings/post)**,****где

**organizationId** - это идентификатор организации,

**webhooksUri** - URL, куда нужно слать уведомления (задаете самостоятельно),

**authToken** - используется принимающей стороной для того, чтобы убедиться, что хук вам прислал именно iikoCloud API.

Сгенерируйте любую строку, задайте её как токен веб-хука в настройках в вебе/вызвав метод сохранения веб-хуков, напишите код сервера, проверяющий, что iikoCloud API прислал вам именно этот токен в заголовке Authorization.

Ознакомиться с сохраненными настройками можно POST-запросом **[/api/1/webhooks/settings](https://api-ru.iiko.services/docs#tag/Webhooks/paths/~1api~11~1webhooks~1settings/post).**

Веб-хук об изменении стоп-листа является лишь уведомлением, что стоп-лист был изменен, и нужно выполнить метод опроса стоп-листов **[/api/1/stop_lists](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists/post).** В теле ответа самого веб-хука позиции из стоп-листов **не приходят**.
После того, как параметры вызова веб-хуков заданы, транспорт при создании / редактировании / удалении доставки / резерва / заказа будет делать POST-запрос на указанный в настройках URL (токен авторизации будет передаваться в заголовке Authorization). В body передаётся информация об изменённой доставке / резерве / заказе.Если вызов метода веб-хука не удался, то в течение часа будут происходить повторные попытки его вызова каждые 10 минут.

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | С 04.08.2025 включен механизм блокировки не отвечающих веб-хуков. |
| --- | --- |

Правила корректной работы, а также критерии блокировки описаны в статье [ограничения веб-хуков](/articles/api-documentations/ogranicheniya-veb-hukov).
