"""Linux and BSD: Spotify, read over MPRIS on the session bus."""
import threading

from jeepney import DBusAddress, MessageType, Properties, new_method_call
from jeepney.io.blocking import open_dbus_connection

from spotify_widget.players.base import Player, State, is_spotify

PREFIX = 'org.mpris.MediaPlayer2.'
BUS = DBusAddress('/org/freedesktop/DBus', bus_name='org.freedesktop.DBus', interface='org.freedesktop.DBus')


class MprisPlayer(Player):
    def __init__(self):
        self.lock = threading.Lock()
        self.connection = None
        self.name = None

    def call(self, message):
        """Send one message and return its body, reconnecting once if the bus went away."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.connection is None:
                        self.connection = open_dbus_connection(bus='SESSION')
                    reply = self.connection.send_and_get_reply(message, timeout=2)
                    break
                except (OSError, ConnectionError):
                    self.connection = None
                    if attempt:
                        raise
        if reply.header.message_type == MessageType.error:
            raise RuntimeError(str(reply.body))
        return reply.body

    def address(self, name):
        return DBusAddress('/org/mpris/MediaPlayer2', bus_name=name, interface=PREFIX+'Player')

    def properties(self, name):
        try:
            return {key: value for key, (_, value) in self.call(Properties(self.address(name)).get_all())[0].items()}
        except (RuntimeError, TimeoutError):
            return None

    def choose(self):
        """Stay with the current Spotify client while it plays, otherwise move to one that does."""
        names = [name for name in self.call(new_method_call(BUS, 'ListNames'))[0]
                 if name.startswith(PREFIX) and is_spotify(name[len(PREFIX):])]
        if self.name not in names:
            self.name = None
        props = self.properties(self.name) if self.name else None
        if props and props.get('PlaybackStatus') == 'Playing':
            return props
        for name in names:
            other = self.properties(name) if name != self.name else None
            if other and other.get('PlaybackStatus') == 'Playing':
                self.name = name
                return other
        if props is None and names:
            self.name = names[0]
            props = self.properties(self.name)
        return props

    def poll(self):
        props = self.choose()
        if not props:
            return None
        meta = {key: value for key, (_, value) in props.get('Metadata', {}).items()}
        title = str(meta.get('xesam:title', ''))
        if not title:
            return None
        artist = meta.get('xesam:artist', '')
        volume = props.get('Volume')
        return State(
            track_id=str(meta.get('mpris:trackid', '')) + title,
            title=title,
            artist=', '.join(artist) if isinstance(artist, list) else str(artist),
            album=str(meta.get('xesam:album', '')),
            length=int(meta.get('mpris:length', 0))/1e6,
            position=int(props.get('Position', 0))/1e6,
            playing=props.get('PlaybackStatus') == 'Playing',
            volume=max(0.0, min(1.0, float(volume))) if volume is not None else None,
            art=str(meta['mpris:artUrl']) if meta.get('mpris:artUrl') else None,
        )

    def command(self, action):
        if self.name:
            self.call(new_method_call(self.address(self.name), action))

    def set_volume(self, level):
        if self.name:
            self.call(Properties(self.address(self.name)).set('Volume', 'd', float(level)))
