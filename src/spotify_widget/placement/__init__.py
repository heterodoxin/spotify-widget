"""Pick how the card is placed on this desktop."""
import os
import sys


def on_hyprland():
    return bool(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')) and os.environ.get('SPOTIFY_WIDGET_PLACEMENT') != 'generic'


def prepare_environment():
    """Choose the Qt platform plugin before the application is created."""
    # Qt warns when no desktop file matches the app id, which an installed script never has.
    os.environ.setdefault('QT_LOGGING_RULES', 'qt.qpa.services=false')
    if 'QT_QPA_PLATFORM' in os.environ or not sys.platform.startswith(('linux', 'freebsd')):
        return
    if on_hyprland():
        os.environ['QT_QPA_PLATFORM'] = 'wayland'
    elif os.environ.get('DISPLAY'):
        # A Wayland client cannot position itself, so other desktops go through X11 or XWayland.
        os.environ['QT_QPA_PLATFORM'] = 'xcb'


def open_placement():
    if on_hyprland():
        from spotify_widget.placement.hyprland import HyprlandPlacement
        return HyprlandPlacement()
    from spotify_widget.placement.generic import GenericPlacement
    return GenericPlacement()
