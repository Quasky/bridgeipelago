from pathlib import Path
import json
import os
import sys

# =========================
# PATHS
# =========================

def get_base_dir(CoreConfig):
    return os.getcwd() + "/ReactionRegister/" + CoreConfig["ArchipelagoConfig"]["UniqueID"] + '/'

def get_data_path(CoreConfig):
    return Path(get_base_dir(CoreConfig) + "RegisteredGames.json")

def get_config_path(CoreConfig):
    return Path(get_base_dir(CoreConfig) + "ReactionConfig.json")


# =========================
# CONFIG
# =========================

class ReactionConfig:
    def __init__(self, CoreConfig):
        self.base_dir = get_base_dir(CoreConfig)
        os.makedirs(self.base_dir, exist_ok=True)

        self.path = get_config_path(CoreConfig)

        self.config = {"ReactionChannel": None}
        self.data = {"messages": []}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    saved = json.load(f)
                    self.config.update(saved.get("config", {}))
                    self.data = {"messages": saved.get("messages", [])}
            except Exception as e:
                log_module_error(f"Failed to load config {self.path}: {e}")
                self.save()
        else:
            self.save()

    def save(self):
        with open(self.path, "w") as f:
            json.dump({
                "config": self.config,
                "messages": self.data["messages"]
            }, f, indent=2)

    def add_message(self, message_id, slots, emojis):
        self.data["messages"].append({
            "message_id": message_id,
            "slots": slots,
            "emojis": emojis
        })
        self.save()

    def get_all_messages(self):
        return self.data["messages"]

    def get_slot_by_reaction(self, message_id, emoji):
        for msg in self.data["messages"]:
            if msg["message_id"] == message_id:
                if emoji in msg["emojis"]:
                    return msg["slots"][msg["emojis"].index(emoji)]
        return None

    def is_managed_message(self, message_id):
        return any(msg["message_id"] == message_id for msg in self.data["messages"])


# =========================
# DATA (JSON)
# =========================

def load_data(CoreConfig):
    path = get_data_path(CoreConfig)
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_data(CoreConfig, data):
    path = get_data_path(CoreConfig)
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =========================
# MESSAGE BUILDER
# =========================

def build_message_content(slots, emojis, CoreConfig):
    data = load_data(CoreConfig)

    lines = ["**Slot Subscription**", "React to suscribe to slot:\n"]

    for i, slot in enumerate(slots):
        line = f"{emojis[i]} {slot}"
        if slot in data:
            info = data[slot]
            if info["type"] == 0:
                users = info.get("users", [])
                if users:
                    line += " => " + ", ".join([f"<@{u}>" for u in users])
            else:
                line += f" => <@&{info['role']}>"
        lines.append(line)

    return "\n".join(lines)


# =========================
# MESSAGE UPDATE
# =========================

async def update_reaction_message(bot, message_id, slots, emojis, CoreConfig, channel_id):
    channel = bot.get_channel(channel_id)
    if channel is None:
        log_module_error(f"Channel {channel_id} not found while updating message {message_id}")
        return
    try:
        message = await channel.fetch_message(message_id)
    except Exception as e:
        log_module_error(f"Failed to fetch reaction message {message_id}: {e}")
        return

    try:
        await message.edit(content=build_message_content(slots, emojis, CoreConfig))
    except Exception as e:
        log_module_error(f"Failed to edit reaction message {message_id}: {e}")


async def refresh_single_message(bot, config, CoreConfig, message_id):
    channel_id = config.config["ReactionChannel"]

    for msg in config.get_all_messages():
        if msg["message_id"] == message_id:
            await update_reaction_message(
                bot, msg["message_id"], msg["slots"], msg["emojis"], CoreConfig, channel_id
            )
            break


def log_module_error(message):
    main = sys.modules.get("bridgeipelago") or sys.modules.get("__main__")
    writer = getattr(main, "WriteToErrorLog", None)
    if writer:
        writer("ReactionRegister", message)


def get_registration_path(member_name):
    main = sys.modules.get("bridgeipelago") or sys.modules.get("__main__")
    get_core_directory = getattr(main, "GetCoreDirectory", None)
    if get_core_directory is None:
        raise RuntimeError("GetCoreDirectory is not available from the main module.")
    return Path(get_core_directory("reg")) / f"{member_name}.json"


def add_slot_registration(member_name, slot):
    registration_path = get_registration_path(member_name)
    registration_path.parent.mkdir(parents=True, exist_ok=True)

    if not registration_path.exists():
        registration_path.write_text("[]")

    registration_contents = json.loads(registration_path.read_text())
    if slot not in registration_contents:
        registration_contents.append(slot)
        registration_path.write_text(json.dumps(registration_contents, indent=4))


def remove_slot_registration(member_name, slot):
    registration_path = get_registration_path(member_name)

    if not registration_path.exists():
        return

    registration_contents = json.loads(registration_path.read_text())
    if slot in registration_contents:
        registration_contents.remove(slot)

    if registration_contents:
        registration_path.write_text(json.dumps(registration_contents, indent=4))
    else:
        registration_path.unlink(missing_ok=True)


# =========================
# MESSAGE CREATION
# =========================

EMOJIS = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🇦","🇧","🇨","🇩","🇪"]
CHUNK_SIZE = 15

async def create_reaction_messages(bot, channel, slots, config, CoreConfig):
    chunks = [slots[i:i+CHUNK_SIZE] for i in range(0, len(slots), CHUNK_SIZE)]

    for chunk in chunks:
        emojis = EMOJIS[:len(chunk)]
        msg = await channel.send(build_message_content(chunk, emojis, CoreConfig))

        for e in emojis:
            await msg.add_reaction(e)

        config.add_message(msg.id, chunk, emojis)


async def prompt_for_message(bot, check, timeout=30):
    try:
        return await bot.wait_for("message", timeout=timeout, check=check)
    except Exception:
        return None


async def prompt_for_reaction(bot, check, timeout=30):
    try:
        return await bot.wait_for("reaction_add", timeout=timeout, check=check)
    except Exception:
        return None


# =========================
# SETUP REACTIONREGISTER
# =========================

def setup(bot, CoreConfig):

    main = sys.modules.get("bridgeipelago") or sys.modules.get("__main__")
    GetCoreFiles = main.GetCoreFiles
    config = ReactionConfig(CoreConfig)

    original_on_message = getattr(bot, "on_message", None)

    async def new_on_message(message):

        if message.author.bot:
            return

        if not message.content.lower().strip().startswith('$setupreactionregister'):
            if original_on_message:
                await original_on_message(message)
            return

        if message.author.id != int(CoreConfig["DiscordConfig"]["DiscordAlertUserID"]):
            return

        if message.channel.id != int(CoreConfig["DiscordConfig"]["DiscordDebugChannel"]):
            return

        path = get_data_path(CoreConfig)

        if path.exists():
            confirm_msg = await message.channel.send(
                "⚠️ Configuration already exists.\nReact:\n✅ reset\n❌ cancel"
            )

            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")

            def check(r, u): return u == message.author and r.message.id == confirm_msg.id

            result = await prompt_for_reaction(bot, check)
            if not result:
                await message.channel.send("Setup cancelled: no reaction received in time.")
                return
            reaction, _ = result

            if str(reaction.emoji) == "❌":
                return

            #DELETE OLD DISCORD MESSAGES
            channel_id = config.config.get("ReactionChannel")
            if channel_id:
                channel = bot.get_channel(channel_id)
                if channel:
                    for msg in config.get_all_messages():
                        try:
                            m = await channel.fetch_message(msg["message_id"])
                            await m.delete()
                        except Exception as e:
                            log_module_error(f"Failed to delete old reaction message {msg['message_id']}: {e}")

            #DELETE DATA FILE
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except Exception as e:
                log_module_error(f"Failed to delete reaction data file {path}: {e}")

            #RESET CONFIG
            config.data = {"messages": []}
            config.config = {"ReactionChannel": None}
            config.save()

        await message.channel.send("Mention the reaction channel")

        def check(m): return m.author == message.author and m.channel == message.channel

        reply = await prompt_for_message(bot, check)
        if not reply:
            await message.channel.send("Setup cancelled: no channel reply received in time.")
            return
        if not reply.channel_mentions:
            await message.channel.send("Setup cancelled: you need to mention a channel.")
            return
        channel_id = reply.channel_mentions[0].id

        config.config["ReactionChannel"] = channel_id
        config.save()

        channel = bot.get_channel(channel_id)
        if channel is None:
            await message.channel.send("Setup cancelled: I couldn't access that channel.")
            return

        with open(GetCoreFiles("archconnectiondump")) as f:
            data = json.load(f)

        slots = [data['slot_info'][k]['name'] for k in data['slot_info']]

        confirm_msg = await message.channel.send(
            "Will there be slots assigned to role? (for group games)\nReact:\n✅ Yes\n❌ No"
        )

        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check_react(r, u): return u == message.author and r.message.id == confirm_msg.id

        result = await prompt_for_reaction(bot, check_react)
        if not result:
            await message.channel.send("Setup cancelled: no reaction received in time.")
            return
        reaction, _ = result

        group_map = {}

        if str(reaction.emoji) == "✅":
            await message.channel.send(
                "Configure slots assigned to roles using this format:\n"
                "`number @role`\n\n"
                "Example:\n"
                "`1 @PlayerRole`\n"
                "`3 @TeamRed`\n\n"
                "Each line assigns a slot to a role.\n"
                "Slots not listed will be treated as individual (no role)."
            )
            await message.channel.send("\n".join([f"{i+1}. {s}" for i, s in enumerate(slots)]))

            reply = await prompt_for_message(bot, check)
            if not reply:
                await message.channel.send("Setup cancelled: no role mapping reply received in time.")
                return

            for line in reply.content.splitlines():
                try:
                    num, role = line.split()
                    group_map[slots[int(num)-1]] = role.replace("<@&","").replace(">","")
                except Exception as e:
                    log_module_error(f"Invalid role mapping line '{line}': {e}")

        data = {
            s: {"type": 1, "role": group_map[s]} if s in group_map else {"type": 0, "users": []}
            for s in slots
        }

        save_data(CoreConfig, data)
        await create_reaction_messages(bot, channel, slots, config, CoreConfig)

        await message.channel.send("✅ Setup complete")

    bot.on_message = new_on_message

    # =========================
    # CHECK INITIAL SETUP, ON READY
    # =========================

    original_on_ready = getattr(bot, "on_ready", None)

    async def new_on_ready():
        if original_on_ready:
            await original_on_ready()

        if hasattr(bot, "_reactionregister_warned"):
            return
        bot._reactionregister_warned = True

        path = get_data_path(CoreConfig)

        needs_setup = False

        if not path.exists():
            needs_setup = True
        else:
            try:
                with open(path) as f:
                    data = json.load(f)
                    if not data:
                        needs_setup = True
            except Exception as e:
                log_module_error(f"Failed to inspect setup data {path}: {e}")
                needs_setup = True

        if needs_setup:
            channel = bot.get_channel(int(CoreConfig["DiscordConfig"]["DiscordDebugChannel"]))
            user_id = int(CoreConfig["DiscordConfig"]["DiscordAlertUserID"])

            if channel:
                await channel.send(
                    f"<@{user_id}> ⚠️ No ReactionRegister configuration detected.\n"
                    "Use `$setupreactionregister` to initialize it."
                )

    bot.on_ready = new_on_ready

    # =========================
    # REACTION HANDLERS
    # =========================

    async def new_add(payload):
        try:
            if bot.user is None or payload.user_id == bot.user.id:
                return

            if payload.guild_id is None:
                return

            if not config.is_managed_message(payload.message_id):
                return

            slot = config.get_slot_by_reaction(payload.message_id, str(payload.emoji))
            if not slot:
                return

            guild = bot.get_guild(payload.guild_id)
            if guild is None:
                log_module_error(f"Guild not found for reaction add: {payload.guild_id}")
                return

            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception as e:
                log_module_error(f"Unable to fetch member {payload.user_id} in guild {payload.guild_id}: {e}")
                return

            data = load_data(CoreConfig)
            info = data.get(slot)

            if not info:
                return

            #Type is for user/role
            #0=User
            #1=Role (meant for group games)
            if info["type"] == 0:
                users = info.get("users", [])
                if str(member.id) not in users:
                    users.append(str(member.id))
                try:
                    add_slot_registration(str(member), slot)
                except Exception as e:
                    log_module_error(f"Failed to add registration for {member} -> {slot}: {e}")
            else:
                role = guild.get_role(int(info["role"]))
                if role is None:
                    log_module_error(f"Role {info['role']} not found for slot {slot}")
                    return
                await member.add_roles(role)

            save_data(CoreConfig, data)
            await refresh_single_message(bot, config, CoreConfig, payload.message_id)
        except Exception as e:
            log_module_error(f"Unhandled reaction add error: {e}")

    bot.on_raw_reaction_add = new_add


    async def new_remove(payload):
        try:
            if bot.user is None or payload.user_id == bot.user.id:
                return

            if payload.guild_id is None:
                return

            if not config.is_managed_message(payload.message_id):
                return

            slot = config.get_slot_by_reaction(payload.message_id, str(payload.emoji))
            if not slot:
                return

            guild = bot.get_guild(payload.guild_id)
            if guild is None:
                log_module_error(f"Guild not found for reaction remove: {payload.guild_id}")
                return

            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception as e:
                log_module_error(f"Unable to fetch member {payload.user_id} in guild {payload.guild_id}: {e}")
                return

            data = load_data(CoreConfig)
            info = data.get(slot)

            if not info:
                return

            if info["type"] == 0:
                users = info.get("users", [])
                if str(member.id) in users:
                    users.remove(str(member.id))
                try:
                    remove_slot_registration(str(member), slot)
                except Exception as e:
                    log_module_error(f"Failed to remove registration for {member} -> {slot}: {e}")
            else:
                role = guild.get_role(int(info["role"]))
                if role is None:
                    log_module_error(f"Role {info['role']} not found for slot {slot}")
                    return
                await member.remove_roles(role)

            save_data(CoreConfig, data)
            await refresh_single_message(bot, config, CoreConfig, payload.message_id)
        except Exception as e:
            log_module_error(f"Unhandled reaction remove error: {e}")

    bot.on_raw_reaction_remove = new_remove
