import unittest

from pylinkirc.protocols import unreal

import protocol_test_fixture as ptf

class UnrealProtocolTest(ptf.BaseProtocolTest):
    proto_class = unreal.UnrealProtocol

    def test_targets_unreal6_protocol(self):
        self.assertEqual(self.p.proto_ver, 6000)

    def test_protoctl_mtags_enables_message_tags(self):
        self.assertNotIn('has-message-tags', self.p.protocol_caps)
        self.p.handle_protoctl('000', 'PROTOCTL', ['NOQUIT', 'MTAGS', 'SID=001'])
        self.assertIn('has-message-tags', self.p.protocol_caps)

    def test_protoctl_without_mtags_leaves_tags_off(self):
        self.p.handle_protoctl('000', 'PROTOCTL', ['NOQUIT', 'NICKv2', 'SID=001'])
        self.assertNotIn('has-message-tags', self.p.protocol_caps)

if __name__ == '__main__':
    unittest.main()
