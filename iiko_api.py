import hashlib
import requests
from config import IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD

class IikoAPI:
    """Класс для работы с iiko API"""
    
    def __init__(self):
        self.base_url = IIKO_BASE_URL
        self.login = IIKO_LOGIN
        self.password = IIKO_PASSWORD
        self.token = None
    
    def get_sha1_hash(self, text):
        """Получить SHA-1 хэш от текста"""
        return hashlib.sha1(text.encode()).hexdigest()
    
    def authenticate(self):
        """Получить токен авторизации"""
        password_hash = self.get_sha1_hash(self.password)
        
        url = f"{self.base_url}/auth"
        params = {
            "login": self.login,
            "pass": password_hash
        }
        
        print(f"🔑 Подключаюсь к {self.base_url}...")
        
        try:
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                # Токен приходит в формате <string>токен</string>
                self.token = response.text.strip().replace("<string>", "").replace("</string>", "")
                print(f"✅ Успешно получен токен: {self.token[:20]}...")
                return True
            else:
                print(f"❌ Ошибка авторизации: {response.status_code}")
                print(f"   Ответ сервера: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
    
    def logout(self):
        """Освободить токен (освободить слот лицензии)"""
        if not self.token:
            return
        
        url = f"{self.base_url}/logout"
        params = {"key": self.token}
        
        try:
            requests.get(url, params=params)
            print("👋 Токен освобожден")
        except:
            pass

# Тестовый запуск
if __name__ == "__main__":
    print("🍺 Тестируем подключение к iiko API\n")
    
    api = IikoAPI()
    
    if api.authenticate():
        print("\n🎉 Все работает! Можем переходить к получению данных.")
        api.logout()
    else:
        print("\n❌ Не удалось подключиться. Проверьте настройки в config.py")