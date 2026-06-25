"""Test cases for coremods/login.py (authentication)."""
import unittest
from unittest.mock import MagicMock, patch

from netlink import conf, utils
from netlink.coremods import login


class _FakeUser:
    def __init__(self):
        self.account = None


class _FakeIRC:
    def __init__(self, *, internal=False, oper=False, host_match=True):
        self.name = 'testnet'
        self.called_in = 'uidA'  # a UID, i.e. a private message, by default
        self._internal = internal
        self._oper = oper
        self._host_match = host_match
        self.users = {'uidA': _FakeUser()}
        self.replies = []
        self.errors = []

    def is_internal_client(self, source):
        return self._internal

    def is_oper(self, source):
        return self._oper

    def is_channel(self, target):
        return isinstance(target, str) and target.startswith('#')

    def match_host(self, host, source):
        return self._host_match

    def get_hostmask(self, source):
        return 'nick!user@host'

    def reply(self, text, **kwargs):
        self.replies.append(text)

    def error(self, text, **kwargs):
        self.errors.append(text)


class LoginTestCase(unittest.TestCase):
    def setUp(self):
        self._saved = conf.conf.get('login')
        conf.conf['login'] = {
            'accounts': {
                'alice': {'password': 'secret', 'encrypted': False},
                'bob': {'password': 'hashedpw', 'encrypted': True},
                'nopass': {},
            },
            'user': 'admin',
            'password': 'adminpass',
        }

    def tearDown(self):
        if self._saved is None:
            conf.conf.pop('login', None)
        else:
            conf.conf['login'] = self._saved
        login._warned_plaintext.clear()

    # --- _get_account ---
    def test_get_account_found_case_insensitive(self):
        self.assertEqual(login._get_account('ALICE')['password'], 'secret')

    def test_get_account_missing(self):
        self.assertFalse(login._get_account('nobody'))

    # --- check_login ---
    def test_check_login_plaintext_ok(self):
        self.assertTrue(login.check_login('alice', 'secret'))

    def test_check_login_plaintext_wrong(self):
        self.assertFalse(login.check_login('alice', 'nope'))

    def test_check_login_warns_once_about_plaintext(self):
        login.check_login('alice', 'secret')
        login.check_login('alice', 'secret')
        self.assertIn('alice', login._warned_plaintext)

    def test_check_login_no_account(self):
        self.assertFalse(login.check_login('ghost', 'x'))

    def test_check_login_account_without_password(self):
        self.assertFalse(login.check_login('nopass', 'x'))

    def test_check_login_encrypted_delegates_to_verify(self):
        with patch.object(login, 'verify_hash', return_value=True) as vh:
            self.assertTrue(login.check_login('bob', 'plaintext'))
            vh.assert_called_once_with('plaintext', 'hashedpw')

    # --- verify_hash ---
    def test_verify_hash_no_password(self):
        self.assertFalse(login.verify_hash('', 'hash'))

    def test_verify_hash_no_context_raises(self):
        with patch.object(login, 'pwd_context', None), \
                self.assertRaises(utils.NotAuthorizedError):
            login.verify_hash('pw', 'hash')

    def test_verify_hash_delegates_to_context(self):
        ctx = MagicMock()
        ctx.verify.return_value = True
        with patch.object(login, 'pwd_context', ctx):
            self.assertTrue(login.verify_hash('pw', 'hash'))
            ctx.verify.assert_called_once_with('pw', 'hash')

    # --- identify ---
    def test_identify_in_channel_refused(self):
        irc = _FakeIRC()
        irc.called_in = '#chan'
        login.identify(irc, 'uidA', ['alice', 'secret'])
        self.assertTrue(any('private' in r for r in irc.replies))
        self.assertIsNone(irc.users['uidA'].account)

    def test_identify_missing_args(self):
        irc = _FakeIRC()
        login.identify(irc, 'uidA', ['alice'])
        self.assertTrue(any('argument' in r.lower() for r in irc.replies))

    def test_identify_account_success(self):
        irc = _FakeIRC()
        login.identify(irc, 'uidA', ['alice', 'secret'])
        self.assertEqual(irc.users['uidA'].account, 'alice')

    def test_identify_legacy_admin_success(self):
        irc = _FakeIRC()
        login.identify(irc, 'uidA', ['admin', 'adminpass'])
        self.assertEqual(irc.users['uidA'].account, 'admin')

    def test_identify_legacy_admin_wrong_password_raises(self):
        irc = _FakeIRC()
        with self.assertRaises(utils.NotAuthorizedError):
            login.identify(irc, 'uidA', ['admin', 'wrong'])

    def test_identify_unknown_user_raises(self):
        irc = _FakeIRC()
        with self.assertRaises(utils.NotAuthorizedError):
            login.identify(irc, 'uidA', ['ghost', 'x'])

    # --- _irc_try_login filters ---
    def test_try_login_internal_client_refused(self):
        irc = _FakeIRC(internal=True)
        self.assertIsNone(login._irc_try_login(irc, 'uidA', 'alice'))
        self.assertTrue(irc.errors)

    def test_try_login_network_filter_mismatch(self):
        conf.conf['login']['accounts']['alice']['networks'] = ['othernet']
        irc = _FakeIRC()
        with self.assertRaises(utils.NotAuthorizedError):
            login._irc_try_login(irc, 'uidA', 'alice')

    def test_try_login_require_oper(self):
        conf.conf['login']['accounts']['alice']['require_oper'] = True
        irc = _FakeIRC(oper=False)
        with self.assertRaises(utils.NotAuthorizedError):
            login._irc_try_login(irc, 'uidA', 'alice')

    def test_try_login_host_filter_mismatch(self):
        conf.conf['login']['accounts']['alice']['hosts'] = ['*@good.host']
        irc = _FakeIRC(host_match=False)
        with self.assertRaises(utils.NotAuthorizedError):
            login._irc_try_login(irc, 'uidA', 'alice')

    def test_try_login_success_sets_account(self):
        irc = _FakeIRC()
        self.assertTrue(login._irc_try_login(irc, 'uidA', 'alice'))
        self.assertEqual(irc.users['uidA'].account, 'alice')

    def test_try_login_skip_checks_bypasses_filters(self):
        conf.conf['login']['accounts']['alice']['require_oper'] = True
        irc = _FakeIRC(oper=False)
        self.assertTrue(login._irc_try_login(irc, 'uidA', 'alice', skip_checks=True))


if __name__ == '__main__':
    unittest.main()
