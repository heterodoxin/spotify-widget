import json

from lyrics_overlay import lyrics


class Reply:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        assert self.status_code == 200


def test_parse_orders_lines_and_repeats_shared_stamps():
    parsed = lyrics.parse_lrc('[00:12.50]second\n[00:01.00][00:20.00]chorus\n[ar:someone]\n[00:15.00]')
    assert parsed == [(1.0, 'chorus'), (12.5, 'second'), (15.0, ''), (20.0, 'chorus')]


def test_parse_of_nothing_is_empty():
    assert lyrics.parse_lrc(None) == [] and lyrics.parse_lrc('just words') == []


def test_closest_wants_synced_lyrics_of_the_same_length():
    results = [{'duration': 200, 'syncedLyrics': None}, {'duration': 230, 'syncedLyrics': '[00:01.00]far'},
               {'duration': 202, 'syncedLyrics': '[00:01.00]near'}, {'duration': 199.5, 'syncedLyrics': '[00:01.00]nearest'}]
    assert lyrics.closest(results, 200)['syncedLyrics'].endswith('nearest')
    assert lyrics.closest(results[:2], 200) is None


def test_fetch_caches_an_exact_match(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: calls.append(url) or Reply(200, {'syncedLyrics': '[00:03.00]hello'}))
    assert lyrics.fetch('Song', 'Artist', 'Album', 200.4) == ([(3.0, 'hello')], '')
    assert lyrics.fetch('Song', 'Artist', 'Album', 200.4)[0] == [(3.0, 'hello')]
    assert calls == [lyrics.API+'/get']


def test_fetch_searches_by_first_artist_when_the_exact_lookup_misses(tmp_path, monkeypatch):
    asked = []

    def get(url, params, **kw):
        asked.append((url, params))
        if url.endswith('/get'):
            return Reply(404, {})
        return Reply(200, [{'duration': 201, 'syncedLyrics': '[00:05.00]found'}])

    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', get)
    assert lyrics.fetch('Song', 'One, Two', 'Album', 200)[0] == [(5.0, 'found')]
    assert asked[1] == (lyrics.API+'/search', {'track_name': 'Song', 'artist_name': 'One'})


def test_fetch_searches_when_the_exact_record_has_only_plain_text(tmp_path, monkeypatch):
    def get(url, params, **kw):
        if url.endswith('/get'):
            return Reply(200, {'plainLyrics': 'words', 'syncedLyrics': None, 'instrumental': False})
        return Reply(200, [{'duration': 199, 'syncedLyrics': '[00:07.00]synced'}])

    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', get)
    assert lyrics.fetch('Song', 'Artist', 'Album', 200) == ([(7.0, 'synced')], '')


def test_fetch_retries_a_cached_record_that_has_no_synced_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: Reply(200, {'syncedLyrics': '[00:01.00]first'}))
    lyrics.fetch('Song', 'Artist', 'Album', 200)
    cached, = tmp_path.iterdir()
    cached.write_text(json.dumps({'plainLyrics': 'words', 'syncedLyrics': None}))
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: Reply(200, {'syncedLyrics': '[00:02.00]now synced'}))
    assert lyrics.fetch('Song', 'Artist', 'Album', 200)[0] == [(2.0, 'now synced')]


def test_fetch_reports_a_song_without_synced_lyrics_and_does_not_cache_it(tmp_path, monkeypatch):
    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: Reply(404, {}) if url.endswith('/get') else Reply(200, []))
    assert lyrics.fetch('Song', 'Artist', 'Album', 200) == ([], 'No synced lyrics for this song')
    assert list(tmp_path.iterdir()) == []


def test_instrumental_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: Reply(200, {'instrumental': True, 'syncedLyrics': None}))
    assert lyrics.fetch('Song', 'Artist', 'Album', 200) == ([], 'Instrumental')


def test_cover_accepts_file_urls_paths_and_downloads_once(tmp_path, monkeypatch):
    fetched = []

    class Image:
        content = b'png'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(lyrics, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics.requests, 'get', lambda url, **kw: fetched.append(url) or Image())
    assert lyrics.cover(None) is None
    assert lyrics.cover('file:///tmp/a%20b.png') == '/tmp/a b.png'
    assert lyrics.cover('/tmp/plain.png') == '/tmp/plain.png'
    first = lyrics.cover('https://example.com/a.png')
    assert lyrics.cover('https://example.com/a.png') == first and fetched == ['https://example.com/a.png']
    assert open(first, 'rb').read() == b'png'
