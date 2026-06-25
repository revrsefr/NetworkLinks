"""Test cases for plugins/automode.py."""
import unittest
from unittest.mock import patch

from netlink import utils
from netlink.plugins import automode


class _FakeChannel:
    def __init__(self, users=None):
        self.users = set(users or [])


class _FakeIRC:
    def __init__(self):
        self.name = 'testnet'
        self.users = {}
        self.channels = {}
        self.prefixmodes = {'o': '@', 'v': '+', 'h': '%'}
        self.sid = '7NL'
        self.protoname = 'inspircd'
        self._caps = {'has-irc-modes'}
        self._hostmatch = {}
        self.actions = []

    def has_cap(self, c):
        return c in self._caps

    def to_lower(self, s):
        return s.lower()

    def get_hostmask(self, uid):
        return '%s!u@h' % uid

    def match_host(self, mask, uid):
        return uid in self._hostmatch.get(mask, set())

    def mode(self, src, chan, modes):
        self.actions.append(('mode', chan, list(modes)))

    def call_hooks(self, args):
        pass


class AutomodeTestBase(unittest.TestCase):
    def setUp(self):
        automode.db.clear()
        self.replies = []
        self.errors = []
        self._patches = [
            patch.object(automode, 'reply', side_effect=lambda irc, t, **k: self.replies.append(t)),
            patch.object(automode, 'error', side_effect=lambda irc, t, **k: self.errors.append(t)),
            patch.object(automode.permissions, 'check_permissions', return_value=True),
            patch.object(automode.modebot, 'add_persistent_channel'),
            patch.object(automode.modebot, 'remove_persistent_channel'),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        automode.db.clear()


class GetChannelPairTest(AutomodeTestBase):
    def test_local_channel(self):
        irc = _FakeIRC()
        ircobj, channel = automode._get_channel_pair(irc, 'u', '#chan')
        self.assertIs(ircobj, irc)
        self.assertEqual(channel, '#chan')

    def test_invalid_pair_raises(self):
        irc = _FakeIRC()
        with self.assertRaises(ValueError):
            automode._get_channel_pair(irc, 'u', 'nohash')


class SetAccTest(AutomodeTestBase):
    def test_sets_modes(self):
        irc = _FakeIRC()
        automode.setacc(irc, 'u', ['#chan', '*!*@host', '+ov'])
        self.assertEqual(automode.db['testnet#chan']['*!*@host'], 'ov')
        self.assertTrue(self.replies)

    def test_requires_modes_cap(self):
        irc = _FakeIRC()
        irc._caps.clear()
        automode.setacc(irc, 'u', ['#chan', '*!*@host', 'ov'])
        self.assertTrue(self.errors)

    def test_wrong_arg_count(self):
        irc = _FakeIRC()
        automode.setacc(irc, 'u', ['#chan', '*!*@host'])
        self.assertTrue(self.errors)


class DelAccTest(AutomodeTestBase):
    def test_remove_by_mask(self):
        irc = _FakeIRC()
        automode.db['testnet#chan'] = {'*!*@host': 'ov', '$account': 'v'}
        automode.delacc(irc, 'u', ['#chan', '*!*@host'])
        self.assertNotIn('*!*@host', automode.db['testnet#chan'])

    def test_remove_last_purges_channel(self):
        irc = _FakeIRC()
        automode.db['testnet#chan'] = {'*!*@host': 'ov'}
        automode.delacc(irc, 'u', ['#chan', '*!*@host'])
        self.assertNotIn('testnet#chan', automode.db)

    def test_remove_by_range(self):
        irc = _FakeIRC()
        automode.db['testnet#chan'] = {'a': 'o', 'b': 'o', 'c': 'o'}
        automode.delacc(irc, 'u', ['#chan', '1'])  # remove first sorted entry ('a')
        self.assertNotIn('a', automode.db['testnet#chan'])

    def test_no_entries_errors(self):
        irc = _FakeIRC()
        automode.delacc(irc, 'u', ['#chan', '*!*@host'])
        self.assertTrue(self.errors)

    def test_wrong_args(self):
        irc = _FakeIRC()
        automode.delacc(irc, 'u', ['#chan'])
        self.assertTrue(self.errors)


class ListAccTest(AutomodeTestBase):
    def test_lists_entries(self):
        irc = _FakeIRC()
        automode.db['testnet#chan'] = {'*!*@a': 'o', '*!*@b': 'v'}
        automode.listacc(irc, 'u', ['#chan'])
        joined = ' '.join(self.replies)
        self.assertIn('*!*@a', joined)
        self.assertIn('*!*@b', joined)

    def test_empty_errors(self):
        irc = _FakeIRC()
        automode.listacc(irc, 'u', ['#chan'])
        self.assertTrue(self.errors)

    def test_no_args_errors(self):
        irc = _FakeIRC()
        automode.listacc(irc, 'u', [])
        self.assertTrue(self.errors)


class MatchTest(AutomodeTestBase):
    def test_applies_modes_to_matching_user(self):
        irc = _FakeIRC()
        automode.modebot.uids['testnet'] = 'ABOT'
        irc.users['ABOT'] = object()
        irc.users['u1'] = object()
        irc.channels['#chan'] = _FakeChannel(users={'u1'})
        irc._hostmatch['*!*@good'] = {'u1'}
        automode.db['testnet#chan'] = {'*!*@good': 'ov'}
        try:
            automode.match(irc, '#chan')
        finally:
            automode.modebot.uids.pop('testnet', None)
        self.assertTrue(any(a[0] == 'mode' for a in irc.actions))
        modes = [a for a in irc.actions if a[0] == 'mode'][0][2]
        self.assertIn(('+o', 'u1'), modes)
        self.assertIn(('+v', 'u1'), modes)

    def test_no_dbentry_is_noop(self):
        irc = _FakeIRC()
        automode.match(irc, '#nope')
        self.assertFalse(irc.actions)

    def test_skips_without_modes_cap(self):
        irc = _FakeIRC()
        irc._caps.clear()
        automode.db['testnet#chan'] = {'*!*@good': 'o'}
        automode.match(irc, '#chan')
        self.assertFalse(irc.actions)


if __name__ == '__main__':
    unittest.main()
