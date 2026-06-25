"""Test cases for coremods/service_support.py (global command flood protection, #383)."""
import time
import unittest

from netlink import conf, world
from netlink.coremods import service_support as ss


class _FakeIRC:
    name = 'testnet'

    def get_hostmask(self, source):
        return 'nick!user@host'


class CommandFloodTest(unittest.TestCase):
    KEYS = ('command_flood_count', 'command_flood_time')

    def setUp(self):
        ss._recent_command_times.clear()
        self.irc = _FakeIRC()
        self._saved = {k: conf.conf['netlink'].get(k) for k in self.KEYS}

    def tearDown(self):
        ss._recent_command_times.clear()
        for k, v in self._saved.items():
            if v is None:
                conf.conf['netlink'].pop(k, None)
            else:
                conf.conf['netlink'][k] = v

    def test_disabled_by_default(self):
        conf.conf['netlink'].pop('command_flood_count', None)
        for _ in range(50):
            self.assertFalse(ss._command_flood_check(self.irc, 'u'))

    def test_drops_over_limit(self):
        conf.conf['netlink']['command_flood_count'] = 3
        conf.conf['netlink']['command_flood_time'] = 100
        self.assertFalse(ss._command_flood_check(self.irc, 'u'))  # 1
        self.assertFalse(ss._command_flood_check(self.irc, 'u'))  # 2
        self.assertFalse(ss._command_flood_check(self.irc, 'u'))  # 3
        self.assertTrue(ss._command_flood_check(self.irc, 'u'))   # 4 -> dropped
        self.assertTrue(ss._command_flood_check(self.irc, 'u'))   # still dropped

    def test_window_expiry_allows_again(self):
        conf.conf['netlink']['command_flood_count'] = 1
        conf.conf['netlink']['command_flood_time'] = 10
        # An entry older than the window must be purged, so the next call is allowed.
        ss._recent_command_times.append(time.time() - 100)
        self.assertFalse(ss._command_flood_check(self.irc, 'u'))


class _Sbot:
    def __init__(self):
        self.called = []

    def call_cmd(self, irc, source, text):
        self.called.append(source)


class HandleCommandsIgnoreTest(unittest.TestCase):
    """The dispatcher consults a loaded ignore plugin (#495)."""

    def setUp(self):
        ss._recent_command_times.clear()
        conf.conf['netlink'].pop('command_flood_count', None)
        self.sbot = _Sbot()

        class _IRC:
            name = 'testnet'

            def get_service_bot(_self, target):
                return self.sbot

            def get_hostmask(_self, s):
                return 's!u@h'

        self.irc = _IRC()

        class _Ignore:
            @staticmethod
            def is_ignored(irc, uid):
                return uid == 'spammer'

        world.plugins['ignore'] = _Ignore

    def tearDown(self):
        world.plugins.pop('ignore', None)
        ss._recent_command_times.clear()

    def test_ignored_source_is_dropped(self):
        ss.handle_commands(self.irc, 'spammer', 'PRIVMSG', {'target': 'bot', 'text': 'help'})
        self.assertEqual(self.sbot.called, [])

    def test_normal_source_is_processed(self):
        ss.handle_commands(self.irc, 'normal', 'PRIVMSG', {'target': 'bot', 'text': 'help'})
        self.assertEqual(self.sbot.called, ['normal'])


if __name__ == '__main__':
    unittest.main()
