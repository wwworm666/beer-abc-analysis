* [Авторизация](/articles/api-documentations/avtorizatsiya/a/h2_1617055750)
* [Выход](/articles/api-documentations/avtorizatsiya/a/h2__1074617610)

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | При авторизации вы занимаете один слот лицензии. Токен, который вы получаете при авторизации, можно использовать до того момента, пока он не перестанет работать. И если у вас только одна лицензия сервера, а вы уже получили токен, следующее обращение к серверу за токеном вызовет ошибку. Если вам негде хранить токен при работе с сервером API, рекомендуем вам разлогиниться, что приводит к отпусканию лицензии. |
| --- | --- |

## Авторизация

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | **https://host:port/resto/api/auth?login=[login]&pass=[sha1passwordhash]** |
| --- | --- |

**Пример запроса**

https://localhost:8080/resto/api/auth?login=admin&pass=2155245b2c002a1986d3f384af93be813537a476

```

```

**Параметры запроса**

| Параметр | Описание |
| --- | --- |
| login | Логин пользователя |
| pass | SHA1 hash от пароля<br> <br>в bash его можно получить так: printf "resto#test" | sha1sum |

**Что в ответе**

Строка-токен, который необходимо передавать как cookie с именем key или как параметр key всех запросов.

Начиная с 4.3 сервер сам устанавливает cookie key.

## Выход

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/logout?key=[token]** |
| --- | --- |


```

```

**Что в ответе**

Строка-токен, полученная при авторизации.

**Пример запроса**

https://localhost:8080/resto/api/logout?key=b354d18c-3d3a-e1a6-c3b9-9ef7b5055318

https://localhost:8080/resto/api/logout c cookie key=c0508074-a052-6276-bf72-871f7acb865e

```

```
