"""What every player backend reports and accepts."""
from dataclasses import dataclass

SPOTIFY = ('spotify', 'ncspot', 'librespot')


def is_spotify(name):
    """Whether a bus name or app id belongs to Spotify or a client that plays from it."""
    return any(client in name.lower() for client in SPOTIFY)


@dataclass(frozen=True)
class State:
    track_id: str
    title: str
    artist: str
    album: str
    length: float
    position: float
    playing: bool
    volume: float | None
    art: str | None


class Player:
    """A source of playback state that can also be told to play, pause, skip and change volume."""

    def poll(self):
        """Return the current State, or None when nothing is playing."""
        raise NotImplementedError

    def command(self, action):
        """Carry out 'PlayPause', 'Next' or 'Previous'."""
        raise NotImplementedError

    def set_volume(self, level):
        """Set the player's volume from 0 to 1."""
        raise NotImplementedError
