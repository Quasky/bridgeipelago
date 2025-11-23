# Setup
Setting the bot up has been as streamlined as possible.  
Following this guide should get you fairly close to complete.  
If you have any questions, feel free to ask in the [Discord](https://discord.gg/5v9P3qNPXp)

## Before you continue:
This bot requires `python` and `pip` at a minimum.  
General knowledge of python is encouraged but <u>not strictly necessary</u>.  
I've also written this guide with Linux in mind, but that can be easily accomplished with WSL on windows, or a VM to run the bot.  
There is some minor help in Step 5 with running python commands in windows.

To be honest, you can figure out most errors by just googling.


## Step 1) Preparing the Archipelago game
When generating the Archipelago game, make sure the <ins>**bridgeipelago.yaml**</ins> is included in the game to ensure the bot has a slot to listen in on.  
This slot has no effect on the AP itself.  
If you'd like to add-in this bot to an existing game (or not have a dedicated slot for the bot) change ArchipelagoBotSlot in the .env to a valid slot-name.

## Step 2) Discord Bot Setup (You only need to do this once)
You'll need a discord bot API token for the bot.

Log into the Discord Developer Portal: https://discord.com/developers/applications
And create a new Application/bot

In the **Installation** tab:  
Check 'Guild Install'  
Default Install Settings:
Scopes: 'application.commands' and 'bot'  
Permissions: 'Send Messages'

In the **Bot** tab:  
Username: Something fun!  
Copy your token down. You'll need it in a bit!  
Enable 'Public Bot'  
Enable 'Message Content Intent'

In the **Discord Provided Link** tab:  
Copy the OAuth link into your browser and add the bot to the discord of your choice.

You're done with the bot for now, but keep that token handy!

## Step 3) Discord Channel Setup (You only need to do this once)
In Discord, enable "Developer Mode" for your client
Create/have two channels for the bot.  
- One will be where the bot posts all the AP information, and where commands are ran (for your users) 
- The second will be for debug reasons (for you, I'd keep this private)

Make sure the bot has access to both channels and can send messages in them.

Right-Click the channels and "Copy Channel ID", and hold them for now!

Next, right-click your name and "Copy User ID", copy it down.

## Step 4) Bridgeipelago Setup
- Core
  1. Download Bridgeipelago  
     - Stable:
       - [Latest stable release](https://github.com/Quasky/bridgeipelago/releases/latest)
     - Unstable (hopefully not):
       - [All releases (Stable and Pre-Release)](https://github.com/Quasky/bridgeipelago/releases)
       - Or clone the main repo for a crazy expierience `https://github.com/Quasky/bridgeipelago.git`
  1. Copy .env.template to .env
- Discord Config
  1. Fill out the 'DiscordToken' with your discord app/bot's token
  1. Fill out 'DiscordBroadcastChannel' with the channel ID that you'd like the bot to post AP info in
  1. Fill out 'DiscordAlertUserID' with your User ID. (This can also be a group/role in discord)
  1. Fill out 'DiscordDebugChannel' with the channel ID of the debug channel
- Archipelago Config
  1. Fill out 'ArchipelagoServer' if you're self-hosting the Archipelago Server
  1. Fill out 'ArchipelagoPort' with the port number you've been assigned
  1. Fill out 'ArchipelagoBotSlot' with the slot name of the bot (Not needed if you used the included yaml)
  1. Fill out 'ArchipelagoTrackerURL' with the Tracker room URL
  1. Fill out 'ArchipelagoServerURL' with the room URL
  1. Fill out 'UniqueID' with the RoomID/seed/an arbitrary value (see [UniqueID](#UniqueID) for detailed useage)
- Item Filter Config
  1. Set 'BotItemSpoilTraps' to 'true' if you'd like to have traps spoiled, or change to 'false' to hide traps
  1. Set 'BotItemFilterLevel' to the level you'd like (0, 1, 2)
- Relay Config
  1. Set desired AP to Discord relay options.
- ! Command Config
  1. Set desired !command relay options.
- Drawbridge Config
  1. Set 'DiscordBridgeEnabled' to 'true' if you'd like chat from discord bridged to AP.
- Meta Config
  1. Set 'FlavorDeathLink' to 'true' if you'd like custom flavored deathlink messages.

You're free to leave the Advanced Config section as-is unless you know what you're doing.  
Detailed references on the .env can be found on the main [Readme](/README.md)

### Selfhosted AP Servers with no WebHost
If you run a selfhosted AP server but elect to not have the webhost module running, the bot will throw a fit unless you disable WebHost-specific functionality.  
In the Advanced Config section:
- Set 'SelfHostNoWeb' to 'true'

## Step 5) Create Python venv + Dependencies (You only need to do this once)

### Linux / WSL / MacOS

1. Create the venv: `python -m venv bridgeipelago`
1. Activate the venv: `source bridgeipelago/bin/activate`
1. Install dependencies: `pip install -r requirements.txt`

### Windows Users (Powershell):
You may need to run `Set-ExecutionPolicy Bypass` to enable scripts.
1. Create the venv: `py -m venv bridgeipelago`
1. Activate the venv: `./bridgeipelago/Scripts/Activate.ps1`
1. Install dependencies: `pip install -r requirements.txt`

## Step 6) Finally: Running the Bot
Ensure you've joined the venv and setup the .env file, then run: `python3 bridgeipelago.py`  
> Windows users may need to run `py bridgeipelago.py` depending on how Python set up its aliases.

You'll see the bot connect to your Discord channel and join the Archipelago game.

# Issues:
You can join the discord and post in the [tech-support](https://discord.gg/wpdPprvYgX) channel for assistance on setting up the bot.

-----
-----

## UniqueID
This value is used to store the bot's files in key'd directories for use in a run.  
When changing rooms / AP runs, you'll need to manually purge the data directories and restart Bridgeipelago or run the [Swapping rooms via Discord](#swapping-rooms-via-discord) process via discord.

## Swapping Rooms via Discord
You have the ability to swap rooms without manually editing the .env of the bot.
This process will automaticly create new directories, and reload all data needed for running Bridgeipelago.  

It's a fairly painless process, but should be done carefully and in order, as to not break Bridgeipelago into a thousand pieces.

**(Make sure the room is up, and connectable by clients before you $reloadtracker!)**

1. $setenv ArchipelagoPort \<port>  
  -- Sets the port
1. $setenv ArchipelagoTrackerURL \<tracker URL>  
  -- Sets the tracker URL
1. $setenv ArchipelagoServerURL \<server URL>  
  -- Sets the ServerURL
1. $setenv UniqueID \<uniqueID>  
  -- Sets the new UniqueID
1. $reloadtracker  
  -- Tells the tracker to reload to fetch new room data, datapackages, and connection data for the new room
1. $reloaddata  
  -- Reloads the room's data into memory
1. $reloaddiscord  
  -- Finally, tell discord to reload to make sure it's cleaned out

By setting the values in this order, you can prep the new connection in steps 1-3, create the new directories in step 4, populate new room data with step 5, load the data into memory with step 6, then finally; refresh discord in step 7

If any any time this process breaks or throws an error here are some common troubleshooting tips:
  - Stopping Bridgeipelago fully and restarting it
  - Stopping Bridgeipelago, deleting the contents of the data directories, and restarting Bridgeipelago
  - Nuking everything and restarting 
  - Praying to the magic smoke god in your comptuer to make it work

If none of this works, poke in the discord for help and someone will get you sorted. :)

