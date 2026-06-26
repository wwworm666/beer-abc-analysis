В разделе **Доставка → Отзывы клиентов** можно создать несколько простых вопросов. Ответы на эти вопросы выглядят как:

* «хорошо» — оценка 100,
* «плохо» — оценка 0.

![](/resources/Storage/api-documentations/otzyv-2019-06-11.png)

Получить id вопросов можно только напрямую из базы данных SQL ресторана, например:


PL/SQL

```
select*from entity wheretype='SurveyItem'

andxmllike'%Понравилось ли%'
```

PL/SQL

```
select*from entity wheretype='SurveyItem'

andxmllike'%Понравилось ли%'
```


![](/resources/Storage/api-documentations/otzyv-2019-06-11-1.png)

Добавить отзыв к заказу на доставку или самовывоз.

POST-запрос:

https://iiko.biz:9900/api/0/orders/sendDeliveryOpinion?access\_token=Pyjd6K-D3qmXL\_UAcOEs63Sn1hng-6RhrqZdLQpVqiOdIXcqgO83VRk4-Ndn1WYQkSZMlv7Ci0bDJifzlAI\_ag2&request\_timeout=00%3A01%3A00

с телом запроса в формате application/json:


```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "deliveryId": "d7148304-b801-5fb7-ed49-e94389ba5497",//ID заказа
  "comment": "комментарий к отзыву",//Данное поле можно выводить в OLAP отчет по доставкам.
  "marks": [
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C4", "mark": "0"},
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C5", "mark": "100"},
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C6", "mark": "100"}]
}
```

```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "deliveryId": "d7148304-b801-5fb7-ed49-e94389ba5497",//ID заказа
  "comment": "комментарий к отзыву",//Данное поле можно выводить в OLAP отчет по доставкам.
  "marks": [
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C4", "mark": "0"},
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C5", "mark": "100"},
    {"surveyItemId": "22C5DC3A-6EF3-2A5C-0162-2E25135C00C6", "mark": "100"}]
}
```


Отзывы можно менять в колл-центре в iikoOffice только у заказов в статусе «Закрыт».
![](/resources/Storage/api-documentations/otzyv-2019-06-11-3.png)
