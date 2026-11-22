"""Build a local-only installer for the existing Kultura OS package from reviewed sources."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / 'plugins/kultura-os'


def build(destination, go, target):
    manifest = json.loads((PLUGIN / 'plugin.json').read_bytes())
    ext = manifest.pop('extensions')['com.openai']
    manifest.pop('$schema')
    # A separate version prevents reuse of the cached portable 1.1.0 package.
    manifest.update(version='1.1.2', interface=ext['interface'], onboardingSkill=ext['onboardingSkill'],
                    skills='./skills/', mcpServers='./.mcp.json')
    with TemporaryDirectory() as tmp:
        binary = Path(tmp) / 'connect'
        subprocess.run([go, 'build', '-trimpath', '-ldflags=-s -w', '-o', str(binary), 'main.go'],
                       cwd=Path(__file__).parent, check=True,
                       env={**os.environ, 'CGO_ENABLED': '0', 'GOOS': target, 'GOARCH': 'amd64'})
        with ZipFile(binary, 'a', ZIP_DEFLATED) as archive:
            market = '.agents/plugins/marketplace.json'
            archive.write(ROOT / market, market)
            base = 'plugins/kultura-os/'
            archive.writestr(base + '.codex-plugin/plugin.json', json.dumps(manifest, ensure_ascii=False))
            servers = json.loads((PLUGIN / 'mcp.json').read_bytes())['mcpServers']
            archive.writestr(base + '.mcp.json', json.dumps({'mcpServers': {
                'kultura_os': {'url': servers['kultura']['url']}}}))
            for folder in ('skills', 'assets'):
                for f in sorted((PLUGIN / folder).rglob('*')):
                    if f.is_file():
                        archive.write(f, base + f.relative_to(PLUGIN).as_posix())
        destination.write_bytes(binary.read_bytes())
        destination.chmod(0o700)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--go', default='go')
    parser.add_argument('--target', choices=('linux', 'windows'), default='windows')
    args = parser.parse_args()
    build(args.destination.resolve(), args.go, args.target)
