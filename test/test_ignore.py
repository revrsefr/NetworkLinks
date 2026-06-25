"""Test cases for plugins/ignore.py (#495)."""
import unittest
from unittest.mock import patch

from netlink.plugins import ignore


class _FakeUser:
    pass


class _FakeIRC:
    def __init__(self):
        self.name = 'testnet'
        self.users = {}
        self._internal = set()
        self._match = {}   # mask -> set of matching uids
        self.replies = []
        self.errors = []

    def is_internal_client(self, uid):
        return uid in self._internal

    def match_host(self, mask, uid):
        return uid in self._match.get(mask, set())

    def get_hostmask(self, uid):
        return '%s!u@h' % uid

    def reply(self, text, **k):
        self.replies.append(text)

    def error(self, text, **k):
        self.errors.append(text)


class IgnoreTest(unittest.TestCase):
    def setUp(self):
        ignore.db['masks'] = []
        self._patches = [
            patch.object(ignore.permissions, 'check_permissions', return_value=True),
            patch.object(ignore.datastore, 'save'),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        ignore.db['masks'] = []

    # --- is_ignored ---
    def test_is_ignored_match(self):
        irc = _FakeIRC()
        irc.users['u1'] = _FakeUser()
        irc._match['*!*@bad'] = {'u1'}
        ignore.db['masks'] = ['*!*@bad']
        self.assertTrue(ignore.is_ignored(irc, 'u1'))

    def test_is_ignored_no_match(self):
        irc = _FakeIRC()
        irc.users['u1'] = _FakeUser()
        ignore.db['masks'] = ['*!*@bad']
        self.assertFalse(ignore.is_ignored(irc, 'u1'))

    def test_internal_clients_never_ignored(self):
        irc = _FakeIRC()
        irc.users['u1'] = _FakeUser()
        irc._internal.add('u1')
        irc._match['*'] = {'u1'}
        ignore.db['masks'] = ['*']
        self.assertFalse(ignore.is_ignored(irc, 'u1'))

    def test_unknown_user_not_ignored(self):
        irc = _FakeIRC()
        ignore.db['masks'] = ['*']
        self.assertFalse(ignore.is_ignored(irc, 'ghost'))

    # --- ignore command ---
    def test_add_then_list_then_del(self):
        irc = _FakeIRC()
        ignore.ignore(irc, 'u', ['add', '*!*@x'])
        self.assertIn('*!*@x', ignore.db['masks'])
        irc2 = _FakeIRC()
        ignore.ignore(irc2, 'u', ['list'])
        self.assertTrue(any('*!*@x' in r for r in irc2.replies))
        ignore.ignore(irc, 'u', ['del', '*!*@x'])
        self.assertNotIn('*!*@x', ignore.db['masks'])

    def test_list_empty(self):
        irc = _FakeIRC()
        ignore.ignore(irc, 'u', [])
        self.assertTrue(any('none' in r.lower() for r in irc.replies))

    def test_add_without_mask_errors(self):
        irc = _FakeIRC()
        ignore.ignore(irc, 'u', ['add'])
        self.assertTrue(irc.errors)

    def test_unknown_subcommand_errors(self):
        irc = _FakeIRC()
        ignore.ignore(irc, 'u', ['frobnicate', 'x'])
        self.assertTrue(irc.errors)


if __name__ == '__main__':
    unittest.main()
