import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parent

def load_on_ready():
    tree = ast.parse((ROOT / "bridgeipelago.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_ready")
    function.decorator_list = []
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "bridgeipelago.py", "exec"), namespace)
    return namespace["on_ready"]

class FakeTask:
    def __init__(self):
        self.running = False
        self.start = Mock(side_effect=self._start)
    def _start(self):
        self.running = True
    def is_running(self):
        return self.running

class ConnectionAnnouncementTests(unittest.TestCase):
    def test_disabled_slash_toggle_syncs_an_empty_guild_command_set(self):
        on_ready = load_on_ready()
        main_channel = SimpleNamespace(guild=SimpleNamespace(id=123))
        client = SimpleNamespace(get_channel=lambda channel_id: main_channel, user="mock bot")
        tree = SimpleNamespace(copy_global_to=Mock(), clear_commands=Mock(), sync=AsyncMock())
        tasks = [FakeTask() for _ in range(5)]
        namespace = on_ready.__globals__
        guild = SimpleNamespace(id=123)
        namespace.update({
            "CoreConfig": {"DiscordConfig": {"DiscordBroadcastChannel": "1", "DiscordDebugChannel": "2"},
                           "CommandConfig": {"SlashCommandsEnabled": False},
                           "AdvancedConfig": {"JoinMessage": "ready"}},
            "discord_client": client, "discord": SimpleNamespace(Object=lambda id: guild),
            "MainChannel": None, "DebugChannel": None, "PlayerCommandsSyncedGuild": None,
            "PlayerCommandsSyncedEnabled": None, "SlashCommandsEnabled": lambda: False, "tree": tree,
            "CheckArchHost": tasks[0], "ProcessItemQueue": tasks[1], "ProcessDeathQueue": tasks[2],
            "ProcessChatQueue": tasks[3], "CheckCommandQueue": tasks[4],
            "StartDailyPostScheduler": AsyncMock(),
        })
        with unittest.mock.patch("builtins.print"):
            asyncio.run(on_ready())
        tree.copy_global_to.assert_not_called()
        tree.clear_commands.assert_called_once_with(guild=guild)
        tree.sync.assert_awaited_once()

    def run_ready_twice(self, announce_setting, main_channel=None, sync_side_effect=None):
        on_ready = load_on_ready()
        debug_channel = SimpleNamespace(send=AsyncMock())
        if main_channel is None:
            main_channel = SimpleNamespace(guild=SimpleNamespace(id=123))
        client = SimpleNamespace(get_channel=lambda channel_id: {1: main_channel, 2: debug_channel}[channel_id], user="mock bot")
        tree = SimpleNamespace(copy_global_to=Mock(), sync=AsyncMock(side_effect=sync_side_effect))
        tasks = [FakeTask() for _ in range(5)]
        discord = SimpleNamespace(Object=lambda id: SimpleNamespace(id=id), HTTPException=Exception)
        discord_config = {"DiscordBroadcastChannel": "1", "DiscordDebugChannel": "2"}
        if announce_setting is not ...:
            discord_config["AnnounceConnection"] = announce_setting
        namespace = on_ready.__globals__
        namespace["SlashCommandsEnabled"] = lambda: True
        namespace.update({
            "CoreConfig": {"DiscordConfig": discord_config, "AdvancedConfig": {"JoinMessage": "ready"}},
            "discord_client": client, "discord": discord, "MainChannel": None, "DebugChannel": None,
            "PlayerCommandsSyncedGuild": None, "PlayerCommandsSyncedEnabled": None, "tree": tree,
            "CheckArchHost": tasks[0], "ProcessItemQueue": tasks[1], "ProcessDeathQueue": tasks[2],
            "ProcessChatQueue": tasks[3], "CheckCommandQueue": tasks[4],
            "StartDailyPostScheduler": AsyncMock(),
        })
        with unittest.mock.patch("builtins.print"):
            asyncio.run(on_ready())
            asyncio.run(on_ready())
        return debug_channel, tree, tasks

    def test_missing_or_false_setting_suppresses_only_startup_announcement(self):
        for setting in (..., False):
            with self.subTest(setting=setting):
                debug, tree, tasks = self.run_ready_twice(setting)
                debug.send.assert_not_awaited()
                self.assertEqual(tree.sync.await_count, 1)
                self.assertEqual(tree.copy_global_to.call_count, 1)
                for task in tasks:
                    task.start.assert_called_once_with()

    def test_true_setting_keeps_announcement_on_each_ready(self):
        debug, tree, tasks = self.run_ready_twice(True)
        self.assertEqual(debug.send.await_count, 2)
        debug.send.assert_awaited_with("Bot connected. Debug control - Online.")
        self.assertEqual(tree.sync.await_count, 1)
        for task in tasks:
            task.start.assert_called_once_with()

    def test_missing_broadcast_channel_skips_sync_but_starts_background_tasks(self):
        on_ready = load_on_ready()
        debug_channel = SimpleNamespace(send=AsyncMock())
        client = SimpleNamespace(get_channel=lambda channel_id: None if channel_id == 1 else debug_channel, user="mock bot")
        tree = SimpleNamespace(copy_global_to=Mock(), sync=AsyncMock())
        tasks = [FakeTask() for _ in range(5)]
        namespace = on_ready.__globals__
        namespace.update({
            "CoreConfig": {"DiscordConfig": {"DiscordBroadcastChannel": "1", "DiscordDebugChannel": "2"},
                           "AdvancedConfig": {"JoinMessage": "ready"}},
            "discord_client": client, "discord": SimpleNamespace(Object=Mock()), "MainChannel": None,
            "DebugChannel": None, "PlayerCommandsSyncedGuild": None, "PlayerCommandsSyncedEnabled": None,
            "SlashCommandsEnabled": lambda: True, "tree": tree,
            "CheckArchHost": tasks[0], "ProcessItemQueue": tasks[1], "ProcessDeathQueue": tasks[2],
            "ProcessChatQueue": tasks[3], "CheckCommandQueue": tasks[4],
            "StartDailyPostScheduler": AsyncMock(),
        })
        with unittest.mock.patch("builtins.print") as printed:
            asyncio.run(on_ready())
        tree.sync.assert_not_awaited()
        tree.copy_global_to.assert_not_called()
        for task in tasks:
            task.start.assert_called_once_with()
        self.assertTrue(any("configured broadcast channel is missing" in str(call) for call in printed.call_args_list))

    def test_sync_failure_happens_after_background_tasks_start(self):
        tasks = [FakeTask() for _ in range(5)]

        async def fail_sync(*args, **kwargs):
            self.assertTrue(all(task.is_running() for task in tasks))
            raise RuntimeError("Discord temporarily unavailable")

        on_ready = load_on_ready()
        debug_channel = SimpleNamespace(send=AsyncMock())
        main_channel = SimpleNamespace(guild=SimpleNamespace(id=123))
        client = SimpleNamespace(get_channel=lambda channel_id: {1: main_channel, 2: debug_channel}[channel_id], user="mock bot")
        tree = SimpleNamespace(copy_global_to=Mock(), sync=AsyncMock(side_effect=fail_sync))
        namespace = on_ready.__globals__
        namespace.update({
            "CoreConfig": {"DiscordConfig": {"DiscordBroadcastChannel": "1", "DiscordDebugChannel": "2"},
                           "AdvancedConfig": {"JoinMessage": "ready"}},
            "discord_client": client, "discord": SimpleNamespace(Object=lambda id: SimpleNamespace(id=id)),
            "MainChannel": None, "DebugChannel": None, "PlayerCommandsSyncedGuild": None,
            "PlayerCommandsSyncedEnabled": None, "SlashCommandsEnabled": lambda: True, "tree": tree,
            "CheckArchHost": tasks[0], "ProcessItemQueue": tasks[1], "ProcessDeathQueue": tasks[2],
            "ProcessChatQueue": tasks[3], "CheckCommandQueue": tasks[4],
            "StartDailyPostScheduler": AsyncMock(),
        })
        with unittest.mock.patch("builtins.print") as printed:
            asyncio.run(on_ready())
        tree.sync.assert_awaited_once()
        for task in tasks:
            task.start.assert_called_once_with()
        printed_text = " ".join(str(call) for call in printed.call_args_list)
        self.assertIn("RuntimeError", printed_text)
        # Exception text can carry request details, so only the type is logged.
        self.assertNotIn("Discord temporarily unavailable", printed_text)

if __name__ == "__main__":
    unittest.main()
