| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Выгружать в API номенклатуру из iikoChain  Выгружать нужно только для колл-центра или самостоятельного торгового предприятия RMS. |
| --- | --- |

Рассмотрим пример запроса номенклатуры:

https://iiko.biz:9900/api/0/nomenclature/f20594c6-2da7-11e8-80e0-d8d38565926f?access\_token=Y4ZOYGUI2prLT4DO0rQRww6tbqwTw\_eocUP2Kpv3f3DYvL0thMOO4tcaRUh1fMhYg0X95hLK3JXrELTOkZFxeg2&revision=0

где:

* revision=0 — номер ревизии, с которой мы получим изменения блюд.
* 0 — запросить с самого начала.

Если состав блюд для выгрузки в API не меняется, не будет меняться и ревизия.

В конце ответа от API будет отображена ревизия и дата последней выгрузки
"revision": 199996109,
"uploadDate": "2019-05-13 16:46:38"
}

По умолчанию внешнее меню выгружается , этот интервал не рекомендуется изменять.

Принудительно выгрузить внешнее меню и поднять ревизию можно через скрипт к tomcat RMS

http://127.0.0.1:8080/resto/service/import/forceNomenclatureImport.jsp с флагом «full Re-export».

В ответе от API будет [список номенклатуры, выгруженной в iiko.biz](/articles/api-documentations/kak-podkluchit-api). Пустой ответ от API означает, что товары не выгружены в iiko.biz.
