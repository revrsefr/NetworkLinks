"""Test cases for i18n.py (#180)."""
import unittest

from netlink import conf, i18n


class I18nTest(unittest.TestCase):
    def setUp(self):
        self._saved = conf.conf['netlink'].get('language')

    def tearDown(self):
        if self._saved is None:
            conf.conf['netlink'].pop('language', None)
        else:
            conf.conf['netlink']['language'] = self._saved
        i18n.setup()

    def _set_lang(self, lang):
        if lang is None:
            conf.conf['netlink'].pop('language', None)
        else:
            conf.conf['netlink']['language'] = lang
        i18n.setup()

    def test_default_is_passthrough(self):
        self._set_lang(None)
        self.assertEqual(i18n._('Done.'), 'Done.')

    def test_explicit_en_is_passthrough(self):
        self._set_lang('en')
        self.assertEqual(i18n._('Bad username or password.'), 'Bad username or password.')

    def test_french_translation(self):
        self._set_lang('fr')
        self.assertEqual(i18n._('Done.'), 'Terminé.')
        self.assertEqual(i18n._('Bad username or password.'),
                         "Nom d'utilisateur ou mot de passe incorrect.")

    def test_format_string_preserved(self):
        self._set_lang('fr')
        self.assertEqual(i18n._('Successfully logged in as %s.') % 'bob',
                         'Connecté avec succès en tant que bob.')

    def test_unknown_language_falls_back_to_passthrough(self):
        self._set_lang('zz')  # no catalogue exists
        self.assertEqual(i18n._('Done.'), 'Done.')


if __name__ == '__main__':
    unittest.main()
