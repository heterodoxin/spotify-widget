# lyrics-overlay

<p align="center"><img src="docs/screenshot.png" width="680" alt="The card showing a song, its cover and its lyrics"></p>

The card takes its colour from each cover, and falls back to grey when the cover has none:

| | |
| --- | --- |
| <img src="docs/navy.png" width="420" alt="A dark blue card"> | <img src="docs/orange.png" width="420" alt="An orange card"> |
| <img src="docs/crimson.png" width="420" alt="A red card with Japanese lyrics"> | <img src="docs/grey.png" width="420" alt="A grey card for a black and white cover, paused"> |

The volume slider lights up under the pointer, and the card says so when Spotify has nothing to play:

| | |
| --- | --- |
| <img src="docs/volume.png" width="420" alt="The volume slider under the pointer"> | <img src="docs/idle.png" width="420" alt="The card with nothing playing"> |

## What is this project

lyrics-overlay is a small always-visible card that shows time-synced lyrics for the song playing in Spotify, next to its cover, name, artist and progress. It reads the song from Spotify through the system's media player interface, fetches matching lyrics from [lrclib.net](https://lrclib.net), and scrolls them in step with playback. The card also carries previous, play/pause and next buttons and a volume slider, takes its colour from the album cover, and can be dragged to any corner of any screen. It listens to Spotify only, so a video in a browser or any other player leaves it alone. It runs on Linux, Windows and macOS.

## Install

Python 3.10 or newer is required.

```bash
git clone https://github.com/heterodoxin/lyrics-overlay
pip install ./lyrics-overlay
lyrics-overlay
```

`pip` installs every dependency: PySide6 and requests on all systems, jeepney on Linux, and the winrt media packages on Windows. The card appears in the top left corner of the screen in use and fills in as soon as Spotify has a song.

| Command | What it does |
| --- | --- |
| `lyrics-overlay` | Show the card, starting the overlay if it is not running |
| `lyrics-overlay toggle` | Hide the card if it is shown, show it otherwise |
| `lyrics-overlay show` / `hide` | Show or hide the card |
| `lyrics-overlay status` | Print whether it is running, the corner it sits in and the current song |
| `lyrics-overlay quit` | Stop the overlay |

On the card itself: drag it to move it, click the buttons to control playback, drag the slider on the right edge or scroll anywhere on the card to change volume, and click the speaker to mute.

### Hyprland

Hyprland treats the card as an ordinary window unless told otherwise, so it needs one window rule. With a Lua configuration:

```lua
hl.window_rule({
    name = "lyrics-overlay",
    match = { class = "^(lyrics-overlay)$" },
    float = true,
    pin = true,
    no_blur = true,
    no_shadow = true,
    no_dim = true,
    no_anim = true,
    no_initial_focus = true,
    no_follow_mouse = true,
    border_size = 0,
    rounding = 12,
    opacity = "1.0 override 1.0 override",
    opaque = true
})

hl.bind("SUPER + CTRL + L", hl.dsp.exec_cmd("lyrics-overlay toggle"), { description = "Toggle lyrics overlay" })
```

Do not add `no_focus` to the rule: it also stops the pointer from reaching the card.

## Why it's better

Measured on a Ryzen 9 9950X running Hyprland 0.56.2 with PySide6 6.11.1:

- One read of the player's state over D-Bus takes 0.3 ms, and it happens once a second. No helper program is started to do it.
- With a song playing and the card at rest, the overlay uses 3.4% of one core and 96 MB of memory, averaged over 30 seconds. It redraws at up to 140 frames a second only while something is moving and drops to a 25 Hz tick otherwise.
- On Hyprland each window move is one message on the compositor's socket, which takes 0.06 ms, so dragging stays in step with the pointer.
- Lyrics and covers are cached on disk, so a song costs one request to lrclib.net the first time it plays and none after that.
- When the exact lookup finds nothing, or finds a record with only unsynced text, a second search by title and first artist picks the synced result whose length is within three seconds of the song. This recovers songs credited to several artists and songs whose album entry was never synced.
- The test suite has 43 tests covering the drag physics, lyric parsing and lookup, the choice of player and the card's controls. It runs without a display or a media player.

## Why should I care

- Lyrics stay on screen while you do something else, in a corner you choose, on every workspace.
- You can pause, skip and change volume from the card instead of switching to the player.
- It follows Spotify and nothing else. A video in a browser, a game or another music player never replaces the song on the card, and with no Spotify song it reads "Nothing playing".
- Nothing needs configuring. There is no account, no API key and no settings file; the only thing it remembers is the corner you left it in.
- The only data that leaves the machine is the song's title, artist, album and length, sent to lrclib.net to find lyrics, plus the request for the cover image.

## Advanced

### Moving the card

The card is tied to its corner by a spring. While you hold it, it follows the pointer by a little over half the distance at first and less the further it is pulled. Its reach is 12% of the screen's width (at most 320 px) sideways and 14% of its height (at most 200 px) up or down:

- Pulled past its reach, the card lets go of its corner and glides to the next one while the button is still down. The pull is then measured from the new corner, so one drag can carry it across two corners or onto another screen.
- Speed counts toward the reach. While held, 0.06 seconds of the pointer's speed is added to the pull; on release, 0.18 seconds is, so a short flick is enough. A sideways flick keeps its row and an upward flick keeps its column.
- On release the card keeps 35% of the pointer's speed and a damped spring carries it to its corner. A short, slow pull returns it to the corner it came from.
- When the pointer enters another screen, the card goes to the corner of that screen nearest the pointer.

The chosen screen and corner are saved and restored on the next start. If that screen is gone, the card moves to the screen in use.

### Platforms

| System | How Spotify is read | How the card is placed | Volume |
| --- | --- | --- | --- |
| Linux on Hyprland | MPRIS over D-Bus | Native Wayland window moved through Hyprland's socket | Yes |
| Linux on other desktops | MPRIS over D-Bus | X11 or XWayland window positioned by Qt | Yes |
| Windows 10 and 11 | Spotify's session in the system media transport controls | Window positioned by Qt | No, the slider is hidden |
| macOS | AppleScript | Window positioned by Qt | Yes |

What has been run: Linux on Hyprland 0.56.2 with a Lua configuration, and the X11 path through XWayland on the same machine. The Windows and macOS backends and the classic (non-Lua) Hyprland dispatcher syntax are written against those platforms' interfaces and have not been run on them.

On Linux the overlay picks its backend from the environment. Setting `LYRICS_OVERLAY_PLACEMENT=generic` forces the X11 path on Hyprland, and setting `QT_QPA_PLATFORM` yourself overrides the choice of Qt platform.

On macOS the first start asks for permission to control Spotify, because the song is read through AppleScript.

Wayland does not let a window choose its own position, which is why the card is moved through the compositor there. Clicking the card gives it keyboard focus, so on release the overlay hands focus back to the window that had it.

### Which players count as Spotify

On Linux a player is read when its MPRIS name contains `spotify`, `ncspot` or `librespot`, which covers the desktop app, `spotifyd` and `spotify_player`. With several of them open, the card stays with the one it is showing while that one plays, and moves to another when it stops and the other is playing. On Windows the session whose app id contains `spotify` is read, which covers the installer build and the Microsoft Store build. Spotify playing in a browser tab is not read on any system.

### Files

| What | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Lyrics and cover cache | `~/.cache/lyrics-overlay` | `~/Library/Caches/lyrics-overlay` | `%LOCALAPPDATA%\lyrics-overlay\cache` |
| Remembered corner | `~/.config/lyrics-overlay/home.json` | `~/Library/Application Support/lyrics-overlay/home.json` | `%APPDATA%\lyrics-overlay\home.json` |

The Linux paths follow `XDG_CACHE_HOME` and `XDG_CONFIG_HOME` when they are set. Deleting the cache is safe; it is rebuilt as songs play.

### Lyrics

Only time-synced lyrics are shown. A song with none shows "No synced lyrics for this song", and a track marked instrumental shows "Instrumental". A failed lookup is not cached, so it is tried again the next time the song plays.

### Tests

```bash
pip install "./lyrics-overlay[test]"
cd lyrics-overlay
pytest
```
