"""
Tests for relay message handling: long-message wrapping (issue #656) and the
server-time forwarding helper.
"""
import time
import unittest

from netlink.classes import User, Server
from netlink.protocols import inspircd
from netlink.plugins import relay

import protocol_test_fixture as ptf

if relay.datastore.exportdb_timer:
    relay.datastore.exportdb_timer.cancel()


def tearDownModule():
    if relay.datastore.exportdb_timer:
        relay.datastore.exportdb_timer.cancel()


class FakeRemote:
    """Minimal stand-in for a remote network object."""
    def __init__(self, wrap_lines=None, wrap_error=None):
        self._wrap_lines = wrap_lines
        self._wrap_error = wrap_error
        self.calls = []

    def wrap_message(self, user, target, text):
        if self._wrap_error:
            raise self._wrap_error
        return self._wrap_lines

    def message(self, user, target, text, tags=None):
        self.calls.append(('message', user, target, text, tags))

    def notice(self, user, target, text, tags=None):
        self.calls.append(('notice', user, target, text, tags))


class RelaySendTest(unittest.TestCase):
    def test_each_wrapped_line_is_sent(self):
        r = FakeRemote(wrap_lines=['line one', 'line two', 'line three'])
        relay._relay_send(r, 'UID', '#chan', 'original', False, None)
        self.assertEqual([c[0] for c in r.calls], ['message'] * 3)
        self.assertEqual([c[3] for c in r.calls], ['line one', 'line two', 'line three'])

    def test_notice_routing_and_tags_forwarded_per_line(self):
        r = FakeRemote(wrap_lines=['a', 'b'])
        relay._relay_send(r, 'UID', 'nick', 'x', True, {'time': 'T'})
        self.assertEqual([c[0] for c in r.calls], ['notice', 'notice'])
        # The server-time tag rides on every line.
        self.assertTrue(all(c[4] == {'time': 'T'} for c in r.calls))

    def test_no_tags_passes_default(self):
        r = FakeRemote(wrap_lines=['only'])
        relay._relay_send(r, 'UID', '#chan', 'only', False, None)
        self.assertEqual(r.calls[0][4], None)

    def test_falls_back_to_raw_text_when_wrap_unavailable(self):
        r = FakeRemote(wrap_error=NotImplementedError())
        relay._relay_send(r, 'UID', '#chan', 'untouched', False, None)
        self.assertEqual(len(r.calls), 1)
        self.assertEqual(r.calls[0][3], 'untouched')


class ChgClientTest(unittest.TestCase):
    def test_no_change_fields_does_not_crash(self):
        # Regression: 'field' used to be referenced before assignment when a
        # CHG* hook carried none of newhost/newident/newgecos (e.g. a cleared
        # value), raising UnboundLocalError. It must now simply do nothing.
        class FakeIrc:
            name = 'test'
        relay.handle_chgclient(FakeIrc(), 'src', 'CHGNAME', {'target': 'UID'})


class WrapMessageTest(unittest.TestCase):
    """The real protocol wrap_message must split long text within the line budget."""
    def setUp(self):
        self.p = inspircd.InspIRCdProtocol('test')
        self.p.connect = lambda self: None
        self.p.socket = ptf.DummySocket()
        self.p.servers['INT'] = Server(self.p, None, 'int.server', internal=True)
        self.p.sid = 'INT'
        self.p.users['BOT'] = User(self.p, 'relaybot', int(time.time()), 'BOT', 'INT',
                                   ident='relay', host='relay.example.org')

    def test_long_message_is_split_within_budget(self):
        text = 'word ' * 200  # ~1000 chars, well over one line
        lines = self.p.wrap_message('BOT', '#chan', text)
        self.assertGreater(len(lines), 1)
        hostmask = self.p.get_hostmask('BOT')
        # InspIRCd allows long S2S lines (S2S_BUFSIZE == 0), so wrap_message uses
        # the 510-byte client budget instead so the destination IRCd doesn't
        # truncate when re-emitting to clients.
        budget = self.p.S2S_BUFSIZE or 510
        for line in lines:
            wire = ':%s PRIVMSG #chan :%s' % (hostmask, line)
            self.assertLessEqual(len(wire), budget)
        # No words are lost across the split.
        self.assertEqual(' '.join(lines).split(), text.split())


if __name__ == '__main__':
    unittest.main()
