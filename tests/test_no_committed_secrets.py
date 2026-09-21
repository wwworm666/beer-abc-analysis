"""Барьер против секрета, уехавшего в репозиторий.

Токен бота утекал дважды: сначала как fallback в коде (docs/lessons.md),
затем открытым текстом в docs/guides/TELEGRAM_BOT_GUIDE.md. Оба раза утечку
находил человек, а не проверка. Тест ищет секреты в отслеживаемых файлах
по форме значения, поэтому ловит и те места, где секрет лежит без имени
переменной рядом — в curl-команде, в таблице, в примере вывода.

Поиск идёт через `git grep` по рабочему дереву: это ровно те файлы, которые
уйдут в следующий коммит, и бинарные файлы пропускаются самим git (-I).
Шаблоны записаны так, чтобы не совпадать с собственным текстом этого файла.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Имя, шаблон POSIX ERE и что делать, если проверка сработала.
PATTERNS = [
    ('Токен бота Telegram',
     r'[0-9]{6,12}:[A-Za-z0-9_-]{35}',
     'Значение хранится в .env сервера и в секрете TELEGRAM_BOT_TOKEN '
     '(docs/guides/TELEGRAM_BOT_GUIDE.md). В тексте оставляют плейсхолдер.'),
    ('Токен доступа в формате JWT',
     r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
     'Токены «Честного знака» и подобные живут в кэше вне репозитория. '
     'В примерах подпись сокращают, чтобы значение было заведомо нерабочим.'),
    ('Приватный ключ',
     r'^-----BEGIN [A-Z ]*PRIVATE KEY-----$',
     'Ключи деплоя и сервис-аккаунтов лежат в секретах GitHub и в '
     '/srv/beer/secrets на сервере.'),
    ('Ключ доступа AWS',
     r'AKIA[0-9A-Z]{16}',
     'Ключ нужно отозвать у провайдера: удаления из файла недостаточно.'),
]

# Путь -> причина. Исключение означает «здесь секрет уже лежит и это известно»,
# поэтому каждая строка обязана быть временной и объяснённой. Сейчас пусто и
# должно таким оставаться: единственное исключение (кэш токена ЧЗ в
# chz_test/debug/token.json) снято вместе с самим файлом 21.09.2026.
# Добавлять строку сюда можно только когда секрет уже отозван, а удалить файл
# прямо сейчас нельзя; проверка ниже не даст исключению пережить свой файл.
ALLOWED = {}


def tracked_matches(pattern):
    """Строки отслеживаемых файлов, совпавшие с шаблоном."""
    result = subprocess.run(['git', 'grep', '-I', '-n', '-E', pattern],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'git grep не отработал')
    return [line for line in result.stdout.splitlines() if line]


@unittest.skipUnless((ROOT / '.git').exists(), 'Нужен git-репозиторий')
class CommittedSecretsTests(unittest.TestCase):
    def test_no_secret_values_in_tracked_files(self):
        found = []
        for name, pattern, remedy in PATTERNS:
            for line in tracked_matches(pattern):
                path = line.split(':', 1)[0]
                if path in ALLOWED:
                    continue
                # Само значение не печатаем: сообщение теста попадёт в лог CI.
                found.append(f'{name}: {line.split(":")[0]}:{line.split(":")[1]} — {remedy}')
        self.assertEqual(found, [], 'Секрет в отслеживаемых файлах:\n' + '\n'.join(found))

    def test_allowlist_entries_still_point_at_tracked_files(self):
        """Исключение, пережившее свой файл, прикрывает уже не то, что задумано."""
        for path in ALLOWED:
            tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', path],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(tracked.returncode, 0,
                             f'{path} больше не отслеживается — убрать строку из ALLOWED')


if __name__ == '__main__':
    unittest.main()
