"""Validate both Actions secrets without logging their values.

Terminal wrapping, CRLF and Markdown-escaped PEM boundaries are formatting only;
OpenSSH still validates the complete decoded private key before any connection.
"""
import base64
import binascii
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap


HOST = '139.100.200.92'
# Public portion of the initial deployment key disclosed during setup.
# This key must never be used again, even if it remains authorized on the VPS.
REVOKED_PUBLIC_KEY = 'AAAAC3NzaC1lZDI1NTE5AAAAIPIfuMZUsG0J6NhApkIRvWPsvCz0FwgJy45G6sSqWxsz'


def normalize_private_key(value):
    value = value.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r', '')
    blocks = re.findall(
        r'\\?-----BEGIN OPENSSH PRIVATE KEY-----\s*(.*?)\s*\\?-----END OPENSSH PRIVATE KEY-----',
        value, re.S,
    )
    if len(blocks) != 1:
        raise ValueError('Expected one complete OPENSSH PRIVATE KEY block, including BEGIN and END lines.')
    body = re.sub(r'\s+', '', blocks[0])
    try:
        decoded = base64.b64decode(body, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Private key contains missing or invalid characters; upload the original server file.') from None
    if not decoded.startswith(b'openssh-key-v1\0'):
        raise ValueError('The supplied value is not an OpenSSH private key.')
    canonical = base64.b64encode(decoded).decode('ascii')
    return ('-----BEGIN OPENSSH PRIVATE KEY-----\n'
            + '\n'.join(textwrap.wrap(canonical, 70))
            + '\n-----END OPENSSH PRIVATE KEY-----\n')


def write_private(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(value)


def ssh_keygen(*args):
    return subprocess.run(['ssh-keygen', *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=10)


def prepare(directory, private_value, host_value):
    """Return all setup errors together; never include raw secret values."""
    directory = Path(directory)
    errors = []
    fingerprint = None
    try:
        private = normalize_private_key(private_value)
        write_private(directory / 'key', private)
        result = ssh_keygen('-y', '-P', '', '-f', str(directory / 'key'))
        if result.returncode:
            raise ValueError('OpenSSH cannot read the key after normalizing line breaks. The key is truncated, damaged or encrypted; upload the original unencrypted server file.')
        public = result.stdout.split()
        if len(public) < 2 or public[0] != 'ssh-ed25519':
            raise ValueError('Expected the dedicated ed25519 deployment key created by install.sh.')
        if public[1] == REVOKED_PUBLIC_KEY:
            raise ValueError('This is the old key disclosed during setup. Rotate it on the VPS and upload the new file.')
        digest = hashlib.sha256(base64.b64decode(public[1], validate=True)).digest()
        fingerprint = 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')
    except ValueError as exc:
        errors.append('BEER_DEPLOY_SSH_KEY: ' + str(exc))

    hosts = host_value.replace('\r', '').strip() + '\n'
    write_private(directory / 'known_hosts', hosts)
    found = ssh_keygen('-F', HOST, '-f', str(directory / 'known_hosts'))
    valid = ssh_keygen('-l', '-f', str(directory / 'known_hosts'))
    if found.returncode or valid.returncode:
        errors.append('BEER_DEPLOY_KNOWN_HOSTS: no valid host key for ' + HOST + '; upload /var/lib/beer-deploy/known_hosts from the VPS.')
    return errors, fingerprint


def main():
    errors, fingerprint = prepare(sys.argv[1], os.environ.get('DEPLOY_KEY', ''),
                                  os.environ.get('DEPLOY_HOST_KEYS', ''))
    for error in errors:
        print('::error::' + error)
    if errors:
        return 1
    print('Both SSH secrets validated. Deployment public-key fingerprint: ' + fingerprint)
    return 0


if __name__ == '__main__':
    sys.exit(main())
