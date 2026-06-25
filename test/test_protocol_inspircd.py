import unittest

from netlink.classes import Server
from netlink.protocols import inspircd

import protocol_test_fixture as ptf

class InspIRCdProtocolTest(ptf.BaseProtocolTest):
    proto_class = inspircd.InspIRCdProtocol

    def _make_server(self, sid='70M', name='remote.test'):
        self.p.servers[sid] = Server(self.p, None, name, internal=False)
        self.p.uplink = sid
        return sid

    def test_handle_uid_insp4_parses_realident(self):
        # insp4 (proto 1206) UID has a separate real-ident field (args[5]).
        # <- :70M UID <uid> <ts> <nick> <realhost> <host> <realident> <ident> <ip> <signon> <modes> :<real>
        sid = self._make_server()
        self.p.remote_proto_ver = 1206
        hook = self.p.handle_uid(sid, 'UID',
            ['70MAAAAAB', '1429934638', 'jlu5', '0::1', 'hidden.host',
             'realj', 'jlu5', '0::1', '1429934638', '+iw', 'Real Name'])
        u = self.p.users['70MAAAAAB']
        self.assertEqual(u.nick, 'jlu5')
        self.assertEqual(u.host, 'hidden.host')
        self.assertEqual(u.realhost, '0::1')
        self.assertEqual(u.ident, 'jlu5')
        self.assertEqual(u.realident, 'realj')   # distinct from the displayed ident
        self.assertEqual(u.realname, 'Real Name')
        self.assertIn('70MAAAAAB', self.p.servers[sid].users)
        self.assertEqual(hook['nick'], 'jlu5')

    def test_handle_fjoin_adds_user_with_prefix(self):
        # insp3 FJOIN: members are "prefixes,UID:membid"
        sid = self._make_server('3IN')
        self.p.proto_ver = 1206
        self._make_user('alice', '3INAAAAAA', sid=sid)
        hook = self.p.handle_fjoin(sid, 'FJOIN',
            ['#test', '1556842195', '+nt', 'o,3INAAAAAA:4'])
        self.assertEqual(hook['channel'], '#test')
        self.assertIn('3INAAAAAA', self.p.channels['#test'].users)
        self.assertIn('#test', self.p.users['3INAAAAAA'].channels)
        # The user should hold +o on the channel (prefix modes live in prefixmodes).
        self.assertTrue(self.p.channels['#test'].is_op('3INAAAAAA'))

    def test_handle_fmode_applies_channel_modes(self):
        sid = self._make_server()
        hook = self.p.handle_fmode(sid, 'FMODE', ['#chat', '1433653462', '+nt'])
        self.assertEqual(hook['target'], '#chat')
        self.assertIn(('+n', None), hook['modes'])
        self.assertIn(('n', None), self.p.channels['#chat'].modes)
        self.assertIn(('t', None), self.p.channels['#chat'].modes)

    def test_metadata_ssl_cert_records_fingerprint(self):
        # InspIRCd flags are 6 chars, the last being 'e' (no error) or 'E' (error).
        u = self._make_user('crypto', 'uid1')
        self.p.handle_metadata('00A', 'METADATA',
                               ['uid1', 'ssl_cert', 'VURTSe 0123456789abcdef0123456789abcdef'])
        self.assertTrue(u.ssl)
        self.assertEqual(u.certfp, '0123456789abcdef0123456789abcdef')

    def test_metadata_ssl_cert_error_has_no_fingerprint(self):
        # A trailing 'E' flag means the value is an error message, not a fingerprint.
        u = self._make_user('crypto', 'uid1')
        self.p.handle_metadata('00A', 'METADATA',
                               ['uid1', 'ssl_cert', 'vurtsE unable to get peer certificate'])
        self.assertTrue(u.ssl)            # still a TLS connection
        self.assertIsNone(u.certfp)       # but no usable fingerprint

    def test_metadata_ssl_cert_unknown_user_ignored(self):
        # Must not raise for a user we don't know about.
        self.p.handle_metadata('00A', 'METADATA',
                               ['nosuchuid', 'ssl_cert', 'vTrE deadbeef'])

if __name__ == '__main__':
    unittest.main()
