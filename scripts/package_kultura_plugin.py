"""Build the publisher upload for the OpenAI Plugins portal from the portable package."""
import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PLUGIN = Path(__file__).resolve().parents[1] / 'plugins' / 'kultura-os'


def build(destination):
    # The portal reads OAuth from OpenAI's extension. The base 1.0 MCP schema used
    # by portable clients only permits type, url and headers on the transport.
    config = json.loads((PLUGIN / 'mcp.json').read_text())
    config['mcpServers']['kultura']['extensions'] = {
        'com.openai': {'auth': {'type': 'oauth', 'client': {'mode': 'dcr'}}}
    }
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        for name in ('plugin.json', 'assets/icon.png', 'assets/logo.png',
                     'skills/setup/SKILL.md', 'skills/kultura-os/SKILL.md'):
            archive.write(PLUGIN / name, name)
        archive.writestr('mcp.json', json.dumps(config, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    build(parser.parse_args().destination)
