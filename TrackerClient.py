import argparse
import json
import typing
import uuid

from enum import StrEnum
from threading import Thread
from websocket import WebSocketApp, enableTrace

class TrackerClient:
    tags: set[str] = {'Tracker', 'DeathLink'}
    version: dict[str, any] = {"major": 0, "minor": 4, "build": 6, "class": "Version"}
    items_handling: int = 0b000  # This client does not receive any items

    class MessageCommand(StrEnum):
        BOUNCED = 'Bounced'
        PRINT_JSON = 'PrintJSON'
        ROOM_INFO = 'RoomInfo'

    def __init__(
        self,
        *,
        server_uri: str,
        port: str,
        slot_name: str,
        on_death_link: callable = None, 
        on_item_send: callable = None, 
        verbose_logging: bool = False,
        **kwargs: typing.Any
    ) -> None:
        self.server_uri = server_uri
        self.port = port
        self.slot_name = slot_name
        self.on_death_link = on_death_link
        self.on_item_send = on_item_send
        self.verbose_logging = verbose_logging
        self.web_socket_app_kwargs = kwargs
        self.uuid: int = uuid.getnode()
        self.wsapp: WebSocketApp = None
        self.socket_thread: Thread = None

    def start(self) -> None:
        """Attempts to open an Archipelago MultiServer websocket connection in a new thread."""
        enableTrace(self.verbose_logging)
        self.wsapp = WebSocketApp(
            f'{self.server_uri}:{self.port}',
            on_message=self.on_message,
            **self.web_socket_app_kwargs,
        )

        self.socket_thread = Thread(target=self.wsapp.run_forever)
        self.socket_thread.daemon = True
        self.socket_thread.start()

    def on_message(self, wsapp: WebSocketApp, message: str) -> None:
        """Handles incoming messages from the Archipelago MultiServer."""
        args: dict = json.loads(message)[0]
        cmd = args.get('cmd')

        if cmd == self.MessageCommand.ROOM_INFO:
            self.send_connect()
        elif cmd == self.MessageCommand.PRINT_JSON and args.get('type') == 'ItemSend':
            if self.on_item_send:
                self.on_item_send(args)
        elif cmd == self.MessageCommand.BOUNCED and 'DeathLink' in args.get('tags', []):
            if self.on_death_link:
                self.on_death_link(args)

    def send_connect(self) -> None:
        """send `Connect` packet to log in to server."""
        payload = {
            'cmd': 'Connect',
            'game': '',
            'password': None,
            'name': self.slot_name,
            'version': self.version,
            'tags': list(self.tags),
            'items_handling': self.items_handling,
            'uuid': self.uuid,
        }
        self.send_message(payload)

    def send_message(self, message: dict) -> None:
        self.wsapp.send(json.dumps([message]))

if __name__ == '__main__':
    """Example usage utilizing configuration via arguments"""
    parser = argparse.ArgumentParser(description='Start the TrackerClient.')
    parser.add_argument('--server_uri', type=str, default='localhost', help='The server URI (default: localhost)')
    parser.add_argument('--port', type=str, default='38281', help='The server port (default: 38281)')
    parser.add_argument('--slot_name', type=str, default='tracker_bot', help='The slot name (default: tracker_bot)')
    parser.add_argument('--verbose_logging', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    server_uri = f'ws://{args.server_uri}' # May need to use 'wss' when connecting to Archipelago.gg hosted servers

    client = TrackerClient(
        server_uri=server_uri,
        port=args.port,
        slot_name=args.slot_name,
        verbose_logging=args.verbose_logging,
        on_death_link=lambda args : print(f'--- DEATH-LINK EVENT RECEIVED ---\n{args}'),
        on_item_send=lambda args : print(f'--- ITEM SEND EVENT RECEIVED ---\n{args}')
    )
    client.start()
    client.socket_thread.join() # Enter the WebSocketApp thread to prevent script from closing immediately