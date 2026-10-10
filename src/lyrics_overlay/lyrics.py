"""Synced lyrics from lrclib.net and album art, both cached on disk."""
import hashlib
import json
import re
from urllib.parse import unquote, urlparse

import requests

from lyrics_overlay.paths import cache_dir

API = 'https://lrclib.net/api'
HEADERS = {'User-Agent': 'lyrics-overlay/1.0 (https://github.com/heterodoxin/lyrics-overlay)'}
STAMP = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\]')


def parse_lrc(text):
    """Turn LRC text into a time-sorted list of (seconds, words)."""
    lines = []
    for line in (text or '').splitlines():
        words = STAMP.sub('', line).strip()
        for minute, second in STAMP.findall(line):
            lines.append((int(minute)*60 + float(second), words))
    return sorted(lines)


def closest(results, duration):
    """The synced result whose length is within three seconds of the song, or None."""
    close = [item for item in results if item.get('syncedLyrics') and abs((item.get('duration') or 0)-duration) <= 3]
    return min(close, key=lambda item: abs(item['duration']-duration)) if close else None


def fetch(title, artist, album, length):
    """Return (lines, status) for a song, where status explains an empty list."""
    params = dict(track_name=title, artist_name=artist, album_name=album, duration=round(length))
    path = cache_dir() / (hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()+'.json')
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        response = requests.get(API+'/get', params=params, headers=HEADERS, timeout=12)
        if response.status_code == 404:
            # The exact lookup misses remasters and multi-artist credits, so search by title and first artist.
            query = dict(track_name=title, artist_name=artist.split(', ')[0])
            found = requests.get(API+'/search', params=query, headers=HEADERS, timeout=12)
            found.raise_for_status()
            data = closest(found.json(), params['duration'])
            if data is None:
                return [], 'No synced lyrics for this song'
        else:
            response.raise_for_status()
            data = response.json()
        path.write_text(json.dumps(data), encoding='utf-8')
    return parse_lrc(data.get('syncedLyrics')), ('Instrumental' if data.get('instrumental') else 'No synced lyrics for this song')


def cover(source):
    """Return a local file for album art given a URL, a file URL or a path."""
    if not source:
        return None
    parsed = urlparse(source)
    if parsed.scheme == 'file':
        return unquote(parsed.path)
    if parsed.scheme not in ('http', 'https'):
        return source
    path = cache_dir() / (hashlib.sha256(source.encode()).hexdigest()+'.img')
    if not path.exists():
        response = requests.get(source, headers=HEADERS, timeout=12)
        response.raise_for_status()
        path.write_bytes(response.content)
    return str(path)
