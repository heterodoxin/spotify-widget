from lyrics_overlay.players.base import is_spotify
from lyrics_overlay.players.mpris import PREFIX, MprisPlayer


def song(title, status):
    return {'PlaybackStatus': status, 'Position': 5_000_000, 'Volume': 0.6,
            'Metadata': {'xesam:title': ('s', title), 'xesam:artist': ('as', ['Artist']), 'mpris:length': ('x', 200_000_000)}}


class Bus(MprisPlayer):
    """A session bus holding the given players, keyed by the end of their bus name."""

    def __init__(self, players):
        super().__init__()
        self.players = players

    def call(self, message):
        return [[PREFIX+name for name in self.players]]

    def properties(self, name):
        return self.players[name[len(PREFIX):]]


def test_spotify_clients_are_recognised_on_every_system():
    for name in ('spotify', 'spotifyd.instance4242', 'spotify_player', 'ncspot', 'Spotify.exe',
                 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify'):
        assert is_spotify(name)
    for name in ('firefox.instance_1_419659', 'chromium.instance7', 'vlc', 'mpv', 'playerctld', 'MSEdge', 'chrome.exe'):
        assert not is_spotify(name)


def test_other_players_are_ignored_even_while_playing():
    bus = Bus({'firefox.instance_1_419659': song('A video', 'Playing'), 'vlc': song('A film', 'Playing')})
    assert bus.poll() is None and bus.name is None


def test_paused_spotify_wins_over_a_playing_browser():
    bus = Bus({'firefox.instance_1_419659': song('A video', 'Playing'), 'spotify': song('A song', 'Paused')})
    state = bus.poll()
    assert (state.title, state.artist, state.playing, state.length, state.volume) == ('A song', 'Artist', False, 200.0, 0.6)
    assert bus.name == PREFIX+'spotify'


def test_the_spotify_client_that_is_playing_is_followed():
    bus = Bus({'spotify': song('Desktop', 'Paused'), 'spotifyd.instance4242': song('Daemon', 'Playing')})
    assert bus.poll().title == 'Daemon'
