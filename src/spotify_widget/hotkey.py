"""A system-wide key that toggles the card, on the systems that let an app claim one."""
import ctypes
import ctypes.util
import os
import sys
import threading

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QGuiApplication

DEFAULT = 'ctrl+super+l'
MODIFIERS = {'ctrl': 'ctrl', 'control': 'ctrl', 'alt': 'alt', 'option': 'alt', 'shift': 'shift', 'super': 'super',
             'win': 'super', 'cmd': 'super', 'meta': 'super'}
WINDOWS = {'alt': 0x1, 'ctrl': 0x2, 'shift': 0x4, 'super': 0x8}
X11 = {'shift': 0x1, 'ctrl': 0x4, 'alt': 0x8, 'super': 0x40}
MAC = {'super': 0x100, 'shift': 0x200, 'alt': 0x800, 'ctrl': 0x1000}
MAC_KEYS = dict(zip('asdfhgzxcvbqweryt123465=97-80]ou[ip', (n for n in range(36) if n != 10)))
MAC_KEYS.update({'l': 37, 'j': 38, 'k': 40, 'n': 45, 'm': 46})
MAC_KEYS.update(zip((f'f{n}' for n in range(1, 13)), (122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111)))


def parse(text):
    """Turn 'ctrl+super+l' into (modifiers, key), or None when the text names no usable key."""
    *held, key = [part.strip() for part in text.lower().split('+')]
    plain = len(key) == 1 and key.isascii() and key.isalnum()
    function = key[:1] == 'f' and key[1:].isdigit() and 1 <= int(key[1:]) <= 12
    if not held or not all(name in MODIFIERS for name in held) or not (plain or function):
        return None
    return frozenset(MODIFIERS[name] for name in held), key


def bits(table, held):
    return sum(table[name] for name in held)


class Pair(ctypes.Structure):
    _fields_ = [('first', ctypes.c_uint32), ('second', ctypes.c_uint32)]


class WindowsKey(QAbstractNativeEventFilter):
    def __init__(self, held, key, fire):
        super().__init__()
        self.fire = fire
        code = 0x6F + int(key[1:]) if len(key) > 1 else ord(key.upper())
        self.claimed = bool(ctypes.windll.user32.RegisterHotKey(None, 1, bits(WINDOWS, held) | 0x4000, code))
        QGuiApplication.instance().installNativeEventFilter(self)

    def nativeEventFilter(self, kind, message):
        from ctypes import wintypes
        if kind == b'windows_generic_MSG' and wintypes.MSG.from_address(int(message)).message == 0x0312:
            self.fire()
            return True, 0
        return False, 0


class MacKey:
    def __init__(self, held, key, fire):
        carbon = ctypes.CDLL(ctypes.util.find_library('Carbon'))
        handler = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        self.handler = handler(lambda call, event, data: fire() or 0)
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.InstallEventHandler.argtypes = [ctypes.c_void_p, handler, ctypes.c_ulong, ctypes.POINTER(Pair),
                                               ctypes.c_void_p, ctypes.c_void_p]
        carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, Pair, ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.POINTER(ctypes.c_void_p)]
        target = carbon.GetApplicationEventTarget()
        # The first pair is the keyboard event class and its hot-key-pressed kind, the second names this hot key.
        carbon.InstallEventHandler(target, self.handler, 1, ctypes.byref(Pair(0x6B657962, 5)), None, None)
        self.reference = ctypes.c_void_p()
        self.claimed = key in MAC_KEYS and carbon.RegisterEventHotKey(
            MAC_KEYS[key], bits(MAC, held), Pair(0x73707477, 1), target, 0, ctypes.byref(self.reference)) == 0


class X11Key(QObject):
    pressed = Signal()

    def __init__(self, held, key, fire):
        super().__init__()
        self.pressed.connect(fire)
        self.x = ctypes.CDLL(ctypes.util.find_library('X11'))
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.display = ctypes.c_void_p(self.x.XOpenDisplay(None))
        self.claimed = bool(self.display)
        if not self.claimed:
            return
        # A key that another program holds raises an X error, which would end the process if left unhandled.
        self.quiet = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda display, error: 0)
        self.x.XSetErrorHandler(self.quiet)
        self.x.XDefaultRootWindow.restype = ctypes.c_ulong
        root = ctypes.c_ulong(self.x.XDefaultRootWindow(self.display))
        symbol = 0xFFBD + int(key[1:]) if len(key) > 1 else ord(key)
        code = self.x.XKeysymToKeycode(self.display, ctypes.c_ulong(symbol)) & 0xFF
        for locks in (0x0, 0x2, 0x10, 0x12):
            # Caps Lock and Num Lock count as modifiers, so the key is claimed with each mix of them.
            self.x.XGrabKey(self.display, code, bits(X11, held) | locks, root, 0, 1, 1)
        self.x.XSync(self.display, 0)
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        event = ctypes.create_string_buffer(192)
        while True:
            self.x.XNextEvent(self.display, event)
            if ctypes.c_int.from_buffer(event).value == 2:
                self.pressed.emit()


def open_hotkey(fire):
    """Claim the toggle key and return the object holding it, or None where no key can be claimed."""
    combo = parse(os.environ.get('SPOTIFY_WIDGET_HOTKEY', DEFAULT))
    if combo is None:
        return None
    if sys.platform == 'win32':
        backend = WindowsKey
    elif sys.platform == 'darwin':
        backend = MacKey
    elif QGuiApplication.platformName() == 'xcb':
        backend = X11Key
    else:
        return None
    try:
        return backend(*combo, fire)
    except (OSError, AttributeError, TypeError):
        return None
