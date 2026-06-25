"""Test cases for plugins/bansync.py (#341)."""
import unittest

from netlink import world
from netlink.plugins import bansync


class _Conn:
    def __init__(self, v=True):
        self._v = v

    def is_set(self):
        return self._v


class _FakeIRC:
    def __init__(self, name, enabled=True):
        self.name = name
        self.serverdata = {'bansync': enabled}
        self.connected = _Conn(True)
        self.sid = name.upper()[:3]
        self.pseudoclient = None
        self.bans = []
        self.unbans = []

    def set_server_ban(self, source, duration, user, host, reason):
        self.bans.append((source, duration, user, host, reason))

    def del_server_ban(self, source, user, host):
        self.unbans.append((source, user, host))


class BanSyncTest(unittest.TestCase):
    def setUp(self):
        bansync._recently_synced.clear()
        self._saved = dict(world.networkobjects)
        world.networkobjects.clear()
        self.a = _FakeIRC('neta')
        self.b = _FakeIRC('netb')
        self.c = _FakeIRC('netc', enabled=False)
        world.networkobjects.update({'neta': self.a, 'netb': self.b, 'netc': self.c})

    def tearDown(self):
        bansync._recently_synced.clear()
        world.networkobjects.clear()
        world.networkobjects.update(self._saved)

    def _ban_args(self, mask='*@1.2.3.4', user='*', host='1.2.3.4', btype='G'):
        return {'type': btype, 'mask': mask, 'user': user, 'host': host,
                'duration': 0, 'reason': 'spam'}

    def test_ban_propagates_to_other_enabled_networks(self):
        bansync.handle_server_ban(self.a, 'src', 'SERVER_BAN', self._ban_args())
        self.assertEqual(len(self.b.bans), 1)   # netb enabled -> got it
        self.assertEqual(len(self.a.bans), 0)   # not replayed back to origin
        self.assertEqual(len(self.c.bans), 0)   # netc disabled -> skipped

    def test_echo_is_suppressed(self):
        bansync.handle_server_ban(self.a, 'src', 'SERVER_BAN', self._ban_args())
        # netb echoes the same ban back; it must not bounce around.
        bansync.handle_server_ban(self.b, 'src', 'SERVER_BAN', self._ban_args())
        self.assertEqual(len(self.a.bans), 0)
        self.assertEqual(len(self.b.bans), 1)

    def test_disabled_origin_does_nothing(self):
        self.a.serverdata['bansync'] = False
        bansync.handle_server_ban(self.a, 'src', 'SERVER_BAN', self._ban_args())
        self.assertEqual(len(self.b.bans), 0)

    def test_non_g_line_ignored(self):
        bansync.handle_server_ban(self.a, 'src', 'SERVER_BAN', self._ban_args(btype='Z'))
        self.assertEqual(len(self.b.bans), 0)

    def test_disconnected_network_skipped(self):
        self.b.connected = _Conn(False)
        bansync.handle_server_ban(self.a, 'src', 'SERVER_BAN', self._ban_args())
        self.assertEqual(len(self.b.bans), 0)

    def test_unban_propagates(self):
        bansync.handle_server_unban(self.a, 'src', 'SERVER_UNBAN',
                                    {'type': 'G', 'mask': '*@1.2.3.4', 'user': '*', 'host': '1.2.3.4'})
        self.assertEqual(len(self.b.unbans), 1)
        self.assertEqual(len(self.a.unbans), 0)


if __name__ == '__main__':
    unittest.main()
