"""Test cases for plugins/antispam.py."""
import unittest
from unittest.mock import patch

from netlink.plugins import antispam


class _Conn:
    def __init__(self, val=True):
        self._v = val

    def is_set(self):
        return self._v


class _FakeChannel:
    def __init__(self, users=None):
        self.users = set(users or [])
        self._voice = set()
        self._halfop = set()
        self._op = set()

    def is_voice_plus(self, uid):
        return uid in (self._voice | self._halfop | self._op)

    def is_halfop_plus(self, uid):
        return uid in (self._halfop | self._op)

    def is_op_plus(self, uid):
        return uid in self._op


class _FakeUser:
    def __init__(self, nick):
        self.nick = nick


class _FakeIRC:
    def __init__(self):
        self.name = 'testnet'
        self.users = {}
        self.channels = {}
        self.serverdata = {}
        self.connected = _Conn(True)
        self.pseudoclient = None
        self._caps = set()
        self._opers = set()
        self._internal = set()
        self.service_options = {}
        self.replies = []
        self.errors = []
        self.actions = []

    def has_cap(self, c):
        return c in self._caps

    def is_oper(self, uid):
        return uid in self._opers

    def is_internal_client(self, uid):
        return uid in self._internal

    def is_channel(self, t):
        return isinstance(t, str) and t.startswith(('#', '&'))

    def get_friendly_name(self, uid):
        return self.users[uid].nick if uid in self.users else uid

    def get_hostmask(self, uid):
        return '%s!u@h' % self.get_friendly_name(uid)

    def get_service_bot(self, uid):
        return None

    def get_service_option(self, service, option, default=None):
        return self.service_options.get(option, default)

    def make_channel_ban(self, uid, ban_type='ban'):
        return ('+b' if ban_type == 'ban' else '+q', '%s!*@*' % self.get_friendly_name(uid))

    def kick(self, my_uid, channel, target, reason):
        self.actions.append(('kick', channel, target))

    def kill(self, my_uid, target, reason):
        self.actions.append(('kill', target))

    def mode(self, my_uid, target, modes):
        self.actions.append(('mode', target, modes))

    def call_hooks(self, args):
        pass

    def reply(self, text, **k):
        self.replies.append(text)

    def error(self, text, **k):
        self.errors.append(text)


class AntispamUnicodeTest(unittest.TestCase):
    def test_homoglyphs_normalize_to_ascii(self):
        # Cyrillic 'а' (U+0430), Greek 'е'-lookalike, math bold etc. should map to ASCII.
        self.assertEqual('а'.translate(antispam.UNICODE_CHARMAP), 'a')
        self.assertEqual('\U0001d400'.translate(antispam.UNICODE_CHARMAP), 'A')  # bold A
        # A whole word built from lookalikes should munge to a plain word.
        word = 'viаgrа'  # "viagra" with cyrillic a's
        self.assertEqual(word.translate(antispam.UNICODE_CHARMAP), 'viagra')


class AntispamSpamfilterCmdTest(unittest.TestCase):
    def setUp(self):
        antispam.db['globs'] = []
        self._perm = patch.object(antispam.permissions, 'check_permissions', return_value=True)
        self._save = patch.object(antispam.datastore, 'save')
        self._perm.start()
        self._save.start()

    def tearDown(self):
        self._perm.stop()
        self._save.stop()
        antispam.db['globs'] = []

    def test_list_empty(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['list'])
        self.assertTrue(any('No text filters' in r for r in irc.replies))

    def test_add_then_list(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['add', '*viagra*'])
        self.assertIn('*viagra*', antispam.db['globs'])
        irc2 = _FakeIRC()
        antispam.spamfilter(irc2, 'u', ['list'])
        self.assertTrue(any('*viagra*' in r for r in irc2.replies))

    def test_add_is_idempotent(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['add', '*x*'])
        antispam.spamfilter(irc, 'u', ['add', '*x*'])
        self.assertEqual(antispam.db['globs'].count('*x*'), 1)

    def test_del(self):
        antispam.db['globs'] = ['*spam*']
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['del', '*spam*'])
        self.assertNotIn('*spam*', antispam.db['globs'])

    def test_add_without_glob_errors(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['add'])
        self.assertTrue(irc.errors)

    def test_unknown_subcommand_errors(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', ['frobnicate', 'x'])
        self.assertTrue(irc.errors)

    def test_no_args_defaults_to_list(self):
        irc = _FakeIRC()
        antispam.spamfilter(irc, 'u', [])
        self.assertTrue(any('No text filters' in r for r in irc.replies))


class AntispamPartQuitTest(unittest.TestCase):
    def _irc(self):
        irc = _FakeIRC()
        irc.service_options['partquit'] = {'watch_quits': True, 'watch_parts': True,
                                           'part_filter_message': 'FILTERED',
                                           'quit_filter_message': 'FILTERED'}
        irc.serverdata['antispam_partquit_globs'] = ['*badword*']
        return irc

    def test_quit_message_filtered(self):
        irc = self._irc()
        args = {'text': 'this has badword in it', 'userdata': _FakeUser('spammer')}
        antispam.handle_partquit(irc, 'u', 'QUIT', args)
        self.assertEqual(args['text'], 'FILTERED')

    def test_part_message_filtered(self):
        irc = self._irc()
        args = {'text': 'badword', 'channels': ['#a', '#b']}
        antispam.handle_partquit(irc, 'u', 'PART', args)
        self.assertEqual(args['text'], 'FILTERED')

    def test_no_text_is_noop(self):
        irc = self._irc()
        args = {'text': None}
        self.assertIsNone(antispam.handle_partquit(irc, 'u', 'QUIT', args))

    def test_non_matching_message_untouched(self):
        irc = self._irc()
        args = {'text': 'totally fine', 'userdata': _FakeUser('joe')}
        antispam.handle_partquit(irc, 'u', 'QUIT', args)
        self.assertEqual(args['text'], 'totally fine')

    def test_disabled_quits_noop(self):
        irc = self._irc()
        irc.service_options['partquit']['watch_quits'] = False
        args = {'text': 'badword', 'userdata': _FakeUser('joe')}
        antispam.handle_partquit(irc, 'u', 'QUIT', args)
        self.assertEqual(args['text'], 'badword')


class _TextfilterMixin:
    def _setup_irc(self, *, punishment='block'):
        irc = _FakeIRC()
        antispam.sbot.uids['testnet'] = 'ASBOT'
        irc.users['spammer'] = _FakeUser('spammer')
        irc.channels['#chan'] = _FakeChannel(users={'ASBOT', 'spammer'})
        irc.service_options['textfilter'] = {'enabled': True, 'punishment': punishment,
                                             'munge_unicode': False}
        irc.service_options['strip_formatting'] = False
        return irc


class AntispamTextfilterTest(unittest.TestCase, _TextfilterMixin):
    def setUp(self):
        antispam.db['globs'] = ['*viagra*']

    def tearDown(self):
        antispam.db['globs'] = []
        antispam.sbot.uids.pop('testnet', None)

    def test_matching_message_is_punished_and_filtered(self):
        irc = self._setup_irc()
        result = antispam.handle_textfilter(irc, 'spammer', 'PRIVMSG',
                                            {'target': '#chan', 'text': 'buy cheap viagra now'})
        self.assertFalse(result)  # punished -> filtered (return not punished)

    def test_non_matching_message_passes(self):
        irc = self._setup_irc()
        result = antispam.handle_textfilter(irc, 'spammer', 'PRIVMSG',
                                            {'target': '#chan', 'text': 'hello friends'})
        self.assertTrue(result)

    def test_disabled_is_noop(self):
        irc = self._setup_irc()
        irc.service_options['textfilter']['enabled'] = False
        self.assertIsNone(antispam.handle_textfilter(irc, 'spammer', 'PRIVMSG',
                          {'target': '#chan', 'text': 'viagra'}))

    def test_internal_client_ignored(self):
        irc = self._setup_irc()
        irc._internal.add('spammer')
        self.assertIsNone(antispam.handle_textfilter(irc, 'spammer', 'PRIVMSG',
                          {'target': '#chan', 'text': 'viagra'}))

    def test_munge_unicode_catches_homoglyph(self):
        irc = self._setup_irc()
        irc.service_options['textfilter']['munge_unicode'] = True
        result = antispam.handle_textfilter(irc, 'spammer', 'PRIVMSG',
                                            {'target': '#chan', 'text': 'viаgrа'})
        self.assertFalse(result)  # homoglyph "viagra" still matched and punished


class AntispamPunishTest(unittest.TestCase, _TextfilterMixin):
    def setUp(self):
        antispam.sbot.uids['testnet'] = 'ASBOT'

    def tearDown(self):
        antispam.sbot.uids.pop('testnet', None)

    def _irc(self):
        irc = _FakeIRC()
        irc.users['spammer'] = _FakeUser('spammer')
        irc.channels['#chan'] = _FakeChannel(users={'ASBOT', 'spammer'})
        irc.service_options['exempt_level'] = 'halfop'
        return irc

    def test_refuses_oper(self):
        irc = self._irc()
        irc._opers.add('spammer')
        self.assertFalse(antispam._punish(irc, 'spammer', '#chan', 'kill', 'r'))

    def test_refuses_unknown_target(self):
        irc = self._irc()
        self.assertFalse(antispam._punish(irc, 'ghost', '#chan', 'kill', 'r'))

    def test_invalid_punishment_returns_none(self):
        irc = self._irc()
        self.assertIsNone(antispam._punish(irc, 'spammer', '#chan', 'frobnicate', 'r'))

    def test_block_only_counts_as_success(self):
        irc = self._irc()
        self.assertTrue(antispam._punish(irc, 'spammer', '#chan', 'block', 'r'))

    def test_kick_calls_irc_kick(self):
        irc = self._irc()
        self.assertTrue(antispam._punish(irc, 'spammer', '#chan', 'kick', 'r'))
        self.assertIn(('kick', '#chan', 'spammer'), irc.actions)

    def test_ban_sets_mode(self):
        irc = self._irc()
        self.assertTrue(antispam._punish(irc, 'spammer', '#chan', 'ban', 'r'))
        self.assertTrue(any(a[0] == 'mode' for a in irc.actions))

    def test_kill_calls_irc_kill(self):
        irc = self._irc()
        self.assertTrue(antispam._punish(irc, 'spammer', None, 'kill', 'r'))
        self.assertIn(('kill', 'spammer'), irc.actions)

    def test_exempt_halfop_is_spared(self):
        irc = self._irc()
        irc.channels['#chan']._halfop.add('spammer')
        self.assertFalse(antispam._punish(irc, 'spammer', '#chan', 'kick', 'r'))


class AntispamMassHighlightTest(unittest.TestCase):
    def setUp(self):
        antispam.sbot.uids['testnet'] = 'ASBOT'

    def tearDown(self):
        antispam.sbot.uids.pop('testnet', None)

    def _irc(self, nicks):
        irc = _FakeIRC()
        chan = _FakeChannel(users={'ASBOT', 'spammer'})
        irc.users['ASBOT'] = _FakeUser('AntiSpam')
        for i, n in enumerate(nicks):
            uid = 'u%d' % i
            irc.users[uid] = _FakeUser(n)
            chan.users.add(uid)
        irc.users['spammer'] = _FakeUser('spammer')
        irc.channels['#chan'] = chan
        irc.service_options['masshighlight'] = {'enabled': True, 'min_length': 10,
                                                'min_nicks': 5, 'punishment': 'kick'}
        irc.service_options['strip_formatting'] = False
        return irc

    def test_mass_highlight_triggers_punishment(self):
        nicks = ['alice', 'bob', 'carol', 'dave', 'erin', 'frank']
        irc = self._irc(nicks)
        text = ' '.join(nicks) + ' check this out everyone'
        result = antispam.handle_masshighlight(irc, 'spammer', 'PRIVMSG',
                                               {'target': '#chan', 'text': text})
        self.assertFalse(result)  # punished -> filtered

    def test_short_message_ignored(self):
        irc = self._irc(['a', 'b', 'c', 'd', 'e'])
        self.assertIsNone(antispam.handle_masshighlight(irc, 'spammer', 'PRIVMSG',
                          {'target': '#chan', 'text': 'hi'}))

    def test_disabled_is_noop(self):
        irc = self._irc(['a', 'b', 'c', 'd', 'e'])
        irc.service_options['masshighlight']['enabled'] = False
        self.assertIsNone(antispam.handle_masshighlight(irc, 'spammer', 'PRIVMSG',
                          {'target': '#chan', 'text': 'a b c d e ' * 5}))


if __name__ == '__main__':
    unittest.main()
