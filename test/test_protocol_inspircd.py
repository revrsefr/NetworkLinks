import unittest

from pylinkirc.protocols import inspircd

import protocol_test_fixture as ptf

class InspIRCdProtocolTest(ptf.BaseProtocolTest):
    proto_class = inspircd.InspIRCdProtocol

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
