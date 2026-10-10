"""Command line entry: start the card, or tell the running one what to do."""
import json
import sys

COMMANDS = ('start', 'show', 'hide', 'toggle', 'quit', 'status')
SERVER = 'spotify-widget'
USAGE = '''usage: spotify-widget [command]

  start    show the card, starting it if needed (the default)
  show     show the card
  hide     hide the card
  toggle   hide the card if it is shown, show it otherwise
  quit     stop the widget
  status   print whether it is running and where the card sits
'''


def send(command):
    """Deliver a command to the running overlay and return its reply, or None if there is none."""
    from PySide6.QtNetwork import QLocalSocket
    link = QLocalSocket()
    link.connectToServer(SERVER)
    if not link.waitForConnected(500):
        return None
    link.write(command.encode())
    link.flush()
    link.waitForReadyRead(2000)
    return bytes(link.readAll()).decode()


def serve(app, card):
    """Listen for commands from later invocations."""
    from PySide6.QtNetwork import QLocalServer
    QLocalServer.removeServer(SERVER)
    server = QLocalServer(app)

    def answer():
        link = server.nextPendingConnection()
        link.waitForReadyRead(500)
        command = bytes(link.readAll()).decode()
        if command in ('start', 'show'):
            card.set_shown(True)
        elif command == 'hide':
            card.set_shown(False)
        elif command == 'toggle':
            card.toggle()
        link.write(json.dumps({'running': True, 'shown': card.enabled, 'corner': card.home, 'song': card.title}).encode())
        link.flush()
        link.disconnectFromServer()
        if command == 'quit':
            app.quit()

    server.newConnection.connect(answer)
    server.listen(SERVER)
    return server


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'start'
    if command in ('-h', '--help', 'help') or command not in COMMANDS:
        sys.stdout.write(USAGE)
        sys.exit(0 if command in ('-h', '--help', 'help') else 2)

    reply = send(command)
    if reply is not None:
        if command == 'status':
            print(reply)
        return
    if command == 'status':
        print(json.dumps({'running': False}))
        return
    if command in ('hide', 'quit'):
        return

    from spotify_widget.placement import open_placement, prepare_environment
    prepare_environment()
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    from spotify_widget.card import Card
    from spotify_widget.hotkey import open_hotkey
    from spotify_widget.players import open_player

    QGuiApplication.setDesktopFileName('spotify-widget')
    app = QApplication(sys.argv[:1])
    app.setApplicationName('spotify-widget')
    app.setQuitOnLastWindowClosed(False)
    card = Card(open_player(), open_placement())
    server, hotkey = serve(app, card), open_hotkey(card.toggle)
    sys.exit(app.exec())
