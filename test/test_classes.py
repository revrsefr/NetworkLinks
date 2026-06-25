"""Test cases for the core data model in classes.py."""
import time
import unittest

from netlink import conf
from netlink.classes import Channel, PUIDGenerator, Server, User
from netlink.protocols.inspircd import InspIRCdProtocol

# conf.conf['servers'] is a defaultdict; accessing 'test' materializes the entry so
# the protocol constructor's `if netname in servers` check passes (same trick the
# shared protocol_test_fixture relies on).
conf.conf['servers']['test']


class ClassesTestCase(unittest.TestCase):
    def setUp(self):
        self.p = InspIRCdProtocol('test')
        self.p.connect = lambda self: None
        # Minimal mode tables for ban/mode tests.
        self.p.cmodes = {'ban': 'b', 'banexception': 'e', 'op': 'o', 'voice': 'v',
                         '*A': 'be', '*B': 'k', '*C': 'l', '*D': 'imnpst'}
        self.p.prefixmodes = {'o': '@', 'v': '+'}
        self.p.extbans_acting = {}

    def _user(self, nick, uid, sid='7NL', **kw):
        kw.setdefault('ident', 'ident')
        kw.setdefault('host', 'host.example')
        kw.setdefault('realhost', 'real.example')
        kw.setdefault('ip', '1.2.3.4')
        kw.setdefault('realname', 'Real Name')
        u = User(self.p, nick, int(time.time()), uid, sid, **kw)
        self.p.users[uid] = u
        return u

    # --- validators ---
    def test_is_nick(self):
        self.assertTrue(self.p.is_nick('jlu5'))
        self.assertTrue(self.p.is_nick('[weird]_nick`'))
        self.assertFalse(self.p.is_nick('1startswithdigit'))
        self.assertFalse(self.p.is_nick('has space'))
        self.assertFalse(self.p.is_nick('toolong', nicklen=3))

    def test_is_channel(self):
        self.assertTrue(self.p.is_channel('#chan'))
        self.assertFalse(self.p.is_channel('chan'))
        self.assertFalse(self.p.is_channel('&local'))

    def test_is_server_name(self):
        self.assertTrue(self.p.is_server_name('irc.example.net'))
        self.assertFalse(self.p.is_server_name('noperiodhere'))

    def test_is_hostmask(self):
        self.assertTrue(self.p.is_hostmask('nick!user@host'))
        self.assertFalse(self.p.is_hostmask('useratdomain'))
        self.assertFalse(self.p.is_hostmask('nick!user@host#chan'))

    # --- to_lower (rfc1459) ---
    def test_to_lower_rfc1459(self):
        self.p.casemapping = 'rfc1459'
        self.assertEqual(self.p.to_lower('ABC{}|~'), 'abc[]\\^')

    # --- join_modes ---
    def test_join_modes_simple(self):
        self.assertEqual(self.p.join_modes([('+n', None), ('+t', None)]), '+nt')

    def test_join_modes_with_args(self):
        self.assertEqual(self.p.join_modes([('+o', 'AAA'), ('+v', 'BBB')]), '+ov AAA BBB')

    def test_join_modes_mixed_prefix(self):
        self.assertEqual(self.p.join_modes([('+n', None), ('-t', None)]), '+n-t')

    def test_join_modes_limit_arg(self):
        self.assertEqual(self.p.join_modes([('+l', '5')]), '+l 5')

    # --- lookups ---
    def test_nick_to_uid(self):
        self._user('Alice', 'uidA')
        self.assertEqual(self.p.nick_to_uid('Alice'), 'uidA')
        self.assertIsNone(self.p.nick_to_uid('Nobody'))
        self._user('Alice', 'uidA2')
        self.assertEqual(sorted(self.p.nick_to_uid('Alice', multi=True)), ['uidA', 'uidA2'])

    def test_is_internal_client_and_server(self):
        self.p.servers['7NL'] = Server(self.p, None, 'nexus.test', internal=True)
        self._user('Bob', 'uidB', sid='7NL')
        self.assertTrue(self.p.is_internal_client('uidB'))
        self.assertTrue(self.p.is_internal_server('7NL'))
        self.assertFalse(self.p.is_internal_server('XYZ'))

    def test_get_server(self):
        self._user('Carol', 'uidC', sid='7NL')
        self.assertEqual(self.p.get_server('uidC'), '7NL')

    # --- hostmask / friendly name ---
    def test_get_hostmask(self):
        self._user('Dave', 'uidD', host='shown.host', realhost='real.host', ip='9.9.9.9')
        self.assertEqual(self.p.get_hostmask('uidD'), 'Dave!ident@shown.host')
        self.assertEqual(self.p.get_hostmask('uidD', realhost=True), 'Dave!ident@real.host')
        self.assertEqual(self.p.get_hostmask('uidD', ip=True), 'Dave!ident@9.9.9.9')

    def test_get_hostmask_unknown(self):
        self.assertEqual(self.p.get_hostmask('ghost'),
                         '<unknown-nick>!<unknown-ident>@<unknown-host>')

    def test_get_friendly_name(self):
        self.p.servers['7NL'] = Server(self.p, None, 'nexus.test', internal=True)
        self._user('Erin', 'uidE')
        self.assertEqual(self.p.get_friendly_name('uidE'), 'Erin')
        self.assertEqual(self.p.get_friendly_name('7NL'), 'nexus.test')
        self.assertEqual(self.p.get_friendly_name('#chan'), '#chan')
        with self.assertRaises(KeyError):
            self.p.get_friendly_name('XXXXX')

    # --- bans ---
    def test_make_channel_ban(self):
        self._user('Frank', 'uidF', host='bad.host')
        self.assertEqual(self.p.make_channel_ban('uidF'), ('+b', '*!*@bad.host'))

    def test_make_channel_ban_unknown_user(self):
        with self.assertRaises(AssertionError):
            self.p.make_channel_ban('ghost')

    # --- has_cap ---
    def test_has_cap(self):
        self.assertTrue(self.p.has_cap('has-message-tags'))
        self.assertFalse(self.p.has_cap('totally-made-up-cap'))


class ChannelTestCase(unittest.TestCase):
    def setUp(self):
        self.p = InspIRCdProtocol('test')
        self.c = Channel(self.p, '#test')
        # Register some users in the channel.
        for uid in ('owner1', 'op1', 'hop1', 'voice1', 'plain1'):
            self.c.users.add(uid)
        self.c.prefixmodes['owner'].add('owner1')
        self.c.prefixmodes['op'].add('op1')
        self.c.prefixmodes['halfop'].add('hop1')
        self.c.prefixmodes['voice'].add('voice1')

    def test_individual_prefix_checks(self):
        self.assertTrue(self.c.is_op('op1'))
        self.assertTrue(self.c.is_voice('voice1'))
        self.assertTrue(self.c.is_halfop('hop1'))
        self.assertTrue(self.c.is_owner('owner1'))
        self.assertFalse(self.c.is_op('voice1'))

    def test_plus_checks(self):
        self.assertTrue(self.c.is_op_plus('owner1'))
        self.assertTrue(self.c.is_op_plus('op1'))
        self.assertFalse(self.c.is_op_plus('hop1'))
        self.assertTrue(self.c.is_halfop_plus('hop1'))
        self.assertTrue(self.c.is_voice_plus('voice1'))
        self.assertFalse(self.c.is_voice_plus('plain1'))

    def test_get_prefix_modes_sorted(self):
        self.p.users['multi'] = User(self.p, 'multi', 0, 'multi', '7NL')
        self.c.users.add('multi')
        self.c.prefixmodes['op'].add('multi')
        self.c.prefixmodes['voice'].add('multi')
        # owner ranks before op before voice; multi has op + voice.
        self.assertEqual(self.c.get_prefix_modes('multi'), ['op', 'voice'])

    def test_remove_user(self):
        self.c.remove_user('op1')
        self.assertNotIn('op1', self.c.users)
        self.assertNotIn('op1', self.c.prefixmodes['op'])


class PUIDGeneratorTest(unittest.TestCase):
    def test_sequential(self):
        gen = PUIDGenerator('PRE')
        self.assertEqual(gen.next_uid(), 'PRE@0')
        self.assertEqual(gen.next_uid(), 'PRE@1')
        self.assertEqual(gen.next_uid('OTHER'), 'OTHER@2')


if __name__ == '__main__':
    unittest.main()
