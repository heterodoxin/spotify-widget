"""Hyprland: a native Wayland window that the compositor moves over its socket."""
import json
import os
import socket
import sys

from PySide6.QtCore import Qt

from spotify_widget import hotkey
from spotify_widget.placement.base import Monitor, Placement

MASKS = {'shift': 1, 'ctrl': 4, 'alt': 8, 'super': 64}
RULE = ('hl.window_rule({ name = "spotify-widget", match = { class = "^(spotify-widget)$" }, float = true, pin = true, '
        'no_blur = true, no_shadow = true, no_dim = true, no_anim = true, no_initial_focus = true, no_follow_mouse = true, '
        'border_size = 0, rounding = 12, opacity = "1.0 override 1.0 override", opaque = true })')


def request(command):
    """Send one command to Hyprland and return its reply."""
    path = f"{os.environ['XDG_RUNTIME_DIR']}/hypr/{os.environ['HYPRLAND_INSTANCE_SIGNATURE']}/.socket.sock"
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect(path)
        sock.sendall(command.encode())
        reply = b''
        while chunk := sock.recv(65536):
            reply += chunk
    return reply.decode()


class HyprlandPlacement(Placement):
    flags = Qt.FramelessWindowHint

    def __init__(self):
        self.address = None
        self.lua = True
        self.last_active = ''
        self.integrate()

    def integrate(self):
        """Give Hyprland the card's window rule and toggle key, again after each reload of its config."""
        # A global in Hyprland's Lua state marks the work as done, and a reload clears it.
        fresh = request(f'/repl if spotify_widget then return 0 end spotify_widget = true {RULE} return 1').strip()
        combo = hotkey.parse(os.environ.get('SPOTIFY_WIDGET_HOTKEY', hotkey.DEFAULT))
        if fresh == '0' or combo is None:
            return
        held, key = combo
        mask = sum(MASKS[name] for name in held)
        if any(b['modmask'] == mask and b['key'].lower() == key and not b['submap'] for b in json.loads(request('j/binds'))):
            return
        toggle = f'{sys.executable} -m spotify_widget toggle'
        names = [name.upper() for name in sorted(held)]
        if fresh == '1':
            keys = ' + '.join(names + [key.upper()])
            request(f'/eval hl.bind("{keys}", hl.dsp.exec_cmd([[{toggle}]]), {{ description = "Toggle Spotify Widget" }})')
        else:
            request(f"/keyword bind {' '.join(names)}, {key.upper()}, exec, {toggle}")

    def monitors(self):
        result = {}
        for m in json.loads(request('j/monitors')):
            left, top, right, bottom = m['reserved']
            result[m['name']] = Monitor(m['x'], m['y'], m['width']/m['scale'], m['height']/m['scale'], left, top, right, bottom)
        return result

    def focused(self):
        return next((m['name'] for m in json.loads(request('j/monitors')) if m['focused']), '')

    def cursor(self):
        point = json.loads(request('j/cursorpos'))
        return float(point['x']), float(point['y'])

    def attach(self, widget):
        mine = [c for c in json.loads(request('j/clients')) if c['pid'] == os.getpid() and c['mapped']]
        if not mine:
            return False
        self.address = mine[0]['address']
        # Hyprland with a Lua config takes Lua dispatchers, older ones take the classic syntax.
        x, y = mine[0]['at']
        self.lua = request(self.lua_move(x, y)).strip() == 'ok'
        return True

    def detach(self):
        self.address = None

    def lua_move(self, x, y):
        return f"/dispatch hl.dsp.window.move({{ x = {x}, y = {y}, window = 'address:{self.address}' }})"

    def move(self, x, y):
        if self.address is None:
            return
        if self.lua:
            request(self.lua_move(x, y))
        else:
            request(f'/dispatch movewindowpixel exact {x} {y},address:{self.address}')

    def tick(self):
        self.integrate()
        active = json.loads(request('j/activewindow')).get('address', '')
        if active and active != self.address:
            self.last_active = active

    def released(self):
        # Clicking the card focused it, so the keyboard goes back to the window that had it.
        if not self.last_active:
            return
        if self.lua:
            request(f"/dispatch hl.dsp.focus({{ window = 'address:{self.last_active}' }})")
        else:
            request(f'/dispatch focuswindow address:{self.last_active}')
