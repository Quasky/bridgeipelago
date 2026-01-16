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
import json
import typing
import uuid
import os
from enum import Enum
import logging

#Threading Dependencies
from threading import Thread, Event
from multiprocessing import Queue, Process, Manager

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
import time

# Global Configuration Loader
## This allows us to share the config across multiple processes/threads without issue
try:
    # Initialize multiprocessing manager
    ConfigManager = Manager()
    ConfigLock = ConfigManager.RLock()
    
    # Load CoreConfig with our config.json
    config_data = json.loads(open('config.json').read())
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

# Metadata
def GetCoreDirectory(folder):
    global CoreConfig
    if folder == "log":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["LoggingDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "reg":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["PlayerRegistrationDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "item":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["PlayerItemQueueDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    elif folder == "arch":
        return str(os.getcwd() + CoreConfig["AdvancedConfig"]["ArchipelagoDataDirectory"] + CoreConfig["ArchipelagoConfig"]['UniqueID'] + '/')
    
def GetCoreFiles(file):
    global CoreConfig
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
ArchGameJSON = []
ArchConnectionJSON = []
ReconnectionTimer = 5

DiscordClient = None
tracker_client = None

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

# Version Checking against GitHub
try:
    BPversion = "pre-v3.0.0"
    GHAPIjson = json.loads(requests.get("https://api.github.com/repos/Quasky/bridgeipelago/releases/latest").content)
    if(GHAPIjson["tag_name"] != BPversion):
        print("You are not running the current release of Bridgeipelago.")
        print("The current version is: " + GHAPIjson["tag_name"] + " -- You are running: " + BPversion)
except:
    print("Unable to query GitHub API for Bridgeipelago version!")

#Discord Bot Initialization
intents = discord.Intents.default()
intents.message_content = True
DiscordClient = discord.Client(intents=intents)
tree = app_commands.CommandTree(DiscordClient)

#TO DO - Central Control for bot I'll just leave this in for now.
DiscordGuildID = 1171964435741544498

# Load Meta Modules if they are enabled in the config
if CoreConfig["MetaConfig"]["FlavorDeathlink"] == True:
    from modules.DeathlinkFlavor import GetFlavorText

## ARCHIPELAGO TRACKER CLIENT + CORE FUNCTION
class TrackerClient:
    global CoreConfig
    tags: set[str] = {'TextOnly','Tracker', 'DeathLink'}
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

    def run(self):
        #=== Main Run Loop ===
        global CoreConfig
        try:
            """Handles incoming messages from the Archipelago MultiServer."""
            
            while not self.is_closed.is_set():
                #=== Message Loop ===#
                try:
                    RawMessage = self.ap_connection.recv(timeout=float(CoreConfig["AdvancedConfig"]["QueueOverclock"]))
                    for i in range(len(json.loads(RawMessage))):
                        args: dict = json.loads(RawMessage)[i]
                        cmd = args.get('cmd')
                        MessageObject = {"type": "APMessage", "data": args, "flag": "None"}
                        
                        if CoreConfig["AdvancedConfig"]["DebugMode"] == True:
                            print(RawMessage)
                            
                        if cmd == self.MessageCommand.ROOM_INFO.value:
                            WriteRoomInfo(args)
                            self.check_datapackage()
                            self.send_connect()
                        elif cmd == self.MessageCommand.DATA_PACKAGE.value:
                            WriteDataPackage(args)
                        elif cmd == self.MessageCommand.CONNECTED.value:
                            WriteArchConnectionJSON(args)
                            print("-- Tracker connected to server.")
                        elif cmd == self.MessageCommand.CONNECTIONREFUSED.value:
                            print("Tracker Connection refused by server - check your slot name / port / whatever, and try again.")
                            WriteToErrorLog("Websocket", "Tracker Connection refused by server - check your slot name / port / whatever, and try again.")
                            WriteToErrorLog("Websocket", str(args))
                            seppuku_queue.put(args)
                        elif cmd == self.MessageCommand.PRINT_JSON.value:
                            if args.get('type') == 'ItemSend':
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
                    WriteToErrorLog("Websocket", "Tracker ConnectionClosedError: " + str(e))
                    websocket_queue.put("!! Tracker ConnectionClosedError ...")
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    WriteToErrorLog("Websocket", "Tracker ConnectionClosed: " + str(e))
                    websocket_queue.put("!! Tracker ConnectionClosed ...")
                    break
                except websockets.exceptions.InvalidState as e:
                    WriteToErrorLog("Websocket", "Tracker InvalidState: " + str(e))
                    websocket_queue.put("!! Tracker InvalidState ...")
                    break
                except TimeoutError as e:
                    pass
                except Exception as e:
                    WriteToErrorLog("Websocket", "Tracker Unspecified Exception: " + str(e))
                    websocket_queue.put("!! Tracker Unspecified Exception !?!?!?!? ...")
                    break
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
        payload = {
            'cmd': 'GetDataPackage'
        }
        self.send_message(payload)

    def send_message(self, message: dict) -> None:
        self.ap_connection.send(json.dumps([message]))

    def stop(self) -> None:
        self.is_closed.set()
        self.ap_connection.close()

    def start(self) -> None:
        print("-- Attempting to open an Archipelago MultiServer websocket connection in a new thread.")
        try:
            self.is_closed.clear()
            self.ap_connection = connect(
                f'{self.server_uri}:{self.port}',
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
            websocket_queue.put("!! Tracker start error...")


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
        **kwargs: typing.Any
    ) -> None:
        self.server_uri = CoreConfig["ArchipelagoConfig"]['ArchipelagoServer']
        self.port = CoreConfig["ArchipelagoConfig"]['ArchipelagoPort']
        self.password = GetArchPassword()
        self.slot_name = slot_name
        self.verbose_logging = CoreConfig["AdvancedConfig"]["DebugMode"]
        self.ap_connection_kwargs = kwargs
        self.uuid: int = uuid.getnode()
        self.ap_connection: ClientConnection = None
        self.socket_thread: Thread = None
        self.is_closed = Event()

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
                            print("-- HintClient received ROOM_INFO sending CONNECT.")
                            self.send_connect()
                        elif cmd == self.MessageCommand.CONNECTED.value:
                            print("-- HintClient received CONNECTED.")
                            self.process_hint()
                        elif cmd == self.MessageCommand.CONNECTIONREFUSED.value:
                            print("HintClient CONNECTION_REFUSED by server - check your slot name / port / whatever, and try again.")
                            MessageObject["data"] = {"text": "HintClient: ERROR - Connection Refused by server. Check your slot name / port / whatever, and try again."}
                            MessageObject["flag"] = "ERROR"
                            chat_queue.put(MessageObject)
                        elif cmd == self.MessageCommand.PRINT_JSON.value:
                            if args.get('type') == 'Hint':
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
            self.ap_connection = connect(
                f'{self.server_uri}:{self.port}',
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
            websocket_queue.put("!! HintClient start error...")

    def process_hint(self) -> None:
        print("-- Requesting Hint from server.")
        received_payload = hintprocessing_queue.get()
        received_payload = "!hint " + str(received_payload)
        payload = {
            'cmd': 'Say',
            'text': str(received_payload)}
        self.send_message(payload)


## DISCORD EVENT HANDLERS + CORE FUNTION
@DiscordClient.event
async def on_ready():
    global MainChannel
    MainChannel = DiscordClient.get_channel(int(CoreConfig["DiscordConfig"]["DiscordBroadcastChannel"]))
    #await MainChannel.send('Bot connected. Battle control - Online.')
    global DebugChannel
    DebugChannel = DiscordClient.get_channel(int(CoreConfig["DiscordConfig"]["DiscordDebugChannel"]))
    await DebugChannel.send('Bot connected. Debug control - Online.')

    # We wont sync the command tree for now, need to roll out central control first.
    #await tree.sync(guild=discord.Object(id=DiscordGuildID))

    #Start background tasks
    CheckArchHost.start()
    ProcessItemQueue.start()
    ProcessDeathQueue.start()
    ProcessChatQueue.start()
    CheckCommandQueue.start()

    print("++ ",CoreConfig["AdvancedConfig"]["JoinMessage"])
    print("++ Async bot started -", DiscordClient.user)

@DiscordClient.event
async def on_message(message):
    if message.author == DiscordClient.user:
        return
    
    if message.channel.id != MainChannel.id:
        return
    
    # Registers user for a alot in Archipelago
    if message.content.startswith('$register'):
        ArchSlot = message.content
        ArchSlot = ArchSlot.replace("$register ","")
        Status = await Command_Register(str(message.author),ArchSlot)
        await SendMainChannelMessage(Status)

    # Clears registration file for user
    if message.content.startswith('$clearreg'):
        Status = await Command_ClearReg(str(message.author))
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
        game = (message.content).split('$groupcheck ')
        await Command_GroupCheck(message.author, game[1])
    
    if message.content.startswith('$hints'):
        await Command_Hints(message.author)
    
    if message.content.startswith('$hint'):
        hintrequest = [item.strip() for item in ((message.content).split('$hint '))[1].split('|')]
        if(len(hintrequest)==2):
            hint_queue.put(hintrequest)
        else:
            await SendMainChannelMessage("Invalid $hint format. Use `$hint <slot>|<item>`")

    if message.content.startswith('$deathcount'):
        await Command_DeathCount()
    
    if message.content.startswith('$checkcount'):
        await Command_CheckCount()
    
    if message.content.startswith('$checkgraph'):
        await Command_CheckGraph()
    
    if message.content.startswith('$iloveyou'):
        await Command_ILoveYou(message)

    if message.content.startswith('$hello'):
        await Command_Hello(message)
    
    if message.content.startswith('$archinfo'):
        await Command_ArchInfo(message)

    if message.content.startswith('$setconfig'):
        pair = ((message.content).split('$setconfig '))[1].split(' ')
        rtrnmessage = SetEnvVariable(pair[0], pair[1])
        await SendMainChannelMessage(rtrnmessage)

    if message.content.startswith('$reloadtracker'):
        ReloadBot()
        await SendMainChannelMessage("Reloading tracker... Please wait about 5-10 seconds.")
    
    if message.content.startswith('$reloaddiscord'):
        discordseppuku_queue.put("Reloading Discord bot...")
        await SendMainChannelMessage("Reloading Discord bot... Please wait.")

    if message.content.startswith('$reloaddata'):
        ReloadJSONPackages()
        await SendMainChannelMessage("Reloading datavars... Please wait 2-3 seconds.")

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

@tasks.loop(seconds=60)
async def CheckArchHost():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await CancelProcess()
    else:
        try:
            ArchRoomID = CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'].split("/")
            ArchAPIUEL = CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'].split("/room/")
            RoomAPI = ArchAPIUEL[0]+"/api/room_status/"+ArchRoomID[4]
            RoomPage = requests.get(RoomAPI)
            RoomData = json.loads(RoomPage.content)

            cond = str(RoomData["last_port"])
            if(cond == CoreConfig["ArchipelagoConfig"]['ArchipelagoPort']):
                return
            else:
                print("Port Check Failed")
                print(RoomData["last_port"])
                print(CoreConfig["ArchipelagoConfig"]['ArchipelagoPort'])
                message = "Port Check Failed.  New port is " + str(RoomData["last_port"]) + "."
                #await MainChannel.send(message)
                await DebugChannel.send(message)
                SetEnvVariable("ArchipelagoPort", str(RoomData["last_port"]))
        except Exception as e:
            WriteToErrorLog("CheckArchHost", "Error occurred while checking ArchHost: " + str(e))
            await DebugChannel.send("ERROR IN CHECKARCHHOST <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

@tasks.loop(seconds=float(CoreConfig["AdvancedConfig"]["QueueOverclock"]))
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
                    ItemQueueFile = GetCoreDirectory("item") + recipient + ".csv"
                    i = open(ItemQueueFile, "a")
                    i.write(ItemCheckLogMessage)
                    i.close()
                elif int(itemclass) != 4:
                    ItemQueueFile = GetCoreDirectory("item") + recipient + ".csv"
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
                await CancelProcess()
            elif int(itemclass) == 4 and CoreConfig["ItemFilterConfig"]["BotItemSpoilTraps"] == True:
                await SendMainChannelMessage(message)
            elif int(itemclass) != 4 and ItemFilter(int(itemclass),CoreConfig["ItemFilterConfig"]["BotItemFilterLevel"]):
                await SendMainChannelMessage(message)
            else:
                #In Theory, this should only be called when the two above conditions are not met
                #So we call this dummy function to escape the async call.
                await CancelProcess()

    except Exception as e:
        WriteToErrorLog("ItemQueue", "Error occurred while processing item queue: " + str(e))
        print(e)
        await SendDebugChannelMessage("Error In Item Queue Process")

@tasks.loop(seconds=float(CoreConfig["AdvancedConfig"]["QueueOverclock"]))
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
            DeathMessage = "**Deathlink received from: " + str(chatmessage['data']['source']) + "**"
            if chatmessage['data'].get('cause') is not None and chatmessage['data'].get('cause') != "":
                DeathMessage = DeathMessage + "\n" + "Cause: " + str(chatmessage['data']['cause'])
            elif CoreConfig["MetaConfig"]["FlavorDeathlink"] == True:
                DeathMessage = "Deathlink: " + GetFlavorText(str(chatmessage['data']['source']))
            await SendMainChannelMessage(DeathMessage)
        else:
            return

@tasks.loop(seconds=float(CoreConfig["AdvancedConfig"]["QueueOverclock"]))
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
        if chat_queue.empty():
            return
        else:
            Message = chat_queue.get()
            if Message['type'] == "CORE":
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
                    if (MessageText).startswith(CoreConfig["ArchipelagoConfig"]['ArchipelagoBotSlot']):
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

@tree.command(name="register",
    description="Registers you for AP slot",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction,slot:str):
    Status = await Command_Register(str(interaction.user),slot)    
    await interaction.response.send_message(content=Status,ephemeral=True)

@tree.command(name="clearreg",
    description="Clears your registration file",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction):
    Status = await Command_ClearReg(str(interaction.user))
    await interaction.response.send_message(content=Status,ephemeral=True)
    
@tree.command(name="ketchmeup",
    description="Ketches the user up with missed items",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction,filter:str):
    await interaction.user.create_dm()
    UserDM = interaction.user
    await Command_KetchMeUp(UserDM, interaction.message.content)
    await interaction.response.send_message(content="Sending your missed items... Please Hold.",ephemeral=True)

@tree.command(name="groupcheck",
    description="Ketches the user up with group game missed items",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction, groupslot:str):
    await Command_GroupCheck(interaction.user, groupslot)
    await interaction.response.send_message(content="Sending group missed items... Please Hold.",ephemeral=True)

@tree.command(name="deathcount",
    description="Posts a deathcount chart and graph",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction):
    await Command_DeathCount()
    await interaction.response.send_message(content="Deathcount")

@tree.command(name="checkcount",
    description="Posts a check chart",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction):
    await Command_CheckCount()
    await interaction.response.send_message(content="Checkcount:")

@tree.command(name="checkgraph",
    description="Posts a check graph",
    guild=discord.Object(id=DiscordGuildID)
)
async def first_command(interaction):
    await Command_CheckGraph()
    await interaction.response.send_message(content="Checkgraph:")

async def SendMainChannelMessage(message):
    await MainChannel.send(message)

async def SendDebugChannelMessage(message):
    await DebugChannel.send(message)

async def SendDMMessage(message,user):
    await MainChannel.send(message)

async def Command_Register(Sender:str, ArchSlot:str):
    try:
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
            return "You've been registered for " + ArchSlot + "!"
        else:
            return "You're already registered for that slot."
    except Exception as e:
        WriteToErrorLog("Command_Register", "Error in register command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN REGISTER <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")
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
    except Exception as e:
        WriteToErrorLog("Command_ListRegistrations", "Error in list registrations command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN LISTREG <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

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
        await DebugChannel.send("ERROR IN CLEARREG <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_KetchMeUp(User, message_filter):
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
            RegistrationContents = json.load(open(RegistrationFile, "r"))
            for reglines in RegistrationContents:
                ItemQueueFile = GetCoreDirectory("item") + reglines.strip() + ".csv"
                if not os.path.isfile(ItemQueueFile):
                    await User.send("There are no items for " + reglines.strip() + " :/")
                    continue
                k = open(ItemQueueFile, "r")
                ItemQueueLines = k.readlines()
                k.close()
                os.remove(ItemQueueFile)
        
                YouWidth = 0
                ItemWidth = 0
                SenderWidth = 0
                YouArray = [0]
                ItemArray = [0]
                SenderArray = [0]
        
                for line in ItemQueueLines:
                    YouArray.append(len(line.split("||")[0]))
                    ItemArray.append(len(line.split("||")[1]))
                    SenderArray.append(len(line.split("||")[2]))
                
                YouArray.sort(reverse=True)
                ItemArray.sort(reverse=True)
                SenderArray.sort(reverse=True)
        
                YouWidth = YouArray[0]
                ItemWidth = ItemArray[0]
                SenderWidth = SenderArray[0]
        
                You = "You"
                Item = "Item"
                Sender = "Sender"
                Location = "Location"
        
                ketchupmessage = "```" + You.ljust(YouWidth) + " || " + Item.ljust(ItemWidth) + " || " + Sender.ljust(SenderWidth) + " || " + Location + "\n"
                for line in ItemQueueLines:
                    You = line.split("||")[0].strip()
                    Item = line.split("||")[1].strip()
                    Sender = line.split("||")[2].strip()
                    Location = line.split("||")[3].strip()
                    Class = line.split("||")[4].strip()

                    if ItemFilter(int(Class),int(message_filter)):
                        ketchupmessage = ketchupmessage + You.ljust(YouWidth) + " || " + Item.ljust(ItemWidth) + " || " + Sender.ljust(SenderWidth) + " || " + Location + "\n"

                    if len(ketchupmessage) > 1500:
                        ketchupmessage = ketchupmessage + "```"
                        await User.send(ketchupmessage)
                        ketchupmessage = "```"
                ketchupmessage = ketchupmessage + "```"
                if not ketchupmessage == "``````":
                    await User.send(ketchupmessage)
    except Exception as e:
        WriteToErrorLog("Command_KetchMeUp", "Error in ketch me up command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN KETCHMEUP <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_GroupCheck(DMauthor, game):
    try:
        ItemQueueFile = GetCoreDirectory("item") + game + ".csv"
        if not os.path.isfile(ItemQueueFile):
            await DMauthor.send("There are no items for " + game[1] + " :/")
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
    except Exception as e:
        WriteToErrorLog("Command_GroupCheck", "Error in group check command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN GROUPCHECK <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_Hints(player):
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return
    
    try:
        await player.create_dm()

        page = requests.get(CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'])
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
    except Exception as e:
        WriteToErrorLog("Command_Hints", "Error in hints command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN HINTLIST <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_DeathCount():
    try:
        d = open(GetCoreFiles("deathlog"),"r")
        DeathLines = d.readlines()
        d.close()
        deathdict = {}

        if len(DeathLines) == 0:
            await MainChannel.send("No deaths to report.")
            return
        
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
    except Exception as e:
        WriteToErrorLog("Command_DeathCount", "Error in death count command: " + str(e))
        await DebugChannel.send("ERROR DEATHCOUNT <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_CheckCount():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        page = requests.get(CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'])
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
    except Exception as e:
        WriteToErrorLog("Command_CheckCount", "Error in check count command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN CHECKCOUNT <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_CheckGraph():
    if CoreConfig["AdvancedConfig"]["SelfHostNoWeb"] == True:
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        page = requests.get(CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'])
        soup = BeautifulSoup(page.content, "html.parser")

        #Yoinks table rows from the checks table
        tables = soup.find("table",id="checks-table")
        for slots in tables.find_all('tbody'):
            rows = slots.find_all('tr')

        GameState = {}
        #Moves through rows for data
        for row in rows:
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
    except Exception as e:
        WriteToErrorLog("Command_CheckGraph", "Error in check graph command: " + str(e))
        print(e)
        await DebugChannel.send("ERROR IN CHECKGRAPH <@"+str(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])+">")

async def Command_ILoveYou(message):
    await message.channel.send("Thank you.  You make a difference in this world. :)")

async def Command_Hello(message):
    await message.channel.send('Hello!')

async def Command_ArchInfo(message):
    if(CoreConfig["AdvancedConfig"]["DebugMode"] == True):
        print("== Discord Config")
        for key, value in CoreConfig["DiscordConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== ArchipelagoConfig Config")
        for key, value in CoreConfig["ArchipelagoConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== ItemFilterConfig Config")
        for key, value in CoreConfig["ItemFilterConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== RelayConfig Config")
        for key, value in CoreConfig["RelayConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== DrawbridgeConfig Config")
        for key, value in CoreConfig["DrawbridgeConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== MetaConfig Config")
        for key, value in CoreConfig["MetaConfig"].items():
            print(str(key) + ": " + str(value))
            
        print("== AdvancedConfig Config")
        for key, value in CoreConfig["AdvancedConfig"].items():
            print(str(key) + ": " + str(value))
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
    for key in ArchGameJSON[game]['item_name_to_id']:
        if str(ArchGameJSON[game]['item_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")
    
def LookupLocation(game,id):
    for key in ArchGameJSON[game]['location_name_to_id']:
        if str(ArchGameJSON[game]['location_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")

def LookupSlot(slot):
    for key in ArchConnectionJSON['slot_info']:
        if key == slot:
            return str(ArchConnectionJSON['slot_info'][key]['name'])
    return str("NULL")

def LookupGame(slot):
    for key in ArchConnectionJSON['slot_info']:
        if key == slot:
            return str(ArchConnectionJSON['slot_info'][key]['game'])
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

def SetEnvVariable(key, value):
    global CoreConfig, ToggleConfig, ConfigLock, ToggleLock
    if key not in ["ArchipelagoPort","ArchipelagoPassword","ArchipelagoTrackerURL","ArchipelagoServerURL","UniqueID"]:
        return "Invalid key. Only 'ArchipelagoPort', 'ArchipelagoPassword', 'ArchipelagoTrackerURL', 'ArchipelagoServerURL', and 'UniqueID' can be set."
    else:
        with ConfigLock:
            if key == "ArchipelagoPort":
                CoreConfig["ArchipelagoConfig"]['ArchipelagoPort'] = value
                with ToggleLock:
                    ToggleConfig["CrippleTracker"] = False
            if key == "ArchipelagoServerURL":
                CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'] = value
            elif key == "ArchipelagoPassword":
                CoreConfig["ArchipelagoConfig"]['ArchipelagoPassword'] = value
            elif key == "ArchipelagoTrackerURL":
                CoreConfig["ArchipelagoConfig"]['ArchipelagoTrackerURL'] = value
            elif key == "ArchipelagoServerURL":
                CoreConfig["ArchipelagoConfig"]['ArchipelagoServerURL'] = value
            elif key == "UniqueID":
                CoreConfig["ArchipelagoConfig"]['UniqueID'] = value
            
            # Convert shared dict to regular dict for JSON serialization
            config_for_json = {k: dict(v) if hasattr(v, 'keys') else v for k, v in CoreConfig.items()}
            json.dump(config_for_json, open('config.json', "w"), indent=4)

        #We'll reconfirm and reload the data locations since we can change values.
        ConfirmSpecialFiles()
        return "Key '" + key + "' set to '" + value + "'!"

def ReloadBot():
    global ToggleConfig
    ToggleConfig["CrippleTracker"] = False
    websocket_queue.put("+++ Discord requested the bot to be reloaded!")

def WriteToErrorLog(module,message):
    with open(GetCoreFiles("errorlog"), 'a') as f:
        put = "["+str(time.strftime("%Y-%m-%d-%H-%M-%S"))+"],["+module+"]," + message
        f.write(put + "\n")

def ReloadJSONPackages():
    global ArchGameJSON
    global ArchConnectionJSON

    with open(GetCoreFiles("archgamedump"), 'r') as f:
        ArchGameJSON = json.load(f)

    with open(GetCoreFiles("archconnectiondump"), 'r') as f:
        ArchConnectionJSON = json.load(f)


async def CancelProcess():
    return 69420

def Discord(shared_config,toggle_config):
    global CoreConfig
    global ToggleConfig
    CoreConfig = shared_config
    ToggleConfig = toggle_config
    print("++ Starting Discord Client")
    DiscordClient.run(str(CoreConfig["DiscordConfig"]["DiscordToken"]))


# ====== MAIN SCRIPT START ====
# The run method is blocking, so it will keep the program running
def main():
    # Confirm all of the core directories and files exist just to be safe
    ConfirmSpecialFiles()
    
    global CoreConfig
    global ToggleConfig
    global ReconnectionTimer
    global DiscordClient
    global tracker_client
    global ArchGameJSON
    global ArchConnectionJSON

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

        if not CheckDatapackage():
            print("!!! Critical Error - Data package is not valid! Restarting the bot normally fixes this issue.")
            seppuku_queue.put("Data package is not valid!")

        # If there is a critical error in the tracker_client, kill the script.
        if not seppuku_queue.empty() or not websocket_queue.empty():
            print("!! Early Loading Seppuku Initiated - Goodbye Friend")
            exit(1)

        # Since there wasn't a critical error, continue as normal :)
        print("== Loading Arch Data...")

        # Wait for game dump to be created by tracker client
        while not CheckGameDump():
            print(f"== waiting for {GetCoreFiles("archgamedump")} to be created on when data package is received")
            time.sleep(2)

        with open(GetCoreFiles("archgamedump"), 'r') as f:
            ArchGameJSON = json.load(f)
        print("=== Arch Game Data Loaded!")

        # Wait for connection dump to be created by tracker client
        while not CheckConnectionDump():
            print(f"== waiting for {GetCoreFiles("archconnectiondump")} to be created on room connection")
            time.sleep(2)

        with open(GetCoreFiles("archconnectiondump"), 'r') as f:
            ArchConnectionJSON = json.load(f)
        print("=== Arch Connection Data Loaded!")

        print("== Arch Data Loaded!")
        time.sleep(3)

    DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig))
    DiscordThread.start()

    DiscordCycleCount = 0
    TrackerCycleCount = 0
    
    ## Gotta keep the bot running!
    while True:
        if TrackerCycleCount >= 3:
            print("!!! Tracker has crtically failed to restart multiple times")
            print("!!! Exiting for manual intervention")
            MessageObject = {"type": "CORE", "data": {"text": "[CORE]: ERROR - Tracker has crtically failed to restart multiple times. Manual intervention required."}, "flag": "ERROR"}
            chat_queue.put(MessageObject)
            ToggleConfig["CrippleTracker"] = True
            TrackerCycleCount = 0
        
        if (CoreConfig["AdvancedConfig"]["DiscordJoinOnly"] == False):
            if not ToggleConfig["CrippleTracker"]:  
                if not tracker_client.socket_thread.is_alive() or not websocket_queue.empty() or not seppuku_queue.empty():
                    print("-- Tracker is not running, requested a restart, or has failed, so we do the needful")

                    if not seppuku_queue.empty():
                        print("-- Tracker commited Seppuku, Requesting new port information")
                        print("-- Sleeping for 5 seconds to allow DiscordBot to process PortScan")
                        with ToggleLock:
                            ToggleConfig["RequestPortScan"] = True
                        time.sleep(5)
                        TrackerCycleCount = TrackerCycleCount + 1

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
                    time.sleep(3)

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
                DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig))
                DiscordThread.start()
                DiscordCycleCount = 0
        
        if not DiscordThread.is_alive():
            print("++ Discord thread is not running, restarting it")
            print("++ Closing the discord thread")
            DiscordThread.close()
            print("++ Sleeping for 3 seconds to allow the discord thread to close")
            time.sleep(3)
            print("++ Starting the discord thread again")
            DiscordThread = Process(target=Discord, args=(CoreConfig,ToggleConfig))
            DiscordThread.start()
            
        if not hint_queue.empty():
            hint_object = hint_queue.get()
            hintprocessing_queue.put(hint_object[1])
            hint_client = HintClient(
                server_uri=CoreConfig["ArchipelagoConfig"]['ArchipelagoServer'],
                port=CoreConfig["ArchipelagoConfig"]['ArchipelagoPort'],
                password=GetArchPassword(),
                slot_name=hint_object[0],
            )      
            hint_client.start()
            time.sleep(5)

        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("   Closing Bot Thread - Have a good day :)")
            exit(1)

if __name__ == '__main__': 
    main()

# On 7/12/2024 Bridgeipelago crashed the AP servers and caused Berserker to give me a code review:
# Berserker - One, what I showed, whatever this bridgeipelago is
# Exempt-Medic - It's some kind of AP Discord Bot
# Berserker - Well it's clearly programmed like shit
