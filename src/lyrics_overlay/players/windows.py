"""Windows: Spotify, read through the system media controls."""
import asyncio
import hashlib
from datetime import datetime, timezone

from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
from winrt.windows.storage.streams import DataReader

from lyrics_overlay.paths import cache_dir
from lyrics_overlay.players.base import Player, State, is_spotify


async def current_session():
    """Spotify's media session, or None when it is not running."""
    manager = await SessionManager.request_async()
    return next((session for session in manager.get_sessions() if is_spotify(session.source_app_user_model_id)), None)


async def save_thumbnail(reference, key):
    """Write the song's thumbnail to the cache once and return its path."""
    path = cache_dir() / (hashlib.sha256(key.encode()).hexdigest()+'.img')
    if not path.exists():
        stream = await reference.open_read_async()
        reader = DataReader(stream)
        await reader.load_async(stream.size)
        path.write_bytes(bytes(reader.read_buffer(stream.size)))
    return str(path)


async def read():
    session = await current_session()
    if session is None:
        return None
    info = await session.try_get_media_properties_async()
    if not info.title:
        return None
    timeline = session.get_timeline_properties()
    playing = session.get_playback_info().playback_status == Status.PLAYING
    position = timeline.position.total_seconds()
    if playing:
        # Windows reports the position as of its last update, so add the time since.
        position += (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
    key = f'{info.title}|{info.artist}|{info.album_title}'
    art = None
    if info.thumbnail is not None:
        try:
            art = await save_thumbnail(info.thumbnail, key)
        except OSError:
            art = None
    return State(track_id=key, title=info.title, artist=info.artist, album=info.album_title,
                 length=(timeline.end_time - timeline.start_time).total_seconds(), position=max(0.0, position),
                 playing=playing, volume=None, art=art)


async def act(action):
    session = await current_session()
    if session is None:
        return
    if action == 'PlayPause':
        await session.try_toggle_play_pause_async()
    elif action == 'Next':
        await session.try_skip_next_async()
    else:
        await session.try_skip_previous_async()


class WindowsPlayer(Player):
    def poll(self):
        return asyncio.run(read())

    def command(self, action):
        asyncio.run(act(action))

    def set_volume(self, level):
        """The system media controls carry no volume, so the card hides its slider on Windows."""
