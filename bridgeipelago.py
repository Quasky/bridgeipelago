# __| |____________________________________________________________________________| |__
# __   ____________________________________________________________________________   __
#   | |                                                                            | |
#   | | ____  ____  ___ ____   ____ _____ ___ ____  _____ _        _    ____  ___  | |
#   | || __ )|  _ \|_ _|  _ \ / ___| ____|_ _|  _ \| ____| |      / \  / ___|/ _ \ | |
#   | ||  _ \| |_) || || | | | |  _|  _|  | || |_) |  _| | |     / _ \| |  _| | | || |
#   | || |_) |  _ < | || |_| | |_| | |___ | ||  __/| |___| |___ / ___ \ |_| | |_| || |
#   | ||____/|_|_\_\___|____/_\____|_____|___|_|   |_____|_____/_/   \_\____|\___/ | |
#   | | / ___/ _ \|  _ \| ____|                                                    | |
#   | || |  | | | | |_) |  _|                                                      | |
#   | || |__| |_| |  _ <| |___                                                     | |
#   | | \____\___/|_| \_\_____| v3.0.0                                             | |
#   | |     A Archipelago Discord Bot                                              | |
#   | |                   - By Quasky                                              | |
# __| |____________________________________________________________________________| |__
# __   ____________________________________________________________________________   __
#   | |                                                                            | |


#Core Dependencies
import asyncio
import json
import typing
import uuid
import os
import sys
from enum import Enum
import logging
import hashlib

#Threading Dependencies
from threading import Thread, Event
from multiprocessing import Queue, Process, Manager, freeze_support

#Plotting Dependencies
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

#Websocket Dependencies
import websockets
from websockets.sync.client import connect, ClientConnection

#Requests Dependencies
import requests
from bs4 import BeautifulSoup


#Discord Dependencies
from discord.ext import tasks
import discord
from discord import app_commands
from modules.player_commands import HINT_FIELD_MAX_LENGTH, HINT_NOT_REGISTERED_MESSAGE, register_player_commands
from modules.daily_post import (
    DailyPostConfigError,
    DailyPostState,
    load_daily_post_settings,
    run_daily_posts,
)
from modules.hint_relay import (
    HintRelayState,
    deliver_pending_hints,
    format_hint_status,
    hint_subscription_keys,
    normalize_requested_hint,
    render_hint_message,
    unused_corrupt_path,
)
from modules.config_store import save_config_atomic
from modules.room_endpoint import resolve_port, verify_seed
from modules.report_completion import all_locations_checked, deathlink_games_finished
from modules.tracker_recovery import TrackerRecovery
from modules.item_notifications import ItemNotificationState, resolved_hint_matches
import time

# Bridgeipelago Optional Modules
from modules.DeathlinkFlavor import GetFlavorText

global ConfigManager
global CoreConfig
global ConfigLock
global ToggleManager
global ToggleConfig
global ToggleLock

# Global Configuration Loader
## This allows us to share the config across multiple processes/threads without issue
def GenerateConfigManagers():
    global ConfigManager
    global CoreConfig
    global ConfigLock
    global ToggleManager
    global ToggleConfig
    global ToggleLock

    try:
        print("== Initilizing ConfigManager")
        if len(sys.argv) > 1 and sys.argv[1]:
            config = sys.argv[1]
        else:
            config = 'config.json'
        print("== Reading config from: " + config)

        # Initialize multiprocessing manager
        ConfigManager = Manager()
        ConfigLock = ConfigManager.RLock()

        # Load CoreConfig with our config.json
        config_data = json.loads(open(config).read())
        CoreConfig = ConfigManager.dict(config_data)

        # Convert nested dictionaries to manager dicts for full sharing
        for key, value in config_data.items():
            if isinstance(value, dict):
                CoreConfig[key] = ConfigManager.dict(value)
    except Exception as e:
        print("!!! Error loading config.json / Setting up ConfigManager:\n" + str(e))
        exit()

    # Global Toggle Loader
    ## This allows us to share the event bools across multiple processes/threads without issue
    try:
        # Initialize multiprocessing manager
        ToggleManager = Manager()
        ToggleLock = ToggleManager.RLock()
        ToggleConfig = ToggleManager.dict({"CrippleTracker": False, "RequestPortScan": False})
    except Exception as e:
        print("!!! Error setting up ToggleManager:\n" + str(e))
        exit()

# Core Filepath Functions
def GetCoreDirectory(folder):
    global CoreConfig
    global ConfigLock
    if folder == "log":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["LoggingDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "reg":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["PlayerRegistrationDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "item":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["PlayerItemQueueDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "arch":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["ArchipelagoDataDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "core":
        return str(os.getcwd())

ItemQueueSafeChars = frozenset("0123456789 _.-")
ItemQueueReservedNames = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com" + str(number) for number in range(10)]
    + ["lpt" + str(number) for number in range(10)]
)

def ItemQueueFileFor(slot):
    # A slot name becomes a file name. Ordinary names (letters of any script,
    # ASCII digits, space, _, -, .) keep the historical "<name>.csv"; every other
    # character is percent-encoded, so the result can never contain a separator,
    # ':' (an NTFS stream), or a Windows device name.
    if slot is None:
        return None
    Name = str(slot).strip().lower()
    if not Name:
        return None
    Encoded = "".join(
        char if char in ItemQueueSafeChars or char.isalpha()
        else "".join("%{:02X}".format(byte) for byte in char.encode("utf-8", "surrogatepass"))
        for char in Name
    )
    if Name in (".", ".."):
        Encoded = Encoded.replace(".", "%2E")
    Base = Encoded.split(".", 1)[0].rstrip(" ")
    if Base in ItemQueueReservedNames:
        # Encode the first letter instead of adding a prefix: "_con" is a real
        # slot whose file is "_con.csv", and encoding never yields "%63" etc.
        # because the letters themselves are safe characters.
        Encoded = "%{:02X}".format(ord(Encoded[0])) + Encoded[1:]
    return GetCoreDirectory("item") + Encoded + ".csv"

def GetCoreFiles(file):
    global CoreConfig
    global ConfigLock
    if file == "botlog":
        return GetCoreDirectory("log") + 'BotLog.txt'
    elif file == "errorlog":
        return GetCoreDirectory("log") + 'ErrorLog.txt'
    elif file == "debuglog":
        return GetCoreDirectory("log") + 'DebugLog.txt'
    elif file == "deathlog":
        return GetCoreDirectory("log") + 'DeathLog.txt'
    elif file == "deathtimecode":
        return GetCoreDirectory("log") + 'DeathTimecode.txt'
    elif file == "deathplot":
        return GetCoreDirectory("log") + 'DeathPlot.png'
    elif file == "checkplot":
        return GetCoreDirectory("log") + 'CheckPlot.png'
    elif file == "archgamedump":
        return GetCoreDirectory("arch") + 'ArchGameDump.json'
    elif file == "archconnectiondump":
        return GetCoreDirectory("arch") + 'ArchConnectionDump.json'
    elif file == "archroomdata":
        return GetCoreDirectory("arch") + 'ArchRoomData.json'
    elif file == "archstatus":
        return GetCoreDirectory("arch") + 'ArchStatus.json'
    elif file == "hintrelay":
        return GetCoreDirectory("log") + 'HintRelay.json'
    elif file == "itemnotifications":
        return GetCoreDirectory("reg") + 'ItemNotifications.json'
    elif file == "lang":
        return GetCoreDirectory("core") + CoreConfig["MetaConfig"]["LanguageFile"] + ".lang"

def SetupLogger():
    global CoreConfig
    global ConfigLock
    # Debugging Logger Setup
    if CoreConfig["AdvancedConfig"]["DebugMode"] == True:
        print("++ Debug Mode Enabled - Writing Websocket debug log to " + GetCoreFiles("debuglog"))
        logging.basicConfig(
            filename=GetCoreFiles("debuglog"),
            format="%(asctime)s %(message)s",
            level=logging.DEBUG,
        )
        logger = logging.getLogger("websockets")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())

# Global Variable Declaration
ReconnectionTimer = 5
discord_client = None
tracker_client = None
RoomAsleep = False
ConnectionUnavailableSince = None
DailyPostTask = None
HintRelayTeam = None
HintRelayStateInstance = None
ItemNotificationStateInstance = None
PlayerCommandsSyncedEnabled = None

DEFAULT_CONNECTION_UNAVAILABLE_MESSAGE = "Archipelago connection unavailable. {room_url}"
DEFAULT_CONNECTION_RESTORED_MESSAGE = "Archipelago connection restored: {server_address}"

def RenderConnectionNotification(message_key, default_message, placeholders):
    """Render a configurable connection notice, falling back safely for bad config."""
    notification_config = CoreConfig.get("NotificationConfig", {})
    if not callable(getattr(notification_config, "get", None)):
        notification_config = {}
    message = notification_config.get(message_key)
    if not isinstance(message, str) or not message.strip():
        message = default_message
    for placeholder, value in placeholders.items():
        message = message.replace("{" + placeholder + "}", str(value))
    return message

def GetConnectionNotificationPlaceholders():
    """Build the values shared by unavailable and restored notices."""
    archipelago_config = CoreConfig.get("ArchipelagoConfig", {})
    if not callable(getattr(archipelago_config, "get", None)):
        archipelago_config = {}
    room_url = archipelago_config.get("ArchipelagoServerURL", "")
    try:
        room_host = room_url.split("/")[2]
    except (AttributeError, IndexError):
        room_host = ""
    room_port = archipelago_config.get("ArchipelagoPort", "")
    return {
        "room_url": "<" + str(room_url) + ">",
        "server_address": str(room_host) + ":" + str(room_port),
    }

## These are the main queues for processing data from the Archipelago Tracker to the Discord Bot
### Main Processing Queues
item_queue = Queue()
death_queue = Queue()
chat_queue = Queue()

### Operation/Control Queues
seppuku_queue = Queue()
discordseppuku_queue = Queue()
websocket_queue = Queue()
lottery_queue = Queue()
discordbridge_queue = Queue()
hint_queue = Queue()
hintprocessing_queue = Queue()

def QueueRoomSleepNotice(close_frame=None):
    """Record a 1001 disconnect; it does not establish that the room is asleep."""
    global ConnectionUnavailableSince
    if close_frame is None or getattr(close_frame, "code", None) != 1001:
        return
    if ConnectionUnavailableSince is None:
        ConnectionUnavailableSince = time.monotonic()

def QueueRoomWakeNotice():
    global RoomAsleep, ConnectionUnavailableSince, CoreConfig
    if ConnectionUnavailableSince is None:
        return
    # Recovery before a notice was emitted is a transient reconnect, so stay quiet.
    if not RoomAsleep:
        ConnectionUnavailableSince = None
        return
    placeholders = GetConnectionNotificationPlaceholders()
    message = RenderConnectionNotification("ConnectionRestoredMessage", DEFAULT_CONNECTION_RESTORED_MESSAGE, placeholders)
    chat_queue.put({"type": "CORE", "data": {"text": message}, "flag": "ROOM_WAKE"})
    RoomAsleep = False
    ConnectionUnavailableSince = None

def QueueRoomUnavailableNotice():
    global RoomAsleep, ConnectionUnavailableSince, CoreConfig
    if ConnectionUnavailableSince is None or RoomAsleep or time.monotonic() - ConnectionUnavailableSince < 60:
        return
    if not RoomAsleep:
        placeholders = GetConnectionNotificationPlaceholders()
        message = RenderConnectionNotification("ConnectionUnavailableMessage", DEFAULT_CONNECTION_UNAVAILABLE_MESSAGE, placeholders)
        chat_queue.put({"type": "CORE", "data": {"text": message}, "flag": "ROOM_SLEEP"})
        RoomAsleep = True

#Discord Bot Initialization
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)
tree = app_commands.CommandTree(discord_client)
try:
    if len(sys.argv) > 1 and sys.argv[1]:
        config = sys.argv[1]
    else:
        config = 'config.json'
    OverClockValue = (json.load(open(config, 'r')))["AdvancedConfig"]["QueueOverclock"]
except Exception as e:
    print("!!! Unable to load Overclock value from config, defaulting to 1 second.")
    print("!!! Error: " + str(e))
    OverClockValue = 1
#TO DO - Central Control for bot I'll just leave this in for now.
PlayerCommandsSyncedGuild = None

## ARCHIPELAGO TRACKER CLIENT + CORE FUNCTION
class TrackerClient():
    global CoreConfig
    global ConfigLock
    tags: set[str] = {'TextOnly','Tracker', 'DeathLink'}
    version: dict[str, any] = {"major": 0, "minor": 6, "build": 8, "class": "Version"}
    items_handling: int = 0b000  # This client does not receive any items
    # SetReply packets can arrive before the initial Retrieved baseline. Keep
    # only the newest few per store so a misbehaving server cannot grow this
    # buffer without bound.
    HINT_PREBASELINE_REPLY_LIMIT: int = 8

    class MessageCommand(Enum):
        BOUNCED = 'Bounced'
        PRINT_JSON = 'PrintJSON'
        ROOM_INFO = 'RoomInfo'
        DATA_PACKAGE = 'DataPackage'
        CONNECTED = 'Connected'
        CONNECTIONREFUSED = 'ConnectionRefused'

    def __init__(
        self,
        **kwargs: typing.Any
    ) -> None:
        self.server_uri = CoreConfig["ArchipelagoConfig"]['ArchipelagoServer']
        self.port = CoreConfig["ArchipelagoConfig"]['ArchipelagoPort']
        self.password = GetArchPassword()
        self.slot_name = CoreConfig["ArchipelagoConfig"]['ArchipelagoBotSlot']
        self.verbose_logging = CoreConfig["AdvancedConfig"]["DebugMode"]
        self.ap_connection_kwargs = kwargs
        self.uuid: int = uuid.getnode()
        self.ap_connection: ClientConnection = None
        self.socket_thread: Thread = None
        self.is_closed = Event()
        self.has_connected = False
        self.hint_baseline_keys = set()
        self.hint_store_keys = set()
        self.hint_prebaseline_replies = {}

    def run(self):
        #=== Main Run Loop ===
        global CoreConfig
        LastReceivedTime = time.monotonic()
        OutstandingPing = None
        PingSentTime = None
        try:
            """Handles incoming messages from the Archipelago MultiServer."""

            while not self.is_closed.is_set():
                #=== Message Loop ===#
                try:
                    RawMessage = self.ap_connection.recv(timeout=float(CoreConfig["AdvancedConfig"]["QueueOverclock"]))
                    LastReceivedTime = time.monotonic()
                    OutstandingPing = None
                    PingSentTime = None
                    for i in range(len(json.loads(RawMessage))):
                        args: dict = json.loads(RawMessage)[i]
                        cmd = args.get('cmd')
                        MessageObject = {"type": "APMessage", "data": args, "flag": "None"}

                        if CoreConfig["AdvancedConfig"]["DebugMode"] == True:
                            print(RawMessage)

                        if cmd == self.MessageCommand.ROOM_INFO.value:
                            try:
                                verify_seed(CoreConfig["ArchipelagoConfig"], args)
                            except ValueError:
                                self.ap_connection.close()
                                raise
                            WriteRoomInfo(args)
                            self.check_datapackage()
                            self.send_connect()
                        elif cmd == self.MessageCommand.DATA_PACKAGE.value:
                            WriteDataPackage(args)
                        elif cmd == self.MessageCommand.CONNECTED.value:
                            self.has_connected = True
                            QueueRoomWakeNotice()
                            WriteArchConnectionJSON(args)
                            print("-- Tracker connected to server.")
                            if CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
                                self.subscribe_hint_results(args)
                        elif cmd == 'Retrieved' and CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
                            retrieved = args.get('keys', {})
                            baseline_count = 0
                            baseline_hints = 0
                            if isinstance(retrieved, dict):
                                for key, values in retrieved.items():
                                    key = str(key)
                                    # Only keys we subscribed to become baselines.
                                    if key not in self.hint_baseline_keys:
                                        continue
                                    self.hint_baseline_keys.remove(key)
                                    # A null or otherwise non-list store is an
                                    # empty baseline. Otherwise its first
                                    # SetReply would be silently baselined.
                                    if not isinstance(values, list):
                                        values = []
                                    baseline_count += 1
                                    baseline_hints += len(values)
                                    self.queue_hint_snapshot(key, values)
                                    for early_values in self.hint_prebaseline_replies.pop(key, []):
                                        self.queue_hint_snapshot(key, early_values)
                            print("-- Hint relay baseline processed: {} stores, {} hints.".format(baseline_count, baseline_hints))
                        elif cmd == 'SetReply' and CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
                            values = args.get('value')
                            if isinstance(values, list):
                                key = str(args.get('key', ''))
                                if key not in self.hint_store_keys:
                                    continue
                                if key in self.hint_baseline_keys:
                                    self.buffer_prebaseline_reply(key, values)
                                else:
                                    self.queue_hint_snapshot(key, values)
                        elif cmd == self.MessageCommand.CONNECTIONREFUSED.value:
                            print("Tracker Connection refused by server - check your slot name / port / whatever, and try again.")
                            WriteToErrorLog("Websocket", "Tracker Connection refused by server - check your slot name / port / whatever, and try again.")
                            WriteToErrorLog("Websocket", str(args))
                            seppuku_queue.put(args)
                        elif cmd == self.MessageCommand.PRINT_JSON.value:
                            if args.get('type') == 'Hint' and CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
                                pass  # Hint PrintJSON is not sent to spectator clients; SetReply is authoritative.
                            elif args.get('type') == 'ItemSend':
                                item_queue.put(args)
                            elif args.get('type') == 'Chat':
                                if CoreConfig["RelayConfig"]["ChatMessages"] == True:
                                    chat_queue.put(MessageObject)
                            elif args.get('type') == 'ServerChat':
                                if CoreConfig["RelayConfig"]["ServerChatMessages"] == True:
                                     chat_queue.put(MessageObject)
                            elif args.get('type') == 'Goal':
                                print("writting to archstatus")
                                print(args,"===============")
                                WriteToArchStatus(args)
                                if CoreConfig["RelayConfig"]["GoalMessages"] == True:
                                    chat_queue.put(MessageObject)
                            elif args.get('type') == 'Release':
                                if CoreConfig["RelayConfig"]["ReleaseMessages"] == True:
                                    chat_queue.put(MessageObject)
                            elif args.get('type') == 'Collect':
                                if CoreConfig["RelayConfig"]["CollectMessages"] == True:
                                    chat_queue.put(MessageObject)
                            elif args.get('type') == 'Countdown':
                                if CoreConfig["RelayConfig"]["CountdownMessages"] == True:
                                    chat_queue.put(MessageObject)
                        elif 'DeathLink' in args.get('tags', []):
                            death_queue.put(args)
                        else:
                            WriteToErrorLog("Websocket", "Tracker Unhandled Message: " + str(args))
                        pass
                except websockets.exceptions.ConnectionClosedError as e:
                    if self.is_closed.is_set():
                        break
                    WriteToErrorLog("Websocket", "Tracker ConnectionClosedError: " + str(e))
                    QueueRoomSleepNotice(getattr(e, "rcvd", None))
                    websocket_queue.put("!! Tracker ConnectionClosedError ...")
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    if self.is_closed.is_set():
                        break
                    WriteToErrorLog("Websocket", "Tracker ConnectionClosed: " + str(e))
                    QueueRoomSleepNotice(getattr(e, "rcvd", None))
                    websocket_queue.put("!! Tracker ConnectionClosed ...")
                    break
                except websockets.exceptions.InvalidState as e:
                    if self.is_closed.is_set():
                        break
                    WriteToErrorLog("Websocket", "Tracker InvalidState: " + str(e))
                    websocket_queue.put("!! Tracker InvalidState ...")
                    break
                except TimeoutError as e:
                    pass
                except Exception as e:
                    WriteToErrorLog("Websocket", "Tracker Unspecified Exception: " + str(e))
                    websocket_queue.put("!! Tracker Unspecified Exception !?!?!?!? ...")
                    break
                CurrentTime = time.monotonic()
                if OutstandingPing is not None:
                    if OutstandingPing.is_set():
                        LastReceivedTime = CurrentTime
                        OutstandingPing = None
                        PingSentTime = None
                    elif CurrentTime - PingSentTime >= 20:
                        WriteToErrorLog("Websocket", "Tracker keepalive ping timed out after 20 seconds.")
                        websocket_queue.put("!! Tracker keepalive timeout ...")
                        break
                elif CurrentTime - LastReceivedTime >= 60:
                    OutstandingPing = self.ap_connection.ping()
                    PingSentTime = CurrentTime
                #=== End Message Loop ===#

                if not discordbridge_queue.empty():
                        received_payload = discordbridge_queue.get()
                        payload = {
                            'cmd': 'Say',
                            'text': str(received_payload)}
                        self.send_message(payload)

        except Exception as e:
            WriteToErrorLog("Websocket", "Tracker Unhandled exception in Main Run loop: " + str(e))
            websocket_queue.put("!! Tracker Unhandled exception in Main Run loop ...")
        #=== End Main Run Loop ===

    def send_connect(self) -> None:
        print("-- Sending `Connect` packet to log in to server.")
        payload = {
            'cmd': 'Connect',
            'game': '',
            'password': self.password,
            'name': self.slot_name,
            'version': self.version,
            'tags': list(self.tags),
            'items_handling': self.items_handling,
            'uuid': self.uuid,
        }
        self.send_message(payload)

    def check_datapackage(self) -> None:
        if CheckDatapackage():
            print("-- DataPackage is valid")
        else:
            print("-- DataPackage is invalid, requesting new one.")
            self.get_datapackage()

    def get_datapackage(self) -> None:
        print("-- Requesting DataPackage from server.")
        RequestedGames = json.load(open(GetCoreFiles("archroomdata"), 'r'))["games"]
        payload = {
            'cmd': 'GetDataPackage',
            'games': RequestedGames
        }
        self.send_message(payload)

    def send_message(self, message: dict) -> None:
        self.ap_connection.send(json.dumps([message]))

    def send_messages(self, messages: list[dict]) -> None:
        self.ap_connection.send(json.dumps(messages))

    def subscribe_hint_results(self, connected: dict) -> None:
        global HintRelayTeam
        team, keys = hint_subscription_keys(connected)
        HintRelayTeam = team
        self.hint_baseline_keys = set(keys)
        self.hint_store_keys = set(keys)
        self.hint_prebaseline_replies = {}
        print("-- Hint relay connected; subscribing to {} same-team hint stores.".format(len(keys)))
        if keys:
            self.send_messages([
                {"cmd": "SetNotify", "keys": keys},
                {"cmd": "Get", "keys": keys},
            ])

    def buffer_prebaseline_reply(self, key: str, values: list) -> None:
        replies = self.hint_prebaseline_replies.setdefault(key, [])
        replies.append(values)
        del replies[:-self.HINT_PREBASELINE_REPLY_LIMIT]

    def queue_hint_snapshot(self, key: str, values: list) -> None:
        values = [dict(hint) if isinstance(hint, dict) else hint for hint in values]
        for hint in values:
            if isinstance(hint, dict):
                hint.setdefault("team", HintRelayTeam)
        chat_queue.put({"type": "HINT_SNAPSHOT", "data": {"key": key, "hints": values}, "flag": "None"})

    def stop(self) -> None:
        self.is_closed.set()
        if self.ap_connection is not None:
            self.ap_connection.close()
        if self.socket_thread is not None:
            self.socket_thread.join(timeout=5)

    def start(self) -> None:
        print("-- Attempting to open an Archipelago MultiServer websocket connection in a new thread.")
        try:
            Port = resolve_port(CoreConfig["ArchipelagoConfig"],
                                CoreConfig["AdvancedConfig"].get("SelfHostNoWeb", False), requests.get)
            if Port != int(CoreConfig["ArchipelagoConfig"]["ArchipelagoPort"]):
                UpdateStatus = SetConfigVariable("ArchipelagoPort", Port)
                if UpdateStatus == "Unable to save configuration. No settings were changed.":
                    raise OSError("Could not persist refreshed room port")
                Host = CoreConfig["ArchipelagoConfig"]["ArchipelagoServer"].split("://")[-1]
                chat_queue.put({"type": "CORE", "data": {"text":
                    "The Archipelago room moved to a new port. Reconnect to **" + Host + ":" + str(Port) + "**"}, "flag": "PORT_CHANGE"})
            _ConnectionString = str(CoreConfig["ArchipelagoConfig"]['ArchipelagoServer']) + ":" + str(Port)
            self.is_closed.clear()
            self.has_connected = False
            self.ap_connection = connect(
                _ConnectionString,
                max_size=None,
                **self.ap_connection_kwargs
            )
            self.socket_thread: Thread = None
            self.socket_thread = Thread(target=self.run)
            self.socket_thread.daemon = True
            self.socket_thread.start()
        except Exception as e:
            print("Error while trying to connect to Archipelago MultiServer:")
            print(e)
            if isinstance(e, ConnectionRefusedError) or getattr(e, "errno", None) == 111 or getattr(e, "winerror", None) == 10061:
                # Refusal is not evidence that the room is asleep. If a 1001
                # candidate exists, retry attempts let the debounce mature.
                QueueRoomUnavailableNotice()
            websocket_queue.put("!! Tracker start error...")

## ARCHIPELAGO HINT CLIENT + CORE FUNCTION
class HintClient:
    global CoreConfig
    tags: set[str] = {'TextOnly'}
    version: dict[str, any] = {"major": 0, "minor": 6, "build": 0, "class": "Version"}
    items_handling: int = 0b000  # This client does not receive any items

    class MessageCommand(Enum):
        BOUNCED = 'Bounced'
        PRINT_JSON = 'PrintJSON'
        ROOM_INFO = 'RoomInfo'
        DATA_PACKAGE = 'DataPackage'
        CONNECTED = 'Connected'
        CONNECTIONREFUSED = 'ConnectionRefused'

    def __init__(
        self,
        slot_name: str,
        request_context: dict = None,
        **kwargs: typing.Any
    ) -> None:
        self.server_uri = CoreConfig["ArchipelagoConfig"]['ArchipelagoServer']
        self.port = CoreConfig["ArchipelagoConfig"]['ArchipelagoPort']
        self.password = GetArchPassword()
        self.slot_name = slot_name
        self.verbose_logging = CoreConfig["AdvancedConfig"]["DebugMode"]
        self.ap_connection_kwargs = kwargs
        self.request_context = request_context
        self.uuid: int = uuid.getnode()
        self.ap_connection: ClientConnection = None
        self.socket_thread: Thread = None
        self.is_closed = Event()
        self.team = None
        self.connected_slot = None
        self.hintqueuepayload = hintprocessing_queue.get()

    def run(self):
        global CoreConfig
        try:
            hintlooper=0
            while not self.is_closed.is_set():
                #=== Message Loop ===#
                try:
                    RawMessage = self.ap_connection.recv(timeout=0.1)
                    for i in range(len(json.loads(RawMessage))):
                        args: dict = json.loads(RawMessage)[i]
                        cmd = args.get('cmd')
                        MessageObject = {"type": "HTMessage", "data": args, "flag": "None"}
                        if cmd == self.MessageCommand.ROOM_INFO.value:
                            try:
                                verify_seed(CoreConfig["ArchipelagoConfig"], args)
                            except ValueError:
                                self.ap_connection.close()
                                raise
                            print("-- HintClient received ROOM_INFO sending CONNECT.")
                            self.send_connect()
                        elif cmd == self.MessageCommand.CONNECTED.value:
                            print("-- HintClient received CONNECTED.")
                            self.team = args.get('team')
                            self.connected_slot = args.get('slot')
                            self.process_hint()
                        elif cmd == self.MessageCommand.CONNECTIONREFUSED.value:
                            print("HintClient CONNECTION_REFUSED by server - check your slot name / port / whatever, and try again.")
                            MessageObject["data"] = {"text": "HintClient: ERROR - Connection Refused by server. Check your slot name / port / whatever, and try again."}
                            MessageObject["flag"] = "ERROR"
                            chat_queue.put(MessageObject)
                        elif cmd == self.MessageCommand.PRINT_JSON.value:
                            if args.get('type') == 'Hint':
                                hint = normalize_requested_hint(args, self.team)
                                request_context = getattr(self, "request_context", None)
                                if (request_context is not None and args.get('found') is not True
                                        and HintWatchMatchesRequest(request_context, hint)
                                        and args.get('receiving') == getattr(self, "connected_slot", None)
                                        and str(LookupSlot(str(getattr(self, "connected_slot", "")))).casefold()
                                            == str(request_context.get("slot", "")).casefold()):
                                    chat_queue.put({"type": "HINT_WATCH_RESOLVED", "data": {
                                        "hint": hint, "request_context": request_context,
                                        "slot": LookupSlot(str(self.connected_slot)),
                                    }, "flag": "None"})
                                if CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
                                    chat_queue.put({"type": "HINT_REQUESTED", "data": hint, "flag": "None"})
                                else:
                                    chat_queue.put(MessageObject)
                            elif args.get('type') == 'CommandResult':
                                chat_queue.put(MessageObject)
                            elif args.get('type') == 'Join' or args.get('type') == 'Tutorial' or args.get('type') == 'Chat':
                                pass
                            else:
                                print("-- HintClient received unhandled PRINT_JSON type." + str(args))
                        else:
                            print("-- HintClient received unknown command." + str(args))
                        pass
                except websockets.exceptions.ConnectionClosedError as e:
                    print(e)
                    self.is_closed.set()
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    print(e)
                    self.is_closed.set()
                    break
                except websockets.exceptions.InvalidState as e:
                    print(e)
                    self.is_closed.set()
                    break
                except TimeoutError as e:
                    pass
                except Exception as e:
                    print(e)
                    self.is_closed.set()
                    break
                if hintlooper >= 20:
                    self.stop()
                    time.sleep(3)
                    break
                time.sleep(0.5)
                hintlooper=hintlooper+1
                #=== End Message Loop ===#

        except Exception as e:
            WriteToErrorLog("Websocket", "HintClient Unhandled exception in Main Run loop: " + str(e))
            self.is_closed.set()
        #=== End Main Run Loop ===

    def send_connect(self) -> None:
        print("-- Sending `Connect` packet to log in to server.")
        payload = {
            'cmd': 'Connect',
            'game': '',
            'password': self.password,
            'name': self.slot_name,
            'version': self.version,
            'tags': list(self.tags),
            'items_handling': self.items_handling,
            'uuid': self.uuid,
        }
        self.send_message(payload)

    def send_message(self, message: dict) -> None:
        self.ap_connection.send(json.dumps([message]))

    def stop(self) -> None:
        self.is_closed.set()
        self.ap_connection.close()

    def start(self) -> None:

        print("-- Attempting to open an HintClient connection in a new thread.")
        try:
            Port = resolve_port(CoreConfig["ArchipelagoConfig"],
                                CoreConfig["AdvancedConfig"].get("SelfHostNoWeb", False), requests.get)
            if Port != int(CoreConfig["ArchipelagoConfig"]["ArchipelagoPort"]):
                UpdateStatus = SetConfigVariable("ArchipelagoPort", Port)
                if UpdateStatus == "Unable to save configuration. No settings were changed.":
                    raise OSError("Could not persist refreshed room port")
                Host = CoreConfig["ArchipelagoConfig"]["ArchipelagoServer"].split("://")[-1]
                chat_queue.put({"type": "CORE", "data": {"text":
                    "The Archipelago room moved to a new port. Reconnect to **" + Host + ":" + str(Port) + "**"}, "flag": "PORT_CHANGE"})
            _ConnectionString = str(CoreConfig["ArchipelagoConfig"]['ArchipelagoServer']) + ":" + str(Port)
            self.ap_connection = connect(
                _ConnectionString,
                max_size=None,
                **self.ap_connection_kwargs
            )
            self.socket_thread: Thread = None
            self.socket_thread = Thread(target=self.run)
            self.socket_thread.daemon = True
            self.socket_thread.start()
        except Exception as e:
            print("Error while trying to connect HintClient to Archipelago:")
            print(e)
            chat_queue.put("!! HintClient start error...")

    def process_hint(self, ) -> None:
        print("-- Requesting Hint from server.")
        received_payload = "!hint " + str(self.hintqueuepayload)
        payload = {
            'cmd': 'Say',
            'text': str(received_payload)}
        self.send_message(payload)


## DISCORD EVENT HANDLERS + CORE FUNTION
async def DailyReportCompletion():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"]:
        return False, False
    page = await asyncio.to_thread(
        requests.get, CoreConfig["ArchipelagoConfig"]["ArchipelagoTrackerURL"], timeout=15,
    )
    page.raise_for_status()
    return (all_locations_checked(page.content),
            deathlink_games_finished(page.content, CoreConfig.get("DailyPostConfig", {}).get("DeathLinkSlots")))


async def PostDailyStats():
    progress_finished, deathlink_finished = await DailyReportCompletion()
    failures = []
    reports = []
    if not progress_finished:
        reports.extend((("check count", Command_CheckCount), ("check graph", Command_CheckGraph)))
    if not deathlink_finished:
        reports.append(("death count", Command_DeathCount))
    # Try every report even if one fails, so a broken report does not
    # hide the other one. The scheduler logs the raised error and tries again
    # at the next day's scheduled time rather than retrying later today.
    for name, report in reports:
        try:
            delivered = await report()
        except Exception as error:
            failures.append("%s raised %s: %s" % (
                name, type(error).__name__, error
            ))
            continue
        if delivered is False:
            failures.append(name + " did not deliver")

    if failures:
        raise RuntimeError("; ".join(failures) + ".")

def ReportDailyPostError(error):
    message = "Daily post failed: " + str(error)
    print("!!! " + message)
    try:
        WriteToErrorLog("DailyPost", message)
    except Exception:
        pass

async def StartDailyPostScheduler():
    global DailyPostTask
    try:
        settings = load_daily_post_settings(CoreConfig.get("DailyPostConfig"))
    except DailyPostConfigError as error:
        message = "Daily post configuration error: " + str(error)
        print("!!! " + message)
        try:
            WriteToErrorLog("DailyPost", message)
        except Exception:
            pass
        try:
            await DebugChannel.send(message)
        except Exception:
            pass
        return

    if settings is None:
        return
    if DailyPostTask is not None and not DailyPostTask.done():
        return

    state = DailyPostState(
        GetCoreDirectory("log") + "DailyPostState.json",
        log=lambda message: print("!!! " + message),
    )
    DailyPostTask = discord_client.loop.create_task(
        run_daily_posts(
            settings,
            state,
            PostDailyStats,
            on_error=ReportDailyPostError,
        )
    )
    print("++ Daily post scheduled for %02d:%02d %s" % (
        settings.hour, settings.minute, settings.timezone_name
    ))

@discord_client.event
async def on_ready():
    global MainChannel
    global PlayerCommandsSyncedEnabled
    MainChannel = discord_client.get_channel(int(CoreConfig["DiscordConfig"]["DiscordBroadcastChannel"]))
    #await MainChannel.send('Bot connected. Battle control - Online.')
    global DebugChannel
    DebugChannel = discord_client.get_channel(int(CoreConfig["DiscordConfig"]["DiscordDebugChannel"]))
    if CoreConfig["DiscordConfig"].get("AnnounceConnection", False) and DebugChannel is not None:
        await DebugChannel.send('Bot connected. Debug control - Online.')

    #Start background tasks
    if not CheckArchHost.is_running():
        CheckArchHost.start()
    if not ProcessItemQueue.is_running():
        ProcessItemQueue.start()
    if not ProcessDeathQueue.is_running():
        ProcessDeathQueue.start()
    if not ProcessChatQueue.is_running():
        ProcessChatQueue.start()
    if not CheckCommandQueue.is_running():
        CheckCommandQueue.start()
    await StartDailyPostScheduler()

    # Keep relay work available even if Discord command registration is unavailable.
    global PlayerCommandsSyncedGuild
    guild = getattr(MainChannel, "guild", None) if MainChannel is not None else None
    if guild is None:
        print("Player command sync skipped: configured broadcast channel is missing or has no guild.")
    else:
        guild_id = guild.id
        if PlayerCommandsSyncedGuild != guild_id or PlayerCommandsSyncedEnabled != SlashCommandsEnabled():
            guild_object = discord.Object(id=guild_id)
            if SlashCommandsEnabled():
                tree.copy_global_to(guild=guild_object)
            else:
                tree.clear_commands(guild=guild_object)
            try:
                await tree.sync(guild=guild_object)
            except Exception as e:
                print("Player command sync failed for configured guild:", getattr(e, "status", None), type(e).__name__)
            else:
                PlayerCommandsSyncedGuild = guild_id
                PlayerCommandsSyncedEnabled = SlashCommandsEnabled()

    print("++ ",CoreConfig["AdvancedConfig"]["JoinMessage"])
    print("++ Async bot started -", discord_client.user)

HelpText = """**Archipelago bot commands** (only work in this channel, lowercase)

**Get started**
`$register <slot>` - link your Discord to your slot (use your exact slot name)
`$listreg` - DM you the slots you're registered for
`$clearreg` - remove all your registrations

**Catch up** (results come by DM)
`$ketchmeup` - items other players sent you that you missed
  `$ketchmeup 2` progression only, `1` + useful, `0` everything
`$groupcheck <slot>` - all queued items for a slot
`$hints` - hinted items for your registered slots
`$notify off|all|watched` - turn item pings off, on for all registered slots, or only watched items
`$watch <slot> | <item>` / `$unwatch <slot> | <item>` - watch or stop watching an item
`$watches` - list your active item watches

**Hints & progress**
`$hint <slot> | <item>` - request a hint for a slot you're registered for, posted here
`$checkcount` - check counts for everyone
`$checkgraph` - progress graph
`$deathcount` - DeathLink tally

If the room moves to a new port, the bot posts the new address here."""

def IsBotAdmin(author):
    # Only trust the guild permissions supplied by Discord; never parse roles
    # or names from the message itself.
    permissions = getattr(author, "guild_permissions", None)
    if permissions is None:
        return False
    return bool(getattr(permissions, "administrator", False) or getattr(permissions, "manage_guild", False))

def SlashCommandsEnabled():
    config = CoreConfig.get("CommandConfig", {})
    if not callable(getattr(config, "get", None)):
        config = {}
    value = config.get("SlashCommandsEnabled", True)
    return value if isinstance(value, bool) else True

def PrefixCommandsEnabled():
    config = CoreConfig.get("CommandConfig", {})
    if not callable(getattr(config, "get", None)):
        config = {}
    value = config.get("PrefixCommandsEnabled", True)
    return value if isinstance(value, bool) else True

def ItemNotificationsEnabled():
    config = CoreConfig.get("NotificationConfig", {})
    if not callable(getattr(config, "get", None)):
        config = {}
    return config.get("ItemMentionsEnabled", False) is True

def GetItemNotificationState():
    global ItemNotificationStateInstance
    path = GetCoreFiles("itemnotifications")
    if ItemNotificationStateInstance is None or ItemNotificationStateInstance.path != path:
        ItemNotificationStateInstance = ItemNotificationState(path)
    return ItemNotificationStateInstance

def RegisteredSlotsFor(User):
    path = GetCoreDirectory("reg") + str(User) + ".json"
    try:
        with open(path, "r", encoding="utf-8") as source:
            slots = json.load(source)
        return slots if isinstance(slots, list) else []
    except (OSError, ValueError):
        return []

def RegisteredUserIDsForSlot(slot):
    return GetItemNotificationState().registered_user_ids(slot, GetCoreDirectory("reg"))

def HintWatchMatchesRequest(context, hint):
    """Only accept the server's result for the requested item, including clear typos."""
    try:
        game = LookupGame(str(hint.get("receiving_player")))
        with open(GetCoreFiles("archgamedump"), "r", encoding="utf-8") as source:
            games = json.load(source)
        return resolved_hint_matches(context.get("item", ""), hint.get("item"),
                                     games.get(game, {}).get("item_name_to_id", {}))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False

def ItemEventKey(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True, default=str).encode("utf-8")).hexdigest()

def HasActiveItemWatch(slot, item, event=None):
    """Whether a currently registered user has an active watch, regardless of ping consent."""
    state = GetItemNotificationState()
    if not state.available:
        return False
    if event is not None and state.was_delivered(ItemEventKey(event)):
        return False
    registered = set(str(user_id) for user_id in RegisteredUserIDsForSlot(slot))
    return any(
        any(state._same(watch, {"slot": slot, "item": item}) for watch in state.watches(user_id))
        for user_id in registered
    )

def ItemPassesChannelFilter(itemclass, slot, item, event=None):
    """Apply normal item filtering, with active watches overriding only level filtering."""
    itemclass = int(itemclass)
    if itemclass == 4:
        return CoreConfig["ItemFilterConfig"]["BotItemSpoilTraps"] is True
    return (ItemFilter(itemclass, CoreConfig["ItemFilterConfig"]["BotItemFilterLevel"])
            or HasActiveItemWatch(slot, item, event))

def IsRegisteredForSlot(User, slot):
    wanted = str(slot).casefold()
    return any(str(value).casefold() == wanted for value in RegisteredSlotsFor(str(User)))

def IsKnownItemForSlot(slot, item):
    try:
        with open(GetCoreFiles("archconnectiondump"), "r", encoding="utf-8") as source:
            connection = json.load(source)
        with open(GetCoreFiles("archgamedump"), "r", encoding="utf-8") as source:
            games = json.load(source)
        slot_id = next((key for key, value in connection.get("slot_info", {}).items()
                        if str(value.get("name", "")).casefold() == str(slot).casefold()), None)
        if slot_id is None:
            return False
        game = connection["slot_info"][slot_id].get("game")
        names = games.get(game, {}).get("item_name_to_id", {})
        return any(str(name).casefold() == str(item).casefold() for name in names)
    except (OSError, ValueError, KeyError, TypeError):
        return False

def UpdateItemNotificationMode(User, mode):
    state = GetItemNotificationState()
    user_id = getattr(User, "id", None)
    if RegisteredSlotsFor(str(User)):
        BindItemNotificationRegistration(User)
    result = state.set_mode(user_id, mode)
    return "Item notifications set to {}.".format(mode) if result else "Could not save notification preferences."

def BindItemNotificationRegistration(User):
    registration_slots = None
    try:
        with open(GetCoreDirectory("reg") + str(User) + ".json", "r", encoding="utf-8") as source:
            value = json.load(source)
        if isinstance(value, list) and all(isinstance(slot, str) for slot in value):
            registration_slots = value
    except (OSError, ValueError, TypeError):
        pass
    return GetItemNotificationState().bind_registration(getattr(User, "id", None), str(User), registration_slots)

def ForgetItemPreferences(User):
    return GetItemNotificationState().unregister(getattr(User, "id", None))

def UpdateItemWatch(User, slot, item, remove=False):
    if not IsRegisteredForSlot(User, slot):
        return "You can only watch items for a slot you're registered for."
    state = GetItemNotificationState()
    user_id = getattr(User, "id", None)
    BindItemNotificationRegistration(User)
    ok = state.remove_watch(user_id, slot, item) if remove else state.add_watch(user_id, slot, item)
    if not ok:
        return "Could not save your watch."
    if remove:
        return "Stopped watching {} for {}.".format(item, slot)
    return "Watching {} for {}. Item pings require `/notify all` or `/notify watched` consent.".format(item, slot)

def ListItemWatches(User):
    state = GetItemNotificationState()
    watches = state.watches(getattr(User, "id", None))
    mode = state.mode(getattr(User, "id", None))
    if not watches:
        return "You are not watching any items. Notification mode: {}.".format(mode)
    message = "**Watched items** (notification mode: {})\n".format(mode) + "\n".join("{} | {}".format(value["slot"], value["item"]) for value in watches)
    return message if len(message) <= 1900 else message[:1880] + "\n… more watches omitted."

def CanRequestHint(author, slot):
    # A hint spends the slot's own hint points, so only people registered to
    # that slot (or bot admins) may ask for one.
    if IsBotAdmin(author):
        return True
    RegistrationFile = GetCoreDirectory("reg") + str(author) + ".json"
    try:
        with open(RegistrationFile, "r") as RegistrationInput:
            RegisteredSlots = json.load(RegistrationInput)
    except (OSError, ValueError):
        return False
    if not isinstance(RegisteredSlots, list):
        return False
    WantedSlot = str(slot).strip().lower()
    return any(str(RegisteredSlot).strip().lower() == WantedSlot for RegisteredSlot in RegisteredSlots)

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    if message.channel.id != MainChannel.id:
        return

    if message.content.lstrip().startswith('$') and not PrefixCommandsEnabled():
        return

    # Registers user for a alot in Archipelago
    RegisterParts = message.content.split(None, 1)
    if RegisterParts and RegisterParts[0] == '$register':
        ArchSlot = RegisterParts[1].strip() if len(RegisterParts) > 1 else ""
        if ArchSlot == "":
            await SendMainChannelMessage("Use `$register <slot>` with the exact slot name from Archipelago.")
        else:
            Status = await Command_Register(str(message.author),ArchSlot)
            if Status.startswith("You've been registered") or Status.startswith("You're already registered"):
                BindItemNotificationRegistration(message.author)
            await SendMainChannelMessage(Status)

    # Clears registration file for user
    if message.content.startswith('$clearreg'):
        Status = await Command_ClearReg(str(message.author))
        if not ForgetItemPreferences(message.author):
            Status = str(Status) + " Item notification preferences could not be cleared; try again."
        elif Status == "You're not registered for any slots :(":
            Status = "You're not registered for slots; item preferences were cleared."
        await SendMainChannelMessage(Status)

    if message.content.startswith('$listreg'):
        await Command_ListRegistrations(message.author)

    # Opens a discord DM with the user, and fires off the Katchmeup process
    # When the user asks, catch them up on checks they're registered for
    ## Yoinks their registration file, scans through it, then find the related ItemQueue file to scan through
    if message.content.startswith('$ketchmeup'):
        await Command_KetchMeUp(message.author, message.content)

    # When the user asks, catch them up on the specified game
    ## Yoinks the specified ItemQueue file, scans through it, then sends the contents to the user
    ## Does NOT delete the file, as it's assumed the other users will want to read the file as well
    if message.content.startswith('$groupcheck'):
        game = message.content[len('$groupcheck'):].strip()
        if game == "":
            await SendMainChannelMessage("Use `$groupcheck <slot>` to see the queued items for a slot.")
        else:
            await Command_GroupCheck(message.author, game)

    if message.content.startswith('$hints'):
        await Command_Hints(message.author)

    NotifyParts = message.content.split(None, 1)
    if NotifyParts and NotifyParts[0] == '$notify':
        mode = NotifyParts[1].strip().lower() if len(NotifyParts) > 1 else ''
        if mode not in ('off', 'all', 'watched'):
            await SendMainChannelMessage("Use `$notify off`, `$notify all`, or `$notify watched`.")
        elif mode != 'off' and not RegisteredSlotsFor(str(message.author)):
            await SendMainChannelMessage("Register for a slot before changing notification settings.")
        elif mode != 'off' and not ItemNotificationsEnabled():
            await SendMainChannelMessage("Item notification pings are disabled by the bot administrator.")
        else:
            await SendMainChannelMessage(UpdateItemNotificationMode(message.author, mode))

    for command_name, remove in (('$watch', False), ('$unwatch', True)):
        if NotifyParts and NotifyParts[0] == command_name:
            fields = [value.strip() for value in (NotifyParts[1] if len(NotifyParts) > 1 else '').split('|', 1)]
            if len(fields) != 2 or not all(fields):
                await SendMainChannelMessage("Use `{}` <slot> | <item>.".format(command_name))
            elif not IsRegisteredForSlot(message.author, fields[0]):
                await SendMainChannelMessage(HINT_NOT_REGISTERED_MESSAGE)
            elif not IsKnownItemForSlot(fields[0], fields[1]):
                await SendMainChannelMessage("Use the exact item name for that slot.")
            else:
                await SendMainChannelMessage(UpdateItemWatch(message.author, fields[0], fields[1], remove))

    if NotifyParts and NotifyParts[0] == '$watches':
        await SendMainChannelMessage(ListItemWatches(message.author))

    HintParts = message.content.split(None, 1)
    if HintParts and HintParts[0] == '$hint':
        hintrequest = [item.strip() for item in (HintParts[1] if len(HintParts) > 1 else "").split('|', 1)]
        if not(len(hintrequest)==2 and all(hintrequest)):
            await SendMainChannelMessage("Invalid $hint format. Use `$hint <slot>|<item>`")
        elif any(len(field) > HINT_FIELD_MAX_LENGTH for field in hintrequest):
            await SendMainChannelMessage("Slot and item must each be {} characters or fewer.".format(HINT_FIELD_MAX_LENGTH))
        elif not CanRequestHint(message.author, hintrequest[0]):
            await SendMainChannelMessage(HINT_NOT_REGISTERED_MESSAGE)
        else:
            registered_at_request = IsRegisteredForSlot(message.author, hintrequest[0])
            if registered_at_request:
                BindItemNotificationRegistration(message.author)
            hint_queue.put({"slot": hintrequest[0], "item": hintrequest[1], "request_context": {
                "requester_id": getattr(message.author, "id", None),
                "requester_name": str(message.author),
                "registered_at_request": registered_at_request,
            }})
            await SendMainChannelMessage(str(message.author) + " requested a hint for " + hintrequest[0] + ": " + hintrequest[1])

    if message.content.startswith('$deathcount'):
        await Command_DeathCount()

    if message.content.startswith('$checkcount'):
        await Command_CheckCount()

    if message.content.startswith('$checkgraph'):
        await Command_CheckGraph()

    # Local patch: list the player commands.
    if message.content.startswith('$help'):
        await SendMainChannelMessage(HelpText)

    if message.content.startswith('$iloveyou'):
        await Command_ILoveYou(message)

    if message.content.startswith('$hello'):
        await Command_Hello(message)

    if message.content.startswith('$archinfo'):
        if not IsBotAdmin(message.author):
            await message.channel.send("Only server administrators can use that command.")
            return
        await Command_ArchInfo(message)

    if message.content.startswith('$setconfig'):
        if not IsBotAdmin(message.author):
            await message.channel.send("Only server administrators can use that command.")
            return
        settings = message.content[len('$setconfig'):].strip()
        key, separator, value = settings.partition(' ')
        value = value.strip()
        if separator == "" or key == "" or value == "":
            await SendMainChannelMessage("Invalid $setconfig format. Use `$setconfig <key> <value>`")
        else:
            rtrnmessage = SetConfigVariable(key, value)
            await SendMainChannelMessage(rtrnmessage)

    if message.content.startswith('$reloadtracker'):
        if not IsBotAdmin(message.author):
            await message.channel.send("Only server administrators can use that command.")
            return
        ReloadBot()
        await SendMainChannelMessage("Reloading tracker... Please wait about 5-10 seconds.")

    if message.content.startswith('$reloaddiscord'):
        if not IsBotAdmin(message.author):
            await message.channel.send("Only server administrators can use that command.")
            return
        discordseppuku_queue.put("Reloading Discord bot...")
        await SendMainChannelMessage("Reloading Discord bot... Please wait.")

    if not message.content.startswith('$') and CoreConfig["DrawbridgeConfig"]["DiscordBridgeEnabled"] == True:
        relayed_message = "(Discord) " + str(message.author) + " - " + str(message.content)
        discordbridge_queue.put(relayed_message)

@tasks.loop(seconds=1)
async def CheckCommandQueue():
    global CoreConfig
    global ToggleConfig

    if ToggleConfig["RequestPortScan"]:
        print("++ RequestPortScan set, checking ArchHost for port change.")
        with ToggleLock:
            ToggleConfig["RequestPortScan"] = False
        CheckArchHost.restart()

    if discordseppuku_queue.empty():
        return
    else:
        while not discordseppuku_queue.empty():
                QueueMessage = discordseppuku_queue.get()
        print("++ Shutting down Discord tasks")
        CheckArchHost.stop()
        ProcessItemQueue.stop()
        ProcessDeathQueue.stop()
        ProcessChatQueue.stop()

        print("++ Closing Discord Client")
        exit()

# Alert only after a sustained Archipelago status check outage.
CheckArchHostFailureCount = 0
CheckArchHostAlertSent = False

def AlertMention():
    AlertUserID = str(CoreConfig["DiscordConfig"].get("DiscordAlertUserID", "")).strip()
    if AlertUserID == "":
        return ""
    if AlertUserID.startswith("&"):
        if AlertUserID[1:].isdigit():
            return " <@&" + AlertUserID[1:] + ">"
    elif AlertUserID.isdigit():
        return " <@" + AlertUserID + ">"
    WriteToErrorLog("AlertMention", "DiscordAlertUserID must be a numeric user ID or '&role-id': " + AlertUserID)
    return ""

async def RecordCheckArchHostFailure(Error):
    global CheckArchHostFailureCount, CheckArchHostAlertSent
    CheckArchHostFailureCount += 1
    if CheckArchHostFailureCount >= 5 and not CheckArchHostAlertSent:
        LastError = str(Error).replace("\n", " ")[:200]
        await DebugChannel.send("ERROR IN CHECKARCHHOST: couldn't reach archipelago.gg for " + str(CheckArchHostFailureCount) + " checks in a row. Last error: " + LastError + AlertMention())
        CheckArchHostAlertSent = True

async def ResetCheckArchHostFailures():
    global CheckArchHostFailureCount, CheckArchHostAlertSent
    if CheckArchHostAlertSent:
        await DebugChannel.send("CheckArchHost recovered after " + str(CheckArchHostFailureCount) + " failed checks.")
    CheckArchHostFailureCount = 0
    CheckArchHostAlertSent = False



@tasks.loop(seconds=60)
async def CheckArchHost():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await CancelProcess()
    else:
        try:
            ArchRoomID = CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'].split("/")
            ArchAPIUEL = CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'].split("/room/")
            RoomAPI = ArchAPIUEL[0]+"/api/room_status/"+ArchRoomID[4]
            RoomPage = await asyncio.to_thread(requests.get, RoomAPI, timeout=10)
            RoomPage.raise_for_status()
            RoomData = json.loads(RoomPage.content)
            raw_last_port = RoomData["last_port"]
            if isinstance(raw_last_port, bool) or (isinstance(raw_last_port, float) and not raw_last_port.is_integer()):
                raise ValueError("last_port must be an integer")
            last_port = int(raw_last_port)
            if not 1 <= last_port <= 65535:
                raise ValueError("last_port must be between 1 and 65535")
            await ResetCheckArchHostFailures()

            if last_port == int(CoreConfig["ArchipelagoConfig"]['ArchipelagoPort']):
                return
            else:
                print("Port Check Failed")
                print(last_port)
                print(CoreConfig["ArchipelagoConfig"]['ArchipelagoPort'])
                message = "Port Check Failed.  New port is " + str(last_port) + "."
                #await MainChannel.send(message)
                await DebugChannel.send(message)
                # Local patch: tell players where the room moved.
                UpdateStatus = SetConfigVariable("ArchipelagoPort", last_port)
                if UpdateStatus == "Unable to save configuration. No settings were changed.":
                    raise OSError("Could not persist refreshed room port")
                RoomHost = CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'].split("/")[2]
                if MainChannel is not None:
                    await MainChannel.send("The Archipelago room moved to a new port. Reconnect to **" + RoomHost + ":" + str(last_port) + "**")

        # We catch both TypeError and JSONDecodeError becuase they are what are thrown when the Arch server is unresponsive.
        # We don't REALLY mind these, as it's a byproduct of the server being offline and we're unable to fetch it properly.
        # The bot will only scream when there is an unhandled error that we have to look into, as is the case with the other processes.
        except TypeError as e:
            WriteToErrorLog("CheckArchHost", "Error occurred while checking ArchHost: [TypeError] " + str(e))
            await RecordCheckArchHostFailure(e)
        except (json.JSONDecodeError, ValueError) as e:
            WriteToErrorLog("CheckArchHost", "Error occurred while checking ArchHost: [JSONDecodingError] " + str(e))
            await RecordCheckArchHostFailure(e)
        except Exception as e:
            WriteToErrorLog("CheckArchHost", "Error occurred while checking ArchHost: " + str(e))
            await RecordCheckArchHostFailure(e)

@tasks.loop(seconds=float(OverClockValue))
async def ProcessItemQueue():
    try:
        if item_queue.empty():
            return
        else:
            timecode = time.strftime("%Y||%m||%d||%H||%M||%S")
            itemmessage = item_queue.get()

            #if message has "found their" it's a self check, output and dont log
            query = itemmessage['data'][1]['text']
            if query == " found their ":
                game = str(LookupGame(itemmessage['data'][0]['text']))
                name = str(LookupSlot(itemmessage['data'][0]['text']))
                recipient = name
                item = str(LookupItem(game,itemmessage['data'][2]['text']))
                itemclass = str(itemmessage['data'][2]['flags'])
                location = str(LookupLocation(game,itemmessage['data'][4]['text']))

                iitem = SpecialFormat(item,ItemClassColor(int(itemclass)),0)
                message = "" + name + " found their " + iitem + "\nCheck: " + location


                ItemCheckLogMessage = name + "||" + item + "||" + name + "||" + location + "\n"
                BotLogMessage = timecode + "||" + ItemCheckLogMessage
                o = open(GetCoreFiles("botlog"), "a")
                o.write(BotLogMessage)
                o.close()

            elif query == " sent ":
                name = str(LookupSlot(itemmessage['data'][0]['text']))
                game = str(LookupGame(itemmessage['data'][0]['text']))
                recgame = str(LookupGame(itemmessage['data'][4]['text']))
                item = str(LookupItem(recgame,itemmessage['data'][2]['text']))
                itemclass = str(itemmessage['data'][2]['flags'])
                recipient = str(LookupSlot(itemmessage['data'][4]['text']))
                location = str(LookupLocation(game,itemmessage['data'][6]['text']))

                iitem = SpecialFormat(item,ItemClassColor(int(itemclass)),0)
                message = "" + name + " sent " + iitem + " to " + recipient + "\nCheck: " + location


                ItemCheckLogMessage = recipient + "||" + item + "||" + name + "||" + location + "||" + itemclass + "\n"
                BotLogMessage = timecode + "||" + ItemCheckLogMessage
                o = open(GetCoreFiles("botlog"), "a")
                o.write(BotLogMessage)
                o.close()

                if int(itemclass) == 4 and CoreConfig["ItemFilterConfig"]["BotItemSpoilTraps"] == True:
                    ItemQueueFile = ItemQueueFileFor(recipient)
                    if ItemQueueFile is None:
                        WriteToErrorLog("ItemQueue", "Refusing invalid item queue slot name: " + str(recipient))
                    else:
                        i = open(ItemQueueFile, "a")
                        i.write(ItemCheckLogMessage)
                        i.close()
                elif int(itemclass) != 4:
                    ItemQueueFile = ItemQueueFileFor(recipient)
                    if ItemQueueFile is None:
                        WriteToErrorLog("ItemQueue", "Refusing invalid item queue slot name: " + str(recipient))
                    else:
                        i = open(ItemQueueFile, "a")
                        i.write(ItemCheckLogMessage)
                        i.close()
            else:
                message = "Unknown Item Send :("
                print(message)
                await SendDebugChannelMessage(message)

            message = "```ansi\n" + message + "```"

            # If this item is for a player who's snoozed, we skip sending the message entirely
            if CheckSnoozeStatus(recipient):
                RecordFilteredItemArrival(recipient, item, itemmessage)
                await CancelProcess()
            elif ItemPassesChannelFilter(itemclass, recipient, item, itemmessage):
                await SendItemBroadcast(message, recipient, item, itemmessage)
            else:
                RecordFilteredItemArrival(recipient, item, itemmessage)
                #In Theory, this should only be called when the two above conditions are not met
                #So we call this dummy function to escape the async call.
                await CancelProcess()

    except Exception as e:
        WriteToErrorLog("ItemQueue", "Error occurred while processing item queue: " + str(e))
        print(e)
        await SendDebugChannelMessage("Error In Item Queue Process")

@tasks.loop(seconds=float(OverClockValue))
async def ProcessDeathQueue():
    if death_queue.empty():
        return
    else:
        chatmessage = death_queue.get()
        timecode = time.strftime("%Y||%m||%d||%H||%M||%S")
        DeathLogMessage = timecode + "||" + str(chatmessage['data']['source']) + "\n"
        o = open(GetCoreFiles("deathlog"), "a")
        o.write(DeathLogMessage)
        o.close()

        if CoreConfig["RelayConfig"]["DeathlinkMessages"] == True:
            DeathMessage = "**Deathlink!** "
            # Flavour
            if CoreConfig["MetaConfig"]["FlavorDeathlink"] == True:
                DeathMessage += GetFlavorText(str(chatmessage['data']['source']))
            else:
                DeathMessage += "Received from **" + str(chatmessage['data']['source']) + "**"
            # Cause
            if chatmessage['data'].get('cause') is not None and chatmessage['data'].get('cause') != "":
                DeathMessage += "\n" + "*Cause:* " + str(chatmessage['data']['cause'])
            await SendMainChannelMessage(DeathMessage)
        else:
            return

def _hint_lookup(lookup, *args, fallback):
    try:
        result = lookup(*args)
        return result if result not in (None, "", "NULL") else fallback
    except Exception:
        return fallback

async def SendHintResult(hint):
    receiver = str(hint.get("receiving_player", "?"))
    finder = str(hint.get("finding_player", "?"))
    receiver_game = str(_hint_lookup(LookupGame, receiver, fallback="Unknown game"))
    finder_game = str(_hint_lookup(LookupGame, finder, fallback="Unknown game"))
    receiver_name = str(_hint_lookup(LookupSlot, receiver, fallback="Player " + receiver))
    finder_name = str(_hint_lookup(LookupSlot, finder, fallback="Player " + finder))
    item = str(_hint_lookup(LookupItem, receiver_game, str(hint.get("item", "?")), fallback="Item #" + str(hint.get("item", "?"))))
    location = str(_hint_lookup(LookupLocation, finder_game, str(hint.get("location", "?")), fallback="Location #" + str(hint.get("location", "?"))))
    status = format_hint_status(hint.get("status"), hint.get("found", False))
    entrance = hint.get("entrance")
    entrance_text = " Entrance: " + str(entrance) if entrance else ""
    fallback = "Hint result: {receiver}'s {item} is at {finder}'s World at {location}. Status: {status}.{entrance}"
    notification_config = CoreConfig.get("NotificationConfig", {})
    if not callable(getattr(notification_config, "get", None)):
        notification_config = {}
    message = render_hint_message(notification_config.get("HintMessage"), fallback, {
        "receiver": receiver_name, "item": item, "location": location,
        "finder": finder_name, "status": status, "entrance": entrance_text,
    })
    await MainChannel.send(message, allowed_mentions=discord.AllowedMentions.none())

def ReportHintRelayDeliveryIssue(summary):
    """Log one short, payload-free hint delivery summary."""
    try:
        WriteToErrorLog("HintRelay", str(summary))
    except Exception:
        pass

async def InitializeHintRelayState():
    """Load durable hint relay state once, including pending deliveries."""
    global HintRelayStateInstance
    if HintRelayStateInstance is None:
        state = HintRelayState(GetCoreFiles("hintrelay"))
        HintRelayStateInstance = state
        if state.corrupt:
            # Logged once per process, when the state is first loaded.
            if state.corrupt_backup is not None:
                Notice = "Hint relay state was unreadable and was moved to " + state.corrupt_backup + "; the next store snapshots will be silently baselined."
            else:
                Notice = "Hint relay state was unreadable and could not be moved aside (" + str(state.corrupt_error) + "); saving stays blocked until it can be."
            print("-- " + Notice)
            WriteToErrorLog("HintRelay", Notice)
    return HintRelayStateInstance

async def DeliverPendingHintResults():
    """Send due pending hint results with per-item isolation."""
    state = HintRelayStateInstance
    if state is None:
        return 0
    return await deliver_pending_hints(state, SendHintResult, log=ReportHintRelayDeliveryIssue)

async def HandleHintRelayMessage(message):
    try:
        message_type = message.get("type") if isinstance(message, dict) else None
        if message_type == "HINT_WATCH_RESOLVED":
            data = message.get("data", {})
            hint = data.get("hint", {})
            context = data.get("request_context", {})
            requester_id = context.get("requester_id")
            if (context.get("registered_at_request") is True
                    and str(requester_id).isdigit()
                    and int(requester_id) in RegisteredUserIDsForSlot(data.get("slot", ""))):
                canonical_item = LookupItem(LookupGame(str(hint.get("receiving_player"))), hint.get("item"))
                if canonical_item not in (None, "", "NULL"):
                    if not GetItemNotificationState().add_watch(
                            int(requester_id), data.get("slot", ""), canonical_item):
                        ReportHintRelayDeliveryIssue("could not save resolved item watch")
            return
        state = await InitializeHintRelayState()
        if message_type == "HINT_SNAPSHOT":
            data = message.get("data", {})
            if isinstance(data, dict):
                state.observe_snapshot(data.get("key", ""), data.get("hints", []))
        elif message_type == "HINT_REQUESTED":
            state.enqueue_requested(message.get("data", {}))
    except Exception as e:
        ReportHintRelayDeliveryIssue("hint relay state update failed: " + type(e).__name__)
    await DeliverPendingHintResults()

@tasks.loop(seconds=float(OverClockValue))
async def ProcessChatQueue():
    # Messages are passed to the chat queue in the following format:
    #
    # MessageObject = {"type": "<type>", "data": args, "flag": <flag>}
    #
    # <type>:
    # "APMessage" - Standard Archipelago chat message
    # "HTMessage" - Hint Tracker message
    # "CORE" - Core system message
    #
    # <data>:
    #  {text: "message text here"}
    #
    # <flag>:
    # "None" - Standard message
    # "ERROR" - Error message
    #
    # MessageObject = {"type": "APMessage", "data": args, "flag": "None"}
    # MessageObject = {"type": "HTMessage", "data": args, "flag": "None"}
    # MessageObject = {"type": "CORE", "data": args, "flag": "None"}

    try:
        if CoreConfig.get("RelayConfig", {}).get("HintMessages", False) is True:
            try:
                await InitializeHintRelayState()
                await DeliverPendingHintResults()
            except Exception as e:
                # Hint delivery is best effort and must never starve chat.
                ReportHintRelayDeliveryIssue("hint relay delivery pass failed: " + type(e).__name__)
        if chat_queue.empty():
            return
        else:
            Message = chat_queue.get()
            if Message['type'] in ("HINT_SNAPSHOT", "HINT_REQUESTED", "HINT_WATCH_RESOLVED"):
                try:
                    await HandleHintRelayMessage(Message)
                except Exception as e:
                    # Never leak a full hint snapshot into the error log.
                    ReportHintRelayDeliveryIssue("hint relay message failed: " + type(e).__name__)
            elif Message['type'] == "CORE":
                if Message.get('flag') in ("ROOM_SLEEP", "ROOM_WAKE"):
                    await SendRoomConnectionNotice(Message)
                else:
                    await SendMainChannelMessage(Message['data']['text'])
            elif Message['type'] == "HTMessage":
                if Message['flag'] == "ERROR":
                    await SendMainChannelMessage(Message['data']['text'])
                elif Message['flag'] == "None":
                    if Message['data']['type'] == "CommandResult":
                        await SendMainChannelMessage("Hint Result: " + Message['data']['data'][0]['text'])
                    elif Message['data']['type'] == "Hint":
                        # I'm leaving these print()s in untill the feature is tested more. Pay no attention to the man behind the curtin.
                        #print("Hint received in chat queue.")

                        # Raw hint data for processing
                        networkitem = Message['data']['item']
                        receiverslotID = str(Message['data']['receiving'])
                        receiveritemID = str(networkitem['item'])
                        finderslotID = str(networkitem['player'])
                        finderlocationID = str(networkitem['location'])
                        found = Message['data']['found']

                        #print("receiverID: ", receiverslotID)
                        #print("receiveritemID: ", receiveritemID)
                        #print("finderslot: ", finderslotID)
                        #print("finderlocationID: ", finderlocationID)
                        #print("FOUND?: ", found)
                        #print("---")

                        #Translated hint data for user display
                        receiverGame = str(LookupGame(receiverslotID))
                        findersGame = str(LookupGame(finderslotID))
                        receiverSlot = str(LookupSlot(receiverslotID))
                        receiverItem = str(LookupItem(receiverGame, receiveritemID))
                        finderSlot = str(LookupSlot(finderslotID))
                        finderLocation = str(LookupLocation(findersGame, finderlocationID))

                        #print("receiverSlot: ", receiverSlot)
                        #print("receiverItem: ", receiverItem)
                        #print("finderSlot: ", finderSlot)
                        #print("finderLocation: ", finderLocation)

                        if found:
                            foundtext = SpecialFormat("(Found)",3,1)
                        else:
                            foundtext = SpecialFormat("(Not Found)",2,0)

                        FinishedHintMessage =  "```ansi\n" + foundtext + " " + receiverSlot + "\'s " + receiverItem + " is at " + finderSlot + "\'s World at " + finderLocation + "```"
                        #print(FinishedHintMessage)
                        await SendMainChannelMessage(FinishedHintMessage)
            elif Message['type'] == "APMessage":
                if Message['data']['type'] == 'Chat':
                    MessageMessage = Message['data']['message'].lower()
                    MessageText = Message['data']['data'][0]['text']
                    if (MessageText).startswith(CoreConfig["ArchipelagoConfig"]['ArchipelagoBotSlot']) and (
                        (MessageMessage).startswith('(discord)') or CoreConfig["RelayConfig"]["SendOwnSlotMessages"] == False
                    ):
                        await CancelProcess()
                    elif not MessageMessage.startswith("!"):
                        await SendMainChannelMessage(MessageText)
                    else:
                        if CoreConfig["RelayConfig"]["APClientHelp"] == True and MessageMessage.startswith("!help"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientLicense"] == True and MessageMessage.startswith("!license"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientCountdown"] == True and MessageMessage.startswith("!countdown"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientOptions"] == True and MessageMessage.startswith("!options"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientAdmin"] == True and MessageMessage.startswith("!admin"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientPlayers"] == True and MessageMessage.startswith("!players"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientStatus"] == True and MessageMessage.startswith("!status"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientRelease"] == True and MessageMessage.startswith("!release"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientCollect"] == True and MessageMessage.startswith("!collect"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientRemaining"] == True and MessageMessage.startswith("!remaining"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientMissing"] == True and MessageMessage.startswith("!missing"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientChecked"] == True and MessageMessage.startswith("!checked"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientAlias"] == True and MessageMessage.startswith("!alias"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientGetItem"] == True and MessageMessage.startswith("!getitem"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientHint"] == True and MessageMessage.startswith("!hint"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientHintLocation"] == True and MessageMessage.startswith("!hint_location"):
                            await SendMainChannelMessage(MessageText)
                        elif CoreConfig["RelayConfig"]["APClientVideo"] == True and MessageMessage.startswith("!video"):
                            await SendMainChannelMessage(MessageText)
                else:
                    await SendMainChannelMessage(Message['data']['data'][0]['text'])
            else:
                WriteToErrorLog("ChatQueue", "Unknown chat message type received: " + str(Message))
    except Exception as e:
        WriteToErrorLog("ChatQueue", "Error occurred while processing chat queue: " + str(e))
        print("ChatQueue - Error occurred while processing chat queue: " , str(e))
        await SendDebugChannelMessage("Error In Chat Queue Process")

async def SendMainChannelMessage(message):
    # Relayed Archipelago chat must never be able to ping @everyone or roles.
    await MainChannel.send(message, allowed_mentions=discord.AllowedMentions.none())

async def SendItemBroadcast(message, slot, item, event):
    """Post the existing item broadcast with only explicitly opted-in mentions."""
    registered_ids = RegisteredUserIDsForSlot(slot)
    event_key = ItemEventKey(event)
    state = GetItemNotificationState()
    recipients = [] if state.was_delivered(event_key) else state.recipients(slot, item, registered_ids)
    users = [discord.Object(id=user_id) for user_id in recipients]
    if not ItemNotificationsEnabled():
        users = []
    # Keep the normal case to one post: original item text plus all mentions
    # that fit under Discord's content and allowed-user limits.
    base = str(message)
    first_users, remaining = [], []
    first_text = base
    for user in users:
        mention = "<@{}>".format(user.id)
        appended = " " + mention
        if len(first_users) < 100 and len(first_text) + len(appended) <= 2000:
            first_users.append(user)
            first_text += appended
        else:
            remaining.append((user, mention))
    # Extremely long legacy text is chunked; actual item broadcasts fit one post.
    base_chunks = [first_text[i:i + 2000] for i in range(0, len(first_text), 2000)] or [""]
    await MainChannel.send(
        base_chunks[0],
        allowed_mentions=discord.AllowedMentions(users=first_users, roles=False, everyone=False, replied_user=False),
    )
    for chunk in base_chunks[1:]:
        await MainChannel.send(chunk, allowed_mentions=discord.AllowedMentions.none())
    # Overflow is exceptional. Keep each follow-up contextual and within both
    # Discord limits; the base post has already succeeded if an overflow send fails.
    overflow = []
    context = "More opted-in players for {} / {}: ".format(slot, item)
    current, current_length = [], len(context)
    for user, mention in remaining:
        added = len(mention) + (1 if current else 0)
        if current and (len(current) >= 100 or current_length + added > 2000):
            overflow.append(current)
            current, current_length, added = [], len(context), len(mention)
        current.append((user, mention))
        current_length += added
    if current:
        overflow.append(current)
    for chunk in overflow:
        content = context + " ".join(mention for _, mention in chunk)
        await MainChannel.send(content, allowed_mentions=discord.AllowedMentions(users=[user for user, _ in chunk], roles=False, everyone=False, replied_user=False))
    if not state.was_delivered(event_key):
        state.complete_delivery(event_key, slot, item, registered_ids)

def RecordFilteredItemArrival(slot, item, event):
    """Complete matching watches for an item observed but filtered from channel output."""
    key = ItemEventKey(event)
    state = GetItemNotificationState()
    if not state.was_delivered(key):
        state.complete_delivery(key, slot, item, RegisteredUserIDsForSlot(slot))

DEFAULT_SLEEP_WAKE_EDIT_WINDOW_MINUTES = 15
RoomSleepNoticeMessage = None
RoomSleepNoticeSentAt = None

def GetSleepWakeEditWindowSeconds():
    """NotificationConfig.SleepWakeEditWindowMinutes in seconds; 0 always posts a new wake notice."""
    notification_config = CoreConfig.get("NotificationConfig", {})
    if not callable(getattr(notification_config, "get", None)):
        notification_config = {}
    minutes = notification_config.get("SleepWakeEditWindowMinutes", DEFAULT_SLEEP_WAKE_EDIT_WINDOW_MINUTES)
    try:
        if isinstance(minutes, bool):
            raise ValueError("not a number of minutes")
        minutes = float(minutes)
    except (TypeError, ValueError):
        minutes = DEFAULT_SLEEP_WAKE_EDIT_WINDOW_MINUTES
    if not 0 <= minutes < float("inf"):
        minutes = DEFAULT_SLEEP_WAKE_EDIT_WINDOW_MINUTES
    return minutes * 60

async def SendRoomConnectionNotice(Message):
    """Post a sleep notice. If the room wakes soon after, edit that notice instead of posting again."""
    global RoomSleepNoticeMessage, RoomSleepNoticeSentAt
    text = Message['data']['text']
    SleepMessage = RoomSleepNoticeMessage
    SentAt = RoomSleepNoticeSentAt
    RoomSleepNoticeMessage = None
    RoomSleepNoticeSentAt = None
    if Message.get('flag') == "ROOM_SLEEP":
        RoomSleepNoticeMessage = await MainChannel.send(text, allowed_mentions=discord.AllowedMentions.none())
        RoomSleepNoticeSentAt = time.monotonic()
        return
    if SleepMessage is not None and time.monotonic() - SentAt < GetSleepWakeEditWindowSeconds():
        try:
            await SleepMessage.edit(content=text, allowed_mentions=discord.AllowedMentions.none())
            return
        except discord.HTTPException as e:
            # The notice may have been deleted; fall back to a new message.
            WriteToErrorLog("RoomNotice", "Could not edit the sleep notice, posting instead: " + type(e).__name__)
    await SendMainChannelMessage(text)

async def SendDebugChannelMessage(message):
    await DebugChannel.send(message)

async def SendDMMessage(message,user):
    await MainChannel.send(message)

def CatchupStartFileFor(Sender):
    # Registration files are keyed by the Discord name, so the start marks are too.
    SafeName = "".join(char if char.isalnum() or char in "-_." else "_" for char in str(Sender))
    if SafeName in ("", ".", ".."):
        SafeName = "user"
    return GetCoreDirectory("reg") + "catchup-start/" + SafeName + ".json"

def MoveCatchupStartAside(StartFile):
    """Keep an unreadable start-mark file for recovery. Returns False if it could not be moved."""
    try:
        os.replace(StartFile, unused_corrupt_path(StartFile))
        return True
    except OSError as e:
        WriteToErrorLog("CatchupStart", "Could not move unreadable catch-up start marks aside: " + str(e))
        return False

def LoadCatchupStart(Sender):
    """Return the start marks, or None when the file exists but cannot be read."""
    StartFile = CatchupStartFileFor(Sender)
    try:
        if not os.path.isfile(StartFile):
            return {}
        with open(StartFile, "r") as StartInput:
            Loaded = json.load(StartInput)
        if not isinstance(Loaded, dict):
            raise ValueError("catch-up start marks are not an object")
        return {str(Slot).strip().lower(): max(0, int(Count)) for Slot, Count in Loaded.items()}
    except Exception as e:
        WriteToErrorLog("CatchupStart", "Could not read catch-up start marks: " + str(e))
        # The other slots' marks are still in this file, so move it aside rather than let a write replace it.
        MoveCatchupStartAside(StartFile)
        return None

def RecordCatchupStart(Sender, ArchSlot):
    """Start a new registrant at the current end of the slot queue, not its full history."""
    try:
        ItemQueueFile = ItemQueueFileFor(ArchSlot)
        QueueLength = 0
        if ItemQueueFile is not None and os.path.isfile(ItemQueueFile):
            with open(ItemQueueFile, "r") as QueueInput:
                QueueLength = len(QueueInput.readlines())
        StartFile = CatchupStartFileFor(Sender)
        StartMarks = LoadCatchupStart(Sender)
        if StartMarks is None:
            if os.path.isfile(StartFile):
                # The unreadable file is still in place, so writing would erase the other slots' marks.
                WriteToErrorLog("CatchupStart", "Skipped recording catch-up start mark; unreadable marks left in place.")
                return
            StartMarks = {}
        StartMarks[str(ArchSlot).strip().lower()] = QueueLength
        os.makedirs(os.path.dirname(StartFile), exist_ok=True)
        TemporaryFile = StartFile + ".tmp"
        with open(TemporaryFile, "w") as StartOutput:
            json.dump(StartMarks, StartOutput, indent=4)
        os.replace(TemporaryFile, StartFile)
    except Exception as e:
        WriteToErrorLog("CatchupStart", "Could not record catch-up start mark: " + str(e))

async def Command_Register(Sender:str, ArchSlot:str):
    ArchSlot = str(ArchSlot).strip()
    try:
        if ItemQueueFileFor(ArchSlot) is None:
            return "That slot name is invalid. Use the exact slot name from Archipelago."

        #Compile the Registration File's path
        RegistrationFile = GetCoreDirectory("reg") + Sender + ".json"

        # If the file does not exist, we create it to prevent indexing issues
        if not os.path.exists(RegistrationFile):
            o = open(RegistrationFile, "w")
            o.write("[]")
            o.close()

        # Load the registration file
        RegistrationContents = json.load(open(RegistrationFile, "r"))

        # Check the registration file for ArchSlot, if they are not registered; do so. If they already are; tell them.
        if not ArchSlot in RegistrationContents:

            RegistrationContents.append(ArchSlot)
            json.dump(RegistrationContents, open(RegistrationFile, "w"), indent=4)
            RecordCatchupStart(Sender, ArchSlot)
            return "You've been registered for " + ArchSlot + "!"
        else:
            return "You're already registered for that slot."
    except Exception as e:
        WriteToErrorLog("Command_Register", "Error in register command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN REGISTER"+AlertMention())
        return "Critical error in REGISTER :("

async def Command_ListRegistrations(Sender):
    try:
        RegistrationFile = GetCoreDirectory("reg") + str(Sender) + ".json"

        # If the file does not exist, we create it to prevent indexing issues
        if not os.path.exists(RegistrationFile):
            o = open(RegistrationFile, "w")
            o.write("[]")
            o.close()

        RegistrationContents = json.load(open(RegistrationFile, "r"))
        if len(RegistrationContents) == 0:
            await Sender.send("You are not registered for any slots :(")
        else:
            Message = "**You are registered for:**\n"
            for slots in RegistrationContents:
                Message = Message + slots + "\n"
            await Sender.send(Message)
    except discord.Forbidden as e:
        WriteToErrorLog("Command_ListRegistrations", "Can not send a DM to "+ str(Sender) + " - " + str(e))
        await MainChannel.send("I can't send you a DM! Please check your privacy settings and try again.")
        return False
    except Exception as e:
        WriteToErrorLog("Command_ListRegistrations", "Error in list registrations command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN LISTREG"+AlertMention())
        return False

async def Command_ClearReg(Sender:str):
    try:
        RegistrationFile = GetCoreDirectory("reg") + Sender + ".json"
        if not os.path.exists(RegistrationFile):
            return "You're not registered for any slots :("
        os.remove(RegistrationFile)
        return "Your registration has been cleared."
    except Exception as e:
        WriteToErrorLog("Command_ClearReg", "Error in clear registration command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN CLEARREG"+AlertMention())

def CatchupUserKey(User):
    # One durable cursor per Discord user, keyed by user ID when it is known.
    UserID = getattr(User, "id", None)
    if UserID is None:
        UserKey = "".join(char if char.isalnum() or char in "-_." else "_" for char in str(User))
    else:
        UserKey = str(UserID)
    if UserKey in ("", ".", ".."):
        UserKey = "user"
    return UserKey

# One lock per user, keyed like the cursor file. Without it, two quick
# $ketchmeup calls read the same cursor and DM the same items twice.
CatchupLocks = {}

async def Command_KetchMeUp(User, message_filter):
    async with CatchupLocks.setdefault(CatchupUserKey(User), asyncio.Lock()):
        return await KetchMeUpLocked(User, message_filter)

async def KetchMeUpLocked(User, message_filter):
    try:
        message_filter = message_filter.replace("$ketchmeup","")
        message_filter = message_filter.replace("/ketchmeup","")
        message_filter = message_filter.strip()

        if message_filter == "" or message_filter == None:
            message_filter = 0
        try:
            message_filter = int(message_filter)
        except:
            message_filter = 0

        RegistrationFile = GetCoreDirectory("reg") + str(User) + ".json"
        if not os.path.isfile(RegistrationFile):
            await User.send("You've not registered for a slot : (")
        else:
            # Catching up never removes the shared queue from other players registered to the same slot.
            UserKey = CatchupUserKey(User)

            CursorDirectory = GetCoreDirectory("reg") + "catchup/"
            CursorFile = CursorDirectory + UserKey + ".json"
            Cursor = {}
            try:
                if os.path.isfile(CursorFile):
                    LoadedCursor = json.load(open(CursorFile, "r"))
                    if isinstance(LoadedCursor, dict):
                        for StoredSlot, Delivered in LoadedCursor.items():
                            try:
                                Cursor[str(StoredSlot).strip().lower()] = max(0, int(Delivered))
                            except (TypeError, ValueError):
                                continue
            except Exception as e:
                WriteToErrorLog("Command_KetchMeUp", "Could not read catch-up cursor: " + str(e))
                Cursor = {}

            try:
                os.makedirs(CursorDirectory, exist_ok=True)
            except OSError as e:
                WriteToErrorLog("Command_KetchMeUp", "Could not create catch-up cursor directory: " + str(e))

            def SaveCursor():
                TemporaryFile = CursorFile + ".tmp"
                try:
                    with open(TemporaryFile, "w") as CursorOutput:
                        json.dump(Cursor, CursorOutput, indent=4)
                    os.replace(TemporaryFile, CursorFile)
                finally:
                    if os.path.exists(TemporaryFile):
                        os.remove(TemporaryFile)

            CatchupStart = LoadCatchupStart(User) or {}
            RegistrationContents = json.load(open(RegistrationFile, "r"))
            for reglines in RegistrationContents:
                SlotName = str(reglines).strip()
                ItemQueueFile = ItemQueueFileFor(SlotName)
                if ItemQueueFile is None:
                    await User.send("Skipping invalid slot name: " + SlotName)
                    continue
                if not os.path.isfile(ItemQueueFile):
                    await User.send("There are no items for " + SlotName + " :/")
                    continue
                k = open(ItemQueueFile, "r")
                ItemQueueLines = k.readlines()
                k.close()

                CursorKey = SlotName.strip().lower()
                if CursorKey not in Cursor:
                    # First catch-up: begin where this user registered.
                    Cursor[CursorKey] = CatchupStart.get(CursorKey, 0)
                Delivered = Cursor[CursorKey]
                if Delivered < 0 or Delivered > len(ItemQueueLines):
                    Delivered = 0

                YouWidth = len("You")
                ItemWidth = len("Item")
                SenderWidth = len("Sender")
                NewRows = []
                for line in ItemQueueLines[Delivered:]:
                    Fields = line.split("||")
                    if len(Fields) < 5:
                        continue
                    try:
                        ItemClass = int(Fields[4].strip())
                    except (TypeError, ValueError):
                        continue
                    if not ItemFilter(ItemClass, int(message_filter)):
                        continue
                    You = Fields[0].strip()
                    Item = Fields[1].strip()
                    Sender = Fields[2].strip()
                    Location = Fields[3].strip()
                    NewRows.append((You, Item, Sender, Location))
                    YouWidth = max(YouWidth, len(You))
                    ItemWidth = max(ItemWidth, len(Item))
                    SenderWidth = max(SenderWidth, len(Sender))

                if NewRows:
                    ketchupmessage = "```" + "You".ljust(YouWidth) + " || " + "Item".ljust(ItemWidth) + " || " + "Sender".ljust(SenderWidth) + " || Location\n"
                    for You, Item, Sender, Location in NewRows:
                        ketchupmessage = ketchupmessage + You.ljust(YouWidth) + " || " + Item.ljust(ItemWidth) + " || " + Sender.ljust(SenderWidth) + " || " + Location + "\n"

                        if len(ketchupmessage) > 1500:
                            ketchupmessage = ketchupmessage + "```"
                            await User.send(ketchupmessage)
                            ketchupmessage = "```"
                    ketchupmessage = ketchupmessage + "```"
                    if not ketchupmessage == "``````":
                        await User.send(ketchupmessage)

                # Only advance after every DM for this slot succeeded.
                Cursor[CursorKey] = len(ItemQueueLines)
                SaveCursor()
    except discord.Forbidden as e:
        WriteToErrorLog("Command_KetchMeUp", "Can not send a DM to "+ str(User) + " - " + str(e))
        await MainChannel.send("I can't send you a DM! Please check your privacy settings and try again.")
        return False
    except Exception as e:
        WriteToErrorLog("Command_KetchMeUp", "Error in ketch me up command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN KETCHMEUP"+AlertMention())
        return False

async def Command_GroupCheck(DMauthor, game):
    try:
        ItemQueueFile = ItemQueueFileFor(game)
        if ItemQueueFile is None:
            await DMauthor.send("That slot name is invalid.")
        elif not os.path.isfile(ItemQueueFile):
            await DMauthor.send("There are no items for " + game + " :/")
        else:
            k = open(ItemQueueFile, "r")
            ItemQueueLines = k.readlines()
            k.close()

            ketchupmessage = "```You || Item || Sender || Location \n"
            for line in ItemQueueLines:
                ketchupmessage = ketchupmessage + line
                if len(ketchupmessage) > 1900:
                    ketchupmessage = ketchupmessage + "```"
                    await DMauthor.send(ketchupmessage)
                    ketchupmessage = "```"
            ketchupmessage = ketchupmessage + "```"
            if not ketchupmessage == "``````":
                await DMauthor.send(ketchupmessage)
    except discord.Forbidden as e:
        WriteToErrorLog("Command_GroupCheck", "Can not send a DM to "+ str(DMauthor) + " - " + str(e))
        await MainChannel.send("I can't send you a DM! Please check your privacy settings and try again.")
        return False
    except Exception as e:
        WriteToErrorLog("Command_GroupCheck", "Error in group check command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN GROUPCHECK"+AlertMention())
        return False

async def Command_Hints(player):
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        await player.create_dm()

        page = await asyncio.to_thread(
            requests.get, CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'], timeout=15,
        )
        page.raise_for_status()
        soup = BeautifulSoup(page.content, "html.parser")

        #Yoinks table rows from the checks table
        tables = soup.find("table",id="hints-table")
        for slots in tables.find_all('tbody'):
            rows = slots.find_all('tr')


        RegistrationFile = GetCoreDirectory("reg") + player.name + ".json"
        if not os.path.isfile(RegistrationFile):
            await player.dm_channel.send("You've not registered for a slot : (")
        else:
            RegistrationContents = json.load(open(RegistrationFile, "r"))
            for reglines in RegistrationContents:

                message = "**Here are all of the hints assigned to "+ reglines.strip() +":**"
                await player.dm_channel.send(message)

                FinderWidth = 0
                ReceiverWidth = 0
                ItemWidth = 0
                LocationWidth = 0
                GameWidth = 0
                EntrenceWidth = 0
                FinderArray = [0]
                ReceiverArray = [0]
                ItemArray = [0]
                LocationArray = [0]
                GameArray = [0]
                EntrenceArray = [0]

                #Moves through rows for data
                for row in rows:
                    found = (row.find_all('td')[6].text).strip()
                    if(found == "✔"):
                        continue

                    finder = (row.find_all('td')[0].text).strip()
                    receiver = (row.find_all('td')[1].text).strip()
                    item = (row.find_all('td')[2].text).strip()
                    location = (row.find_all('td')[3].text).strip()
                    game = (row.find_all('td')[4].text).strip()
                    entrence = (row.find_all('td')[5].text).strip()

                    if(reglines.strip() == finder):
                        FinderArray.append(len(finder))
                        ReceiverArray.append(len(receiver))
                        ItemArray.append(len(item))
                        LocationArray.append(len(location))
                        GameArray.append(len(game))
                        EntrenceArray.append(len(entrence))

                FinderArray.sort(reverse=True)
                ReceiverArray.sort(reverse=True)
                ItemArray.sort(reverse=True)
                LocationArray.sort(reverse=True)
                GameArray.sort(reverse=True)
                EntrenceArray.sort(reverse=True)

                FinderWidth = FinderArray[0]
                ReceiverWidth = ReceiverArray[0]
                ItemWidth = ItemArray[0]
                LocationWidth = LocationArray[0]
                GameWidth = GameArray[0]
                EntrenceWidth = EntrenceArray[0]

                finder = "Finder"
                receiver = "Receiver"
                item = "Item"
                location = "Location"
                game = "Game"
                entrence = "Entrance"

                #Preps check message
                checkmessage = "```" + finder.ljust(FinderWidth) + " || " + receiver.ljust(ReceiverWidth) + " || " + item.ljust(ItemWidth) + " || " + location.ljust(LocationWidth) + " || " + game.ljust(GameWidth) + " || " + entrence +"\n"
                for row in rows:
                    found = (row.find_all('td')[6].text).strip()
                    if(found == "✔"):
                        continue

                    finder = (row.find_all('td')[0].text).strip()
                    receiver = (row.find_all('td')[1].text).strip()
                    item = (row.find_all('td')[2].text).strip()
                    location = (row.find_all('td')[3].text).strip()
                    game = (row.find_all('td')[4].text).strip()
                    entrence = (row.find_all('td')[5].text).strip()

                    if(reglines.strip() == finder):
                        checkmessage = checkmessage + finder.ljust(FinderWidth) + " || " + receiver.ljust(ReceiverWidth) + " || " + item.ljust(ItemWidth) + " || " + location.ljust(LocationWidth) + " || " + game.ljust(GameWidth) + " || " + entrence +"\n"

                    if len(checkmessage) > 1500:
                        checkmessage = checkmessage + "```"
                        await player.dm_channel.send(checkmessage)
                        checkmessage = "```"

                # Caps off the message
                checkmessage = checkmessage + "```"
                if not checkmessage == "``````":
                    await player.send(checkmessage)
    except discord.Forbidden as e:
        WriteToErrorLog("Command_Hints", "Can not send a DM to "+ str(player) + " - " + str(e))
        await MainChannel.send("I can't send you a DM! Please check your privacy settings and try again.")
        return False
    except Exception as e:
        WriteToErrorLog("Command_Hints", "Error in hints command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN HINTLIST"+AlertMention())
        return False

async def Command_DeathCount():
    fig = None
    try:
        d = open(GetCoreFiles("deathlog"),"r")
        DeathLines = d.readlines()
        d.close()
        deathdict = {}

        if len(DeathLines) == 0:
            await MainChannel.send("No deaths to report.")
            return True

        for deathline in DeathLines:
            DeathUser = deathline.split("||")[6]
            DeathUser = DeathUser.split("\n")[0]

            if not DeathUser in deathdict:
                deathdict[DeathUser] = 1
            else:
                deathdict[DeathUser] = deathdict[DeathUser] + 1

        deathdict = {key: value for key, value in sorted(deathdict.items())}
        deathnames = []
        deathcounts = []
        message = "**Death Counter:**\n```"
        deathkeys = deathdict.keys()
        for key in deathkeys:
            deathnames.append(str(key))
            deathcounts.append(int(deathdict[key]))
            message = message + "\n" + str(key) + ": " + str(deathdict[key])
        message = message + '```'
        await MainChannel.send(message)

        ### PLOTTING CODE ###
        with plt.xkcd():
            plt.logging.getLogger('matplotlib.font_manager').disabled = True

            # Change length of plot long axis based on player count
            if len(deathnames) >= 20:
                long_axis=32
            elif len(deathnames) >= 5:
                long_axis=16
            else:
                long_axis=8

            # Initialize Plot
            fig = plt.figure(figsize=(long_axis,8))
            ax = fig.add_subplot(111)

            # Index the players in order
            player_index = np.arange(0,len(deathnames),1)

            # Plot count vs. player index
            plot = ax.bar(player_index,deathcounts,color='darkorange')

            # Change "index" label to corresponding player name
            ax.set_xticks(player_index)
            ax.set_xticklabels(deathnames,fontsize=20,rotation=-45,ha='left',rotation_mode="anchor")

            # Set y-axis limits to make sure the biggest bar has space for label above it
            ax.set_ylim(0,max(deathcounts)*1.1)

            # Set y-axis to have integer labels, since this is integer data
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.tick_params(axis='y', labelsize=20)

            # Add labels above bars
            ax.bar_label(plot,fontsize=20)

            # Plot Title
            ax.set_title('Death Counts',fontsize=28)

        # Save image and send - any existing plot will be overwritten
        plt.savefig(GetCoreFiles("deathplot"), bbox_inches="tight")
        await MainChannel.send(file=discord.File(GetCoreFiles("deathplot")))
        return True
    except Exception as e:
        WriteToErrorLog("Command_DeathCount", "Error in death count command: " + str(e))
        await DebugChannel.send("ERROR DEATHCOUNT"+AlertMention())
        return False
    finally:
        if fig is not None:
            plt.close(fig)

async def Command_CheckCount():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        page = await asyncio.to_thread(
            requests.get,
            CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'],
            timeout=15,
        )
        page.raise_for_status()
        soup = BeautifulSoup(page.content, "html.parser")

        #Yoinks table rows from the checks table
        tables = soup.find("table",id="checks-table")
        for slots in tables.find_all('tbody'):
            rows = slots.find_all('tr')

        SlotWidth = 0
        GameWidth = 0
        StatusWidth = 0
        ChecksWidth = 0
        SlotArray = [0]
        GameArray = [0]
        StatusArray = [0]
        ChecksArray = [0]

        #Moves through rows for data
        for row in rows:
            slot = (row.find_all('td')[1].text).strip()
            game = (row.find_all('td')[2].text).strip()
            status = (row.find_all('td')[3].text).strip()
            checks = (row.find_all('td')[4].text).strip()

            SlotArray.append(len(slot))
            GameArray.append(len(game))
            StatusArray.append(len(status))
            ChecksArray.append(len(checks))

        SlotArray.sort(reverse=True)
        GameArray.sort(reverse=True)
        StatusArray.sort(reverse=True)
        ChecksArray.sort(reverse=True)

        SlotWidth = SlotArray[0]
        GameWidth = GameArray[0]
        StatusWidth = StatusArray[0]
        ChecksWidth = ChecksArray[0]

        slot = "Slot"
        game = "Game"
        status = "Status"
        checks = "Checks"
        percent = "%"

        #Preps check message
        checkmessage = "```" + slot.ljust(SlotWidth) + " || " + game.ljust(GameWidth) + " || " + checks.ljust(ChecksWidth) + " || " + percent +"\n"

        for row in rows:
            if len(checkmessage) > 1500:
                checkmessage = checkmessage + "```"
                await MainChannel.send(checkmessage)
                checkmessage = "```"
            slot = (row.find_all('td')[1].text).strip()
            game = (row.find_all('td')[2].text).strip()
            status = (row.find_all('td')[3].text).strip()
            checks = (row.find_all('td')[4].text).strip()
            percent = (row.find_all('td')[5].text).strip()
            checkmessage = checkmessage + slot.ljust(SlotWidth) + " || " + game.ljust(GameWidth) + " || " + checks.ljust(ChecksWidth) + " || " + percent + "\n"


        #Finishes the check message
        checkmessage = checkmessage + "```"
        await MainChannel.send(checkmessage)
        return True
    except Exception as e:
        WriteToErrorLog("Command_CheckCount", "Error in check count command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN CHECKCOUNT"+AlertMention())
        return False

async def Command_CheckGraph():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    fig = None
    try:
        response = await asyncio.to_thread(
            requests.get,
            CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'],
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        #Yoinks table rows from the checks table
        tables = soup.find("table",id="checks-table")
        for slots in tables.find_all('tbody'):
            rows = slots.find_all('tr')

        GameState = {}
        #Moves through rows for data
        for row in rows:
            # print("counting row")
            slot = (row.find_all('td')[1].text).strip()
            game = (row.find_all('td')[2].text).strip()
            status = (row.find_all('td')[3].text).strip()
            checks = (row.find_all('td')[4].text).strip()
            percent = (row.find_all('td')[5].text).strip()
            GameState[slot] = percent

        GameState = {key: value for key, value in sorted(GameState.items())}
        GameNames = []
        GameCounts = []
        deathkeys = GameState.keys()
        for key in deathkeys:
            GameNames.append(str(key))
            GameCounts.append(float(GameState[key]))

        ### PLOTTING CODE ###
        with plt.xkcd():
            # print("BUILDING PLOT")
            plt.logging.getLogger('matplotlib.font_manager').disabled = True

            # Change length of plot long axis based on player count
            if len(GameNames) >= 20:
                long_axis=32
            elif len(GameNames) >= 5:
                long_axis=16
            else:
                long_axis=8

            # Initialize Plot
            fig = plt.figure(figsize=(long_axis,8))
            ax = fig.add_subplot(111)

            # Index the players in order
            player_index = np.arange(0,len(GameNames),1)

            # Plot count vs. player index
            plot = ax.bar(player_index,GameCounts,color='darkorange')

            # Change "index" label to corresponding player name
            ax.set_xticks(player_index)
            ax.set_xticklabels(GameNames,fontsize=20,rotation=-45,ha='left',rotation_mode="anchor")

            # Set y-axis limits to make sure the biggest bar has space for label above it
            ax.set_ylim(0,max(GameCounts)*1.1)

            # Set y-axis to have integer labels, since this is integer data
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.tick_params(axis='y', labelsize=20)

            # Add labels above bars
            ax.bar_label(plot,fontsize=20)

            # Plot Title
            ax.set_title('Completion Percentage',fontsize=28)

        # Save image and send - any existing plot will be overwritten
        plt.savefig(GetCoreFiles("checkplot"), bbox_inches="tight")
        await MainChannel.send(file=discord.File(GetCoreFiles("checkplot")))
        return True
    except Exception as e:
        WriteToErrorLog("Command_CheckGraph", "Error in check graph command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN CHECKGRAPH"+AlertMention())
        return False
    finally:
        if fig is not None:
            plt.close(fig)

PLAYER_COMMAND_NAMES = register_player_commands(
    tree,
    {
        "help_text": """**Player slash commands**
/help — show this list
/register slot — register for a slot
/listreg — DM your registrations
/clearreg — remove your registrations
/ketchmeup filter — DM missed items (0 all, 1 useful and progression, 2 progression)
/groupcheck slot — DM queued items for a slot
/hints — DM assigned hints
/hint slot item — request a hint for a slot you're registered for
/notify mode — choose off, all registered slots, or watched items
/watch slot item — watch an item in a registered slot
/unwatch slot item — stop watching an item
/watches — list active item watches
/checkcount — post check counts
/checkgraph — post progress graph
/deathcount — post DeathLink tally""",
        "register": Command_Register,
        "listreg": Command_ListRegistrations,
        "clearreg": Command_ClearReg,
        "ketchmeup": Command_KetchMeUp,
        "groupcheck": Command_GroupCheck,
        "hints": Command_Hints,
        "hint_queue": lambda: hint_queue,
        "can_hint": CanRequestHint,
        "slash_enabled": SlashCommandsEnabled,
        "global_notifications_enabled": ItemNotificationsEnabled,
        "is_registered_user": lambda user: bool(RegisteredSlotsFor(str(user))),
        "is_registered_for_slot": IsRegisteredForSlot,
        "is_valid_item": IsKnownItemForSlot,
        "set_notify_mode": UpdateItemNotificationMode,
        "bind_registration": BindItemNotificationRegistration,
        "add_watch": lambda user, slot, item: UpdateItemWatch(user, slot, item),
        "remove_watch": lambda user, slot, item: UpdateItemWatch(user, slot, item, True),
        "list_watches": ListItemWatches,
        "clear_preferences": ForgetItemPreferences,
        "checkcount": Command_CheckCount,
        "checkgraph": Command_CheckGraph,
        "deathcount": Command_DeathCount,
    },
    lambda: CoreConfig["DiscordConfig"]["DiscordBroadcastChannel"],
)

async def EnforceSlashCommandToggle(interaction):
    if SlashCommandsEnabled():
        return True
    if not interaction.response.is_done():
        await interaction.response.send_message("Slash commands are disabled.", ephemeral=True)
    return False

tree.interaction_check = EnforceSlashCommandToggle


async def Command_ILoveYou(message):
    await message.channel.send("Thank you.  You make a difference in this world. :)")

async def Command_Hello(message):
    await message.channel.send('Hello!')

def RedactConfigValue(key, value):
    KeyName = str(key).lower()
    for SecretWord in ("token", "password", "secret"):
        if SecretWord in KeyName:
            return "<redacted>"
    return str(value)

async def Command_ArchInfo(message):
    if(CoreConfig["AdvancedConfig"]["DebugMode"] == True):
        print("== Discord Config")
        for key, value in CoreConfig["DiscordConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== ArchipelagoConfig Config")
        for key, value in CoreConfig["ArchipelagoConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== ItemFilterConfig Config")
        for key, value in CoreConfig["ItemFilterConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== RelayConfig Config")
        for key, value in CoreConfig["RelayConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== DrawbridgeConfig Config")
        for key, value in CoreConfig["DrawbridgeConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== MetaConfig Config")
        for key, value in CoreConfig["MetaConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))

        print("== AdvancedConfig Config")
        for key, value in CoreConfig["AdvancedConfig"].items():
            print(str(key) + ": " + RedactConfigValue(key, value))
    else:
        await message.channel.send("Debug Mode is disabled.")

## HELPER FUNCTIONS
def GetArchPassword():
    global CoreConfig
    if CoreConfig["ArchipelagoConfig"]['ArchipelagoPassword'] == None or CoreConfig["ArchipelagoConfig"]['ArchipelagoPassword'] == "<your_archipelago_password>":
        return None
    else:
        return CoreConfig["ArchipelagoConfig"]['ArchipelagoPassword']

def ConfirmSpecialFiles():
    # Make sure all of the directories exist before we start creating files
    if not os.path.exists(GetCoreDirectory("arch")):
        os.makedirs(GetCoreDirectory("arch"))

    if not os.path.exists(GetCoreDirectory("log")):
        os.makedirs(GetCoreDirectory("log"))

    if not os.path.exists(GetCoreDirectory("reg")):
        os.makedirs(GetCoreDirectory("reg"))

    if not os.path.exists(GetCoreDirectory("item")):
        os.makedirs(GetCoreDirectory("item"))

    #Logfile Initialization. We need to make sure the log files exist before we start writing to them.
    l = open(GetCoreFiles("deathlog"), "a")
    l.close()

    l = open(GetCoreFiles("botlog"), "a")
    l.close()

    l = open(GetCoreFiles("deathtimecode"), "a")
    l.close()

    if not os.path.exists(GetCoreFiles("archstatus")):
        json.dump({}, open(GetCoreFiles("archstatus"), "w"))

def WriteDataPackage(data):
    with open(GetCoreFiles("archgamedump"), 'w') as f:
        json.dump(data['data']['games'], f, indent=4)

def WriteArchConnectionJSON(data):
    with open(GetCoreFiles("archconnectiondump"), 'w') as f:
        json.dump(data, f, indent=4)

def WriteRoomInfo(data):
    with open(GetCoreFiles("archroomdata"), 'w') as f:
        json.dump(data, f, indent=4)

def WriteToArchStatus(data):
        #Try and read the data, if it doesn't work, make it blank.
        try:
            status_data = json.load(open(GetCoreFiles("archstatus"), 'r'))
        except:
            status_data = {}
            json.dump(status_data, open(GetCoreFiles("archstatus"), 'w'), indent=4)

        status_data = json.load(open(GetCoreFiles("archstatus"), 'r'))
        status_data[LookupSlot(str(data["slot"]))] = "Goal"
        json.dump(status_data, open(GetCoreFiles("archstatus"), 'w'), indent=4)
def CheckDatapackage():
    if os.path.exists(GetCoreFiles("archgamedump")):
        try:
            room_data = json.load(open(GetCoreFiles("archroomdata"), 'r'))
            datapackage_data = json.load(open(GetCoreFiles("archgamedump"), 'r'))

            for key in room_data["datapackage_checksums"]:
                room_game_checksum = room_data["datapackage_checksums"][key]
                datapackage_game_checksum = datapackage_data[key]["checksum"]
                if not room_game_checksum == datapackage_game_checksum:
                    return False
            return True
        except Exception as e:
            WriteToErrorLog("CheckDatapackage", "Error reading or validating datapackage: " + str(e))
            print("Unknown error in CheckDatapackage, returning False")
            return False
    else:
        return False

def CheckGameDump():
    if os.path.exists(GetCoreFiles("archgamedump")):
        return True
    else:
        return False

def CheckConnectionDump():
    if os.path.exists(GetCoreFiles("archconnectiondump")):
        return True
    else:
        return False

def LookupItem(game,id):
    with open(GetCoreFiles("archgamedump"), 'r') as f:
        _ArchGameJSON = json.load(f)

    for key in _ArchGameJSON[game]['item_name_to_id']:
        if str(_ArchGameJSON[game]['item_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")

def LookupLocation(game,id):
    with open(GetCoreFiles("archgamedump"), 'r') as f:
        _ArchGameJSON = json.load(f)

    for key in _ArchGameJSON[game]['location_name_to_id']:
        if str(_ArchGameJSON[game]['location_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")

def LookupSlot(slot):
    with open(GetCoreFiles("archconnectiondump"), 'r') as f:
        _ArchConnectionJSON = json.load(f)

    for key in _ArchConnectionJSON['slot_info']:
        if key == slot:
            return str(_ArchConnectionJSON['slot_info'][key]['name'])
    return str("NULL")

def LookupGame(slot):
    with open(GetCoreFiles("archconnectiondump"), 'r') as f:
        _ArchConnectionJSON = json.load(f)

    for key in _ArchConnectionJSON['slot_info']:
        if key == slot:
            return str(_ArchConnectionJSON['slot_info'][key]['game'])
    return str("NULL")

def CheckSnoozeStatus(slot):
    try:
        if CoreConfig["AdvancedConfig"]["SnoozeCompletedGames"] == True:
            TempStatusJSON = json.load(open(GetCoreFiles("archstatus"), 'r'))
            for key in TempStatusJSON:
                if key == slot:
                    return True
            return False
        else:
            return False
    except json.JSONDecodeError as e:
        print("!!! JSON Decode Error in CheckSnoozeStatus - Resetting ArchStatus.json just to be safe :)")
        with open(GetCoreFiles("archstatus"), 'w') as f:
            json.dump({}, f)
        return CheckSnoozeStatus(slot)
    except Exception as e:
        print("Error checking Snooze for: " + slot + " - " + str(e))
        return False


def ItemFilter(itmclass,itmfilterlevel):
    #Item Classes are stored in a bit array
    #0bCBA Where:
    #A is if the item is progression / logical
    #B is if the item is useful
    #C is if the item is a trap / spoil
    # (An in-review change is open for the bitflags to be expanded to 5 bits (0bEDCBA) see pull/4610)
    #
    # If ItemFilterLevel == 2 (Progression), only items with bit A are shown
    # If ItemFilterLevel == 1 (Progression + Useful), items with bits A OR B are shown
    # If ItemFilterLevel == 0 (Progression + Useful + Normal), all items are shown as we don't care about the bits
    #
    # (Bits are checked from right to left, so array 0b43210)

    if itmfilterlevel == 2:
        if(itmclass & ( 1 << 0 )):
            return True
        else:
            return False
    elif itmfilterlevel == 1:
        if(itmclass & ( 1 << 0 )):
            return True
        elif(itmclass & ( 1 << 1 )):
            return True
        else:
            return False
    elif itmfilterlevel == 0:
        return True
    else:
        #If the filter is misconfigured, just send the item. It's the user's fault. :)
        return True

def ItemClassColor(itmclass):
    if(itmclass & ( 1 << 0 )):
        return 4
    elif(itmclass & ( 1 << 1 )):
        return 5
    elif(itmclass & ( 1 << 2 )):
        return 2
    else:
        return 0

def SpecialFormat(text,color,format):

    #Text Colors
    #30: Gray   - 1
    #31: Red    - 2
    #32: Green  - 3
    #33: Yellow - 4
    #34: Blue   - 5
    #35: Pink   - 6
    #36: Cyan   - 7
    #37: White  - 8

    #Formats
    #1: Bold      - 1
    #4: Underline - 2

    icolor = 0
    iformat = 0

    match color:
        case 0:
            icolor = 0
        case 1:
            icolor = 30
        case 2:
            icolor = 31
        case 3:
            icolor = 32
        case 4:
            icolor = 33
        case 5:
            icolor = 34
        case 6:
            icolor = 35
        case 7:
            icolor = 36
        case 8:
            icolor = 37

    match format:
        case 0:
            iformat = 0
        case 1:
            iformat = 1
        case 2:
            iformat = 4

    itext =  "\u001b[" + str(iformat) + ";" + str(icolor) + "m" + text + "\u001b[0m"
    return itext

def SetConfigVariable(key, value):
    global CoreConfig, ToggleConfig, ConfigLock, ToggleLock
    if key not in ["ArchipelagoPort","ArchipelagoPassword","ArchipelagoTrackerURL","ArchipelagoServerURL","UniqueID"]:
        return "Invalid key. Only 'ArchipelagoPort', 'ArchipelagoPassword', 'ArchipelagoTrackerURL', 'ArchipelagoServerURL', and 'UniqueID' can be set."
    else:
        if key == "ArchipelagoPort":
            try:
                PortValue = int(str(value).strip())
            except (TypeError, ValueError):
                return "Invalid ArchipelagoPort. Use a whole number from 1 to 65535."
            if not 1 <= PortValue <= 65535:
                return "Invalid ArchipelagoPort. Use a whole number from 1 to 65535."
            value = PortValue
        if key == "UniqueID":
            UniqueIDValue = str(value)
            if UniqueIDValue in ("", ".", ".."):
                return "Invalid UniqueID. Use a plain value without path separators or control characters."
            if any(char in UniqueIDValue for char in ("/", "\\")):
                return "Invalid UniqueID. Use a plain value without path separators or control characters."
            if any(ord(char) < 32 or ord(char) == 127 for char in UniqueIDValue):
                return "Invalid UniqueID. Use a plain value without path separators or control characters."
        with ConfigLock:
            # Stage a detached snapshot; publish memory only after disk succeeds.
            config_for_json = {k: dict(v) if hasattr(v, 'keys') else v for k, v in CoreConfig.items()}
            config_for_json["ArchipelagoConfig"][key] = value
            try:
                save_config_atomic(config, config_for_json)
            except (OSError, TypeError, ValueError):
                # Do not echo exception text: it can contain config secrets.
                return "Unable to save configuration. No settings were changed."
            CoreConfig["ArchipelagoConfig"][key] = value
            if key == "ArchipelagoPort":
                with ToggleLock:
                    ToggleConfig["CrippleTracker"] = False

        #We'll reconfirm and reload the data locations since we can change values.
        ConfirmSpecialFiles()
        if key == "ArchipelagoPassword":
            return "Key 'ArchipelagoPassword' updated."
        return "Key '" + key + "' set to '" + str(value) + "'!"

def ReloadBot():
    global ToggleConfig
    ToggleConfig["CrippleTracker"] = False
    websocket_queue.put("+++ Discord requested the bot to be reloaded!")

def WriteToErrorLog(module,message):
    with open(GetCoreFiles("errorlog"), 'a') as f:
        put = "["+str(time.strftime("%Y-%m-%d-%H-%M-%S"))+"],["+module+"]," + message
        f.write(put + "\n")

def GetLanguage(key):
    try:
        LanguagePack = json.loads(open(GetCoreFiles("lang")).read())
        return LanguagePack[key]
    except KeyError:
        WriteToErrorLog("GetLanguage", "KeyError for language key: " + str(key))
        return "LANG_KEY_ERROR"

async def CancelProcess():
    return 69420

def Discord(shared_config,toggle_config,shared_item_queue, shared_death_queue, shared_chat_queue, shared_seppuku_queue, shared_discordseppuku_queue, shared_websocket_queue, shared_lottery_queue, shared_discordbridge_queue, shared_hint_queue, shared_hintprocessing_queue):
    global CoreConfig
    global ToggleConfig
    global item_queue
    global death_queue
    global chat_queue
    global seppuku_queue
    global discordseppuku_queue
    global websocket_queue
    global lottery_queue
    global discordbridge_queue
    global hint_queue
    global hintprocessing_queue

    CoreConfig = shared_config
    ToggleConfig = toggle_config
    item_queue = shared_item_queue
    death_queue = shared_death_queue
    chat_queue = shared_chat_queue
    seppuku_queue = shared_seppuku_queue
    discordseppuku_queue = shared_discordseppuku_queue
    websocket_queue = shared_websocket_queue
    lottery_queue = shared_lottery_queue
    discordbridge_queue = shared_discordbridge_queue
    hint_queue = shared_hint_queue
    hintprocessing_queue = shared_hintprocessing_queue

    print("++ Starting Discord Client")
    discord_client.run(str(CoreConfig["DiscordConfig"]["DiscordToken"]))


# ====== MAIN SCRIPT START ====
# The run method is blocking, so it will keep the program running
def main():
    global CoreConfig
    global ConfigLock
    global ToggleConfig
    global ToggleLock
    global ReconnectionTimer
    global discord_client
    global tracker_client
    global ConnectionUnavailableSince

    # Version Checking against GitHub
    try:
        BPversion = "live-v3.0.1"
        response = requests.get("https://api.github.com/repos/Quasky/bridgeipelago/releases/latest", timeout=15)
        response.raise_for_status()
        GHAPIjson = json.loads(response.content)
        if(GHAPIjson["tag_name"] != BPversion):
            print("You are not running the current release of Bridgeipelago.")
            print("The current version is: " + GHAPIjson["tag_name"] + " -- You are running: " + BPversion)
    except:
        print("Unable to query GitHub API for Bridgeipelago version!")

    # Generate the config managers and load the configs
    GenerateConfigManagers()
    #Setup Logging for the bot
    SetupLogger()
    # Confirm all of the core directories and files exist just to be safe
    ConfirmSpecialFiles()

    ## Threadded async functions
    if(CoreConfig["AdvancedConfig"]["DiscordJoinOnly"] == False):
        # Start the tracker client
        tracker_client = TrackerClient()

        # Start the tracker client in a seperate thread then sleep for 5 seconds to allow the datapackage to download.
        try:
            tracker_client.start()
        except Exception as e:
            WriteToErrorLog("TrackerClient", "Error starting tracker client: " + str(e))
            print("!!! Tracker can't start!")
            seppuku_queue.put("Tracker Client can't start! Seppuku initiated.")
        time.sleep(5)

        # Discord must start even if the room is asleep or the endpoint lookup
        # fails. The supervisor below retries; no stale dump is required to boot.
        print("== Tracker startup attempted; waiting for connection data if unavailable.")

    DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig, item_queue, death_queue, chat_queue, seppuku_queue, discordseppuku_queue, websocket_queue, lottery_queue, discordbridge_queue, hint_queue, hintprocessing_queue))
    DiscordThread.start()

    DiscordCycleCount = 0
    TrackerRetries = TrackerRecovery()

    ## Gotta keep the bot running!
    while True:
        if not CoreConfig["AdvancedConfig"]["DiscordJoinOnly"] and tracker_client.has_connected:
            TrackerRetries.connected()

        if (CoreConfig["AdvancedConfig"]["DiscordJoinOnly"] == False):
            if not ToggleConfig["CrippleTracker"] and TrackerRetries.ready(time.monotonic()):
                if tracker_client.socket_thread is None or not tracker_client.socket_thread.is_alive() or not websocket_queue.empty() or not seppuku_queue.empty():
                    print("-- Tracker is not running, requested a restart, or has failed, so we do the needful")

                    tracker_client.has_connected = False
                    if TrackerRetries.failed(time.monotonic()):
                        print("!! Tracker reconnect attempts failed; retrying every 60 seconds.")
                        if ConnectionUnavailableSince is None:
                            ConnectionUnavailableSince = time.monotonic() - 60
                        QueueRoomUnavailableNotice()
                    if not seppuku_queue.empty():
                        print("-- Tracker commited Seppuku, Requesting new port information")
                        print("-- Sleeping for 5 seconds to allow DiscordBot to process PortScan")
                        with ToggleLock:
                            ToggleConfig["RequestPortScan"] = True
                        time.sleep(5)

                    while not websocket_queue.empty():
                        SQMessage = websocket_queue.get()
                        print("-- clearing websocket queue -- ", SQMessage)
                    while not seppuku_queue.empty():
                        SQMessage = seppuku_queue.get()
                        print("-- clearing seppuku queue -- ", SQMessage)

                    print("-- Stopping Tracker...")
                    tracker_client.stop()
                    print("-- Sleeping for 3 seconds to allow the tracker to close")
                    time.sleep(3)
                    print("-- Restarting tracker client...")
                    tracker_client.start()
                    time.sleep(10)

        if not CoreConfig["AdvancedConfig"]["CycleDiscord"] == 0:
            DiscordCycleCount = DiscordCycleCount + 1
            if DiscordCycleCount == CoreConfig["AdvancedConfig"]["CycleDiscord"]:
                print("++ Issuing Discord close command")
                discordseppuku_queue.put("Discord thread is being killed to test if it can be restarted")
                time.sleep(3)

                print("++ Closing the discord thread")
                DiscordThread.close()

                print("++ Sleeping for 3 seconds to allow the discord thread to close")
                time.sleep(3)

                print("++ Starting the discord thread again")
                DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig, item_queue, death_queue, chat_queue, seppuku_queue, discordseppuku_queue, websocket_queue, lottery_queue, discordbridge_queue, hint_queue, hintprocessing_queue))
                DiscordThread.start()
                DiscordCycleCount = 0

        if not DiscordThread.is_alive():
            print("++ Discord thread is not running, restarting it")
            print("++ Closing the discord thread")
            DiscordThread.close()
            print("++ Sleeping for 3 seconds to allow the discord thread to close")
            time.sleep(3)
            print("++ Starting the discord thread again")
            DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig, item_queue, death_queue, chat_queue, seppuku_queue, discordseppuku_queue, websocket_queue, lottery_queue, discordbridge_queue, hint_queue, hintprocessing_queue))
            DiscordThread.start()

        if not hint_queue.empty():
            hint_object = hint_queue.get()
            if isinstance(hint_object, dict):
                hint_slot, hint_item = hint_object.get("slot", ""), hint_object.get("item", "")
                request_context = dict(hint_object.get("request_context") or {})
            else:
                hint_slot, hint_item = hint_object[0], hint_object[1]
                request_context = None
            if request_context is not None:
                request_context["slot"] = hint_slot
                request_context["item"] = hint_item
            hintprocessing_queue.put(hint_item)
            hint_client = HintClient(
                slot_name=hint_slot, request_context=request_context,
            )
            hint_client.start()
            time.sleep(5)

        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("   Closing Bot Thread - Have a good day :)")
            exit(1)

if __name__ == '__main__':
    freeze_support()
    main()

# On 7/12/2025 Bridgeipelago crashed the AP servers and caused Berserker to give me a code review:
# Berserker - One, what I showed, whatever this bridgeipelago is
# Exempt-Medic - It's some kind of AP Discord Bot
# Berserker - Well it's clearly programmed like shit
