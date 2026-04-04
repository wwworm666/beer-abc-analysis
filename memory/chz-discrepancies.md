# 🔍 Сверка нашей документации с официальной документацией ЧЗ

**Дата проверки:** 27 марта 2026
**Источники:**
- `c:\Users\1\Desktop\чз\docs.cr11pt.ru.html` (официальная документация True API)
- `c:\Users\1\Desktop\чз\docs.crpt.ru.html` (основная документация)
- `c:\Users\1\Desktop\чз\docs_crpt_ru_gismt_Инструкция_по_работе_с_API_.html`

---

## ❌ КРИТИЧЕСКИЕ НЕСООТВЕТСТВИЯ

### 1. Тип подписи для аутентификации

| Наша документация | Официальная документация |
|-------------------|--------------------------|
| Подпись через `-sfsign -hash` (откреплённая подпись хэша) | **Присоединённая подпись** (attached signature) строки `data` |
| Подписываем **хэш** строки | Подписываем **саму строку** `data` |

**Цитата из оф. документации (docs.cr11pt.ru.html:479):**
> «Отправка в Систему маркировки данных в том же виде, в котором данные были получены (пара «uuid — data»), только теперь «data» — это подписанная УКЭП строка»

**Наш код (неправильно):**
```python
# ❌ Подписываем хэш отдельно
hash_cmd = f'"{CSP_PATH}" -hash -in "{data_file}" -out "{hash_file}"'
sign_cmd = f'"{CSP_PATH}" -sfsign -cont "{KEY_CONTAINER}" -hash "{hash_value}" -base64'
```

**Как правильно:**
```python
# ✅ Подписываем саму строку data присоединённой подписью
sign_cmd = f'"{CSP_PATH}" -sign -cont "{KEY_CONTAINER}" "{data_file}" -base64'
```

**Почему важно:**
- `/auth/simpleSignIn` требует **присоединённую подпись** (данные + подпись вместе)
- `/doc` требует **откреплённую подпись** (signature отдельно в поле)

---

### 2. Команда подписи: `-sfsign` vs `-sign`

| Команда | Назначение | Когда использовать |
|---------|------------|-------------------|
| `-sign` | **Присоединённая подпись** (attached) | `/auth/simpleSignIn` — аутентификация |
| `-sfsign` | **Откреплённая подпись** (detached) | `/doc` — документы, `/cises/info` — запросы с подписью |

**Наш код (неправильно):**
```python
# ❌ Используем -sfsign для аутентификации
sign_cmd = f'"{CSP_PATH}" -sfsign -cont "{KEY_CONTAINER}" -hash "{hash_value}" -base64'
```

**Как правильно:**
```python
# ✅ Для аутентификации используем -sign
sign_cmd = f'"{CSP_PATH}" -sign -cont "{KEY_CONTAINER}" "{data_file}" -base64'

# ✅ Для документов используем -sfsign
sign_cmd = f'"{CSP_PATH}" -sfsign -cont "{KEY_CONTAINER}" -hash "{hash_value}" -base64'
```

---

### 3. Формат входных данных для подписи

| Наша документация | Официальная документация |
|-------------------|--------------------------|
| Сохраняем как binary: `f.write(data.encode('utf-8'))` | **Текстовая строка** без BOM и спецсимволов |

**Проблема:**
При сохранении в binary режиме может добавляться BOM (Byte Order Mark), что изменит хэш и подпись не пройдёт валидацию.

**Как правильно:**
```python
# ✅ Текстовый режим без BOM
with open(data_file_path, 'w', encoding='utf-8') as f:
    f.write(data)  # Просто строка, без encode()
```

---

### 4. Алгоритм хэширования (не указан явно)

| Наша документация | Официальная документация |
|-------------------|--------------------------|
| Не указан, используется по умолчанию | **ГОСТ Р 34.11-2012 (256 бит)** для ГОСТ УКЭП |

**Проблема:**
CSP может использовать разные алгоритмы хэширования по умолчанию в зависимости от типа ключа.

**Как правильно:**
```bash
# ✅ Явное указание алгоритма для ГОСТ
csptest.exe -hash -alg "GOSTR3411_2012_256" -in data.txt -out hash.txt

# ИЛИ для RSA
csptest.exe -hash -alg "SHA256" -in data.txt -out hash.txt
```

---

## ✅ ЧТО ВЕРНО В НАШЕЙ ДОКУМЕНТАЦИИ

| Элемент | Статус | Комментарий |
|---------|--------|-------------|
| URL аутентификации | ✅ Верно | `/auth/key` и `/auth/simpleSignIn` |
| Срок действия токена | ✅ Верно | 10 часов |
| Формат UUID | ✅ Верно | UUID v4 |
| Структура запроса simpleSignIn | ✅ Верно | `{"uuid": "...", "data": "..."}` |
| Экранирование кодов маркировки | ✅ Верно | `"` → `\"` в JSON |
| Кодировка cp866 для вывода CSP | ✅ Верно | Подтверждено практикой |
| Базовый URL API | ✅ Верно | `https://markirovka.crpt.ru/api/v3/true-api` |
| Метод `/participants` | ✅ Верно | Проверка УОТ по ИНН |
| Метод `/cises/info` | ✅ Верно | Проверка кодов маркировки |
| Метод `/dispenser/tasks` | ✅ Верно | Выгрузка данных |

---

## 🔧 ЧТО НУЖНО ИСПРАВИТЬ

### В коде (`test_chz_api.py`):

1. **Заменить `-sfsign` на `-sign`** для аутентификации
2. **Подписывать строку data**, а не её хэш
3. **Использовать текстовый режим** для записи файла (не binary)
4. **Добавить явное указание алгоритма** хэширования

### В документации (`chestny-znak-api.md`):

1. **Добавить раздел про типы подписей** (attached vs detached)
2. **Уточнить команды csptest** для разных сценариев
3. **Добавить примеры** для документов (`/doc`)
4. **Исправить примеры** с `-sfsign` на `-sign` для аутентификации

---

## 📋 ПРАВИЛЬНЫЙ ПОРЯДОК АУТЕНТИФИКАЦИИ

```
┌─────────────────────────────────────────────────────────────────┐
│  1. GET /auth/key                                               │
│     Ответ: {"uuid": "...", "data": "QTWDKMSEFNQRTDAOZAXSYLAHZBXNUD"}
│                                                                 │
│  2. Подписать СТРОКУ data присоединённой подписью              │
│     csptest.exe -sign -cont "<container>" data.txt -base64     │
│     Ответ: base64-строка (присоединённая подпись)              │
│                                                                 │
│  3. POST /auth/simpleSignIn                                    │
│     Запрос: {"uuid": "...", "data": "<base64-подпись из шага 2>"}
│     Ответ: {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}│
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 ТИПЫ ПОДПИСЕЙ: Когда что использовать

| Сценарий | Тип подписи | Команда csptest | Параметр в запросе |
|----------|-------------|-----------------|-------------------|
| **Аутентификация** (`/auth/simpleSignIn`) | Присоединённая (attached) | `-sign -cont "..." file.txt -base64` | `data` = подпись |
| **Документы** (`/doc`) | Откреплённая (detached) | `-sfsign -cont "..." -hash "..." -base64` | `signature` = подпись |
| **Запросы с подписью** | Откреплённая (detached) | `-sfsign -cont "..." -hash "..." -base64` | `X-Signature` = подпись |

---

## 📎 ПРИМЕРЫ КОДА

### ✅ Правильная аутентификация (Python + csptest)

```python
import subprocess
import tempfile
import os

CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
KEY_CONTAINER = "2508151514-781421365746"

def sign_for_auth(data: str) -> str:
    """
    Подпись строки data для аутентификации в ЧЗ
    Используется ПРИСОЕДИНЁННАЯ подпись (attached signature)
    """
    temp_dir = tempfile.gettempdir()
    data_file = os.path.join(temp_dir, "auth_data.txt")
    sig_file = os.path.join(temp_dir, "auth_sig.txt")

    # Сохраняем СТРОКУ (не binary!)
    with open(data_file, 'w', encoding='utf-8') as f:
        f.write(data)  # Просто строка, без BOM

    try:
        # Подписываем присоединённой подписью
        sign_cmd = f'"{CSP_PATH}" -sign -cont "{KEY_CONTAINER}" "{data_file}" -base64 > "{sig_file}" 2>&1'
        result = subprocess.run(sign_cmd, shell=True, capture_output=True, text=True, encoding='cp866')

        if result.returncode != 0:
            raise Exception(f"Ошибка подписи: {result.stdout}")

        # Читаем подпись
        with open(sig_file, 'r', encoding='cp866') as f:
            signature = f.read().strip()

        # Извлекаем только base64
        for line in signature.split('\n'):
            line = line.strip()
            if len(line) > 100 and '=' in line[-3:]:
                return line

        raise Exception("Не удалось извлечь base64 подпись")

    finally:
        for f in [data_file, sig_file]:
            if os.path.exists(f):
                os.unlink(f)

# Использование
data_to_sign = "QTWDKMSEFNQRTDAOZAXSYLAHZBXNUD"
signature = sign_for_auth(data_to_sign)

# Отправляем в ЧЗ
import urllib.request
import json

token_response = urllib.request.urlopen(
    "https://markirovka.crpt.ru/api/v3/true-api/auth/simpleSignIn",
    data=json.dumps({
        "uuid": "33e83139-efab-4dd0-ae1d-6c3876037acd",
        "data": signature
    }).encode('utf-8'),
    headers={"Content-Type": "application/json"},
    timeout=60
)

token = json.loads(token_response.read())['token']
```

---

## 📎 ИСТОЧНИКИ

1. **docs.cr11pt.ru.html** — True API документация (полная версия)
   - Раздел 1.5 "Единая аутентификация" (строки 457-650)
   - Раздел 2.3 "Метод /auth/simpleSignIn" (строки 520-550)

2. **docs.crpt.ru.html** — Основная документация
   - Раздел "Аутентификация и авторизация"

3. **docs_crpt_ru_gismt_Инструкция_по_работе_с_API_.html**
   - Раздел 2.3.2 "Подписание документов УКЭП"
   - Раздел 2.3.2.1 "Подписание присоединённой подписью"

---

**Дата обновления:** 27 марта 2026
**Статус:** Требует исправления в коде и документации
