"""Build and upload a draft version to the existing Kultura OS publisher listing."""
import argparse
import json
import re
import shutil
import sys
import tempfile
from time import monotonic
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import expect, sync_playwright

from package_kultura_plugin import PLUGIN, build


PORTAL = 'https://platform.openai.com/plugins'
UPDATE = re.compile(r'^Upload (new version|plugin to (make changes|fix issues))$', re.I)


def is_listing(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'platform.openai.com'
            and re.fullmatch(r'/plugins/[^/]+/?', parsed.path) is not None)


def check_identity(page, listing, package_name):
    check_identity_url(page, listing)
    # Use the immutable package name in the Metadata tab, not the editable display name.
    expect(page.get_by_text(package_name, exact=True).first).to_be_visible(timeout=15000)


def update(page, listing, manifest, upload):
    page.goto(listing, wait_until='domcontentloaded')
    check_identity(page, listing, manifest['name'])
    button = page.get_by_role('button', name=UPDATE)
    expect(button).to_be_visible()
    version = manifest['version']
    selected = page.get_by_text(re.compile(r'^Version\s+' + re.escape(version) + r'(?:\s|$)', re.I)).first
    if selected.is_visible():
        return f'Publisher already shows version {version}.'
    if not upload:
        return f'Existing listing verified. Local package version {version}.'
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / f"{manifest['name']}-{version}.zip"
        build(package)
        # Playwright also exposes dynamically created file inputs via filechooser.
        chosen = False

        def select_file(chooser):
            nonlocal chosen
            check_identity_url(page, listing)
            chosen = True
            chooser.set_files(str(package))

        page.on('filechooser', select_file)
        try:
            button.click()
            dialog = page.get_by_role('dialog')
            picker = dialog.locator('input[type=file]')
            action = dialog.get_by_role('button', name=re.compile(r'^Upload(?: plugin)?$', re.I))
            clicked_dialog = False
            deadline = monotonic() + 60
            while not selected.is_visible():
                check_identity_url(page, listing)
                if monotonic() >= deadline:
                    raise ValueError('The portal did not confirm the version. Inspect the draft before retrying.')
                if not chosen and dialog.is_visible() and picker.count() == 1:
                    picker.set_input_files(str(package))
                    chosen = True
                elif not clicked_dialog and action.is_visible() and action.is_enabled():
                    action.click()
                    clicked_dialog = True
                else:
                    page.wait_for_timeout(200)
        finally:
            page.remove_listener('filechooser', select_file)
    page.reload(wait_until='domcontentloaded')
    check_identity(page, listing, manifest['name'])
    expect(selected).to_be_visible(timeout=15000)
    return f'Publisher shows version {version} after reload. Draft upload verified.'


def check_identity_url(page, listing):
    if page.url.split('?')[0].rstrip('/') != listing:
        raise ValueError('Publisher navigated away from the selected listing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('listing', nargs='?', help='Existing publisher listing URL. Optional for --login.')
    session = parser.add_mutually_exclusive_group(required=True)
    session.add_argument('--cdp', help='Local HTTP endpoint of an authorized Chromium session')
    session.add_argument('--profile', type=Path, help='Private Chromium profile outside the repository')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--upload', action='store_true', help='Upload a draft. Default checks publisher access.')
    action.add_argument('--login', action='store_true', help='Open the portal in the dedicated visible browser.')
    args = parser.parse_args()
    if args.login and not args.profile:
        parser.error('--login requires --profile')
    if args.cdp:
        cdp = urlsplit(args.cdp)
        if (cdp.scheme != 'http' or cdp.hostname not in ('127.0.0.1', 'localhost', '::1')
                or cdp.username or cdp.password or cdp.query or cdp.fragment or cdp.path not in ('', '/')):
            parser.error('--cdp requires a local browser endpoint')
    if args.profile:
        profile = args.profile.expanduser().resolve()
        if profile.is_relative_to(PLUGIN.parents[1]):
            parser.error('Keep the publisher profile outside the source repository.')
        profile.mkdir(mode=0o700, parents=True, exist_ok=True)
        if profile.stat().st_mode & 0o077:
            parser.error('Use a private profile directory with permissions 0700.')
        saved_listing = profile / 'kultura-publisher-listing.txt'
        if not args.login and not args.listing and saved_listing.is_file():
            args.listing = saved_listing.read_text(encoding='utf-8').strip()
    if not args.login and not is_listing(args.listing or ''):
        parser.error('Pass the existing plugin detail URL or authorize a dedicated profile with --login.')
    manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
    with sync_playwright() as pw:
        if args.cdp:
            browser = pw.chromium.connect_over_cdp(args.cdp, timeout=10000)
            context = browser.contexts[0]
        else:
            context = pw.chromium.launch_persistent_context(
                str(profile), executable_path=shutil.which('chromium'), headless=not args.login)
        page = context.new_page()
        try:
            if args.login:
                page.goto(PORTAL, wait_until='domcontentloaded')
                print('Sign in and open Kultura OS in this browser. Waiting for the existing listing.', flush=True)
                page.wait_for_url(lambda url: is_listing(url), timeout=600000)
                listing = page.url.split('?')[0].rstrip('/')
                check_identity(page, listing, manifest['name'])
                saved_listing.write_text(listing + '\n', encoding='utf-8')
                print(f'Publisher listing verified: {listing}')
            else:
                listing = args.listing.split('?')[0].rstrip('/')
                print(update(page, listing, manifest, args.upload))
        finally:
            page.close()
            if args.profile:
                context.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, BrowserError, AssertionError) as error:
        print(f'Publisher update could not be verified: {error}', file=sys.stderr)
        sys.exit(1)
