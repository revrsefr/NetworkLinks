"""Test cases for the pure helper functions in plugins/relay.py."""
import unittest

from netlink.plugins import relay


class _FakeUser:
    def __init__(self, remote=None):
        if remote is not None:
            self.remote = remote


class _FakeIRC:
    def __init__(self, name):
        self.name = name
        self.users = {}

    def to_lower(self, s):
        return str(s).lower()


class RelayLookupTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(relay.db)
        relay.db.clear()
        # netA#chan is the shared channel; netB and netC link to it.
        relay.db[('neta', '#chan')] = {'links': {('netb', '#chan'), ('netc', '#other')},
                                       'creator': 'x', 'ts': 0}
        self.a = _FakeIRC('neta')
        self.b = _FakeIRC('netb')
        self.c = _FakeIRC('netc')

    def tearDown(self):
        relay.db.clear()
        relay.db.update(self._saved)

    def test_get_relay_shared_channel(self):
        self.assertEqual(relay.get_relay(self.a, '#chan'), ('neta', '#chan'))

    def test_get_relay_linked_channel(self):
        self.assertEqual(relay.get_relay(self.b, '#chan'), ('neta', '#chan'))
        self.assertEqual(relay.get_relay(self.c, '#other'), ('neta', '#chan'))

    def test_get_relay_case_insensitive(self):
        self.assertEqual(relay.get_relay(self.a, '#CHAN'), ('neta', '#chan'))

    def test_get_relay_none(self):
        self.assertIsNone(relay.get_relay(self.a, '#nope'))

    def test_get_remote_channel(self):
        # From neta's #chan, the linked channel on netb is #chan and on netc is #other.
        self.assertEqual(relay.get_remote_channel(self.a, self.b, '#chan'), '#chan')
        self.assertEqual(relay.get_remote_channel(self.a, self.c, '#chan'), '#other')

    def test_get_remote_channel_back_to_owner(self):
        # From netb's #chan, the linked channel on neta (the owner) is #chan.
        self.assertEqual(relay.get_remote_channel(self.b, self.a, '#chan'), '#chan')

    def test_get_remote_channel_none(self):
        self.assertIsNone(relay.get_remote_channel(self.a, self.b, '#nope'))


class IsRelayClientTest(unittest.TestCase):
    def test_relay_client(self):
        irc = _FakeIRC('neta')
        irc.users['relay1'] = _FakeUser(remote=('netb', 'origuid'))
        self.assertTrue(relay.is_relay_client(irc, 'relay1'))

    def test_local_client(self):
        irc = _FakeIRC('neta')
        irc.users['local1'] = _FakeUser()
        self.assertFalse(relay.is_relay_client(irc, 'local1'))

    def test_unknown_user(self):
        irc = _FakeIRC('neta')
        self.assertFalse(relay.is_relay_client(irc, 'ghost'))


if __name__ == '__main__':
    unittest.main()
