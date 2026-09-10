"""Exercise real OpenSSH parsing using newly generated, disposable test keys."""
from pathlib import Path
import subprocess

import pytest

from prepare_ssh import normalize_private_key, prepare


@pytest.fixture(scope='module')
def credentials(tmp_path_factory):
    key = tmp_path_factory.mktemp('ssh-fixture') / 'key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    return key.read_text(), '139.100.200.92 ' + Path(str(key) + '.pub').read_text()


@pytest.mark.parametrize('formatting', [
    'original', 'crlf', 'literal-newlines', 'one-line', 'no-final-newline',
    'terminal-wrap', 'markdown-boundaries', 'terminal-context',
])
def test_copy_formats_remain_the_same_valid_key(tmp_path, credentials, formatting):
    original, host = credentials
    value = original
    if formatting == 'crlf': value = value.replace('\n', '\r\n')
    if formatting == 'literal-newlines': value = value.replace('\n', '\\n')
    if formatting == 'one-line': value = value.replace('\n', ' ')
    if formatting == 'no-final-newline': value = value.rstrip()
    if formatting == 'terminal-wrap':
        value = '\n'.join(line[:23] + '\n' + line[23:] if not line.startswith('-') else line
                          for line in value.splitlines())
    if formatting == 'markdown-boundaries': value = value.replace('-----BEGIN', '\\-----BEGIN').replace('-----END', '\\-----END')
    if formatting == 'terminal-context': value = 'root@host:~# cat key\n' + value + 'root@host:~# '
    errors, fingerprint = prepare(tmp_path, value, host.replace('\n', '\r\n'))
    assert errors == []
    assert fingerprint.startswith('SHA256:')
    assert (tmp_path / 'key').read_text() == normalize_private_key(original)
    assert (tmp_path / 'key').stat().st_mode & 0o777 == 0o600


def test_reports_both_bad_secrets_without_values(tmp_path):
    errors, fingerprint = prepare(tmp_path, 'PRIVATE_SENTINEL', 'HOST_SENTINEL')
    assert len(errors) == 2 and fingerprint is None
    assert 'BEER_DEPLOY_SSH_KEY' in errors[0]
    assert 'BEER_DEPLOY_KNOWN_HOSTS' in errors[1]
    assert 'SENTINEL' not in '\n'.join(errors)


def test_damaged_key_is_not_repaired_or_accepted(tmp_path, credentials):
    original, host = credentials
    lines = original.splitlines()
    lines[2] = lines[2][8:]  # still decodable base64, but incomplete OpenSSH data
    errors, fingerprint = prepare(tmp_path, '\n'.join(lines), host)
    assert len(errors) == 1 and 'OpenSSH cannot read' in errors[0]
    assert fingerprint is None


def test_revoked_key_is_rejected(tmp_path, credentials, monkeypatch):
    original, host = credentials
    monkeypatch.setattr('prepare_ssh.REVOKED_PUBLIC_KEY', host.split()[2])
    errors, fingerprint = prepare(tmp_path, original, host)
    assert len(errors) == 1 and 'old key disclosed' in errors[0]
    assert fingerprint is None


def test_ambiguous_multiple_keys_are_rejected(tmp_path, credentials):
    original, host = credentials
    errors, _ = prepare(tmp_path, original + original, host)
    assert len(errors) == 1 and 'one complete' in errors[0]
