"""gunicorn.conf.py: при старте приложение отдаёт Caddyfile в admin API Caddy."""
import fnmatch
import importlib.util
import io
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_conf():
    spec = importlib.util.spec_from_file_location('gunicorn_conf', ROOT / 'gunicorn.conf.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Log:
    def __init__(self):
        self.records = []

    def info(self, msg, *args):
        self.records.append(('info', msg % args))

    def warning(self, msg, *args):
        self.records.append(('warning', msg % args))


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, error=None):
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return Response()


def test_posts_repo_caddyfile_to_local_admin_api():
    conf = load_conf()
    opener, log = Opener(), Log()
    assert conf.apply_caddyfile(log, opener) is True
    request, timeout = opener.requests[0]
    assert request.full_url == 'http://127.0.0.1:2019/load'
    assert request.get_method() == 'POST'
    assert request.get_header('Content-type') == 'text/caddyfile'
    assert request.data == (ROOT / 'Caddyfile').read_bytes()
    assert timeout == conf.CADDY_TIMEOUT
    assert log.records == [('info', 'Caddyfile передан в Caddy: HTTP 200')]


def test_rejected_config_is_logged_and_does_not_raise():
    conf = load_conf()
    body = io.BytesIO(b'{"error":"adapting config using caddyfile: unknown directive"}')
    error = urllib.error.HTTPError(conf.CADDY_LOAD_URL, 400, 'Bad Request', {}, body)
    log = Log()
    assert conf.apply_caddyfile(log, Opener(error)) is False
    level, text = log.records[0]
    assert level == 'warning'
    assert 'HTTP 400' in text and 'unknown directive' in text


def test_unreachable_caddy_does_not_raise():
    conf = load_conf()
    log = Log()
    assert conf.apply_caddyfile(log, Opener(ConnectionRefusedError(111, 'refused'))) is False
    assert log.records[0][0] == 'warning'


def test_only_gunicorn_hook_is_exposed_as_setting():
    """Gunicorn берёт из файла имена своих настроек; лишняя совпавшая — тихо меняет запуск."""
    conf = load_conf()
    public = {name for name in vars(conf) if not name.startswith('_') and name.islower()}
    assert public - {'urllib', 'Path', 'apply_caddyfile'} == {'when_ready'}


def test_dockerignore_keeps_hook_inputs_in_image():
    """2026-10-27: Caddyfile стоял в .dockerignore, хуку нечего было отдать, Caddy не менялся."""
    patterns = [line.strip() for line in (ROOT / '.dockerignore').read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#')]
    for name in ('Caddyfile', 'gunicorn.conf.py'):
        assert not any(fnmatch.fnmatch(name, p) for p in patterns), name


def test_caddyfile_keeps_main_domain_for_deploy_check():
    """beer-deploy проверяет https://beerkultura.ru/login через Caddy: без домена релиз откатится."""
    lines = (ROOT / 'Caddyfile').read_text(encoding='utf-8').splitlines()
    site_lines = [line for line in lines if line.endswith('{') and not line[0].isspace()
                  and not line.startswith(('#', '{'))]
    hosts = {h.strip() for line in site_lines for h in line.rstrip('{ ').split(',')}
    assert 'beerkultura.ru' in hosts
    assert '139-100-200-92.sslip.io' in hosts


def test_internal_tls_only_on_emergency_address():
    """tls internal в общем блоке сменил бы публичный сертификат beerkultura.ru самоподписанным."""
    blocks = (ROOT / 'Caddyfile').read_text(encoding='utf-8').split('\n}\n')
    internal = [b for b in blocks if 'tls internal' in b]
    assert len(internal) == 1
    site_line = [line for line in internal[0].splitlines() if line.endswith('{')][0]
    assert site_line == '139-100-200-92.nip.io {'


def test_caddyfile_sets_acme_email_for_zerossl_fallback():
    """Без email Caddy (v2.8+) не берёт ZeroSSL, а Let's Encrypt не выдаёт sslip.io."""
    text = (ROOT / 'Caddyfile').read_text(encoding='utf-8')
    global_block = text[text.index('\n{\n') + 3:text.index('\n}\n')]
    assert [line.split() for line in global_block.splitlines()] == [['email', 'ssl@beerkultura.ru']]
