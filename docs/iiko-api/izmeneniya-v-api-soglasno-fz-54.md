* [Изменение процессов согласно ФЗ-54](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h2_2096486514)
* [Типовые сценарии интеграции](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h2_59334343)
* [Плагин: система лояльности - чекин гостя и применение механик лояльности](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3_1622385015)
* [Плагин: система лояльности - чекин гостя, применение механик лояльности и чек коррекции](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3_1477189748)
* [Плагин: система лояльности - заказ за столом](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3__1139704334)
* [Плагин: система лояльности - заказ за столом (чек коррекции)](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3__1564850730)
* [Плагин: оплата в режиме фастфуд (СБП)](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3_1721237770)
* [Плагин: оплата заказа в ресторане (СБП) - кассовые ссылки за столом](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3__1057661630)
* [Плагин: оплата заказа в ресторане (СБП) - динамический QR-код](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3_1993450838)
* [Плагин: оплата заказа за столиком (упрощенная схема с приложением)](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3__33266342)
* [Плагин: оплата в гостиничных системах (упрощенная схема)](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h3__1331047548)
* [Онлайн-таблица совместимости интеграций с ФЗ-54](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h2_1709422833)
* [Полезные ссылки](/articles/api-documentations/izmeneniya-v-api-soglasno-fz-54/a/h2_1685500781)

#  Изменения в API согласно ФЗ-54 с 01.03.2025

##  Изменение процессов согласно ФЗ-54

![](/resources/Storage/api-documentations/novosti-po-api/Draft%20-%202025-02-25T115618.462%20%281%29.png)

### 

### 

![](/resources/Storage/api-documentations/novosti-po-api/Draft%20-%202025-02-25T120231.553%20%281%29.png)

![](/resources/Storage/api-documentations/novosti-po-api/diagram%20%2868%29.png)

 ![](/resources/Storage/api-documentations/novosti-po-api/Draft%20-%202025-02-25T120631.390%20%281%29.png) 

##  Типовые сценарии интеграции

###  Плагин: система лояльности - чекин гостя и применение механик лояльности

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXdyNts7GNwmPHzuNQqBxqc0-VnRfl-gALKpK-8oFPYWOntBCr8uTCYYqCmwnukOB9Y9sxUVldlPmnJy105SuYBBhd5hM0mLvWpYlZAUX_lGydudKEIBGb1FyMEvdRsyOouaOMaFIw?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Кассир создает или открывает существующий заказ, спрашивает у гостя карту лояльности/ID.
* Плагин после получения ID гостя запрашивает и рассчитывает доступные преимущества (баллы, скидки).
* Кассир решает, использовать ли эти бонусы.

    * Если да – плагин запускает процесс их списания и добавляет соответствующий «внешний тип оплаты» (например, «Списание бонусов»).
* После перехода на экран «Касса» кассир выбирает окончательные типы оплат, в том числе, при наличии, «Списание бонусов».
* iikoFront выполняет фискализацию, печатает фискальный чек и закрывает заказ при подтверждении оплаты.
* Плагин информирует внешнюю систему лояльности о факте закрытия заказа, чтобы начислить (или окончательно списать) бонусы.

###  

### Плагин: система лояльности - чекин гостя, применение механик лояльности и чек коррекции

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXdZ_xEHMV87wmZThTdMLAYWjxe_z1xEH67c2LU0pv7hyxq3ghA6UIf7QiHfiLLcArDozT3GVhRMigkq3PReINRppV9jL3eV2EVRAbU51ynq1IpJYal1k41lKu_A-qz4H9B06UUIqQ?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Если после фискализации типов оплат изменяется состав заказа или тип оплаты, возникает необходимость сформировать чек коррекции.
* Плагин отправляет во внешнюю систему лояльности команду на отмену уже списанных бонусных баллов.
* Кассир может внести любые изменения (позиции заказа, виды оплат).
* При повторном добавлении бонусного типа оплаты плагин следит, чтобы не допустить списания сверх доступных баллов.
* Кассир снова жмёт «Оплатить», с клиента берутся средства, система формирует чек коррекции и закрывает заказ.
* Плагин повторно отправляет уведомление о закрытии (с учётом изменений) во внешнюю систему лояльности.

### Плагин: система лояльности - заказ за столом

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXcYSRPW_V3BpVNgb98xcPWhG219yScA_Ha-N2qQnPG313r8dzW8WCQuMIMZrGGnOR0hRGRuANxUHgzHoLcSE1zBd__f8aoQVd8jWKaLCHZzmCHQj5QnJMMYWeRN7Ld4sHrUlYW2hg?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Официант открывает заказ за столом и вводит/сканирует данные лояльности гостя.
* Плагин запрашивает в системе лояльности доступные бонусы/скидки и при необходимости списывает их.
* Кассир в окне кассы выбирает способы оплаты.

    * Если задействованы бонусы, Плагин добавляет соответствующий тип оплаты.
* Кассир добавляет сторонние типы оплат.
* При нажатии кнопки «Фискальный чек» происходит фискализация (до фактической оплаты).
* После фискализации при нажатии «Оплатить» заказ закрывается через iikoFront.
* Плагин отсылает финальное уведомление о закрытии заказа в систему лояльности.

### Плагин: система лояльности - заказ за столом (чек коррекции)

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXfRnlTV1vgC2Z7YZp440wCpXgBBlD4yqCW1D0mNQObOUb2c-RD45JwnQD0O-I8tH18xPksumnwxmDy6I07_6t8yLQdJV4lybn27wmzSNUsOjSBVKcE6lLEHoQcU6sgtBFKuowSNLA?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Официант открывает заказ, считывает карту лояльности, плагин запрашивает и рассчитывает бонусы/скидки. При положительном условии бонусы списываются.
* Кассир запрашивает печать пречека. Если заказ не изменялся, дальнейшая фискализация происходит в обычном режиме.
* При изменении состава заказа или типа оплаты пречек отменяется.
* Плагин отправляет команду об отмене списания, кассир вносит изменения, запрашивается новый пречек.
* Плагин повторно применяет списание бонусов и проводится коррекция (печатается чек коррекции).

### Плагин: оплата в режиме фастфуд (СБП)

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXeqbnV_hf3Xk85BMLuo7WFpQQB9cJIn8pvsMT86shybgRqmQ_8eJ5_EkO_YwZOEjhlW2qF3uDspzz65ZO9T8JVOMQZbcLnbZLlDU2BPt5m0wIROqN3bxXBjTYt8M-5k3-suGfTz8g?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Кассир открывает заказ в режиме фастфуд и добавляет позиции.
* Плагин добавляет внешний тип оплаты “СБП”.
* Кассир нажимает на кнопку «Фискальный чек», после чего iikoFront выполняет фискализацию типов оплат до момента фактической оплаты заказа.
* Далее Кассир инициирует оплату, нажав на кнопку “Оплатить”.
* Плагин запрашивает у банка QR-код который затем будет отображаться гостю на дисплее покупателя для сканирования.
* Если банк подтверждает оплату, плагин фиксирует успешную оплату, и iikoFront автоматически закрывает заказ.
* Если оплата не подтверждается, выполняется изменение типа оплаты: Кассир изменяет тип оплаты и нажимает на кнопку “Оплатить”. При успешном проведении оплаты на этом этапе, система формирует чек коррекции и закрывает заказа. Если оплата по прежнему не проходит, процесс повторно возвращается к выбору нового типа оплаты.

### Плагин: оплата заказа в ресторане (СБП) - кассовые ссылки за столом

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXc5hkA8J8vqYH9GtAB7mLIWazHhYemWmHPAA5EZZ-C9GYFn-5t39EhxTCpTF8SmcCUeTyv1auTvnulDU3d7jTnrYSk0teIkPyi1umlDA8wrTpuSlw_8hk5LKM6UqVikI2fJ8bAXPw?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Официант создает заказ за столом и набирает необходимые позиции.

    * Плагин идентифицирует режим работы через кассовые ссылки.
* Официант запрашивает печать пречека и нажимает на кнопку “Пречек”.
* Кассир переходит к окну Кассы, указывает тип оплаты СБП и нажимает на кнопку «Фискальный чек». Терминал iikoFront выполняет печать фискального чека.
* Плагин активирует кассовую ссылку в Банковский сервисах, и кассир информирует гостя о том что заказ готов к оплате по СБП.
* Гость пытается оплатить заказ через кассовую ссылку. Если банк подтверждает оплату, плагин фиксирует успешный платеж, затем iikoFront закрывает заказ.

    * В случае отказа или ошибки, производится изменение типов оплат кассиром, затем Кассир нажимает повторно кнопку “Оплатить” и если оплата проходит, формируется чек коррекции, после чего заказ на терминале iikoFront закрывается.
    * Если оплата снова не удается, процесс(взаимодействие кассира и кассовой системы iikoFront) возвращается к выбору другого типа оплаты.

### Плагин: оплата заказа в ресторане (СБП) - динамический QR-код

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXcCo2urFlkdw-Ne0SgAiAzX1RrcxIQm3NQ1gUMZ8lm2tPwSvTd_lH0QbFmKzNlL6CFZ2B6J_pD_fTrhZbyvSKs1zaZ8maMuceCw6aHuVsI0QYNotwBNgXZFASFEObos9xJYq_Vohw?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Официант создает заказ за столом и набирает необходимые позиции.

    * Плагин идентифицирует режим работы динамический QR-код..
* Официант запрашивает печать пречека и нажимает на кнопку “Пречек”.
* Кассир переходит к окну Кассы, указывает тип оплаты СБП и нажимает на кнопку «Фискальный чек». Терминал iikoFront выполняет печать фискального чека.
* Плагин запрашивает и собирает данные по динамическому QR-коду, который будет использован для печати непосредственно на фискальном чеке. Гость использует динамический QR-код для оплаты заказа.
* Если банк подтверждает оплату, плагин фиксирует успешную транзакцию, затем iikoFront автоматически закрывает заказ.

    * В случае отказа или ошибки, производится изменение типов оплат кассиром, затем Кассир нажимает повторно кнопку “Оплатить” и если оплата проходит, формируется чек коррекции, после чего заказ на терминале iikoFront закрывается.
    * Если оплата снова не удается, процесс(взаимодействие кассира и кассовой системы iikoFront) возвращается к выбору другого типа оплаты.

### Плагин: оплата заказа за столиком (упрощенная схема с приложением) 

 ![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXcmUqb-LebngtrVnlqarLQR85IjnzQlD2wBLsWHj2KxyVJnwLEhdVzeQLGRAJ18lOs5wcb-Ey6yxkd4jL08aqLNZ7CTLbdxcHcJ_sI5xGcx3M0oK1lj9EqsWrBcXBHjB0x0W-4M?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

    Пояснение к схеме:

* Официант создает заказ за столик и добавляет необходимые позиции.
* Гость, используя приложение, идентифицирует заказ при помощи сканирования статического QR-кода и/или используя QR-код с пречека.
* Гость, используя приложение, выбирает нужный способ оплаты и подтверждает намерение оплаты заказа кнопкой Оплаты, после чего Приложение обращается к Плагину для обработки запроса.
* Плагин добавляет внешний тип оплаты с учетом скидок и бонусов и запрашивает у iikoFront фискализацию типов оплат.
* Терминал iikoFront печатает фискальный чек, затем плагин уведомляет Приложение о завершении фискализации.
* Если Гость подтверждает оплату в приложении, то приложение информирует плагин. В результате Плагин отправляет команду терминалу iikoFront на закрытие заказа, и заказ автоматически закрывается.

### Плагин: оплата в гостиничных системах (упрощенная схема) 

![](https://lh7-rt.googleusercontent.com/docsz/AD_4nXdz1ZznjrD-eP7P5MuAoHqeFXNktV6NSB-NhL5RK1uYyd3PRzYGxyCiE9hC12rUsT38M8d5_9wPToSBDaFgdD1xRnsifY87oTaAnf2VLXeuf1hf4QsO3txGdAxpo8r8vUXiw38U?key=rOWwIPLsxd04jxQPQ1cjVrdJ)

Пояснение к схеме:

* Если гость отказывается или выбирает другой тип оплаты, плагин инициирует отмену фискализации.
* Официант/Кассир создаёт заказ для гостя, выбирая соответствующий номер комнаты.
* Плагин инициирует фискализацию. iikoFront печатает фискальный чек (по новым требованиям – до фактического получения оплаты).
* Плагин отправляет запрос на покрытие заказа по «кредиту» номера. Гостиничная система либо подтверждает операцию, либо отказывает.
* При успешном подтверждении гостиничной системой заказ в iikoFront автоматически закрывается. В случае отказа гостю (или кассиру) предлагается выбрать другой тип оплаты и по необходимости повторить фискализацию.

##  Онлайн-таблица совместимости интеграций с ФЗ-54

| Название плагина | Тип | Команда разработчик | Версия API | Совместимость | Версия плагина |
| --- | --- | --- | --- | --- | --- |
| Resto.Front.Api.AisinoPaymentPlugin | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.PaymentSystem.DualConnector | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.ArcusPlugin | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.SberbankPlugin | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.SberbankPlugin Spasibo | Лояльность | Integration\_Projects |  | Доработано | V9Preview3.1.2.29 |
| Resto.Front.Api.CreditEuropaPlugin | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.SkyPOSPayment | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| YarusTerminalPlugin | POS терминал | Integration\_Projects |  | Доработка не требуется |  |
| Resto.Front.Api.TravellinePlugin | Гостиничная система | Integration\_Projects |  | Доработано | V9Preview4.1.0.0 |
| Resto.Front.Api.1CHotePlugin | Гостиничная система | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.EcviPlugin | Гостиничная система | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.HoresPlugin | Гостиничная система | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.LoyaltyPlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.ManzanaPlugin | Лояльность | Integration\_Projects |  | Доработано | V7.1.0.17 |
| Resto.Front.Api.PremiumBonusPlugin | Лояльность | Integration\_Projects | v8 | Доработано | V8.2.0.73 |
| Resto.Front.Api.BonusMoneyPlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.MindBoxPlugin | Лояльность | Integration\_Projects |  | Доработано | V8.1.0.63 |
| Resto.Front.Api.BoomerangmePlugin | Лояльность | Integration\_Projects |  | Доработано | V7.1.0.0 |
| Resto.Front.Api.HardRockCafePlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.CloudLoyaltyPlugin | Лояльность | Integration\_Projects |  | Доработано | V6.1.0.84 |
| Resto.Front.Api.LoyaPlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.LoyaltyPlantPlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.APi.GKANPlugin | Лояльность | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.PrintNumberOnOrderClose | Мелкая фича | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.OrderClosingPlugin | Мелкая фича | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.SberbankQrPlugin | сейчас Resto.Front.Api.SberbankQrV3Plugin | Integration\_Projects |  | не используется |  |
| Resto.Front.Api.CloseSessionPlugin | Плагин закрытия кассовой смены | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.AlfabankSBPPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.28 |
| Resto.Front.Api.ISDPlugin | Платежный | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.SberbankQrV3Plugin | Платежный СБП | Integration\_Projects |  | Тестирование |  |
| Resto.Front.Api.TinkoffSbpPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.80-beta |
| Resto.Front.Api.YandexEdaPlugin | Платежный | Integration\_Projects |  | Доработано | V9Preview4.1.0.27 |
| Resto.Front.Api.QrServicePlugin | Платежный СБП | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.GazprombankPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.16 |
| Resto.Front.Api.SBPPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.69 |
| Resto.Front.Api.SendyPlugin | Платежный | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.RaiffeisenSbpPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.16 |
| Resto.Front.Api.WebMoneyPlugin | Платежный СБП | Integration\_Projects |  | Доработано | V8.1.0.8 |
| Resto.Front.Api.SwipPlugin | Платежный | Integration\_Projects |  | Доработано | V9Preview4.1.0.66 |
| Resto.Front.Api.FoodCardPlugin\_new | Платежный - корпоративное питание | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.YandexPlugin\_new | Платежный - корпоративное питание | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.ObedPlugin | Платежный - корпоративное питание | Integration\_Projects |  | В процессе доработки |  |
| Resto.Front.Api.VtbTipsPlugin | Платежный+Чаевые | Integration\_Projects |  | Доработано | V9Preview4.1.0.136 |
| Resto.Front.Api.MitsuCRPlugin | Фискальный регистратор | Integration\_Projects | не ниже 8 | Доработано | V8.1.3.2 |
| Resto.Front.Api.Spark130.FFD12.Plugin | Фискальный регистратор | Integration\_Projects | не ниже 8 | Доработано | V8.1.0.71 <br>  V9Preview1.1.0.77 <br>  V9Preview3.1.0.77 <br>  V9Preview4.1.0.77 |

##  

##  Полезные ссылки

* [Рекомендации налоговой](https://kkt-online.nalog.ru/html/sites/www.kkt-online.nalog.ru/materials/kktpit01032025.pdf)

* [Включение нового режима и работа на кассе](/articles/iikofront-9-1/fiscalization-before-payment)

* [Новые методы API](https://iiko.github.io/front.api.doc/2025/01/23/print-fiscal-cheque-before-payment.html)
