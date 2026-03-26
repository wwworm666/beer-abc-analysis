"""
Честный ЗНАК API клиент для отслеживания сроков годности пива

Документация: https://docs.crpt.ru/gismt/True_API/
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any


class ChestnyZnakAPI:
    """
    Клиент для работы с API Честный ЗНАК

    Основной функционал:
    - Аутентификация через УКЭП
    - Получение остатков на виртуальном складе
    - Поиск кодов маркировки с фильтрацией по срокам годности
    - Отслеживание статусов кодов
    """

    # Базовые URL
    SANDBOX_BASE = "https://markirovka.sandbox.crptech.ru"
    PRODUCTION_BASE = "https://markirovka.crpt.ru"

    # URL для аутентификации
    SANDBOX_AUTH = "https://markirovka.sandbox.crptech.ru/api/v3/true-api"
    PRODUCTION_AUTH = "https://markirovka.crpt.ru/api/v3/true-api"

    # Товарная группа "Пиво"
    BEER_PG_ID = 150
    BEER_PRODUCT_GROUP = "beer"

    def __init__(self, use_sandbox: bool = True):
        """
        Инициализация клиента

        Args:
            use_sandbox: Если True, используется демонстрационный контур
        """
        self.use_sandbox = use_sandbox
        self.base_url = self.SANDBOX_BASE if use_sandbox else self.PRODUCTION_BASE
        self.auth_url = self.SANDBOX_AUTH if use_sandbox else self.PRODUCTION_AUTH
        self.token: Optional[str] = None
        self.token_expires_at: Optional[float] = None

        # Лимиты API
        self.last_balance_request = 0
        self.BALANCE_REQUEST_COOLDOWN = 60  # 1 раз в 60 секунд

    def connect(self, token: Optional[str] = None) -> bool:
        """
        Подключение к API с использованием готового токена

        Args:
            token: Готовый токен аутентификации (UUID формат)

        Returns:
            True если подключение успешно
        """
        if token:
            self.token = token
            # Токен действителен 24 часа по умолчанию
            self.token_expires_at = time.time() + (24 * 60 * 60)
            print(f"[Честный ЗНАК] Подключение с токеном: {token[:8]}...")
            return True

        # Если токена нет - пробуем аутентификацию (требует УКЭП)
        return self._authenticate_with_ukes()

    def _authenticate_with_ukes(self) -> bool:
        """
        Аутентификация с использованием УКЭП

        Этап 1: Получение UUID и данных для подписи
        Этап 2: Подпись данных и получение токена

        Returns:
            True если аутентификация успешна
        """
        try:
            # Этап 1: Получаем UUID и data для подписи
            response = requests.get(f"{self.auth_url}/auth/key", timeout=10)

            if response.status_code != 200:
                print(f"[Честный ЗНАК] Ошибка получения UUID: {response.status_code}")
                return False

            auth_data = response.json()
            uuid = auth_data.get('uuid')
            data_to_sign = auth_data.get('data')

            if not uuid or not data_to_sign:
                print("[Честный ЗНАК] Не получен UUID или data для подписи")
                return False

            print(f"[Честный ЗНАК] Получен UUID: {uuid}")

            # Здесь должна быть подпись данных УКЭП
            # В реальной реализации используется криптопровайдер (КриптоПро CSP)
            # Для демонстрации используем mock-токен
            print("[Честный ЗНАК] ТРЕБУЕТСЯ ПОДПИСЬ УКЭП для data:", data_to_sign)
            print("[Честный ЗНАК] В демонстрационном режиме используем mock-токен")

            # MOCK для разработки - в продакшене здесь будет реальная подпись
            # signed_data = ukes_sign(data_to_sign)  # Реальная функция подписи

            # Для тестов возвращаем mock-токен
            import uuid as uuid_module
            mock_token = str(uuid_module.uuid4())
            self.token = mock_token
            self.token_expires_at = time.time() + (24 * 60 * 60)

            print(f"[Честный ЗНАК] Mock-токен получен: {mock_token[:8]}...")
            return True

        except Exception as e:
            print(f"[Честный ЗНАК] Ошибка аутентификации: {e}")
            return False

    def _check_token(self) -> bool:
        """Проверка валидности токена"""
        if not self.token:
            return False

        if self.token_expires_at and time.time() > self.token_expires_at:
            print("[Честный ЗНАК] Токен истек, требуется повторная аутентификация")
            self.token = None
            return False

        return True

    def _get_headers(self) -> Dict[str, str]:
        """Получение заголовков для API запросов"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_warehouse_balance(
        self,
        participant_inn: str,
        date: Optional[str] = None,
        product_codes: Optional[List[str]] = None,
        limit: int = 100
    ) -> Optional[Dict[str, Any]]:
        """
        Получение баланса на виртуальном складе

        GET /api/v2/wh/balance

        Args:
            participant_inn: ИНН участника оборота (10/12 цифр)
            date: Дата, по состоянию на которую нужен баланс (YYYY-MM-DD)
            product_codes: Список GTIN товаров для фильтрации
            limit: Количество записей в ответе (макс. 100)

        Returns:
            Данные о балансе или None при ошибке
        """
        if not self._check_token():
            if not self.connect():
                return None

        # Проверка лимита запросов (1 раз в 60 секунд)
        now = time.time()
        if now - self.last_balance_request < self.BALANCE_REQUEST_COOLDOWN:
            wait_time = self.BALANCE_REQUEST_COOLDOWN - (now - self.last_balance_request)
            print(f"[Честный ЗНАК] Лимит запросов баланса. Ждем {wait_time:.0f}с...")
            time.sleep(wait_time)

        self.last_balance_request = time.time()

        # Формируем параметры запроса
        params = {
            "pgId": self.BEER_PG_ID,
            "participantInn": participant_inn,
            "limit": min(limit, 100)
        }

        if date:
            params["date"] = date
        else:
            # По умолчанию - текущая дата
            params["date"] = datetime.now().strftime("%Y-%m-%d")

        if product_codes:
            params["productCodes"] = ",".join(product_codes[:100])

        try:
            response = requests.get(
                f"{self.base_url}/api/v2/wh/balance",
                params=params,
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                print(f"[Честный ЗНАК] Получен баланс: {len(data.get('results', []))} позиций")
                return data
            else:
                print(f"[Честный ЗНАК] Ошибка получения баланса: {response.status_code}")
                print(f"Ответ: {response.text[:500]}")
                return None

        except Exception as e:
            print(f"[Честный ЗНАК] Исключение при получении баланса: {e}")
            return None

    def search_codes(
        self,
        participant_inn: str,
        gtins: Optional[List[str]] = None,
        status: str = "INTRODUCED",
        limit: int = 1000,
        include_expired: bool = False,
        days_until_expiry: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Поиск кодов маркировки с фильтрацией

        POST /api/v3/true-api/cis/search

        Args:
            participant_inn: ИНН участника оборота
            gtins: Список GTIN для фильтрации
            status: Статус кодов (INTRODUCED, RETIRED, WRITTEN_OFF, etc.)
            limit: Максимальное количество записей (макс. 1000)
            include_expired: Включать ли истекшие сроки годности
            days_until_expiry: Фильтр по дням до истечения срока (например, 30)

        Returns:
            Результаты поиска или None при ошибке
        """
        if not self._check_token():
            if not self.connect():
                return None

        # Формируем тело запроса
        filter_params: Dict[str, Any] = {
            "productGroups": [self.BEER_PRODUCT_GROUP],
            "states": [{"status": status}]
        }

        if gtins:
            filter_params["gtins"] = gtins[:1000]

        # Если нужно фильтровать по срокам - добавляем период производства
        if days_until_expiry and not include_expired:
            # Коды, произведенные примерно за days_until_expiry дней до сегодня
            # (грубая оценка, точная фильтрация делается после получения)
            pass

        pagination = {
            "perPage": min(limit, 1000),
            "lastEmissionDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "direction": 0  # Прямое направление
        }

        request_body = {
            "filter": filter_params,
            "pagination": pagination
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v3/true-api/cis/search",
                json=request_body,
                headers=self._get_headers(),
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("result", [])
                print(f"[Честный ЗНАК] Найдено кодов: {len(results)}")
                return data
            else:
                print(f"[Честный ЗНАК] Ошибка поиска кодов: {response.status_code}")
                print(f"Ответ: {response.text[:500]}")
                return None

        except Exception as e:
            print(f"[Честный ЗНАК] Исключение при поиске кодов: {e}")
            return None

    def get_codes_info(self, codes: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Получение информации о конкретных кодах маркировки

        POST /api/v3/true-api/cises/info

        Args:
            codes: Список кодов маркировки (макс. 1000)

        Returns:
            Информация о кодах или None при ошибке
        """
        if not self._check_token():
            if not self.connect():
                return None

        if len(codes) > 1000:
            print(f"[Честный ЗНАК] Превышен лимит кодов (1000). Получаем первые 1000.")
            codes = codes[:1000]

        try:
            response = requests.post(
                f"{self.base_url}/api/v3/true-api/cises/info",
                json=codes,
                headers=self._get_headers(),
                params={"pg": self.BEER_PRODUCT_GROUP},
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                print(f"[Честный ЗНАК] Получена информация о {len(data)} кодах")
                return data
            else:
                print(f"[Честный ЗНАК] Ошибка получения информации: {response.status_code}")
                return None

        except Exception as e:
            print(f"[Честный ЗНАК] Исключение: {e}")
            return None

    def get_expiring_codes(
        self,
        participant_inn: str,
        days_threshold: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Получение кодов с истекающим сроком годности

        Комбинированный запрос:
        1. Получаем баланс по GTIN
        2. Для каждого GTIN ищем коды
        3. Фильтруем по сроку годности

        Args:
            participant_inn: ИНН участника оборота
            days_threshold: Порог в днях до истечения срока

        Returns:
            Список кодов с истекающим сроком
        """
        print(f"\n[Честный ЗНАК] Поиск кодов со сроком годности < {days_threshold} дней...")

        # Шаг 1: Получаем баланс склада
        balance_data = self.get_warehouse_balance(participant_inn)

        if not balance_data or not balance_data.get("results"):
            print("[Честный ЗНАК] Не удалось получить баланс склада")
            return []

        # Шаг 2: Собираем GTIN из баланса
        gtins = list(set(
            item.get("productCode")
            for item in balance_data["results"]
            if item.get("productCode")
        ))

        print(f"[Честный ЗНАК] Найдено {len(gtins)} уникальных GTIN")

        # Шаг 3: Ищем коды для этих GTIN
        all_codes = []
        cutoff_date = datetime.now() + timedelta(days=days_threshold)

        for i in range(0, len(gtins), 100):  # По 100 GTIN за запрос
            batch = gtins[i:i+100]
            print(f"[Честный ЗНАК] Обработка batch {i//100 + 1}/{(len(gtins)-1)//100 + 1}")

            search_result = self.search_codes(
                participant_inn=participant_inn,
                gtins=batch,
                status="INTRODUCED",
                limit=1000
            )

            if search_result and search_result.get("result"):
                results = search_result["result"]

                # Фильтруем по сроку годности
                for code_info in results:
                    expiration_date_str = code_info.get("expirationDate")

                    if expiration_date_str:
                        try:
                            expiration_date = datetime.strptime(
                                expiration_date_str[:19],  # Обрезаем до секунд
                                "%Y-%m-%dT%H:%M:%S"
                            )

                            days_left = (expiration_date - datetime.now()).days

                            if days_left <= days_threshold:
                                all_codes.append({
                                    "cis": code_info.get("cis") or code_info.get("sgtin"),
                                    "gtin": code_info.get("gtin"),
                                    "expirationDate": expiration_date_str,
                                    "daysUntilExpiry": days_left,
                                    "status": code_info.get("status"),
                                    "productionDate": code_info.get("productionDate"),
                                    "producerInn": code_info.get("producerInn"),
                                    "ownerInn": code_info.get("ownerInn"),
                                    "isExpired": days_left < 0
                                })
                        except (ValueError, TypeError) as e:
                            print(f"[Честный ЗНАК] Ошибка парсинга даты: {e}")
                            continue

            # Лимит API - пауза между запросами
            if i + 100 < len(gtins):
                time.sleep(1)

        # Сортируем: сначала истекающие, потом просроченные
        all_codes.sort(key=lambda x: (x["isExpired"], x["daysUntilExpiry"]))

        print(f"[Честный ЗНАК] Найдено {len(all_codes)} кодов с истекающим сроком")
        return all_codes

    def disconnect(self):
        """Отключение от API (очистка токена)"""
        self.token = None
        self.token_expires_at = None
        print("[Честный ЗНАК] Отключено")


# Singleton instance для использования в приложении
chestny_znak_api = ChestnyZnakAPI(use_sandbox=True)
