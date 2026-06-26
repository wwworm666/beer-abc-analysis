* [Выгрузка изображения](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Выгрузкаизображения)
* [Параметры запроса](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Параметры)
* [Что в ответе](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Результат)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Примерзапросаирезультата)
* [Импорт изображений](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Импортизображений)
* [Тело запроса](/articles/api-documentations/rabota-s-izobrazheniyami/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Результат.1)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Примерзапросаирезультата.1)
* [Удаление изображений](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Удалениеизображений)
* [Тело запроса](/articles/api-documentations/rabota-s-izobrazheniyami/a/h3__1377878181)
* [Результат](/articles/api-documentations/rabota-s-izobrazheniyami/a/v2.APIизображений-Результат.2)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-izobrazheniyami/a/h3_1561844723)

## Выгрузка изображения

Версия iiko: 6.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/images/load?imageId={imageId} |
| --- | --- |

### Параметры запроса

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| **imageId** | UUID | UUID запрашиваемого изображения. |

### Что в ответе

Выгружено изображение.

| Поле | Версия iiko | Тип данных | Описание |
| --- | --- | --- | --- |
| **id** | 6.2 | UUID | UUID изображения. |
| **data** | 6.2 | byte[] | Изображение в Base64. |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/images/load?imageId=567791bd-7881-4bcf-8f84-138ca9d0f53c
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


## Импорт изображений

Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/images/save |
| --- | --- |

### Тело запроса

| Поле | Версия iiko | Тип данных | Значение |
| --- | --- | --- | --- |
| id | 6.2 | byte[] | Изображение в Base64.<br>Размер изображения не должен превышать<br>максимальный размер установленный в настройках сервера.<br>Настройка "*saved-image-max-size-mb*". По умолчанию 512Мб. |

### Что в ответе

Json структура результата импорта.

### Результат

| Поле | Тип данных | Значение |
| --- | --- | --- |
| result | Enum: <br>"SUCCESS", <br>"ERROR" | Результата операции. |
| errors | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт документа. |
| response | ImageDto | Cохраненное изображение. |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/images/save
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```


## Удаление изображений

Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/images/delete |
| --- | --- |

### **Тело запроса**

| Поле | Тип данных | Значение |
| --- | --- | --- |
| items | List&lt;IdCodetDto&gt; | Список UUID изображений, которые нужно удалить.<br><br><br>| Поле | Тип данных | Значение |<br>| --- | --- | --- |<br>| id | UUID | UUID элемента | |
| --- | --- | --- |


Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```


### Результат

| Поле | Тип данных | Описание |
| --- | --- | --- |
| **result** | Enum:<br>"SUCCESS",<br>"ERROR" | Результат операции. |
| **errors** | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт документа. |
| **response** | IdListDto | Список UUID изображений, которые удалили. |

### **Пример запроса и результата**

**Запрос**

https://localhost:8080/resto/api/v2/images/delete

#### **Результат**

**
```json
Formatted JSON Data{ 
   "result":"SUCCESS",
   "errors":null,
   "response":{ 
      "items":[ 
         { 
            "id":"48ba540a-d767-f95a-0164-f56e1e50007f"
         }
      ]
   }
}
```

```json
Formatted JSON Data{ 
   "result":"SUCCESS",
   "errors":null,
   "response":{ 
      "items":[ 
         { 
            "id":"48ba540a-d767-f95a-0164-f56e1e50007f"
         }
      ]
   }
}
```
**
