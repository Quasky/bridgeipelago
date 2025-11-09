<p align="center">
<img src="assets/bridgeipelago_r.png" alt="[bridgeipelago logo]" width="300"/>
</p>

# bridgeipelago

Discord bridge for Archipelago in python

[Discord Link](https://discord.gg/5v9P3qNPXp)

## Setup:
See the [SETUP GUIDE](docs/setup.md)  

There is also a [DOCKER](docs/docker.md) setup guide as well (if you're into that kind of thing)

You can chagne rooms via discord by following the directions in [SWAPPING ROOMS IN DISCORD](docs/setup.md#swapping-rooms-via-discord)

## Funtionality:

### Core
This bot will monitor and track progress as you play through your Archipelago run.  
This allows for some fun stats to be collected, logging from the bot on item checks that are found, and death notices from DeathLink players.

When a check is found or a deathlink is received, it'll output the check in a discord channel.

```
Examples:
An item for yourself: 
> Quasky_SM64 found their Power Star
> Check: LLL: Boil the Big Bully

An item for someone else:
> Quasky_SM64 sent Lens of Truth to Quasky_OOT
> Check: LLL: Bully the Bullies

When someone with deathlink dies, it'll shame them in this channel.
> Deathlink received from: Quasky_OOT
```

What this bot will NOT do:
 - DM / ping you without consent
 - Find items for you
 - Give hints
 - Find the reason the children of this world have forgotten the meaning of Christmas


In v1.2.5 and above, messages will be colorcoded to their usefulness in the Archipelago run.  
|Color|Item Type|
|---|---
|YELLOW|Progression Item|
|BLUE|Useful Item|
|WHITE|Filler/Normal Item|
|RED|Trap Item|

---
### Ketchmeup
You can also ask the bot to DM you all the items you've gained since last asking him.
(See the registration below)

**IMPORTANT NOTES:**
- This will send you EVERYTHING you've registered for since last asking. So even as you're playing and someone sends you an item, it'll still appear in the queue to be sent to you. (as the bot has no idea if you're playing or not)
- The bot will NOT log items you give to your own game. You're expected to remember what you find for yourself
- However the bot only understands slots. So if you're playing two games, the bot just assumes the other game is someone else and logs it. While ignoring the checks from your own game.

```
Example:
You         || Item                         || Sender      || Location
Quasky_OOT2 || Piece of Heart               || Quasky_OOT4 || Gerudo Training Ground Near Scarecrow Chest
Quasky_OOT2 || Rupees (20)                  || Quasky_OOT4 || Ganons Castle Shadow Trial Front Chest
Quasky_OOT2 || Bow                          || Quasky_OOT4 || Ganons Tower Boss Key Chest
Quasky_OOT2 || Gold Skulltula Token         || Quasky_OOT4 || Sheik at Colossus
Quasky_OOT2 || Rupees (200)                 || Quasky_OOT4 || KF Midos Bottom Left Chest
Quasky_OOT2 || Gold Skulltula Token         || Quasky_OOT4 || KF Shop Item 6
```
Hopefully that makes sense. 

---
---

## Commands
**All commands are case-sensitive.**
|Player Commands|Description|
|---|---|
|$register \<slot>|Adds the slot provided to the user's registration file
|$clearreg|Clears the user's registration file|
|$ketchmeup \<filter>|DMs the user all checks in their ItemQueue file, used to catch you up on missed checks|
||2 - Only Logical Progression Items|
||1 - Logical + Useful items|
||0 or empty - Logical + Useful + Normal items + Traps\*|
||\*Traps will only be sent if the filter is 0 AND BotItemSpoilTraps is enabled|
|$groupcheck \<slot>|DMs the user all checks in the slot's ItemQueue file, used to catch up on group games|
|$hints|DMs the hinted items for a player's registered slots|
|$deathcount|Scans the deathlog and tallies up the current deathcount for each slot|
|$checkcount|Fetches the current Arch server's progress in simple txt format|
|$checkgraph|Plots the current Arch progress in a picture|

|Debug Commands|Description|
|---|---|
|$iloveyou|We all need to hear this sometimes.|
|$hello|The bot says hello!|
|$reloadtracker|Forces the tracker client to reload|
|$reloaddiscord|Forces the discord bot to reload|
|$setenv \<key> \<value>|Allows you to set .env options via discord|
||Current keys: ArchipelagoPort, ArchipelagoPassword, ArchipelagoTrackerURL, ArchipelagoServerURL, UniqueID|
|$ArchInfo|\[CONSOLE] General bot details for debugging .env tables^|

**\[^] DebugMode only commands**  
**\[^] DebugMode can expose unintended system information. Use with care.**
  
## .env Keys and Descriptions
|Key|Description|
|---|---|
|**Discord Config**||
|DiscordToken|Your Discord Bot's token|
|DiscordBroadcastChannel|Discord Channel ID for live-check purposes|
|DiscordAlertUserID|Discord User/Group ID for yelling about issues%|
|DiscordDebugChannel|Discord channel ID for debug purposes|
|||
|**Archipelago Config**||
|ArchipelagoServer|The URL of the Archipelago server you'd like to connect to|
|ArchipelagoPort|The port of the Archipelago server you'd like to connect to|
|ArchipelagoPassword|The password of the Archipelago sroom you'd like to connect to|
|ArchipelagoBotSlot|The name of the slot you'd like the bot to use when connecting to archipelago|
|ArchipelagoTrackerURL|URL of the tracker you'd like to query|
|ArchipelagoServerURL|URL of the server you'd like to query|
|UniqueID|This UniqueID will sort all the game data into a key'd folder so you can swap between rooms via discord #|
|||
|**Item Filter Config**||
|BotItemSpoilTraps|The Bot will spoil traps by posting them in chat and ketchmeup&|
|BotItemFilterLevel|Sets the bot filter level 0 - 1 - 2, to exclude items from discord posts&|
||All items are still be queued for ketchmeup|
||2 - Only Logical Progression Items|
||1 - Logical + Useful items|
||0 - Logical + Useful + Normal items|
|||
|**Relay Config**||
|ChatMessages|Will relay chat messages (This also includes any ! messages, eg. !hint, !release, !collect)|
|ServerChatMessages|Will relay server chat messages|
|GoalMessages|Will relay goal messages|
|ReleaseMessages|Will relay release messages|
|CollectMessages|Will relay collect messages|
|CountdownMessages|Will relay server coutndown messages|
|DeathlinkMessages|Will relay deathlink messages|
|||
|**! Command Config**||
|APClientHelp|Will relay `!help` to discord|
|APClientLicense|Will relay `!License` to discord|
|APClientCountdown|etc...|
|APClientOptions|etc...|
|APClientAdmin||
|APClientPlayers||
|APClientStatus||
|APClientRelease||
|APClientCollect||
|APClientRemaining||
|APClientMissing||
|APClientChecked||
|APClientAlias||
|APClientGetItem||
|APClientHint||
|APClientHintLocation||
|APClientVideo|You get the idea. :)|
|||
|**Drawbridge Config**||
|DiscordBridgeEnabled|Will toggle the ability to send messages to AP from Discord|
|||
|**Meta Config**||
|FlavorDeathLink|Will change deathlink messages to have a little more personality$|
|DeathLinkLottery|Unused... for now >:) |
|||
|**Advanced Config**||
|LoggingDirectory|Directory of the bot's own logs*|
|PlayerRegistrationDirectory|Directory of the Player Registration Mappings*|
|PlayerItemQueueDirectory|Directory that stores player item queues*|
|ArchipelagoDataDirectory|Directory for the Archipelago data packages*|
|QueueOverclock|The speed the bot will process messages|
||1 - 1/second (default)|
||0.5 - 2/second|
||0.2 - 5/second|
||0.1 - 10/second|
|SnoozeCompletedGames|Enables skipping posting items to discord FOR completed games|
|JoinMessage|A custom join message (console only) for the bot|
|DebugMode|Enables extra debug chat/bot options^|
|SelfHostNoWeb|Disabled WebHost-specific functionality for self-hosted games with no WebHost module|
|CycleDiscord|Setting to a value above 0 will restart the discord process every X seconds|

**\[%] For group IDs, ensure the '&' character is at the beggining of the ID** 

**\[#] Check [UniqueID](docs/setup.md/#UniqueID) in the setup readme on what this value is used for**  

**\[&] Items will still be logged in the BotLog**

**\[$] Edit /modules/DeathlinkFlavor.py to your heart's content for custom flavor**

**\[*] Ensure directories end in a /**  
**\[*] These should be four diffrent directories, all these logs in the same place will break the bot.**

**\[^] DebugMode can expose unintended system information. Use with care.**

---
---

### Special Thanks

Thank you to the people who encourged me to pour my time into this bot. Specificaly the Zajcats.

Thank you to Rainwave Discord community to help with a private beta and bugfixing.

Thank you to [endrawr](https://github.com/endrawr) and [ZeroShork](https://github.com/ZeroShork) for getting the basics of the docker implimentation set up and allowing me to use their work.

Thank you to the Archipelago Community for making an amazing platform for the world to use.



