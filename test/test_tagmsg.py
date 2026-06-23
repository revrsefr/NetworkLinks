"""
Tests for IRCv3 TAGMSG (message-tags) handling and forwarding.
"""
import time
import unittest

from pylinkirc import conf
from pylinkirc.classes import User, Server
from pylinkirc.protocols import inspircd, clientbot

import protocol_test_fixture as ptf


class _Base(unittest.TestCase):
    netname = 'test'
    serverdata = conf.conf['servers']['test']

    def setUp(self):
        self.p = self.proto_class(self.netname)
        self.p.connect = lambda self: None
        self.p.socket = ptf.DummySocket()
        if self.serverdata:
            self.p.serverdata = self.serverdata
        # Capture raw lines directly; there's no send thread/queue in unit tests.
        self.sent = []
        self.p.send = lambda data, queue=True: self.sent.append(data)

    def _sent(self):
        data = self.sent[-1]
        return data.decode() if isinstance(data, (bytes, bytearray)) else data


class InspIRCdTagmsgTest(_Base):
    proto_class = inspircd.InspIRCdProtocol

    def _setup_users(self):
        # A remote (non-internal) server + user that may originate a TAGMSG...
        self.p.servers['S1'] = Server(self.p, None, 'remote.server', internal=False)
        self.p.uplink = 'S1'
        self.p.users['S1ALICE'] = User(self.p, 'alice', int(time.time()), 'S1ALICE', 'S1')
        # ...and an internal server + client that may send one.
        self.p.servers['INT'] = Server(self.p, None, 'int.server', internal=True)
        self.p.sid = 'INT'
        self.p.users['INTBOT'] = User(self.p, 'bot', int(time.time()), 'INTBOT', 'INT')

    def test_has_message_tags_cap(self):
        self.assertTrue(self.p.has_cap('has-message-tags'))

    def test_handle_tagmsg_does_not_crash_on_list_args(self):
        # Regression: handler must read the target from the args list, not call
        # args.get() (args is a list, not the hook payload).
        self._setup_users()
        res = self.p.handle_tagmsg('S1ALICE', 'TAGMSG', ['#chan'])
        self.assertEqual(res, {'target': '#chan'})

    def test_handle_tagmsg_unknown_source_dropped(self):
        self._setup_users()
        self.assertIsNone(self.p.handle_tagmsg('NOSUCH', 'TAGMSG', ['#chan']))

    def test_handle_events_attaches_tags(self):
        # Full inbound pipeline: tags must reach the hook payload.
        self._setup_users()
        line = r'@+typing=active;+example/x=a\sb :S1ALICE TAGMSG #chan'
        hook = self.p.handle_events(line)
        self.assertIsNotNone(hook)
        self.assertEqual(hook[1], 'TAGMSG')
        self.assertEqual(hook[2]['target'], '#chan')
        self.assertEqual(hook[2]['tags']['+typing'], 'active')
        self.assertEqual(hook[2]['tags']['+example/x'], 'a b')  # \s unescaped

    def test_tagmsg_send_wire_order_and_roundtrip(self):
        self._setup_users()
        value = 'GS$ Mik r=Bronze p=0'
        self.p.tagmsg('INTBOT', '#chan', {'+tchatou.fr/gs': value})
        raw = self._sent().strip()
        # Tags MUST precede the source prefix.
        self.assertTrue(raw.startswith('@'), raw)
        self.assertIn(' :INTBOT TAGMSG #chan', raw)
        # The emitted tags must parse back to the original value.
        tagpart = raw.split(' ', 1)[0]
        parsed = self.p.parse_message_tags([tagpart])
        self.assertEqual(parsed['+tchatou.fr/gs'], value)

    def test_tagmsg_requires_internal_source(self):
        self._setup_users()
        with self.assertRaises(LookupError):
            self.p.tagmsg('S1ALICE', '#chan', {'+typing': 'active'})

    def test_tagmsg_noop_without_tags(self):
        self._setup_users()
        before = len(self.sent)
        self.p.tagmsg('INTBOT', '#chan', {})
        self.assertEqual(len(self.sent), before)

    def test_message_with_server_time_tag(self):
        self._setup_users()
        self.p.message('INTBOT', '#chan', 'hello', tags={'time': '2026-06-23T18:40:54.011Z'})
        raw = self._sent().strip()
        # Tags precede the source prefix.
        self.assertEqual(raw, '@time=2026-06-23T18:40:54.011Z :INTBOT PRIVMSG #chan :hello')

    def test_notice_with_server_time_tag(self):
        self._setup_users()
        self.p.notice('INTBOT', '#chan', 'hi', tags={'time': '2026-06-23T18:40:54.011Z'})
        raw = self._sent().strip()
        self.assertEqual(raw, '@time=2026-06-23T18:40:54.011Z :INTBOT NOTICE #chan :hi')

    def test_message_without_tags_is_untagged(self):
        self._setup_users()
        self.p.message('INTBOT', '#chan', 'hello')
        raw = self._sent().strip()
        self.assertFalse(raw.startswith('@'), raw)
        self.assertEqual(raw, ':INTBOT PRIVMSG #chan :hello')

    def test_message_tags_suppressed_without_cap(self):
        self._setup_users()
        self.p.protocol_caps.discard('has-message-tags')
        self.p.message('INTBOT', '#chan', 'hello', tags={'time': '2026-06-23T18:40:54.011Z'})
        raw = self._sent().strip()
        self.assertEqual(raw, ':INTBOT PRIVMSG #chan :hello')


class ClientbotTagmsgTest(_Base):
    proto_class = clientbot.ClientbotWrapperProtocol

    def test_send_tagmsg_gated_on_cap(self):
        # Without negotiating message-tags, nothing is sent.
        before = len(self.sent)
        self.p.tagmsg('somebody', '#chan', {'+typing': 'active'})
        self.assertEqual(len(self.sent), before)

    def test_send_tagmsg_wire_order(self):
        self.p.ircv3_caps.add('message-tags')
        self.p.tagmsg('somebody', '#chan', {'+draft/react': '👍'})
        raw = self._sent().strip()
        # Clientbot sends as itself: tags first, no source prefix.
        self.assertTrue(raw.startswith('@'), raw)
        self.assertIn(' TAGMSG #chan', raw)
        self.assertNotIn(':somebody', raw)


if __name__ == '__main__':
    unittest.main()
