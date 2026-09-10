"""Collect deployment prerequisites in one pass; stdout is reserved for copy-key.

Run through an authenticated administrator SSH session. No deployment, Docker
restart, application data edits or private-key logging occurs in this checker.
"""
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

from prepare_ssh import HOST, REVOKED_PUBLIC_KEY, prepare


REPO = Path('/opt/beer')


def run(*args, timeout=30):
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, '', '')


def git(*args):
    return run('runuser', '-u', 'deploy', '--', 'git', '-C', str(REPO), *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy-key', action='store_true',
                        help='After all checks pass, emit ONLY the private key on stdout for Set-Clipboard.')
    args = parser.parse_args()
    if os.geteuid() != 0:
        print('FAIL: run this checker as root on the VPS.', file=sys.stderr)
        return 1
    errors = []

    def check(label, ok, detail=''):
        print(('OK: ' if ok else 'FAIL: ') + label + (': ' + detail if detail else ''), file=sys.stderr)
        if not ok:
            errors.append(label)
        return ok

    for tool in ('git', 'docker', 'runuser', 'curl', 'flock', 'timeout', 'ssh', 'ssh-keygen'):
        check('Command ' + tool, shutil.which(tool) is not None)
    for filename in ('.env', 'docker-compose.yml'):
        check('Server file ' + filename, (REPO / filename).is_file())
    check('Installed deployment script', Path('/usr/local/sbin/beer-deploy').is_file())
    syntax = run('bash', '-n', '/usr/local/sbin/beer-deploy')
    check('Deployment script syntax', syntax.returncode == 0)
    installed = Path('/usr/local/sbin/beer-deploy')
    if installed.is_file():
        check('Installed script matches repository', installed.read_bytes() == (REPO / 'scripts/deploy/beer-deploy.sh').read_bytes())

    branch = git('symbolic-ref', '--short', 'HEAD')
    check('Server branch main', branch.returncode == 0 and branch.stdout.strip() == 'main')
    status = git('status', '--porcelain')
    check('Clean Git checkout', status.returncode == 0 and not status.stdout.strip(),
          'Run git status --short on the VPS if this check fails.')
    files = git('ls-files', '-z')
    try:
        uid = pwd.getpwnam('deploy').pw_uid
        wrong_owner = sum((REPO / name).stat().st_uid != uid for name in files.stdout.split('\0') if name)
        owned = files.returncode == 0 and wrong_owner == 0 and (REPO / '.git').stat().st_uid == uid
    except (OSError, KeyError):
        owned = False
    check('Repository files owned by deploy', owned)
    fetched = git('fetch', '--no-tags', 'origin', 'main')
    check('GitHub access as deploy', fetched.returncode == 0)
    if fetched.returncode == 0:
        check('Fast-forward release', git('merge-base', '--is-ancestor', 'HEAD', 'FETCH_HEAD').returncode == 0)

    compose = run('docker', 'compose', '--project-directory', str(REPO), '-f', str(REPO / 'docker-compose.yml'), 'config', '--quiet')
    check('Docker Compose configuration and .env', compose.returncode == 0)
    for container in ('beer-app', 'beer-caddy'):
        state = run('docker', 'inspect', '--format', '{{.State.Running}}', container)
        check(container + ' running', state.returncode == 0 and state.stdout.strip() == 'true')
    image = run('docker', 'inspect', '--format', '{{.Image}}', 'beer-app')
    if image.returncode == 0 and fetched.returncode == 0:
        revision = run('docker', 'image', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', image.stdout.strip()).stdout.strip()
        base = revision if len(revision) == 40 and all(c in '0123456789abcdef' for c in revision) else 'HEAD'
        changed = git('diff', '--name-only', base, 'FETCH_HEAD', '--', 'data/')
        check('No pending mounted-data changes', changed.returncode == 0 and not changed.stdout.strip())
    for label, curl_args in (
        ('Application HTTP /login', ['http://127.0.0.1:10000/login']),
        ('Caddy HTTPS /login', ['--resolve', 'beerkultura.ru:443:127.0.0.1', 'https://beerkultura.ru/login']),
    ):
        response = run('curl', '-sS', '--max-time', '10', '-o', '/dev/null', '-w', '%{http_code}', *curl_args)
        check(label, response.returncode == 0 and response.stdout == '200')
    if REPO.exists():
        print('INFO: free disk space: %.1f GiB' % (shutil.disk_usage(REPO).free / 1024**3), file=sys.stderr)

    key_file = Path('/root/.ssh/beer_github_actions')
    host_file = Path('/var/lib/beer-deploy/known_hosts')
    canonical = None
    with tempfile.TemporaryDirectory(prefix='beer-key-check-') as directory:
        try:
            key_errors, fingerprint = prepare(directory, key_file.read_text(), host_file.read_text())
        except OSError:
            key_errors, fingerprint = ['Server key files could not be read; run install.sh.'], None
        check('Both original SSH files valid', not key_errors, '; '.join(key_errors))
        if key_file.is_file():
            check('Private key permissions', key_file.stat().st_uid == 0 and key_file.stat().st_mode & 0o077 == 0)
        authorized_file = Path('/root/.ssh/authorized_keys')
        authorized = authorized_file.read_text() if authorized_file.is_file() else ''
        check('Disclosed initial key revoked', not any(REVOKED_PUBLIC_KEY in line for line in authorized.splitlines() if not line.lstrip().startswith('#')))
        if not key_errors:
            key = str(Path(directory) / 'key')
            public = run('ssh-keygen', '-y', '-P', '', '-f', key).stdout.split()
            prefix = 'restrict,command="/usr/local/sbin/beer-deploy" ' + ' '.join(public[:2])
            check('Restricted key in authorized_keys', any(line == prefix or line.startswith(prefix + ' ') for line in authorized.splitlines()))
            print('INFO: deployment public-key fingerprint: ' + fingerprint, file=sys.stderr)
            # A deliberately disallowed command checks SSH authentication and
            # the forced-command boundary without running a deployment.
            probe = run('ssh', '-T', '-i', key, '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                        '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=' + HOST,
                        '-o', 'UserKnownHostsFile=' + str(Path(directory) / 'known_hosts'),
                        '-o', 'ConnectTimeout=5', 'root@127.0.0.1', 'check', timeout=10)
            check('SSH login and forced-command boundary', probe.returncode == 1 and 'Only deploy <40-character commit SHA> is permitted.' in probe.stderr)
            canonical = Path(key).read_text()

    if errors:
        print('FAILED: %d checks. No private key was sent to the clipboard. Send the OK/FAIL report for diagnosis.' % len(errors), file=sys.stderr)
        return 1
    print('READY: all server checks passed. Paste the copied key into BEER_DEPLOY_SSH_KEY.', file=sys.stderr)
    if args.copy_key:
        sys.stdout.write(canonical)
    return 0


if __name__ == '__main__':
    sys.exit(main())
