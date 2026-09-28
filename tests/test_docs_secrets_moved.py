# -*- coding: utf-8 -*-
"""
Секреты вынесены из служебных документов (2026-09-28, контракт «доделать интеграцию», 7.8).

docs/CONNECTIVITY.md, docs/remote-sync.md и docs/technical/CODE_ANALYSIS_COMPLETE.md
содержали пароли учёток компьютеров баров, пароль iiko API и ИНН / ОГРНИП владельца
сертификата; chz_test/README.md — пароль sshuser, docs/archive/PROJECT_OVERVIEW.md —
действующие логин и пароль iiko API. Значения перенесены в локальный
secrets/LOCAL_NOTES.md (в .gitignore и .dockerignore), в документах — ссылка на него.

Что проверяется:
- в трёх документах нет присваиваний пароля или секрета с настоящим значением, ИНН /
  ОГРН с цифрами, токенов Telegram-ботов, `net user <имя> <пароль>` с настоящим паролем;
- каждый документ ссылается на secrets/LOCAL_NOTES.md;
- secrets/ исключён из git и из образа;
- если локальный secrets/LOCAL_NOTES.md есть (машина владельца, не CI): ни одно значение
  в обратных кавычках из разделов этих документов в них не встречается.

Детектор — того же вида, что в tests/test_mcp_docs_allowlist.py (там проверяются
документы для агентов, эти три туда не входят). Запуск:
py -3 -m pytest -q tests/test_docs_secrets_moved.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Три документа контракта + (2026-09-28, поручение оркестратора) README папки chz_test и
# архивный обзор проекта, где лежали те же пароли и действующий логин/пароль iiko API.
DOCS = ('docs/CONNECTIVITY.md', 'docs/remote-sync.md', 'docs/technical/CODE_ANALYSIS_COMPLETE.md',
        'chz_test/README.md', 'docs/archive/PROJECT_OVERVIEW.md')
NOTES = os.path.join(ROOT, 'secrets', 'LOCAL_NOTES.md')
# Разделы заметок, куда вынесены значения этих документов.
NOTE_SECTIONS = ('CONNECTIVITY', 'REMOTE_SYNC', 'CODE_ANALYSIS_COMPLETE', 'CHZ_TEST_README',
                 'PROJECT_OVERVIEW')
# Значения короче — не секреты (номера строк, «1» и т. п.) и дали бы ложные совпадения.
MIN_SECRET_LEN = 6

PLACEHOLDER = re.compile(
    r'^(?:<[^>]*>|\$\{?\w+\}?|\*+|\.{2,}|…|x{3,}|your\w*|ваш\w*|пароль|password|secret|none|null'
    r'|os\.\S*|getenv\S*|config\.\S*|/add|/delete)$', re.IGNORECASE)
VALUE_PATTERNS = (
    re.compile(r'(?i)(?<![\w-])(password|passwd|pwd|pass|пароль)(?![\w-])\s*[:=]\s*[`"\']?'
               r'([^\s`"\'<>,;]+)'),
    re.compile(r'(?<![\w])([A-Z][A-Z0-9_]*(?:PASS|PASSWORD|SECRET|TOKEN|API_KEY))\s*[=:]\s*[`"\']?'
               r'([^\s`"\'<>,;]+)'),
    # Команда `net user <имя> <пароль>`: пароль — последнее слово строки (в прозе вроде
    # «net user подтверждает, последний вход …» после второго слова текст продолжается).
    re.compile(r'(?i)\bnet\s+user\s+(\S+)\s+([^\s`]+)`?\s*$'),
)
BARE_PATTERNS = (
    re.compile(r'\b\d{8,10}:[A-Za-z0-9_-]{30,}'),                        # токен бота
    re.compile(r'(?i)(?:ИНН|ОГРН(?:ИП)?|ORGN|OGRN)\s*[:№]?\s*`?\d{10,15}'),  # ИНН/ОГРН
)


def _read(rel):
    with open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8') as f:
        return f.read()


def _hits(text):
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in VALUE_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(2).strip('`"\'.,')
                if len(value) >= 4 and not PLACEHOLDER.match(value):
                    hits.append((number, line.strip()[:120]))
        for pattern in BARE_PATTERNS:
            if pattern.search(line):
                hits.append((number, line.strip()[:120]))
    return hits


def test_docs_have_no_credentials():
    problems = []
    for rel in DOCS:
        problems += [rel + ':' + str(n) + ': ' + line for n, line in _hits(_read(rel))]
    assert not problems, 'похоже на секрет в документе:\n' + '\n'.join(problems)


def test_docs_point_to_local_notes():
    for rel in DOCS:
        assert 'secrets/LOCAL_NOTES.md' in _read(rel), rel


def test_secrets_dir_ignored_by_git_and_docker():
    for name in ('.gitignore', '.dockerignore'):
        lines = [line.strip() for line in _read(name).splitlines()]
        assert 'secrets/' in lines, name


def _note_values():
    """Значения в обратных кавычках из разделов NOTE_SECTIONS локальных заметок."""
    with open(NOTES, encoding='utf-8') as f:
        text = f.read()
    values = set()
    for section in re.split(r'(?m)^## ', text)[1:]:
        title = section.splitlines()[0].strip()
        if title in NOTE_SECTIONS:
            values |= {v for v in re.findall(r'`([^`]+)`', section) if len(v) >= MIN_SECRET_LEN}
    return values


def test_moved_values_absent_locally():
    if not os.path.exists(NOTES):
        return  # CI и чужие машины: заметок нет, проверка по шаблонам выше
    values = _note_values()
    assert values, 'в заметках нет значений разделов ' + ', '.join(NOTE_SECTIONS)
    leaked = [rel for rel in DOCS for value in values if value in _read(rel)]
    assert not leaked, 'значение из заметок снова в документе: ' + ', '.join(sorted(set(leaked)))


def test_detector_catches_and_ignores():
    for line in ('пароль: Qwerty123', 'IIKO_PASSWORD = "Abc12345!"', 'net user sshuser Secret99',
                 'ИНН 7801234567', 'ORGN 1027800000000', 'бот 1234567890:' + 'A' * 32):
        assert _hits(line), line
    for line in ('IIKO_PASSWORD = "<пароль iiko API>"', 'net user sshuser <ПАРОЛЬ>',
                 'net user sshuser /add', 'пароль — значение в локальном secrets/LOCAL_NOTES.md',
                 'Учётка активна (net user подтверждает), последний вход 05.04.2026 20:16:33',
                 'IIKO_PASSWORD = os.environ.get("IIKO_PASSWORD")', '| sshuser | пароль sshuser | OK |'):
        assert not _hits(line), line


if __name__ == '__main__':
    import sys
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok   ' + name)
            except AssertionError as error:
                failed += 1
                print('FAIL ' + name + ': ' + str(error))
    sys.exit(1 if failed else 0)
