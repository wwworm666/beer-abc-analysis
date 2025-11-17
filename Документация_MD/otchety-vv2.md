# Otchety Vv2

*Generated from PDF: otchety-vv2.pdf*

*Total pages: 8*

---


## Page 1

API Documentation Page1 of 8
1. Отчеты
Балансы по счетам, контрагентам и
подразделениям
Версияiiko: 5.2
https://host:port/resto/api/v2/reports/balance/counteragents
Параметры запроса
Параметр Описание
учетная-датавремяотчетавформатеyyyy-MM-dd'T'HH:mm:ss
timestamp
(обязательный)
account idсчетадляфильтрации(необязательный,можноуказатьнесколько)
idконтрагентадляфильтрации (необязательный,можноуказать
counteragent
несколько)
idподразделениядляфильтрации(необязательный,можноуказать
department
несколько)
Что в ответе
Возвращает денежные балансыпоуказанным счетам,контрагентам иподразделениям на
заданнуюучетнуюдату-время.
См.ниже примеррезультата.
Пример запроса и результата
Запрос
https://localhost:9080/resto/api/v2/reports/balance/counteragents
?key=88e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10-
19T23:10:10
[+] Результат
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметр |  |  | Описание |  |

|  |  |  |  |  |  |

| timestamp |  |  | учетная-датавремяотчетавформатеyyyy-MM-dd'T'HH:mm:ss
(обязательный) |  |  |

| account |  |  | idсчетадляфильтрации(необязательный,можноуказатьнесколько) |  |  |

| counteragent |  |  | idконтрагентадляфильтрации (необязательный,можноуказать
несколько) |  |  |

| department |  |  | idподразделениядляфильтрации(необязательный,можноуказать
несколько) |  |  |



### Table:

| https://localhost:9080/resto/api/v2/reports/balance/counteragents |

|---|

| ?key=88e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10- |

| 19T23:10:10 |


---


## Page 2

API Documentation Page2 of 8
[-] Результат
Copy Code
Код
[
{
"account": "657ded9f-a1a3-416c-91a4-5a2fc78e8a36",
"counteragent": null,
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": 64083
},
{
"account": "8a11a460-04f3-43fe-a245-bc32a7d22504",
"counteragent": null,
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": -50
},
{
"account": "97036ddb-b2e1-cd47-1669-c145daa9f9c5",
"counteragent": "6a656dcc-9e1b-4a3a-90a8-01202184c93f",
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": 39.37
},
{
"account": "56729828-f09b-d58e-04be-ed0f2e4e10e1",
"counteragent": "6a656dcc-9e1b-4a3a-90a8-01202184c93f",
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": -66494
},
{
"account": "07926ff3-9319-b93e-80ff-1897825fdead",
"counteragent": null,
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": 728.25
},
{
"account": "1239d270-1bbe-f64f-b7ea-5f00518ef508",
"counteragent": null,
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": 2380.3
},
{
"account": "67af8bc9-628f-2124-2345-3750bb7db6fa",
"counteragent": null,
"department": "ef9461e9-d673-c6ed-0150-a59eb13f000d",
"sum": -686.92
}
]
Allrightsreserved © CompanyInc., 2023


### Table:

| Copy Code |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

|  | [ |  |

|  | { |  |

|  | "account": "657ded9f-a1a3-416c-91a4-5a2fc78e8a36", |  |

|  | "counteragent": null, |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": 64083 |  |

|  | }, |  |

|  | { |  |

|  | "account": "8a11a460-04f3-43fe-a245-bc32a7d22504", |  |

|  | "counteragent": null, |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": -50 |  |

|  | }, |  |

|  | { |  |

|  | "account": "97036ddb-b2e1-cd47-1669-c145daa9f9c5", |  |

|  | "counteragent": "6a656dcc-9e1b-4a3a-90a8-01202184c93f", |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": 39.37 |  |

|  | }, |  |

|  | { |  |

|  | "account": "56729828-f09b-d58e-04be-ed0f2e4e10e1", |  |

|  | "counteragent": "6a656dcc-9e1b-4a3a-90a8-01202184c93f", |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": -66494 |  |

|  | }, |  |

|  | { |  |

|  | "account": "07926ff3-9319-b93e-80ff-1897825fdead", |  |

|  | "counteragent": null, |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": 728.25 |  |

|  | }, |  |

|  | { |  |

|  | "account": "1239d270-1bbe-f64f-b7ea-5f00518ef508", |  |

|  | "counteragent": null, |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": 2380.3 |  |

|  | }, |  |

|  | { |  |

|  | "account": "67af8bc9-628f-2124-2345-3750bb7db6fa", |  |

|  | "counteragent": null, |  |

|  | "department": "ef9461e9-d673-c6ed-0150-a59eb13f000d", |  |

|  | "sum": -686.92 |  |

|  | } |  |

|  | ] |  |

|  |  |  |


---


## Page 3

API Documentation Page3 of 8
Остатки на складах
Версияiiko: 5.2
https://host:port/resto/api/v2/reports/balance/stores
Параметры запроса
Параметр Описание
учетная-датавремяотчетавформатеyyyy-MM-dd'T'HH:mm:ss
timestamp
(обязательный)
idподразделениядляфильтрации(необязательный,можноуказать
department
несколько)
store idсклададляфильтрации(необязательный,можноуказатьнесколько)
idэлементаноменклатурыдляфильтрации (необязательный,можно
product
указатьнесколько)
Что в ответе
Возвращает количественные (amount) иденежные (sum) остаткитоваров(product) на
складах(store) на заданнуюучетнуюдату-время.
См.ниже примеррезультата.
Пример запроса и результата
Запрос
https://localhost:9080/resto/api/v2/reports/balance/stores?key=88
e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10-18T23:10:10
Результат
CopyCode
Код
[
{
"store": "657ded9f-a1a3-416c-91a4-5a2fc78e8a36",
"product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметр |  |  | Описание |  |

|  |  |  |  |  |  |

| timestamp |  |  | учетная-датавремяотчетавформатеyyyy-MM-dd'T'HH:mm:ss
(обязательный) |  |  |

| department |  |  | idподразделениядляфильтрации(необязательный,можноуказать
несколько) |  |  |

| store |  |  | idсклададляфильтрации(необязательный,можноуказатьнесколько) |  |  |

| product |  |  | idэлементаноменклатурыдляфильтрации (необязательный,можно
указатьнесколько) |  |  |



### Table:

| https://localhost:9080/resto/api/v2/reports/balance/stores?key=88 |  |

|---|---|

| e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10-18T23:10:10 |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

|  | [ |  |

|  | { |  |

|  | "store": "657ded9f-a1a3-416c-91a4-5a2fc78e8a36", |  |

|  | "product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801", |  |


---


## Page 4

API Documentation Page4 of 8
"amount": 123,
"sum": 64083
},
{
"store": "1239d270-1bbe-f64f-b7ea-5f00518ef508",
"product": "c6d6c2f2-7e48-4ac9-84ca-1f566c3a941e",
"amount": 29.45,
"sum": 1159.3
},
{
"store": "1239d270-1bbe-f64f-b7ea-5f00518ef508",
"product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801",
"amount": 15,
"sum": 1221
}
]
Отчет по балансу на 3 регистре ЕГАИС (акцизные
марки)
Получение обновлений состояния на 3 регистре
Версияiiko: 7.4
https://host:port/resto/api/v2/reports/egais/marks/list
Параметры запроса
Тип
Название Обязательный Описание
данных
Нет,поумолчанию
СписокРАР-идентификатороворганизаций,баланс
fsRarId List<String>
возвращаютсяданныедлявсех которыхзапрашивается
организаций.
Номерревизии,начинаяскоторойнеобходимо
отфильтроватьсущности.
revisionFrom int Нет,поумолчанию-1
Невключающийсамуревизию,т.е.ревизияобъекта
>revisionFrom.
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "amount": 123, |

|  | "sum": 64083 |

|  | }, |

|  | { |

|  | "store": "1239d270-1bbe-f64f-b7ea-5f00518ef508", |

|  | "product": "c6d6c2f2-7e48-4ac9-84ca-1f566c3a941e", |

|  | "amount": 29.45, |

|  | "sum": 1159.3 |

|  | }, |

|  | { |

|  | "store": "1239d270-1bbe-f64f-b7ea-5f00518ef508", |

|  | "product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801", |

|  | "amount": 15, |

|  | "sum": 1221 |

|  | } |

|  | ] |

|  |  |



### Table:

| Название | Тип
данных | Обязательный | Описание |

|---|---|---|---|

| fsRarId | List<String> | Нет,поумолчанию
возвращаютсяданныедлявсех
организаций. | СписокРАР-идентификатороворганизаций,баланс
которыхзапрашивается |

| revisionFrom | int | Нет,поумолчанию-1 | Номерревизии,начинаяскоторойнеобходимо
отфильтроватьсущности.
Невключающийсамуревизию,т.е.ревизияобъекта
>revisionFrom. |


---


## Page 5

API Documentation Page5 of 8
Пример запроса и результат
Запрос
https://localhost:8080/resto/api/v2/reports/egais/marks/list?fsRa
rId=030000455388&fsRarId=030000455399&revisionFrom=100
[+] Примеррезультата
[-] Примеррезультата
Copy Code
Код
{
"revision": 21850,
"fullUpdate": false,
"marksByBRegId": {
"TEST-FB-000000036836552": {
"sourceRarId": "030000455388",
"alcCode": "0017810000001186747",
"marksOnBalance": {
"45133934586097051828017AQCGHTEIZP591XRZIBAG71CVSHFOLEC7WRJ72HKO8U00O67X
4OPVN13E71JBG20NUOSBUI5W7N3UTAJLYRD5W1C5YUKOECU53EDRC7C07JOLNXETHXNTIJZR
ZEP2637": {
"dateTo": "2500-01-01T00:00:00"
}
},
"marksWrittenOff": {}
},
"TEST-FB-000000038082854": {
"sourceRarId": "030000455388",
"alcCode": "0350643000001257183",
"marksOnBalance": {
"14720028608176101800163J3YZYU7N453A3YLT2H6GOJTATTQ2JLA6CK3KODYV5S4QGJK6
5DQLCK3WH4G4D5UD6R5AY7GW2ORHBPVCTC7TPXMXGX6UNLEPY7RZEIZD6BWUDOTWR5LPNOJ2
VHNR2AY": {
"dateTo": "2500-01-01T00:00:00"
},
"147200297529561018001ZFR4IT3TXXRR3DVKXJ3BCJZNHQWMAPW2IMPAUX6ZLNNQHM2GD6
TDHYL3Q6TMTFAPBFFUPQPFRCWHJT3NB7M3SIPV2EBESP4FXFAXTSHGIWGK3KGSS57PC6BFIZ
GKELM4Y": {
"dateTo": "2500-01-01T00:00:00"
},
"147200297957101018001QEPQGYNG6UCQ3G5WNDPCPMSUXASWVXUKXG5D6G5JN4HN5ISKNG
NPIWUQ7GABVKZFN4F2G4Y234TB6QIBFDL4TQOXUGEXSZFFOYUB3LLY74D3BK4R6DXISEGIOB
EWZWBGI": {
Allrightsreserved © CompanyInc., 2023


### Table:

| https://localhost:8080/resto/api/v2/reports/egais/marks/list?fsRa |  |

|---|---|

| rId=030000455388&fsRarId=030000455399&revisionFrom=100 |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

| {
"revision": 21850,
"fullUpdate": false,
"marksByBRegId": {
"TEST-FB-000000036836552": {
"sourceRarId": "030000455388",
"alcCode": "0017810000001186747",
"marksOnBalance": {
"45133934586097051828017AQCGHTEIZP591XRZIBAG71CVSHFOLEC7WRJ72HKO8U00O67X
4OPVN13E71JBG20NUOSBUI5W7N3UTAJLYRD5W1C5YUKOECU53EDRC7C07JOLNXETHXNTIJZR
ZEP2637": {
"dateTo": "2500-01-01T00:00:00"
}
},
"marksWrittenOff": {}
},
"TEST-FB-000000038082854": {
"sourceRarId": "030000455388",
"alcCode": "0350643000001257183",
"marksOnBalance": {
"14720028608176101800163J3YZYU7N453A3YLT2H6GOJTATTQ2JLA6CK3KODYV5S4QGJK6
5DQLCK3WH4G4D5UD6R5AY7GW2ORHBPVCTC7TPXMXGX6UNLEPY7RZEIZD6BWUDOTWR5LPNOJ2
VHNR2AY": {
"dateTo": "2500-01-01T00:00:00"
},
"147200297529561018001ZFR4IT3TXXRR3DVKXJ3BCJZNHQWMAPW2IMPAUX6ZLNNQHM2GD6
TDHYL3Q6TMTFAPBFFUPQPFRCWHJT3NB7M3SIPV2EBESP4FXFAXTSHGIWGK3KGSS57PC6BFIZ
GKELM4Y": {
"dateTo": "2500-01-01T00:00:00"
},
"147200297957101018001QEPQGYNG6UCQ3G5WNDPCPMSUXASWVXUKXG5D6G5JN4HN5ISKNG
NPIWUQ7GABVKZFN4F2G4Y234TB6QIBFDL4TQOXUGEXSZFFOYUB3LLY74D3BK4R6DXISEGIOB
EWZWBGI": { |  |  |



### Table:

| { |

|---|

| "revision": 21850, |

| "fullUpdate": false, |

| "marksByBRegId": { |

| "TEST-FB-000000036836552": { |

| "sourceRarId": "030000455388", |

| "alcCode": "0017810000001186747", |

| "marksOnBalance": { |



### Table:

| "45133934586097051828017AQCGHTEIZP591XRZIBAG71CVSHFOLEC7WRJ72HKO8U00O67X |

|---|

| 4OPVN13E71JBG20NUOSBUI5W7N3UTAJLYRD5W1C5YUKOECU53EDRC7C07JOLNXETHXNTIJZR |

| ZEP2637": { |

| "dateTo": "2500-01-01T00:00:00" |

| } |

| }, |

| "marksWrittenOff": {} |

| }, |

| "TEST-FB-000000038082854": { |

| "sourceRarId": "030000455388", |

| "alcCode": "0350643000001257183", |

| "marksOnBalance": { |



### Table:

| "14720028608176101800163J3YZYU7N453A3YLT2H6GOJTATTQ2JLA6CK3KODYV5S4QGJK6 |

|---|

| 5DQLCK3WH4G4D5UD6R5AY7GW2ORHBPVCTC7TPXMXGX6UNLEPY7RZEIZD6BWUDOTWR5LPNOJ2 |

| VHNR2AY": { |

| "dateTo": "2500-01-01T00:00:00" |

| }, |



### Table:

| "147200297529561018001ZFR4IT3TXXRR3DVKXJ3BCJZNHQWMAPW2IMPAUX6ZLNNQHM2GD6 |

|---|

| TDHYL3Q6TMTFAPBFFUPQPFRCWHJT3NB7M3SIPV2EBESP4FXFAXTSHGIWGK3KGSS57PC6BFIZ |

| GKELM4Y": { |

| "dateTo": "2500-01-01T00:00:00" |

| }, |



### Table:

| "147200297957101018001QEPQGYNG6UCQ3G5WNDPCPMSUXASWVXUKXG5D6G5JN4HN5ISKNG |

|---|

| NPIWUQ7GABVKZFN4F2G4Y234TB6QIBFDL4TQOXUGEXSZFFOYUB3LLY74D3BK4R6DXISEGIOB |

| EWZWBGI": { |


---


## Page 6

API Documentation Page6 of 8
"dateTo": "2500-01-01T00:00:00"
},
"147200297962451018001WWDHV3WPQE7VF32EKSPQYYTG74SSZOKTXVNUTFLCVB3CEWK3IX
SHEQNSYUOAUJNDWGDR3OT3H4GYRDEL5RWQ4CSUXBYR4MSEJCRJ22FLIMGIP44MZ2XFAUTXL5
6LOS2UQ": {
"dateTo": "2500-01-01T00:00:00"
},
"1473000650085210180015UVE7CKGKV46PWY4QALCZK3DOMXPGAWNUCIJTE7EN2EM6QGS3N
7XAGJDSBLA44VZ25IXK73DSNANNOMASWKU7VRCLLVDZJDEA73KZNMSXSQ2EA73XJNXKOWSKQ
TDR34JI": {
"dateTo": "2500-01-01T00:00:00"
}
},
"marksWrittenOff": {
"147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU
PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X
ZSPXPKA": {
"dateTo": "2020-12-07T00:00:00"
},
"147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU
PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X
ZSPXZZZ": {
"dateTo": "2020-08-28T12:52:44.473"
}
}
}
}
}
Описание полей
Поле Типданных Описание
revision int Ревизия,покоторую(включительно)выданыданные
true-пакетявляется"полнымобновлением",тоесть,клиентдолжен
удалитьвсеимеющиеданные,неперечисленныеявно.
fullUpdate Boolean
false-пакетявляется"частичнымобновлением",клиентдолжен
заменитьзакешированныезаписистемижеключами.
marksByBRegI Map<String, Названиевложенногополя-BRegId-ИдентификаторСправкиБ
d EgaisBRegDto> (Справки2)
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| "dateTo": "2500-01-01T00:00:00"
},
"147200297962451018001WWDHV3WPQE7VF32EKSPQYYTG74SSZOKTXVNUTFLCVB3CEWK3IX
SHEQNSYUOAUJNDWGDR3OT3H4GYRDEL5RWQ4CSUXBYR4MSEJCRJ22FLIMGIP44MZ2XFAUTXL5
6LOS2UQ": {
"dateTo": "2500-01-01T00:00:00"
},
"1473000650085210180015UVE7CKGKV46PWY4QALCZK3DOMXPGAWNUCIJTE7EN2EM6QGS3N
7XAGJDSBLA44VZ25IXK73DSNANNOMASWKU7VRCLLVDZJDEA73KZNMSXSQ2EA73XJNXKOWSKQ
TDR34JI": {
"dateTo": "2500-01-01T00:00:00"
}
},
"marksWrittenOff": {
"147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU
PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X
ZSPXPKA": {
"dateTo": "2020-12-07T00:00:00"
},
"147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU
PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X
ZSPXZZZ": {
"dateTo": "2020-08-28T12:52:44.473"
}
}
}
}
} |

|  |



### Table:

| "dateTo": "2500-01-01T00:00:00" |

|---|

| }, |



### Table:

| "147200297962451018001WWDHV3WPQE7VF32EKSPQYYTG74SSZOKTXVNUTFLCVB3CEWK3IX |

|---|

| SHEQNSYUOAUJNDWGDR3OT3H4GYRDEL5RWQ4CSUXBYR4MSEJCRJ22FLIMGIP44MZ2XFAUTXL5 |

| 6LOS2UQ": { |

| "dateTo": "2500-01-01T00:00:00" |

| }, |



### Table:

| "1473000650085210180015UVE7CKGKV46PWY4QALCZK3DOMXPGAWNUCIJTE7EN2EM6QGS3N |

|---|

| 7XAGJDSBLA44VZ25IXK73DSNANNOMASWKU7VRCLLVDZJDEA73KZNMSXSQ2EA73XJNXKOWSKQ |

| TDR34JI": { |

| "dateTo": "2500-01-01T00:00:00" |

| } |

| }, |

| "marksWrittenOff": { |



### Table:

| "147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU |

|---|

| PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X |

| ZSPXPKA": { |

| "dateTo": "2020-12-07T00:00:00" |

| }, |



### Table:

| "147200326793571018001OGVXMUHLPFDJLQVICCQ4JWJSLARD4QBZ7JSGRLQXTHKESRGMWU |

|---|

| PZMRGRQ3V3X6T6ZMW6OYL45TNYD7YLQGK6XEIB43CELMC7K7XG6IMPSYCCMLJANNZS5XE43X |

| ZSPXZZZ": { |

| "dateTo": "2020-08-28T12:52:44.473" |

| } |

| } |

| } |

| } |

| } |



### Table:

| Поле | Типданных | Описание |

|---|---|---|

| revision | int | Ревизия,покоторую(включительно)выданыданные |

| fullUpdate | Boolean | true-пакетявляется"полнымобновлением",тоесть,клиентдолжен
удалитьвсеимеющиеданные,неперечисленныеявно.
false-пакетявляется"частичнымобновлением",клиентдолжен
заменитьзакешированныезаписистемижеключами. |

| marksByBRegI
d | Map<String,
EgaisBRegDto> | Названиевложенногополя-BRegId-ИдентификаторСправкиБ
(Справки2) |


---


## Page 7

API Documentation Page7 of 8
Поле Типданных Описание
Значениевложенногополя:
Типданных Описание
Поле
Дата-времяактуальности
состояния:
· MAX_DATE,еслимарка
ещенесписана
· Дата-времясписания+
Датавформате
MAX_MARK_KEEP_DAY
dateT yyyy-MM-
Sдней,еслисписана
o dd'T'HH:mm:ss.SS
документом,находящимся
S
внередактируемомстатусе
· Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок).
Множествоакцизныхмарок,списанныхсбалансаорганизации.
Названиевложенногополя-полныйтекстакцизноймарки.
Значениявложенногополя:
Парамет
Тип,формат Описание
р
Map<String,
marksWrittenO
EgasMarkStateDto Дата-времяактуальности
ff
> состояния:
· MAX_DATE,еслимарка
Датавформате ещенесписана
yyyy-MM-
dateTo
dd'T'HH:mm:ss.S · Дата-времясписания+
SS MAX_MARK_KEEP_DA
YSдней,еслисписана
документом,
находящимсяв
нередактируемомстатусе
Allrightsreserved © CompanyInc., 2023


### Table:

| Поле | Типданных | Описание |

|---|---|---|

|  |  | Значениевложенногополя:
Типданных Описание
Поле
Дата-времяактуальности
состояния:
· MAX_DATE,еслимарка
ещенесписана
· Дата-времясписания+
Датавформате
MAX_MARK_KEEP_DAY
dateT yyyy-MM-
Sдней,еслисписана
o dd'T'HH:mm:ss.SS
документом,находящимся
S
внередактируемомстатусе
· Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок). |

| marksWrittenO
ff | Map<String,
EgasMarkStateDto
> | Множествоакцизныхмарок,списанныхсбалансаорганизации.
Названиевложенногополя-полныйтекстакцизноймарки.
Значениявложенногополя:
Парамет
Тип,формат Описание
р
Дата-времяактуальности
состояния:
· MAX_DATE,еслимарка
Датавформате ещенесписана
yyyy-MM-
dateTo
dd'T'HH:mm:ss.S · Дата-времясписания+
SS MAX_MARK_KEEP_DA
YSдней,еслисписана
документом,
находящимсяв
нередактируемомстатусе |



### Table:

|  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|

| Поле |  |  |  |  |  |  |

|  |  | Типданных |  |  | Описание |  |

|  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |

| dateT
o | Датавформате
yyyy-MM-
dd'T'HH:mm:ss.SS
S |  |  | Дата-времяактуальности
состояния:
· MAX_DATE,еслимарка
ещенесписана
· Дата-времясписания+
MAX_MARK_KEEP_DAY
Sдней,еслисписана
документом,находящимся
внередактируемомстатусе
· Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок). |  |  |



### Table:

|  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|

| Парамет
р |  |  |  |  |  |  |

|  |  | Тип,формат |  |  | Описание |  |

|  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |

| dateTo | Датавформате
yyyy-MM-
dd'T'HH:mm:ss.S
SS |  |  | Дата-времяактуальности
состояния:
· MAX_DATE,еслимарка
ещенесписана
· Дата-времясписания+
MAX_MARK_KEEP_DA
YSдней,еслисписана
документом,
находящимсяв
нередактируемомстатусе |  |  |


---


## Page 8

API Documentation Page8 of 8
Поле Типданных Описание
Тип,формат Описание
р
· Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок).
Allrightsreserved © CompanyInc., 2023


### Table:

| Поле | Типданных |  | Описание | Тип,формат | Описание |  |

|---|---|---|---|---|---|---|

|  |  | р
· Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок). | р |  |  |  |

|  |  |  |  |  | · Дата-времяудаления
последнегоизвестного
EgaisMarkTableItem
(информацияодвижении
акцизноймарки)(для
отсутствующихмарок). |  |



### Table:

|  |

|---|

| р |


---
