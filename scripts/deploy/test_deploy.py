"""Deployment transaction tests: real Git repositories, simulated Docker/HTTP.

The script copy only substitutes server paths and the root check, so these tests
cannot operate on a real VPS. Docker and curl are deliberately unavailable here.
"""
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest


SOURCE = Path(__file__).with_name('beer-deploy.sh')
MOCK = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
cmd = Path(sys.argv[0]).name
args = sys.argv[1:]
if cmd == 'runuser':
    sys.exit(subprocess.call(args[3:]))
if cmd == 'timeout':
    sys.exit(subprocess.call(args[1:]))
if cmd == 'sleep':
    sys.exit(0)
path = Path(os.environ['BEER_TEST_STATE'])
s = json.loads(path.read_text())
def save(): path.write_text(json.dumps(s))
def output(value): print(value); save(); sys.exit(0)
def image(ref): return s['images'].get(ref, ref)
s['calls'].append([cmd] + args)
if cmd == 'curl':
    s['probes'] += 1
    if s['container'] == 'sha256:new':
        output('503' if s['mode'] == 'health-failure' or s['probes'] < 3 else '200')
    output('200')
if cmd != 'docker': raise AssertionError(cmd)
if args[:1] == ['inspect']:
    if args[2] == '{{.Image}}': output(s['container'])
    if args[2] == '{{.State.Running}} {{.State.Restarting}}': output('true false')
if args[:2] == ['image', 'inspect']:
    ref = image(args[-1])
    if args[3] == '{{.Id}}': output(ref)
    output(s['old_sha'] if ref == 'sha256:old' else ('wrong' if s['mode'] == 'bad-label' else s['target']))
if args[:2] == ['image', 'tag']:
    s['images'][args[3]] = image(args[2]); save(); sys.exit(0)
if args[:1] == ['compose']:
    if 'build' in args:
        s['images']['beer-abc-analysis:latest'] = 'sha256:new'
        save(); sys.exit(1 if s['mode'] == 'build-failure' else 0)
    if 'up' in args:
        s['container'] = s['images']['beer-abc-analysis:latest']
        s['started'].append(s['container']); save(); sys.exit(0)
if args[:1] == ['logs']: output('Application diagnostics stay on the VPS.')
raise AssertionError(args)
'''


def git(path, *args):
    return subprocess.check_output(
        ['git', '-C', str(path), '-c', 'user.name=Deploy Test',
         '-c', 'user.email=deploy-test@example.invalid', *args],
        text=True, stderr=subprocess.DEVNULL,
    ).strip()


@pytest.fixture
def deployment(tmp_path):
    remote, author, server = (tmp_path / n for n in ('remote', 'author', 'server'))
    remote.mkdir(); author.mkdir()
    git(remote, 'init', '--bare', '--initial-branch=main')
    git(author, 'init', '--initial-branch=main')
    (author / '.gitignore').write_text('.env\n')
    (author / 'docker-compose.yml').write_text('services:\n  app:\n    image: beer-abc-analysis:latest\n')
    (author / 'app.txt').write_text('old')
    git(author, 'add', '.'); git(author, 'commit', '-m', 'Old release')
    old = git(author, 'rev-parse', 'HEAD')
    git(author, 'remote', 'add', 'origin', str(remote))
    git(author, 'push', '-u', 'origin', 'main')
    git(tmp_path, 'clone', str(remote), str(server))
    (server / '.env').write_text('TEST_ONLY=1\n')
    (author / 'app.txt').write_text('new')
    git(author, 'commit', '-am', 'New release')
    target = git(author, 'rev-parse', 'HEAD')
    git(author, 'push')
    mock_state = tmp_path / 'mock.json'
    mock_state.write_text(json.dumps({
        'mode': 'success', 'container': 'sha256:old', 'old_sha': old,
        'target': target, 'probes': 0, 'calls': [], 'started': [],
        'images': {'beer-abc-analysis:latest': 'sha256:old'},
    }))
    bins = tmp_path / 'bin'; bins.mkdir()
    for command in ('runuser', 'timeout', 'sleep', 'docker', 'curl'):
        executable = bins / command
        executable.write_text(MOCK)
        executable.chmod(0o755)
    state = tmp_path / 'releases'
    lock = tmp_path / 'deploy.lock'
    script = tmp_path / 'deploy.sh'
    code = SOURCE.read_text()
    code = code.replace('export PATH=/usr/sbin:/usr/bin:/sbin:/bin',
                        'export PATH=' + shlex.quote(str(bins)) + ':/usr/bin:/bin')
    for name, value in [('REPO', server), ('STATE', state), ('LOCK', lock)]:
        import re
        code = re.sub(r'^readonly ' + name + r'=.*$',
                      'readonly ' + name + '=' + shlex.quote(str(value)), code, flags=re.M)
    code = code.replace('[[ $EUID -eq 0 ]]', 'true')
    script.write_text(code)

    class Deployment:
        def read(self): return json.loads(mock_state.read_text())
        def mode(self, name):
            data = self.read(); data['mode'] = name; mock_state.write_text(json.dumps(data))
        def run(self, command=None):
            env = {**os.environ, 'BEER_TEST_STATE': str(mock_state),
                   'SSH_ORIGINAL_COMMAND': command if command is not None else 'deploy ' + target}
            return subprocess.run(['bash', str(script)], env=env, text=True,
                                  capture_output=True, timeout=15)
    result = Deployment()
    result.server, result.author, result.state = server, author, state
    result.target, result.old, result.lock = target, old, lock
    return result


def test_success_runs_exact_commit_and_checks_new_container(deployment):
    run = deployment.run()
    assert run.returncode == 0, run.stdout + run.stderr
    data = deployment.read()
    assert data['container'] == 'sha256:new'
    assert data['images']['beer-abc-analysis:previous'] == 'sha256:old'
    assert data['probes'] >= 8  # initial 503 responses must not count as success
    assert git(deployment.server, 'rev-parse', 'HEAD') == deployment.target
    assert (deployment.state / 'deployed-revision').read_text().strip() == deployment.target


@pytest.mark.parametrize('command', ['bash', 'deploy main', 'deploy ' + 'a' * 40 + '; id',
                                     'deploy ' + 'A' * 40, 'deploy ' + 'a' * 40 + '\nid'])
def test_forced_key_rejects_other_commands(deployment, command):
    assert deployment.run(command).returncode != 0
    assert deployment.read()['calls'] == []
    assert git(deployment.server, 'rev-parse', 'HEAD') == deployment.old


def test_outdated_run_cannot_roll_back_main(deployment):
    run = deployment.run('deploy ' + deployment.old)
    assert run.returncode != 0 and 'outdated' in run.stderr
    assert deployment.read()['calls'] == []


def test_local_changes_stop_deployment(deployment):
    (deployment.server / 'app.txt').write_text('manual edit')
    run = deployment.run()
    assert run.returncode != 0 and 'local changes' in run.stderr
    assert (deployment.server / 'app.txt').read_text() == 'manual edit'
    assert deployment.read()['calls'] == []


@pytest.mark.parametrize('mode', ['build-failure', 'bad-label'])
def test_build_failure_keeps_old_container_and_restores_latest_tag(deployment, mode):
    deployment.mode(mode)
    run = deployment.run()
    assert run.returncode != 0
    data = deployment.read()
    assert data['container'] == data['images']['beer-abc-analysis:latest'] == 'sha256:old'
    assert data['started'] == []


def test_unhealthy_release_restores_previous_image_and_reports_failure(deployment):
    deployment.mode('health-failure')
    run = deployment.run()
    assert run.returncode != 0 and 'Previous application image restored' in run.stderr
    data = deployment.read()
    assert data['started'] == ['sha256:new', 'sha256:old']
    assert data['container'] == data['images']['beer-abc-analysis:latest'] == 'sha256:old'
    assert not (deployment.state / 'deployed-revision').exists()
    assert git(deployment.server, 'rev-parse', 'HEAD') == deployment.target


def test_lock_blocks_overlapping_deployment(deployment):
    with deployment.lock.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = deployment.run()
    assert run.returncode != 0 and 'already running' in run.stderr
    assert deployment.read()['calls'] == []


def test_retry_rollback_keeps_configuration_of_running_image(deployment):
    original = (deployment.server / 'docker-compose.yml').read_text()
    (deployment.author / 'docker-compose.yml').write_text(original + '# new configuration\n')
    git(deployment.author, 'commit', '-am', 'Change Compose configuration')
    git(deployment.author, 'push')
    target = git(deployment.author, 'rev-parse', 'HEAD')
    deployment.mode('build-failure')
    # The first failure advances checkout but leaves the previous image running.
    for _ in range(2):
        run = deployment.run('deploy ' + target)
        assert run.returncode != 0
        assert git(deployment.server, 'rev-parse', 'HEAD') == target
    snapshots = list(deployment.state.glob('release-*/compose-before.yml'))
    assert len(snapshots) == 2
    assert all(snapshot.read_text() == original for snapshot in snapshots)


def test_changed_mounted_data_requires_manual_handling(deployment):
    (deployment.author / 'data').mkdir()
    (deployment.author / 'data' / 'targets.json').write_text('{}')
    git(deployment.author, 'add', '.'); git(deployment.author, 'commit', '-m', 'Data change')
    git(deployment.author, 'push')
    target = git(deployment.author, 'rev-parse', 'HEAD')
    run = deployment.run('deploy ' + target)
    assert run.returncode != 0 and 'data/' in run.stderr
    assert deployment.read()['started'] == []
    assert git(deployment.server, 'rev-parse', 'HEAD') == deployment.old
