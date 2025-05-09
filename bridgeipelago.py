# ______        _      _               _               _                      
# | ___ \      (_)    | |             (_)             | |                     
# | |_/ / _ __  _   __| |  __ _   ___  _  _ __    ___ | |  __ _   __ _   ___  
# | ___ \| '__|| | / _` | / _` | / _ \| || '_ \  / _ \| | / _` | / _` | / _ \ 
# | |_/ /| |   | || (_| || (_| ||  __/| || |_) ||  __/| || (_| || (_| || (_) |
# \____/ |_|   |_| \__,_| \__, | \___||_|| .__/  \___||_| \__,_| \__, | \___/ 
#                          __/ |         | |                      __/ |       
#                         |___/          |_|                     |___/  v1.2.4
#
# An Archipelago Discord Bot
#                - By the Zajcats

#Core Dependencies
import argparse
import json
import typing
import uuid
import os
import sys
from dotenv import load_dotenv
from enum import Enum
import glob
import random
import requests
from bs4 import BeautifulSoup
import ast

#Threading Dependencies
from threading import Thread
from multiprocessing import Queue, Process

#Plotting Dependencies
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

#Websocket Dependencies
from websocket import WebSocketApp, enableTrace

#Discord Dependencies
from discord.ext import tasks
import discord
from discord import app_commands
import time

#.env Config Setup + Metadata
load_dotenv()
DiscordToken = os.getenv('DiscordToken')
DiscordBroadcastChannel = int(os.getenv('DiscordBroadcastChannel'))
DiscordAlertUserID = os.getenv('DiscordAlertUserID')
DiscordDebugChannel = int(os.getenv('DiscordDebugChannel'))

ArchHost = os.getenv('ArchipelagoServer')
ArchPort = os.getenv('ArchipelagoPort')
ArchipelagoBotSlot = os.getenv('ArchipelagoBotSlot')
ArchTrackerURL = os.getenv('ArchipelagoTrackerURL')
ArchServerURL = os.getenv('ArchipelagoServerURL')

SpoilTraps = os.getenv('BotItemSpoilTraps')
ItemFilterLevel = int(os.getenv('BotItemFilterLevel'))

EnableChatMessages = os.getenv('ChatMessages')
EnableServerChatMessages = os.getenv('ServerChatMessages')
EnableGoalMessages = os.getenv('GoalMessages')
EnableReleaseMessages = os.getenv('ReleaseMessages')
EnableCollectMessages = os.getenv('CollectMessages')
EnableCountdownMessages = os.getenv('CountdownMessages')
EnableDeathlinkMessages = os.getenv('DeathlinkMessages')

EnableFlavorDeathlink = os.getenv('FlavorDeathlink')
EnableDeathlinkLottery = os.getenv('DeathlinkLottery')

LoggingDirectory = os.getcwd() + os.getenv('LoggingDirectory')
RegistrationDirectory = os.getcwd() + os.getenv('PlayerRegistrationDirectory')
ItemQueueDirectory = os.getcwd() + os.getenv('PlayerItemQueueDirectory')
ArchDataDirectory = os.getcwd() + os.getenv('ArchipelagoDataDirectory')
JoinMessage = os.getenv('JoinMessage')
DebugMode = os.getenv('DebugMode')
DiscordJoinOnly = os.getenv('DiscordJoinOnly')
SelfHostNoWeb = os.getenv('SelfHostNoWeb')

# Metadata
ArchInfo = ArchHost + ':' + ArchPort
OutputFileLocation = LoggingDirectory + 'BotLog.txt'
DeathFileLocation = LoggingDirectory + 'DeathLog.txt'
DeathTimecodeLocation = LoggingDirectory + 'DeathTimecode.txt'
DeathPlotLocation = LoggingDirectory + 'DeathPlot.png'
CheckPlotLocation = LoggingDirectory + 'CheckPlot.png'
ArchDataDump = ArchDataDirectory + 'ArchDataDump.json'
ArchGameDump = ArchDataDirectory + 'ArchGameDump.json'
ArchConnectionDump = ArchDataDirectory + 'ArchConnectionDump.json'
ArchRawData = ArchDataDirectory + 'ArchRawData.txt'

# Global Variable Declaration
DumpJSON = []
ConnectionPackage = []

# Version Checking against GitHub
try:
    BPversion = "live-v1.2.4"
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

# Make sure all of the directories exist before we start creating files
if not os.path.exists(ArchDataDirectory):
    os.makedirs(ArchDataDirectory)

if not os.path.exists(LoggingDirectory):
    os.makedirs(LoggingDirectory)

if not os.path.exists(RegistrationDirectory):
    os.makedirs(RegistrationDirectory)

if not os.path.exists(ItemQueueDirectory):
    os.makedirs(ItemQueueDirectory)

#Logfile Initialization. We need to make sure the log files exist before we start writing to them.
l = open(DeathFileLocation, "a")
l.close()

l = open(OutputFileLocation, "a")
l.close()

l = open(DeathTimecodeLocation, "a")
l.close()

# Load Meta Modules if they are enabled in the .env
if EnableFlavorDeathlink == "true":
    from modules.DeathlinkFlavor import GetFlavorText

## ARCHIPELAGO TRACKER CLIENT + CORE FUNCTION
class TrackerClient:
    tags: set[str] = {'Tracker', 'DeathLink'}
    version: dict[str, any] = {"major": 0, "minor": 4, "build": 6, "class": "Version"}
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
        *,
        server_uri: str,
        port: str,
        slot_name: str,
        on_death_link: callable = None, 
        on_item_send: callable = None, 
        on_chat_send: callable = None, 
        on_datapackage: callable = None,
        verbose_logging: bool = False,
        **kwargs: typing.Any
    ) -> None:
        self.server_uri = server_uri
        self.port = port
        self.slot_name = slot_name
        self.on_death_link = on_death_link
        self.on_item_send = on_item_send
        self.on_chat_send = on_chat_send
        self.on_datapackage = on_datapackage
        self.verbose_logging = verbose_logging
        self.web_socket_app_kwargs = kwargs
        self.uuid: int = uuid.getnode()
        self.wsapp: WebSocketApp = None
        self.socket_thread: Thread = None

    def start(self) -> None:
        print("Attempting to open an Archipelago MultiServer websocket connection in a new thread.")
        enableTrace(self.verbose_logging)
        self.wsapp = WebSocketApp(
            f'{self.server_uri}:{self.port}',
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            **self.web_socket_app_kwargs,
        )

        self.socket_thread = Thread(target=self.wsapp.run_forever)
        self.socket_thread.daemon = True
        self.socket_thread.start()

    def on_error(self, string, opcode) -> None:
        if self.verbose_logging:
            print(f"error self: {self}")
            print(f"error string: {string}")
            print(f"error opcode: {opcode}")
        websocket_queue.put("Tracker Error...")
        sys.exit()

    def on_close(self, string, opcode, flag) -> None:
        if self.verbose_logging:
            print(f"closed self: {self}")
            print(f"closed string: {string}")
            print(f"closed opcode: {opcode}") #1001 used for closure initiated by the server
            print(f"closed opcode: {flag}")
        websocket_queue.put("Tracker Closed...")
        sys.exit()

    def on_message(self, wsapp: WebSocketApp, RawMessage: str) -> None:
        """Handles incoming messages from the Archipelago MultiServer."""

        DebugMode = os.getenv('DebugMode')
        if(DebugMode == "true"):
            print("==RawMessage==")
            print(RawMessage)
            print("=====")

        for i in range(len(json.loads(RawMessage))):

            args: dict = json.loads(RawMessage)[i]
            cmd = args.get('cmd')

            if(DebugMode == "true"):
                print("==Args==")
                print(args)
                print("=====")

            if cmd == self.MessageCommand.ROOM_INFO.value:
                self.send_connect()
                self.get_datapackage()
            elif cmd == self.MessageCommand.DATA_PACKAGE.value:
                WriteDataPackage(args)
            elif cmd == self.MessageCommand.CONNECTED.value:
                WriteConnectionPackage(args)
                print("Connected to server.")
            elif cmd == self.MessageCommand.CONNECTIONREFUSED.value:
                print("Connection refused by server - check your slot name / port / whatever, and try again.")
                print(args)
                seppuku_queue.put(args)
                exit()
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'ItemSend':
                if self.on_item_send:
                    self.on_item_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'Chat':
                if EnableChatMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'ServerChat':
                if EnableServerChatMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'Goal':
                if EnableGoalMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'Release':
                if EnableReleaseMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'Collect':
                if EnableCollectMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.PRINT_JSON.value and args.get('type') == 'Countdown':
                if EnableCountdownMessages == "true":
                    if self.on_chat_send:
                        self.on_chat_send(args)
            elif cmd == self.MessageCommand.BOUNCED.value and 'DeathLink' in args.get('tags', []):
                if self.on_death_link:
                    self.on_death_link(args)

    def send_connect(self) -> None:
        print("Sending `Connect` packet to log in to server.")
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

    def get_datapackage(self) -> None:
        print("Sending `DataPackage` packet to request data.")
        payload = {
            'cmd': 'GetDataPackage'
        }
        self.send_message(payload)

    def send_message(self, message: dict) -> None:
        self.wsapp.send(json.dumps([message]))

    def stop(self) -> None:
        self.wsapp.close()


## DISCORD EVENT HANDLERS + CORE FUNTION
@DiscordClient.event
async def on_ready():
    global MainChannel
    MainChannel = DiscordClient.get_channel(DiscordBroadcastChannel)
    #await MainChannel.send('Bot connected. Battle control - Online.')
    global DebugChannel
    DebugChannel = DiscordClient.get_channel(DiscordDebugChannel)
    await DebugChannel.send('Bot connected. Debug control - Online.')

    # We wont sync the command tree for now, need to roll out central control first.
    #await tree.sync(guild=discord.Object(id=DiscordGuildID))

    #Start background tasks
    CheckArchHost.start()
    ProcessItemQueue.start()
    ProcessDeathQueue.start()
    ProcessChatQueue.start()

    print(JoinMessage)
    print("Async bot started -", DiscordClient.user)

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

    # Opens a discord DM with the user, and fires off the Katchmeup process
    # When the user asks, catch them up on checks they're registered for
    ## Yoinks their registration file, scans through it, then find the related ItemQueue file to scan through 
    if message.content.startswith('$ketchmeup'):
        await Command_KetchMeUp(message.author)
    
    # When the user asks, catch them up on the specified game
    ## Yoinks the specified ItemQueue file, scans through it, then sends the contents to the user
    ## Does NOT delete the file, as it's assumed the other users will want to read the file as well
    if message.content.startswith('$groupcheck'):
        game = (message.content).split('$groupcheck ')
        await Command_GroupCheck(message.author, game[1])
    
    if message.content.startswith('$hints'):
        await Command_Hints(message.author)
    
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

@tasks.loop(seconds=900)
async def CheckArchHost():
    if SelfHostNoWeb == "true":
        await CancelProcess()

    try:
        ArchRoomID = ArchServerURL.split("/")
        ArchAPIUEL = ArchServerURL.split("/room/")
        RoomAPI = ArchAPIUEL[0]+"/api/room_status/"+ArchRoomID[4]
        RoomPage = requests.get(RoomAPI)
        RoomData = json.loads(RoomPage.content)

        cond = str(RoomData["last_port"])
        if(cond == ArchPort):
            return
        else:
            print("Port Check Failed")
            print(RoomData["last_port"])
            print(ArchPort)
            message = "Port Check Failed - Restart tracker process <@"+DiscordAlertUserID+">"
            #await MainChannel.send(message)
            await DebugChannel.send(message)
    except:
        await DebugChannel.send("ERROR IN CHECKARCHHOST <@"+DiscordAlertUserID+">")

@tasks.loop(seconds=1)
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
                item = str(LookupItem(game,itemmessage['data'][2]['text']))
                itemclass = str(itemmessage['data'][2]['flags'])
                location = str(LookupLocation(game,itemmessage['data'][4]['text']))

                iitem = SpecialFormat(item,ItemClassColor(int(itemclass)),0)
                message = "" + name + " found their " + iitem + "\nCheck: " + location


                ItemCheckLogMessage = name + "||" + item + "||" + name + "||" + location + "\n"
                BotLogMessage = timecode + "||" + ItemCheckLogMessage
                o = open(OutputFileLocation, "a")
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
            

                ItemCheckLogMessage = recipient + "||" + item + "||" + name + "||" + location + "\n"
                BotLogMessage = timecode + "||" + ItemCheckLogMessage
                o = open(OutputFileLocation, "a")
                o.write(BotLogMessage)
                o.close()

                if int(itemclass) == 4 and SpoilTraps == 'true':
                    ItemQueueFile = ItemQueueDirectory + recipient + ".csv"
                    i = open(ItemQueueFile, "a")
                    i.write(ItemCheckLogMessage)
                    i.close()
                elif int(itemclass) != 4:
                    ItemQueueFile = ItemQueueDirectory + recipient + ".csv"
                    i = open(ItemQueueFile, "a")
                    i.write(ItemCheckLogMessage)
                    i.close()
            else:
                message = "Unknown Item Send :("
                print(message)
                await SendDebugChannelMessage(message)

            message = "```ansi\n" + message + "```"

            if int(itemclass) == 4 and SpoilTraps == 'true':
                await SendMainChannelMessage(message)
            elif int(itemclass) != 4 and ItemFilter(int(itemclass)):
                await SendMainChannelMessage(message)
            else:
                #In Theory, this should only be called when the two above conditions are not met
                #So we call this dummy function to escape the async call.
                await CancelProcess()

    except Exception as e:
        print(e)
        await SendDebugChannelMessage("Error In Item Queue Process")

@tasks.loop(seconds=1)
async def ProcessDeathQueue():
    if death_queue.empty():
        return
    else:
        chatmessage = death_queue.get()
        timecode = time.strftime("%Y||%m||%d||%H||%M||%S")
        DeathMessage = "**Deathlink received from: " + str(chatmessage['data']['source']) + "**"
        DeathLogMessage = timecode + "||" + str(chatmessage['data']['source']) + "\n"
        o = open(DeathFileLocation, "a")
        o.write(DeathLogMessage)
        o.close()
        if EnableDeathlinkMessages == "true":
            if EnableFlavorDeathlink == "true":
                FlavorMessage = "Deathlink: " + GetFlavorText(str(chatmessage['data']['source']))
                await SendMainChannelMessage(FlavorMessage)
            else:
                await SendMainChannelMessage(DeathMessage)
        else:
            return

@tasks.loop(seconds=1)
async def ProcessChatQueue():
    if chat_queue.empty():
        return
    else:
        chatmessage = chat_queue.get()
        await SendMainChannelMessage(chatmessage['data'][0]['text'])

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
async def first_command(interaction):
    await interaction.user.create_dm()
    UserDM = interaction.user
    await Command_KetchMeUp(UserDM)
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
        RegistrationFile = RegistrationDirectory + Sender + ".csv"
        RegistrationContent = ArchSlot + "\n"
        # Generate the Registration File if it doesn't exist
        o = open(RegistrationFile, "a")
        o.close()
        # Get contents of the registration file and save it to 'line'
        o = open(RegistrationFile, "r")
        line = o.read()
        o.close()
        # Check the registration file for ArchSlot, if they are not registered; do so. If they already are; tell them.
        if not ArchSlot in line:
            o = open(RegistrationFile, "a")
            o.write(RegistrationContent)
            o.close()
            return "You've been registered for " + ArchSlot + "!"
        else:
            return "You're already registered for that slot."
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN REGISTER <@"+DiscordAlertUserID+">")

async def Command_ClearReg(Sender:str):
    try:
        RegistrationFile = RegistrationDirectory + Sender + ".csv"
        if not os.path.exists(RegistrationFile):
            return "You're not registered for any slots :("
        os.remove(RegistrationFile)
        return "Your registration has been cleared."
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN CLEARREG <@"+DiscordAlertUserID+">")

async def Command_KetchMeUp(User):
    try:
        RegistrationFile = RegistrationDirectory + str(User) + ".csv"
        if not os.path.isfile(RegistrationFile):
            await User.send("You've not registered for a slot : (")
        else:
            r = open(RegistrationFile,"r")
            RegistrationLines = r.readlines()
            r.close()
            for reglines in RegistrationLines:
                ItemQueueFile = ItemQueueDirectory + reglines.strip() + ".csv"
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
                    ketchupmessage = ketchupmessage + You.ljust(YouWidth) + " || " + Item.ljust(ItemWidth) + " || " + Sender.ljust(SenderWidth) + " || " + Location + "\n"
                    
                    if len(ketchupmessage) > 1500:
                        ketchupmessage = ketchupmessage + "```"
                        await User.send(ketchupmessage)
                        ketchupmessage = "```"
                ketchupmessage = ketchupmessage + "```"
                await User.send(ketchupmessage)
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN KETCHMEUP <@"+DiscordAlertUserID+">")

async def Command_GroupCheck(DMauthor, game):
    try:
        ItemQueueFile = ItemQueueDirectory + game + ".csv"
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
            await DMauthor.send(ketchupmessage)
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN GROUPCHECK <@"+DiscordAlertUserID+">")

async def Command_Hints(player):
    if SelfHostNoWeb == "true":
        await MainChannel.send("This command is not available in self-hosted mode.")
        return
    
    try:
        await player.create_dm()

        page = requests.get(ArchTrackerURL)
        soup = BeautifulSoup(page.content, "html.parser")

        #Yoinks table rows from the checks table
        tables = soup.find("table",id="hints-table")
        for slots in tables.find_all('tbody'):
            rows = slots.find_all('tr')


        RegistrationFile = RegistrationDirectory + player.name + ".csv"
        if not os.path.isfile(RegistrationFile):
            await player.dm_channel.send("You've not registered for a slot : (")
        else:
            r = open(RegistrationFile,"r")
            RegistrationLines = r.readlines()
            r.close()
            for reglines in RegistrationLines:

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
                await player.dm_channel.send(checkmessage)
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN HINTLIST <@"+DiscordAlertUserID+">")

async def Command_DeathCount():
    try:
        d = open(DeathFileLocation,"r")
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
        plt.savefig(DeathPlotLocation, bbox_inches="tight")
        await MainChannel.send(file=discord.File(DeathPlotLocation))
    except:
        await DebugChannel.send("ERROR DEATHCOUNT <@"+DiscordAlertUserID+">")

async def Command_CheckCount():
    if SelfHostNoWeb == "true":
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        page = requests.get(ArchTrackerURL)
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
            slot = (row.find_all('td')[1].text).strip()
            game = (row.find_all('td')[2].text).strip()
            status = (row.find_all('td')[3].text).strip()
            checks = (row.find_all('td')[4].text).strip()
            percent = (row.find_all('td')[5].text).strip()
            checkmessage = checkmessage + slot.ljust(SlotWidth) + " || " + game.ljust(GameWidth) + " || " + checks.ljust(ChecksWidth) + " || " + percent + "\n"
            if len(checkmessage) > 1900:
                checkmessage = checkmessage + "```"
                await MainChannel.send(checkmessage)
                checkmessage = "```"

        #Finishes the check message
        checkmessage = checkmessage + "```"
        await MainChannel.send(checkmessage)
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN CHECKCOUNT <@"+DiscordAlertUserID+">")

async def Command_CheckGraph():
    if SelfHostNoWeb == "true":
        await MainChannel.send("This command is not available in self-hosted mode.")
        return

    try:
        page = requests.get(ArchTrackerURL)
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
        plt.savefig(CheckPlotLocation, bbox_inches="tight")
        await MainChannel.send(file=discord.File(CheckPlotLocation))
    except Exception as e:
        print(e)
        await DebugChannel.send("ERROR IN CHECKGRAPH <@"+DiscordAlertUserID+">")

async def Command_ILoveYou(message):
    await message.channel.send("Thank you.  You make a difference in this world. :)")

async def Command_Hello(message):
    await message.channel.send('Hello!')

async def Command_ArchInfo(message):
    DebugMode = os.getenv('DebugMode')
    if(DebugMode == "true"):
        print("===ENV_VARIABLES===")
        print(DiscordBroadcastChannel)
        print(DiscordAlertUserID)
        print(DiscordAlertUserID)
        print(ArchHost)
        print(ArchPort)
        print(ArchipelagoBotSlot)
        print(ArchTrackerURL)
        print(ArchServerURL)
        print(SpoilTraps)
        print(ItemFilterLevel)
        print(EnableChatMessages)
        print(EnableServerChatMessages)
        print(EnableGoalMessages)
        print(EnableReleaseMessages)
        print(EnableCollectMessages)
        print(EnableCountdownMessages )
        print(EnableDeathlinkMessages )
        print(LoggingDirectory)
        print(RegistrationDirectory)
        print(ItemQueueDirectory)
        print(ArchDataDirectory)
        print(JoinMessage)
        print(DebugMode)
        print(DiscordJoinOnly)
        print(DiscordDebugChannel)
        print("")
        print("===GLOBAL_VARIABLES===")
        print(ArchInfo)
        print(OutputFileLocation)
        print(DeathFileLocation)
        print(DeathTimecodeLocation)
        print(DeathPlotLocation)
        print(CheckPlotLocation)
        print(ArchDataDump)
        print(ArchGameDump)
        print(ArchConnectionDump)
        print(ArchRawData)
        print("")
    else:
        await message.channel.send("Debug Mode is disabled.")

## HELPER FUNCTIONS
def WriteDataPackage(data):
    with open(ArchDataDump, 'w') as f:
        json.dump(data, f)
    
    with open(ArchDataDump, 'r') as f:
        LoadedJSON = json.load(f)

    Games = LoadedJSON['data']['games']

    with open(ArchGameDump, 'w') as f:
        json.dump(Games, f)

def WriteConnectionPackage(data):
    with open(ArchConnectionDump, 'w') as f:
        json.dump(data, f)

def LookupItem(game,id):
    for key in DumpJSON[game]['item_name_to_id']:
        if str(DumpJSON[game]['item_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")
    
def LookupLocation(game,id):
    for key in DumpJSON[game]['location_name_to_id']:
        if str(DumpJSON[game]['location_name_to_id'][key]) == str(id):
            return str(key)
    return str("NULL")

def LookupSlot(slot):
    for key in ConnectionPackage['slot_info']:
        if key == slot:
            return str(ConnectionPackage['slot_info'][key]['name'])
    return str("NULL")

def LookupGame(slot):
    for key in ConnectionPackage['slot_info']:
        if key == slot:
            return str(ConnectionPackage['slot_info'][key]['game'])
    return str("NULL")

def ItemFilter(itmclass):
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

    if ItemFilterLevel == 2:
        if(itmclass & ( 1 << 0 )):
            return True
        else:
            return False
    elif ItemFilterLevel == 1:
        if(itmclass & ( 1 << 0 )):
            return True
        elif(itmclass & ( 1 << 1 )):
            return True
        else:
            return False
    elif ItemFilterLevel == 0:
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
    

async def CancelProcess():
    return 69420

def Discord():
    DiscordClient.run(DiscordToken)

## Three main queues for processing data from the Archipelago Tracker to the bot
item_queue = Queue()
death_queue = Queue()
chat_queue = Queue()
seppuku_queue = Queue()
websocket_queue = Queue()
lottery_queue = Queue()

## Threadded async functions
if(DiscordJoinOnly == "false"):
    # Start the tracker client
    tracker_client = TrackerClient(
        server_uri=ArchHost,
        port=ArchPort,
        slot_name=ArchipelagoBotSlot,
        verbose_logging=False,
        on_chat_send=lambda args : chat_queue.put(args),
        on_death_link=lambda args : death_queue.put(args),
        on_item_send=lambda args : item_queue.put(args)
    )
    tracker_client.start()

    time.sleep(5)

    if seppuku_queue.empty():
        print("Loading Arch Data...")
    else:
        print("Seppuku Initiated - Goodbye Friend")
        exit(1)

    # Wait for game dump to be created by tracker client
    while not os.path.exists(ArchGameDump):
        print(f"waiting for {ArchGameDump} to be created on when data package is received")
        time.sleep(2)

    with open(ArchGameDump, 'r') as f:
        DumpJSON = json.load(f)

    # Wait for connection dump to be created by tracker client
    while not os.path.exists(ArchConnectionDump):
        print(f"waiting for {ArchConnectionDump} to be created on room connection")
        time.sleep(2)

    with open(ArchConnectionDump, 'r') as f:
        ConnectionPackage = json.load(f)

    time.sleep(3)

# The run method is blocking, so it will keep the program running
def main():
    DiscordThread = Process(target=Discord)
    DiscordThread.start()

    ## Gotta keep the bot running!
    while True:
        if not websocket_queue.empty():
            while not websocket_queue.empty():
                SQMessage = websocket_queue.get()
                print(SQMessage)
            print("Restarting tracker client...")
            tracker_client.start()
            time.sleep(10)

        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("   Closing Bot Thread - Have a good day :)")
            exit(1)

if __name__ == '__main__':
    main()