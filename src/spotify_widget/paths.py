"""Where the widget keeps its cache and its remembered corner."""
import os
import sys
from pathlib import Path

NAME = 'spotify-widget'


def cache_dir():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / NAME / 'cache'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Caches' / NAME
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir():
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / NAME
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support' / NAME
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / NAME
    base.mkdir(parents=True, exist_ok=True)
    return base
