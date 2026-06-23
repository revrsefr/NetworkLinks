"""
Tests for protocols/p10
"""

import unittest
from unittest import mock

from pylinkirc import conf
from pylinkirc.protocols import p10

import protocol_test_fixture as ptf


class P10PostConnectTest(unittest.TestCase):
    def setUp(self):
        self.serverdata = {'sendpass': 'x', 'hostname': 'pylink.test',
                           'sid': 1, 'serverdesc': 'test', 'sidrange': '1-100'}
        # The constructor builds a SID generator from serverdata['sidrange'], so
        # supply a valid config during construction.
        with mock.patch.dict(conf.conf['servers'], {'test': self.serverdata}):
            self.p = p10.P10Protocol('test')
        self.p.connect = lambda self: None
        self.p.socket = ptf.DummySocket()
        self.p.send = lambda data, queue=True: None
        self.p.serverdata = self.serverdata

    def test_unsupported_p10_ircd_raises_configuration_error(self):
        # Regression: an unknown p10_ircd used to leave 'cmodes' unassigned and
        # crash with UnboundLocalError; it must now be a clear config error.
        self.p.serverdata['p10_ircd'] = 'bogus'
        with self.assertRaises(conf.ConfigurationError):
            self.p.post_connect()

    def test_supported_p10_ircd_does_not_raise(self):
        self.p.serverdata['p10_ircd'] = 'ircu'
        self.p.post_connect()

    def test_servlist_and_servset_tokens_distinct(self):
        # Regression: a duplicate 'SERVSET' key previously clobbered the SERVLIST
        # token mapping.
        self.assertEqual(self.p.COMMAND_TOKENS['SERVLIST'], 'SERVLIST')
        self.assertEqual(self.p.COMMAND_TOKENS['SERVSET'], 'SERVSET')

class P10UIDGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.uidgen = p10.P10UIDGenerator('HI')

    def test_initial_UID(self):
        expected = [
            "HIAAA",
            "HIAAB",
            "HIAAC",
            "HIAAD",
            "HIAAE",
            "HIAAF"
        ]
        self.uidgen.counter = 0
        actual = [self.uidgen.next_uid() for i in range(6)]
        self.assertEqual(expected, actual)

    def test_rollover_first_lowercase(self):
        expected = [
            "HIAAY",
            "HIAAZ",
            "HIAAa",
            "HIAAb",
            "HIAAc",
            "HIAAd",
        ]
        self.uidgen.counter = 24
        actual = [self.uidgen.next_uid() for i in range(6)]
        self.assertEqual(expected, actual)

    def test_rollover_first_num(self):
        expected = [
            "HIAAz",
            "HIAA0",
            "HIAA1",
            "HIAA2",
            "HIAA3",
            "HIAA4",
        ]
        self.uidgen.counter = 26*2-1
        actual = [self.uidgen.next_uid() for i in range(6)]
        self.assertEqual(expected, actual)

    def test_rollover_second(self):
        expected = [
            "HIAA8",
            "HIAA9",
            "HIAA[",
            "HIAA]",
            "HIABA",
            "HIABB",
            "HIABC",
            "HIABD",
        ]
        self.uidgen.counter = 26*2+10-2
        actual = [self.uidgen.next_uid() for i in range(8)]
        self.assertEqual(expected, actual)

    def test_rollover_third(self):
        expected = [
            "HIE]9",
            "HIE][",
            "HIE]]",
            "HIFAA",
            "HIFAB",
            "HIFAC",
        ]
        self.uidgen.counter = 5*64**2 - 3
        actual = [self.uidgen.next_uid() for i in range(6)]
        self.assertEqual(expected, actual)

    def test_overflow(self):
        self.uidgen.counter = 64**3-1
        self.assertTrue(self.uidgen.next_uid())
        self.assertRaises(RuntimeError, self.uidgen.next_uid)

if __name__ == '__main__':
    unittest.main()
