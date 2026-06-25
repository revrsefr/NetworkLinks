"""Test cases for coremods/service_support.py (global command flood protection, #383)."""
import time
import unittest

from netlink import conf
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


if __name__ == '__main__':
    unittest.main()
