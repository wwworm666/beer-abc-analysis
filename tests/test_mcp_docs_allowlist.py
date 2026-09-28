"""
Документация, которую видят ИИ-агенты (common_docs_list / common_docs_read), — только явный
список DOCS_ALLOWLIST из core/mcp/tools/common.py (проверка безопасности 2026-09-28).

Совместим с pytest и запускается сам: `py -3 tests/test_mcp_docs_allowlist.py`.

Почему тест: в docs/ лежат и служебные документы — подключения к компьютерам баров,
пароли, токены ботов. Агенту и прод-образу отдаются только документы модулей с формулами.
Проверяется:
(a) DOCS_ALLOWLIST совпадает со строками «!docs/…» в .dockerignore (в образ идёт то же, что
    видит агент), а сама папка docs/ в .dockerignore исключена целиком;
(b) каждый документ из списка существует;
(c) ни в одном документе из списка (и в wiki/content.md) нет паролей и токенов: присваиваний
    пароля с настоящим значением (по-русски и по-английски), `net user`, токенов Telegram-ботов,
    ИНН/ОГРН с цифрами, REMOTE_PASS / IIKO_PASSWORD и других *_PASS/*_TOKEN/*_SECRET с настоящим
    значением. Примеры вида ssh root@<ip> допустимы;
(d) известные служебные документы в список не попали;
плюс сам детектор проверяется на заведомо плохих и заведомо безобидных строках, иначе
«ничего не найдено» ничего бы не доказывало.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mcp.tools import common  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Значения-заглушки: так в документах пишут примеры, это не секреты.
PLACEHOLDER = re.compile(
    r'^(?:<[^>]*>|\$\{?\w+\}?|\*+|\.{2,}|…|x{3,}|your\w*|ваш\w*|пароль|password|secret|changeme|none|null'
    r'|os\.\S*|getenv\S*|config\.\S*|\{\{.*\}\}|\[.*\]|\(.*\))$', re.IGNORECASE)
CREDENTIAL_PATTERNS = (
    # «пароль: …», «password = …» (слово целиком, не MIN_PASSWORD_LEN)
    ('присваивание пароля', re.compile(
        r'(?i)(?<![\w-])(password|passwd|pwd|pass|пароль)(?![\w-])\s*[:=]\s*[`"\']?([^\s`"\'<>,;]+)'), True),
    # REMOTE_PASS=…, IIKO_PASSWORD = "…", TELEGRAM_BOT_TOKEN=…, …_SECRET, …_API_KEY
    ('секрет в переменной окружения', re.compile(
        r'(?<![\w])([A-Z][A-Z0-9_]*(?:PASS|PASSWORD|SECRET|TOKEN|API_KEY))\s*[=:]\s*[`"\']?([^\s`"\'<>,;]+)'),
     True),
    ('команда net user (учётные записи Windows)', re.compile(r'(?i)\bnet\s+user\b'), False),
    ('токен Telegram-бота', re.compile(r'\b\d{8,10}:[A-Za-z0-9_-]{30,}'), False),
    ('ИНН/ОГРН с цифрами', re.compile(r'(?i)(?:ИНН|ОГРН(?:ИП)?)\s*[:№]?\s*\d{10,15}'), False),
)

NOT_FOR_AGENTS = ('docs/CONNECTIVITY.md', 'docs/remote-sync.md', 'docs/CHANGELOG.md', 'docs/chz-stock-integration.md',
                  'docs/auth.md', 'docs/guides/DEPLOYMENT_GUIDE.md', 'docs/guides/TELEGRAM_BOT_GUIDE.md',
                  'docs/technical/CODE_ANALYSIS_COMPLETE.md')


def credential_hits(text: str):
    """[(правило, номер строки, строка)] — подозрения на пароли и токены."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for title, pattern, has_value in CREDENTIAL_PATTERNS:
            for match in pattern.finditer(line):
                if has_value:
                    value = match.group(2).strip('`"\'.,')
                    if len(value) < 4 or PLACEHOLDER.match(value):
                        continue
                hits.append((title, number, line.strip()[:160]))
    return hits


def _dockerignore_docs():
    with open(os.path.join(ROOT, '.dockerignore'), encoding='utf-8') as f:
        lines = [line.strip() for line in f]
    return lines, tuple(line[1:] for line in lines if re.match(r'^!docs/.+\.md$', line))


def test_allowlist_matches_dockerignore():
    lines, shipped = _dockerignore_docs()
    assert 'docs/**' in lines, '.dockerignore должен исключать docs/ целиком, кроме списка'
    assert lines.index('docs/**') < min(lines.index('!' + name) for name in shipped), \
        'исключение docs/** должно стоять до строк-исключений «!docs/…»'
    assert common.DOCS_ALLOWLIST == shipped, (
        'DOCS_ALLOWLIST и строки «!docs/…» в .dockerignore расходятся:\n'
        f'  только в коде: {sorted(set(common.DOCS_ALLOWLIST) - set(shipped))}\n'
        f'  только в .dockerignore: {sorted(set(shipped) - set(common.DOCS_ALLOWLIST))}')
    assert len(set(common.DOCS_ALLOWLIST)) == len(common.DOCS_ALLOWLIST), 'повторы в списке'


def test_every_allowlisted_doc_exists_and_is_served():
    missing = [name for name in common.DOCS_ALLOWLIST if not os.path.isfile(os.path.join(ROOT, *name.split('/')))]
    assert not missing, f'нет файлов из списка: {missing}'
    served = common.docs_whitelist()
    assert set(served) == set(common.DOCS_ALLOWLIST) | {'wiki/content.md'}, 'агенту — ровно список и вики'


def test_no_credentials_in_agent_docs():
    problems = []
    for name in common.DOCS_ALLOWLIST + ('wiki/content.md',):
        with open(os.path.join(ROOT, *name.split('/')), encoding='utf-8', errors='replace') as f:
            for title, number, line in credential_hits(f.read()):
                problems.append(f'{name}:{number}: {title}: {line}')
    assert not problems, 'Похоже на пароли или токены в документах для агентов:\n' + '\n'.join(problems)


def test_service_docs_are_not_allowlisted():
    listed = set(common.DOCS_ALLOWLIST)
    leaked = [name for name in NOT_FOR_AGENTS if name in listed]
    assert not leaked, f'служебные документы в списке для агентов: {leaked}'
    served = common.docs_whitelist()
    assert not [name for name in NOT_FOR_AGENTS if name in served]
    assert not any(n.startswith(('docs/archive/', 'docs/iiko-api/', 'docs/changelog/')) for n in listed)


def test_credential_detector_catches_and_ignores():
    # Все значения ниже ВЫДУМАНЫ (той же формы, что настоящие): настоящим паролям, логинам,
    # ИНН/ОГРН и адресам серверов не место в репозитории даже как примерам (замечание
    # оркестратора 2026-09-28 — прежние примеры повторяли настоящие значения). Адрес в
    # безобидных — из документационного диапазона RFC 5737 (203.0.113.0/24).
    must_catch = (
        'пароль: Vzlom4567',
        'Password = kolobok1999',
        'IIKO_PASSWORD = "Primer2031!"',
        'REMOTE_PASS=bar1999',
        'TELEGRAM_BOT_TOKEN=12345678:abc',
        'net user demouser bar1999',
        'бот: 1234567890:AAH' + 'x' * 32,
        'ИНН 1234567890',
        'ОГРН: 1000000000001',
    )
    for line in must_catch:
        assert credential_hits(line), f'детектор пропустил: {line}'
    must_ignore = (
        'пароль: <пароль>',
        'PASSWORD=***',
        'IIKO_PASSWORD = os.environ.get("IIKO_PASSWORD")',
        'REMOTE_PASS=<из .env>',
        'ssh root@203.0.113.10',
        'MIN_PASSWORD_LEN = 4',
        'Пароль хранится только как хэш.',
        'password: ...',
        'SECRET_KEY=${SECRET_KEY}',
        'ИНН поставщика берётся из накладной',
    )
    for line in must_ignore:
        assert not credential_hits(line), f'ложное срабатывание: {line} -> {credential_hits(line)}'


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
