"""Exercise the installer, real Codex client and Kultura OAuth in a disposable profile."""
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit

import requests
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from test_mcp_oauth import Env, _hidden_fields
from routes.mcp import mcp_bp
from core.mcp import audit


def consent(session, login_url, site):
    page = session.get(login_url, timeout=10)
    assert urlsplit(page.url).path == "/login"
    consent_page = session.post(page.url, data={"login": "owner", "password": "ownerpass"}, timeout=10)
    fields = _hidden_fields(consent_page.text) + [("decision", "allow"), ("mode", "full")]
    response = session.post(site + "/oauth/authorize", data=fields, allow_redirects=False, timeout=10)
    assert response.status_code == 303
    callback = response.headers["Location"]
    assert urlsplit(callback).hostname == "127.0.0.1"
    session.get(callback, timeout=10).raise_for_status()


def build_fixture(tmp, site):
    # Only replace the public endpoint in a disposable copy of the production sources.
    src = tmp / "src"
    build_dir = src / "scripts/kultura_local_connect"
    plugin = src / "plugins/kultura-os"
    shutil.copytree(ROOT / "scripts/kultura_local_connect", build_dir)
    shutil.copytree(ROOT / "plugins/kultura-os", plugin)
    shutil.copytree(ROOT / ".agents/plugins", src / ".agents/plugins")
    for p in (build_dir / "main.go", plugin / "mcp.json"):
        s = p.read_text(encoding="utf-8")
        assert "https://beerkultura.ru/mcp" in s
        p.write_text(s.replace("https://beerkultura.ru/mcp", site + "/mcp"), encoding="utf-8")
    target = "windows" if os.name == "nt" else "linux"
    exe = tmp / ("installer.exe" if os.name == "nt" else "installer")
    subprocess.run([sys.executable, str(build_dir / "build.py"), str(exe), "--target", target], check=True)
    return exe


def exercise(tmp, site):
    exe = build_fixture(tmp, site)
    profile = tmp / "profile"
    profile.mkdir()
    (profile / "config.toml").write_text('mcp_oauth_credentials_store = "file"\n', encoding="utf-8")
    env = {**os.environ, "CODEX_HOME": str(profile), "APPDATA": str(tmp / "settings"),
           "XDG_CONFIG_HOME": str(tmp / "settings"), "NO_PROXY": "127.0.0.1,localhost"}
    session = requests.Session()
    session.trust_env = False
    expected = ["common_whoami", "common_instructions", "common_docs_list", "common_bars_reference"]
    for run in (1, 2, 3):
        if run == 3:
            # Reproduce the older Downloads marketplace on an already authorised PC.
            old = tmp / "downloads/kultura-os-1.1.0-local"
            shutil.copytree(ROOT / ".agents/plugins", old / ".agents/plugins")
            shutil.copytree(ROOT / "plugins/kultura-os", old / "plugins/kultura-os")
            for args in (["marketplace", "remove", "kultura-plugins"],
                         ["marketplace", "add", str(old)], ["add", "kultura-os@kultura-plugins"]):
                subprocess.run(["codex", "plugin", *args], cwd=tmp, env=env,
                               check=True, capture_output=True, timeout=45)
        count = 0
        proc = subprocess.Popen([str(exe)], env=env, cwd=tmp, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding="utf-8", errors="replace")
        try:
            for line in proc.stdout:
                match = re.search(re.escape(site) + r"/oauth/authorize\?\S+", line)
                if match:
                    count += 1
                    assert run == 1, "unexpected repeated sign-in"
                    consent(session, match.group(), site)
                elif "://" not in line:
                    print(line.rstrip(), flush=True)
            assert proc.wait(timeout=10) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        assert count == (1 if run == 1 else 0)
        assert [r["tool"] for r in reversed(audit.recent())] == expected * run
        listing = subprocess.run(["codex", "plugin", "list", "--json"], cwd=tmp, env=env,
                                 capture_output=True, encoding="utf-8", check=True, timeout=60)
        assert "kultura-os" in json.dumps(json.loads(listing.stdout)["installed"])
        sources = subprocess.run(["codex", "plugin", "marketplace", "list", "--json"], cwd=tmp,
                                 env=env, capture_output=True, encoding="utf-8", check=True, timeout=60)
        roots = [Path(m["root"]) for m in json.loads(sources.stdout)["marketplaces"]
                 if m["name"] == "kultura-plugins"]
        assert roots == [tmp / "settings/KulturaOS/marketplaces/kultura-os-1.1.2"]
        print(f"Install {run} verified in the server audit.", flush=True)


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    env = Env()
    env.app.register_blueprint(mcp_bp)
    server = make_server("127.0.0.1", 0, env.app, threaded=True)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TemporaryDirectory() as folder:
            exercise(Path(folder), f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        env.close()
