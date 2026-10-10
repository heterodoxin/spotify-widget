"""macOS: the Spotify app, driven through AppleScript."""
import subprocess

from spotify_widget.players.base import Player, State

SEPARATOR = '\x1f'
READ = f'''
if application "Spotify" is running then
    tell application "Spotify"
        if player state is stopped then return ""
        set t to current track
        set d to "{SEPARATOR}"
        return (id of t) & d & (name of t) & d & (artist of t) & d & (album of t) & d & (duration of t) & d & (player position) & d & (player state as string) & d & (sound volume) & d & (artwork url of t)
    end tell
end if
return ""
'''
ACTIONS = {'PlayPause': 'playpause', 'Next': 'next track', 'Previous': 'previous track'}


def run(script):
    return subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5).stdout.strip()


def number(text):
    """Parse a number that AppleScript may have written with a decimal comma."""
    return float(text.replace(',', '.'))


class MacPlayer(Player):
    def poll(self):
        fields = run(READ).split(SEPARATOR)
        if len(fields) != 9:
            return None
        track_id, title, artist, album, length, position, state, volume, art = fields
        return State(track_id=track_id, title=title, artist=artist, album=album, length=number(length)/1000,
                     position=number(position), playing=state == 'playing', volume=number(volume)/100, art=art or None)

    def command(self, action):
        run(f'tell application "Spotify" to {ACTIONS[action]}')

    def set_volume(self, level):
        run(f'tell application "Spotify" to set sound volume to {round(level*100)}')
