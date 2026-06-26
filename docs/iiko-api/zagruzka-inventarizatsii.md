* [Тело запроса](/articles/api-documentations/zagruzka-inventarizatsii/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-inventarizatsii/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/zagruzka-inventarizatsii/a/h3_41887754)

Версия iiko: 5.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/incomingInventory |
| --- | --- |

Content-Type: application/xml

### Тело запроса

Структура *incomingInventoryDto*
 [+] [XSD Инвентаризация](javascript:void%280%29)
 [-] [XSD Инвентаризация](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### Что в ответе

Структура *incomingInventoryValidationResult*
 [+] [XSD Результат валидации документа инвентаризации](javascript:void%280%29)
 [-] [XSD Результат валидации документа инвентаризации](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
### **Пример запроса и результат**

**Запрос**


```xml
<?xml version="1.0" encoding="UTF-8"?>
<document>
  <documentNumber>Imv20160703j</documentNumber>
  <dateIncoming>2016-07-03T00:24:00</dateIncoming>
  <status>PROCESSED</status>
  <storeId>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeId>
  <comment>Ничего не изменилось</comment>
  <items>
    <item>
      <productId>F464E4D4-CF9C-49A2-9E18-1227B41A3801</productId>
      <amountContainer>5.0</amountContainer>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <containerId>551E0382-64CA-49F1-B74F-733EBC6902C4</containerId>
      <amountContainer>18.0</amountContainer>
      <comment>Их же было 19?</comment>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <containerId>4D32F56F-89D4-4E2D-8912-3D3593A8284D</containerId>
      <amountContainer>28.0</amountContainer>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <amountContainer>1.0</amountContainer>
    </item>
  </items>
</document>
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<document>
  <documentNumber>Imv20160703j</documentNumber>
  <dateIncoming>2016-07-03T00:24:00</dateIncoming>
  <status>PROCESSED</status>
  <storeId>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeId>
  <comment>Ничего не изменилось</comment>
  <items>
    <item>
      <productId>F464E4D4-CF9C-49A2-9E18-1227B41A3801</productId>
      <amountContainer>5.0</amountContainer>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <containerId>551E0382-64CA-49F1-B74F-733EBC6902C4</containerId>
      <amountContainer>18.0</amountContainer>
      <comment>Их же было 19?</comment>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <containerId>4D32F56F-89D4-4E2D-8912-3D3593A8284D</containerId>
      <amountContainer>28.0</amountContainer>
    </item>
    <item>
      <productId>C6D6C2F2-7E48-4AC9-84CA-1F566C3A941E</productId>
      <amountContainer>1.0</amountContainer>
    </item>
  </items>
</document>
```


**Результат**


```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<incomingInventoryValidationResult>
    <valid>true</valid>
    <warning>false</warning>
    <documentNumber>Imv20160703k</documentNumber>
    <store>
        <id>1239d270-1bbe-f64f-b7ea-5f00518ef508</id>
        <code>1</code>
        <name>Main storage</name>
    </store>
    <date>2016-07-03T00:26:00+03:00</date>
    <items>
        <item>
            <product>
                <id>c6d6c2f2-7e48-4ac9-84ca-1f566c3a941e</id>
                <code>00001</code>
                <name>Товар с разными фасовками</name>
            </product>
            <expectedAmount>13.600000000</expectedAmount>
            <expectedSum>535.370000000</expectedSum>
            <actualAmount>29.450</actualAmount>
            <differenceAmount>15.850000000</differenceAmount>
            <differenceSum>623.930000000</differenceSum>
        </item>
        <item>
            <product>
                <id>f464e4d4-cf9c-49a2-9e18-1227b41a3801</id>
                <code>00002</code>
                <name>Другой товар</name>
            </product>
            <expectedAmount>5.000000000</expectedAmount>
            <expectedSum>0</expectedSum>
            <actualAmount>4.000</actualAmount>
            <differenceAmount>1.000000000</differenceAmount>
            <differenceSum>0</differenceSum>
        </item>
    </items>
</incomingInventoryValidationResult>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<incomingInventoryValidationResult>
    <valid>true</valid>
    <warning>false</warning>
    <documentNumber>Imv20160703k</documentNumber>
    <store>
        <id>1239d270-1bbe-f64f-b7ea-5f00518ef508</id>
        <code>1</code>
        <name>Main storage</name>
    </store>
    <date>2016-07-03T00:26:00+03:00</date>
    <items>
        <item>
            <product>
                <id>c6d6c2f2-7e48-4ac9-84ca-1f566c3a941e</id>
                <code>00001</code>
                <name>Товар с разными фасовками</name>
            </product>
            <expectedAmount>13.600000000</expectedAmount>
            <expectedSum>535.370000000</expectedSum>
            <actualAmount>29.450</actualAmount>
            <differenceAmount>15.850000000</differenceAmount>
            <differenceSum>623.930000000</differenceSum>
        </item>
        <item>
            <product>
                <id>f464e4d4-cf9c-49a2-9e18-1227b41a3801</id>
                <code>00002</code>
                <name>Другой товар</name>
            </product>
            <expectedAmount>5.000000000</expectedAmount>
            <expectedSum>0</expectedSum>
            <actualAmount>4.000</actualAmount>
            <differenceAmount>1.000000000</differenceAmount>
            <differenceSum>0</differenceSum>
        </item>
    </items>
</incomingInventoryValidationResult>
```


##  

##
