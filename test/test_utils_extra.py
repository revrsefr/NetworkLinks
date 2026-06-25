"""Additional test cases for utils.py (pure helpers not covered elsewhere)."""
import os
import unittest

from netlink import utils


class SplitHostmaskTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(utils.split_hostmask('nick!user@host.name'),
                         ['nick', 'user', 'host.name'])

    def test_host_with_at_in_it(self):
        # Only the first @ separates ident from host.
        self.assertEqual(utils.split_hostmask('n!u@a@b'), ['n', 'u', 'a@b'])

    def test_missing_field_raises(self):
        with self.assertRaises(ValueError):
            utils.split_hostmask('nick!@host')
        with self.assertRaises(ValueError):
            utils.split_hostmask('!user@host')


class MatchTextTest(unittest.TestCase):
    def test_case_insensitive_by_default(self):
        self.assertTrue(utils.match_text('*viagra*', 'BUY ChEaP ViAgRa NOW'))

    def test_no_match(self):
        self.assertFalse(utils.match_text('hello', 'world'))

    def test_star_and_question_globs(self):
        self.assertTrue(utils.match_text('a*c', 'abbbc'))
        self.assertTrue(utils.match_text('a?c', 'abc'))
        self.assertFalse(utils.match_text('a?c', 'abbc'))

    def test_filterfunc_none_is_case_sensitive(self):
        self.assertFalse(utils.match_text('abc', 'ABC', filterfunc=None))
        self.assertTrue(utils.match_text('abc', 'abc', filterfunc=None))


class MergeIterablesTest(unittest.TestCase):
    def test_lists(self):
        self.assertEqual(utils.merge_iterables([1, 2], [3]), [1, 2, 3])

    def test_sets(self):
        self.assertEqual(utils.merge_iterables({1, 2}, {2, 3}), {1, 2, 3})

    def test_dicts(self):
        self.assertEqual(utils.merge_iterables({'a': 1}, {'b': 2, 'a': 9}),
                         {'a': 9, 'b': 2})

    def test_type_mismatch_raises(self):
        with self.assertRaises(ValueError):
            utils.merge_iterables([1], {2})

    def test_unsupported_type_returns_none(self):
        self.assertIsNone(utils.merge_iterables((1,), (2,)))


class WrapArgumentsTest(unittest.TestCase):
    def test_all_on_one_line_when_short(self):
        self.assertEqual(utils.wrap_arguments('P ', ['a', 'b', 'c'], 100),
                         ['P a b c'])

    def test_wraps_across_lines(self):
        out = utils.wrap_arguments('P ', ['aa', 'bb', 'cc', 'dd'], 8)
        self.assertTrue(len(out) > 1)
        for line in out:
            self.assertLessEqual(len(line), 8)

    def test_max_args_per_line(self):
        out = utils.wrap_arguments('P ', ['a', 'b', 'c', 'd'], 100, max_args_per_line=2)
        self.assertTrue(len(out) >= 2)

    def test_empty_args_asserts(self):
        with self.assertRaises(AssertionError):
            utils.wrap_arguments('P ', [], 100)


class ExpandPathTest(unittest.TestCase):
    def test_expands_home(self):
        self.assertEqual(utils.expand_path('~/x'), os.path.join(os.path.expanduser('~'), 'x'))

    def test_expands_env(self):
        os.environ['NL_TEST_VAR'] = '/tmp/nltest'
        try:
            self.assertEqual(utils.expand_path('$NL_TEST_VAR/y'), '/tmp/nltest/y')
        finally:
            del os.environ['NL_TEST_VAR']


if __name__ == '__main__':
    unittest.main()
