"""Pick the player backend for this operating system."""
import sys


def open_player():
    if sys.platform == 'win32':
        from spotify_widget.players.windows import WindowsPlayer
        return WindowsPlayer()
    if sys.platform == 'darwin':
        from spotify_widget.players.macos import MacPlayer
        return MacPlayer()
    from spotify_widget.players.mpris import MprisPlayer
    return MprisPlayer()
