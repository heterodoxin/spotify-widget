"""Pick the player backend for this operating system."""
import sys


def open_player():
    if sys.platform == 'win32':
        from lyrics_overlay.players.windows import WindowsPlayer
        return WindowsPlayer()
    if sys.platform == 'darwin':
        from lyrics_overlay.players.macos import MacPlayer
        return MacPlayer()
    from lyrics_overlay.players.mpris import MprisPlayer
    return MprisPlayer()
