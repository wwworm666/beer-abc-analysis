"""The clipboard channel must stay empty on any failed server prerequisite."""
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import check_server


@pytest.mark.parametrize('failure', [None, 'git', 'https', 'authorization'])
def test_clipboard_is_emitted_only_after_all_checks_pass(tmp_path, monkeypatch, capsys, failure):
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    (repo / 'scripts/deploy').mkdir(parents=True)
    (repo / '.env').write_text('TEST_ONLY=1')
    (repo / 'docker-compose.yml').write_text('services: {}')
    (repo / 'scripts/deploy/beer-deploy.sh').write_text('#!/bin/bash\n')
    installed = tmp_path / 'installed'
    installed.write_bytes((repo / 'scripts/deploy/beer-deploy.sh').read_bytes())
    key = tmp_path / 'key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    public = Path(str(key) + '.pub').read_text()
    hosts = tmp_path / 'known_hosts'
    hosts.write_text('139.100.200.92 ' + public)
    authorized = tmp_path / 'authorized_keys'
    authorized.write_text('' if failure == 'authorization' else 'restrict,command="/usr/local/sbin/beer-deploy" ' + public)
    mapping = {
        '/usr/local/sbin/beer-deploy': installed,
        '/root/.ssh/beer_github_actions': key,
        '/var/lib/beer-deploy/known_hosts': hosts,
        '/root/.ssh/authorized_keys': authorized,
    }
    monkeypatch.setattr(check_server, 'REPO', repo)
    monkeypatch.setattr(check_server, 'Path', lambda value: mapping.get(str(value), Path(value)))
    monkeypatch.setattr(check_server.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(check_server.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(check_server.shutil, 'which', lambda name: '/test/' + name)
    monkeypatch.setattr(check_server.sys, 'argv', ['check_server.py', '--copy-key'])
    real_run = check_server.run

    def fake_git(*args):
        output = ''
        if args[0] == 'symbolic-ref': output = 'main\n'
        if args[0] == 'status' and failure == 'git': output = ' M app.py\n'
        if args[0] == 'ls-files': output = 'docker-compose.yml\0'
        return subprocess.CompletedProcess(args, 0, output, '')

    def fake_run(*args, **kwargs):
        if args[0] == 'ssh-keygen': return real_run(*args, **kwargs)
        code, output, error = 0, '', ''
        if args[0] == 'docker' and args[1] == 'inspect':
            output = 'sha256:test' if '{{.Image}}' in args else 'true\n'
        if args[0] == 'curl':
            output = '503' if failure == 'https' and '--resolve' in args else '200'
        if args[0] == 'ssh':
            code, error = 1, 'Only deploy <40-character commit SHA> is permitted.'
        return subprocess.CompletedProcess(args, code, output, error)

    monkeypatch.setattr(check_server, 'git', fake_git)
    monkeypatch.setattr(check_server, 'run', fake_run)
    result = check_server.main()
    output = capsys.readouterr()
    assert 'SSH login and forced-command boundary' in output.err  # checks continue after failures
    assert 'PRIVATE KEY' not in output.err
    if failure:
        assert result == 1 and output.out == ''
        assert 'FAILED:' in output.err
    else:
        assert result == 0 and output.out == key.read_text()
        assert 'READY:' in output.err
