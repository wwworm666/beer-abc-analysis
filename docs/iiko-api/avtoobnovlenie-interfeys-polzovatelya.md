* [Особенности функционала автообновления плагинов](/articles/api-documentations/avtoobnovlenie-interfeys-polzovatelya/a/h2__1633432948)
* [Алгоритм автоустановки](/articles/api-documentations/avtoobnovlenie-interfeys-polzovatelya/a/h3__636108227)
* [Полномочия на переключение тумблера](/articles/api-documentations/avtoobnovlenie-interfeys-polzovatelya/a/h3_1349033102)
* [Наименование плагинов](/articles/api-documentations/avtoobnovlenie-interfeys-polzovatelya/a/h3__1113203769)
* [Поддержка локализации описания](/articles/api-documentations/avtoobnovlenie-interfeys-polzovatelya/a/h3__1340192669)

Интерфейс пользователя представляет собой список плагинов с возможностью управления обновлением. Сейчас данный функционал доступен только непосредственно на терминале и выглядит следующим образом:
![](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20.png)

Вызов окна с информацией о плагинах из iikoFront: Дополнения – Проверить и обновить плагины.

В появившемся окне видна информация:

* Наименование плагина, автор;
* Версия API;
* Версия плагина;
* ID лицензии;
* Краткое описание;
* Дополнения (детали по плагину);
* Тумблер разрешения запуска плагина: Разрешен и Запрещен.

Зеленый индикатор напротив плагина свидетельствует о том, что он запущен и успешно работает (физически загружен в память). Если переключить тумблер на «Запрещен», то происходит выгрузка из памяти, индикатор перестает быть «зеленым».

В столбце «Версия API» может встретиться значок предупреждения ![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB8AAAAlCAMAAACNkcLAAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAINUExURT9BQD5AQD0/QDw+Pzk7P09RRHByS2ttSkpMQjo8P0pMQ4GDT7S2WrCyWXBxS21vSq+xWK2vWLe5W5ydVV9gR1NVRZeZVHV3TYeJULGzWYmLUEFDQHl7TbW2WpSWU0tNQ09RQ6CiVmRnSD0/Pzw+QFZYRaOlVmNlSDc5PjM2PXd4TLO1WklLQjs9P0NFQISHT7a4WomKUEZIQUxOQ0dJQlNURJWWU7K0WkBCQF1fRqirV6SlVltcR1JUQ3d5TWhqSZyeVDk7Pjg6P4yOUXx+TWRmSJ6gVVRWRXd5TERGQWdpSZ2fVVdZRTI0PWBiR7e5WqGjVVhaRjQ2PautWFxeR1FTRJWXU3FzSz9BP6utV5CSUTQ2PkZIQoCCToSFT0RFQXR1TLW3WpKUU4iKUEhKQlRWRKmqV2ZnSFlbRp6fVa6wWU1PREJEQXh7TbO1WY6QUUVHQn6AToqNUWVnSVpcRkRHQZqcVK+xWT9BQV5gR6aoV6iqV1lcRj5AP6KkVo+SUlRXRW9wS5qcVY2PUbK0WXt9TTs8Pzg6PlVXRY6QUkxPQ4uMUHV3TEFDQWNlR6yuWKCiVVtcRUNFQUVHQWxuSa6wWKKkVVVXREVIQnt+TbS2WZ6fVHJzS3J0THN1THR2THByTGJkRzs9QGdqSby9XLa4W7m7W5+hVUlKQnp8TX1/TX1/TnZ4TDU3PjY4Pj9iFQ4AAAAJcEhZcwAAFxEAABcRAcom8z8AAAGmSURBVDhPY6AvYGRihLKwA2YWFiYoExtgZGVj5+CEcjABCxc3Dy8fAy4TGFn4BQSFhEWYsbuBkVlUjFdcQlJKGrsjmZhlZOXkFRQFlRiYoULIQFlFVU1AXUNTS1tORxeLAbp6+gaGRsYmpmbm7Ba6UEEEUGG0tLK2sZWwM7IXcBB1hIoigJOOs4ELk6ukm7uRFI+HJ7oLlBm9eL19fP38AwKD/ILVQjSg4jCgERqmHR4R5BMZFRodE2sQF49qACNTQmKSggZLaDJbiq5uqlpaOidyKDJyZmRmqTOqMBllZFsw6Obk5uUXIAcSI2NhYpEOCwNzSnFJKSOTsnFZOX8Fwo/KTJVV1TW1Koy6IXX1DZwMyrqN5U3Z8GhgZDZqbmlta9fVderoLOzS0NVl8ew27/GEGaDS29c/YeKkSZMne5qEcnlOBtK1U6ZOmw4LJM4ZM2fNnjN3HgjMnTtvPpBaUFidt3AR1AKVnMVVS1p4wEAbQvEsXbZclAUizcDIsKJ45SoXFLB6jd8kRBAxta9duw4FrF3HwmgBlQUCRiwAKjUKyAcMDAD38WjSkYGM0QAAAABJRU5ErkJggg==), который, при наведении на него, сообщает информацию, например, о том, что плагин использует другую версию API:

![Èçîáðàæåíèå âûãëÿäèò êàê òåêñò, ñíèìîê ýêðàíà, ïðîãðàììíîå îáåñïå÷åíèå, Ìóëüòèìåäèéíîå ïðîãðàììíîå îáåñïå÷åíèåÑîäåðæèìîå, ñîçäàííîå èñêóññòâåííûì èíòåëëåêòîì, ìîæåò áûòü íåâåðíûì.](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20-1.png)

ID лицензии может быть подсвечен красным, это говорит о том о возможном истечении срока лицензии.

Системные плагины, которыми нельзя управлять, отображаются с недоступным для изменения тумблером.

Проверить обновления можно по нажатию на кнопку «Проверить обновления» - в столбце «Версия плагина» появится значок![](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20-2.png), акцентирующий внимание на плагин, который можно обновить.

Кнопка «Обновить все (…)» - выполнит обновление всех плагинов, по которым появился индикатор о возможном обновлении.

## Особенности функционала автообновления плагинов

### Алгоритм автоустановки

Если плагин устанавливается на терминале впервые, то по умолчанию он устанавливаются в выключенном режиме.

Плагины, которые были включены к моменту начала использования автообновления, продолжат работу в том же режиме.

Системные плагины по умолчанию устанавливаются в включенном режиме.

### Полномочия на переключение тумблера

На старых версиях фронта тумблер доступен для всех пользователей, так как в API нет возможности проверять права доступа. В версиях, начиная с 7.9, производится проверка полномочий и тумблер закрыт правом F\_CA "Закрывать приложение": тумблер могут переключать пользователи с правом F\_CA, остальные пользователи смогут только увидеть перечень плагинов.

Плагины, которые отключаются через данный интерфейс, в папке %ProgramFiles%\iiko\iikoFront\Plugins помечаются точкой в начале названия. Например, «.WaiterServer».

### Наименование плагинов

Краткое наименование плагина, отображаемое на панели автообновления, вносится в файл с разрешением «.nuspec».

В title вносится краткое наименование плагина, в authors вносится информация об авторе и в description описание информации о плагине.

Пример:
![Èçîáðàæåíèå âûãëÿäèò êàê òåêñò, ñíèìîê ýêðàíà, ïðîãðàììíîå îáåñïå÷åíèå, âåá-ñòðàíèöàÑîäåðæèìîå, ñîçäàííîå èñêóññòâåííûì èíòåëëåêòîì, ìîæåò áûòü íåâåðíûì.](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20-3.png)

Отображение на панели:
![](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20-4.png)

Если в манифесте в явном виде не указано нужное название плагина, то «под капотом» из названия плагина вырезается «Resto.Front.Api.», информация о версии и, при наличии, слово «Plugin». Итог – короткое наименование плагина, которое отражается над строкой «Автор».

### Поддержка локализации описания

Текст описания разбивается на разделы при помощи знака «;». Каждый раздел может иметь в начале метку идентификатора локализации, в которой выводится описание. Если такой метки нет, то по умолчанию считается, что текст будет выводиться в английской локализации.

Например, текст первого раздела (строки) будет отображаться при переключении интерфейса фронта на английский язык. Второй раздел описания будет отображаться при русском интерфейсе.

![](/resources/Storage/api-documentations/avtoobnovlenie-interfeys-polzovatelya/avtoobnovlenie-interfeys-polzovatelya-2025-08-20-5.png)

Ограничение – общий текст должен быть не более 4000 символов.

*Как выполнить это в Visual Studio*

В разделе Package c# проекта заполните поля:

* Title - краткое описание плагина,
* Authors – информация об авторе,
* Description – описание информации о плагине. Для локализации в начале раздела используйте идентификатор «ru:»/ «en:» / «it:» и т.д. Разделение разделов также работает через «;».
