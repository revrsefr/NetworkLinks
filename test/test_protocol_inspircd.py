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

    def test_handle_ftopic(self):
        sid = self._make_server()
        hook = self.p.handle_ftopic(sid, 'FTOPIC',
                                    ['#chan', '1556828864', '1556844505', 'setter!u@h', 'the topic'])
        self.assertEqual(hook['channel'], '#chan')
        self.assertEqual(hook['text'], 'the topic')
        self.assertEqual(self.p._channels['#chan'].topic, 'the topic')
        self.assertTrue(self.p._channels['#chan'].topicset)

    def test_handle_opertype_sets_oper(self):
        sid = self._make_server()
        self._make_user('op', 'opuid', sid=sid)
        hook = self.p.handle_opertype('opuid', 'OPERTYPE', ['Network_Owner'])
        self.assertIn(('+o', None), hook['modes'])
        self.assertIn(('o', None), self.p.users['opuid'].modes)

    def test_handle_fident(self):
        sid = self._make_server()
        self._make_user('u', 'fuid', sid=sid, ident='old')
        hook = self.p.handle_fident('fuid', 'FIDENT', ['newident'])
        self.assertEqual(self.p.users['fuid'].ident, 'newident')
        self.assertEqual(hook['newident'], 'newident')

    def test_handle_fhost(self):
        sid = self._make_server()
        self._make_user('u', 'huid', sid=sid, host='old.host')
        hook = self.p.handle_fhost('huid', 'FHOST', ['new.host'])
        self.assertEqual(self.p.users['huid'].host, 'new.host')
        self.assertEqual(hook['newhost'], 'new.host')

    def test_handle_fname(self):
        sid = self._make_server()
        self._make_user('u', 'nuid', sid=sid)
        hook = self.p.handle_fname('nuid', 'FNAME', ['New Real Name'])
        self.assertEqual(self.p.users['nuid'].realname, 'New Real Name')
        self.assertEqual(hook['newgecos'], 'New Real Name')

    def test_handle_away_set_and_unset(self):
        sid = self._make_server()
        self._make_user('u', 'auid', sid=sid)
        hook = self.p.handle_away('auid', 'AWAY', ['1439371390', 'gone fishing'])
        self.assertEqual(self.p.users['auid'].away, 'gone fishing')
        self.assertEqual(hook['text'], 'gone fishing')
        hook2 = self.p.handle_away('auid', 'AWAY', [])
        self.assertEqual(self.p.users['auid'].away, '')
        self.assertEqual(hook2['text'], '')

    def test_handle_endburst_sets_eob(self):
        sid = self._make_server()
        self.p.handle_endburst(sid, 'ENDBURST', [])
        self.assertTrue(self.p.servers[sid].has_eob)

    def test_handle_addline(self):
        hook = self.p.handle_addline('70M', 'ADDLINE',
                                     ['G', '*@1.2.3.4', 'oper.name', '1433704565', '3600', 'spam reason'])
        self.assertEqual(hook['type'], 'G')
        self.assertEqual(hook['user'], '*')
        self.assertEqual(hook['host'], '1.2.3.4')
        self.assertEqual(hook['duration'], 3600)
        self.assertEqual(hook['reason'], 'spam reason')

    def test_handle_addline_malformed_is_safe(self):
        # A short/garbage line must not raise (which would drop the S2S link).
        self.assertIsNone(self.p.handle_addline('70M', 'ADDLINE', ['G']))

    def test_handle_delline(self):
        hook = self.p.handle_delline('70M', 'DELLINE', ['G', 'baduser@1.2.3.4'])
        self.assertEqual(hook['mask'], 'baduser@1.2.3.4')
        self.assertEqual(hook['user'], 'baduser')
        self.assertEqual(hook['host'], '1.2.3.4')

    def test_handle_server_other_introduction(self):
        self._make_server()  # sets uplink
        hook = self.p.handle_server(self.p.uplink, 'SERVER',
                                    ['leaf.test', '0SV', ':Some server'])
        self.assertEqual(hook['name'], 'leaf.test')
        self.assertEqual(hook['sid'], '0SV')
        self.assertIn('0SV', self.p.servers)

if __name__ == '__main__':
    unittest.main()
