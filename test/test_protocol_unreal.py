import unittest

from pylinkirc.classes import ProtocolError, Server
from pylinkirc.protocols import unreal

import protocol_test_fixture as ptf

class UnrealProtocolTest(ptf.BaseProtocolTest):
    proto_class = unreal.UnrealProtocol

    def test_targets_unreal6_protocol(self):
        self.assertEqual(self.p.proto_ver, 6000)

    def test_requires_unreal6_minimum(self):
        self.assertEqual(self.p.min_proto_ver, 6000)

    def test_protoctl_mtags_enables_message_tags(self):
        self.assertNotIn('has-message-tags', self.p.protocol_caps)
        self.p.handle_protoctl('000', 'PROTOCTL', ['NOQUIT', 'MTAGS', 'SID=001'])
        self.assertIn('has-message-tags', self.p.protocol_caps)

    def test_protoctl_without_mtags_leaves_tags_off(self):
        self.p.handle_protoctl('000', 'PROTOCTL', ['NOQUIT', 'NICKv2', 'SID=001'])
        self.assertNotIn('has-message-tags', self.p.protocol_caps)

    def test_pre_unreal6_server_is_rejected(self):
        # An UnrealIRCd 5 uplink (protocol 5002) must be refused.
        self.p.caps = list(self.p.needed_caps)  # skip the capability check
        with self.assertRaises(ProtocolError):
            self.p.handle_server('unreal.test', 'SERVER',
                                 ['unreal.test', '1', 'U5002-Fhin6OoEM UnrealIRCd test'])

    def test_md_certfp_is_tracked(self):
        u = self._make_user('crypto', 'uid1')
        self.p.handle_md('001', 'MD', ['client', 'uid1', 'certfp', 'deadbeefcafe1234'])
        self.assertEqual(u.certfp, 'deadbeefcafe1234')
        self.assertTrue(u.ssl)

    def test_md_empty_certfp_clears(self):
        u = self._make_user('crypto', 'uid1')
        u.certfp = 'old'
        self.p.handle_md('001', 'MD', ['client', 'uid1', 'certfp', ''])
        self.assertIsNone(u.certfp)

    def test_md_unknown_object_is_ignored(self):
        # Must not raise for objects/vars we don't track.
        self.p.handle_md('001', 'MD', ['channel', '#x', 'something', 'value'])
        self.p.handle_md('001', 'MD', ['client', 'nosuchuid', 'certfp', 'x'])

    def test_sjsby_ban_prefix_is_stripped(self):
        # SJSBY prefixes list entries with <setat,setby>; the ban mask must still
        # be parsed correctly with that metadata removed.
        self.p.servers['001'] = Server(self.p, None, 'unreal.test', internal=False)
        self.p.uplink = '001'
        self.p.handle_sjoin('001', 'SJOIN',
                            ['1000000000', '#chan', '+nt',
                             '<1548605202,UserOne>&*!*@badhost.com'])
        bans = [v for m, v in self.p.channels['#chan'].modes if m == 'b']
        self.assertIn('*!*@badhost.com', bans)

if __name__ == '__main__':
    unittest.main()
