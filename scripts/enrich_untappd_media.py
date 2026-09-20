"""Add observed label URLs and short source excerpts to reviewed Untappd IDs.

Never search by name or follow a redirect to a different beer. Photos remain
external links. Source HTML and failures stay in output/, outside the release.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]


class BeerHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.photo = None
        self.checkin_photo = None
        self.canonical = None
        self.description = []
        self.depth = 0
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = a.get('class', '').split()
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'a' and 'label' in classes and a.get('data-image') and not self.photo:
            self.photo = a.get('data-image')
        if tag == 'img' and a.get('alt') == 'Check-in Photo' and not self.checkin_photo:
            self.checkin_photo = a.get('src')
        if tag == 'div':
            if 'beer-descrption-read-less' in classes:
                self.depth = 1
            elif self.depth:
                self.depth += 1
        if self.depth and tag == 'a':
            self.skipping += 1

    def handle_endtag(self, tag):
        if self.depth and tag == 'a':
            self.skipping = max(0, self.skipping - 1)
        if self.depth and tag == 'div':
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skipping:
            self.description.append(data)


def parse_media(html, beer_id):
    parsed = BeerHTML()
    parsed.feed(html)
    if not parsed.canonical or not re.fullmatch(
            r'https://untappd.com/b/[^/]+/' + re.escape(beer_id) + r'/?', parsed.canonical):
        raise ValueError('Canonical beer ID does not match reviewed identity')
    photo = parsed.photo
    if photo and not re.fullmatch(
            r'https://assets\.untappd\.com/site/beer_logos(?:_hd)?/beer-[A-Za-z0-9_.%-]+', photo):
        photo = None
    photo_kind = 'label' if photo else None
    if not photo and parsed.checkin_photo:
        parts = urlparse(parsed.checkin_photo)
        origin = parse_qs(parts.query).get('url', [''])[0]
        if (parts.scheme == 'https' and parts.netloc == 'images.untp.beer' and parts.path == '/crop'
                and re.fullmatch(r'https://untappd\.s3\.amazonaws\.com/photos/[A-Za-z0-9_/.-]+', origin)):
            photo = parsed.checkin_photo
            photo_kind = 'community_photo'
    description = ' '.join(' '.join(parsed.description).split())
    words = description.split()
    # Publish only a short excerpt of source prose, at most 25 words per beer.
    excerpt = ' '.join(words[:25]) + ('…' if len(words) > 25 else '')
    return {'photo_url': photo, 'photo_kind': photo_kind, 'description': excerpt or None,
            'description_is_excerpt': len(words) > 25,
            'media_source_url': parsed.canonical}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', nargs='*')
    args = parser.parse_args()
    path = ROOT / 'resources/untappd_observations.json'
    observations = json.loads(path.read_text(encoding='utf8'))
    registry = json.loads((ROOT / 'resources/iiko_untappd_registry.json').read_text(encoding='utf8'))
    ids = args.ids or sorted(registry['beers'], key=int)
    cache = ROOT / 'output/untappd-media'
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(bid):
        try:
            url = observations[bid]['url']
            target = cache / (bid + '.html')
            if not target.exists():
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as response:
                    # A merged/deleted beer must be reviewed again, not silently replaced.
                    if not re.fullmatch(r'https://untappd.com/b/[^/]+/' + re.escape(bid) + r'/?', response.url):
                        raise ValueError('Beer URL redirected')
                    text = response.read().decode('utf8')
                target.write_text(text, encoding='utf8')
            result = parse_media(target.read_text(encoding='utf8'), bid)
            result['media_observed_at'] = datetime.now(timezone.utc).isoformat()
            return bid, result, None
        except (OSError, ValueError) as error:
            return bid, None, type(error).__name__

    failures = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for number, (bid, media, error) in enumerate(pool.map(fetch, ids), 1):
            if media:
                observations[bid].update(media)
            else:
                failures[bid] = error
            if number % 25 == 0:
                print(f'Processed {number}/{len(ids)}; failed {len(failures)}', flush=True)
    path.write_text(json.dumps(observations, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    (cache / 'failures.json').write_text(json.dumps(failures, indent=2), encoding='utf8')
    print(json.dumps({'checked': len(ids), 'photos': sum(bool(x.get('photo_url')) for x in observations.values()),
                      'descriptions': sum(bool(x.get('description')) for x in observations.values()),
                      'failed': len(failures)}), flush=True)


if __name__ == '__main__':
    main()
