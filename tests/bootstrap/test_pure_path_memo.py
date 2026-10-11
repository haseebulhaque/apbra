"""Pure path memoization parity; no product or provider execution."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bootstrap_path_memo', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class PurePathMemoTests(unittest.TestCase):
    def test_exact_builtin_strings_reuse_only_pure_validation(self):
        from unittest.mock import Mock
        original = lambda value: value == 'docs/example.md'
        measured = Mock(side_effect=original)
        wrapped = c._memoized_path(measured)
        self.assertTrue(wrapped('docs/example.md'))
        self.assertTrue(wrapped(''.join(['docs/', 'example.md'])))
        self.assertFalse(wrapped('../unsafe'))
        self.assertFalse(wrapped('../unsafe'))
        self.assertEqual(measured.call_count, 2)

    def test_mutable_task_and_card_decisions_are_never_cached(self):
        task = {'allowed_paths': ['docs/**'], 'restricted_paths': []}
        card = {'allowed_paths': ['*']}
        self.assertTrue(c.path_allowed('docs/example.md', task, card))
        task['restricted_paths'].append('docs/**')
        self.assertFalse(c.path_allowed('docs/example.md', task, card))
        task['restricted_paths'].clear()
        card['allowed_paths'] = ['scripts/**']
        self.assertFalse(c.path_allowed('docs/example.md', task, card))

    def test_string_subclass_behavior_is_rechecked(self):
        class MutablePath(str):
            blocked = False
            def startswith(self, prefix):
                return self.blocked or super().startswith(prefix)
        value = MutablePath('docs/example.md')
        self.assertTrue(c.valid_path(value))
        value.blocked = True
        self.assertFalse(c.valid_path(value))
        self.assertTrue(c.valid_path(str(value)))

    def test_keyword_calls_preserve_original_result_and_errors(self):
        for value, expected in [('docs/example.md', True), ('../unsafe', False)]:
            self.assertEqual(c.valid_path(path=value), expected)
        original = next(cell.cell_contents for cell in c.valid_path.__closure__
                        if getattr(cell.cell_contents, '__name__', None) == 'valid_path')
        for args, kwargs in [((), {}), (('a', 'b'), {}), ((), {'unexpected': 'a'})]:
            with self.assertRaises(TypeError) as expected:
                original(*args, **kwargs)
            with self.assertRaises(TypeError) as actual:
                c.valid_path(*args, **kwargs)
            self.assertEqual(str(actual.exception), str(expected.exception))

    def test_non_string_inputs_preserve_original_results_and_exception_details(self):
        original = next(cell.cell_contents for cell in c.valid_path.__closure__
                        if getattr(cell.cell_contents, '__name__', None) == 'valid_path')
        for value in [None, [], {}, 0, False]:
            self.assertEqual(c.valid_path(value), original(value))
        for value in [['x'], {'x': 1}, 1, True]:
            try:
                original(value)
            except Exception as expected:
                with self.assertRaises(type(expected)) as actual:
                    c.valid_path(value)
                self.assertEqual(str(actual.exception), str(expected))

    def test_matches_observes_current_dependencies_after_path_cache_warms(self):
        self.assertTrue(c.matches('docs/example.md', 'docs/**'))
        with patch.object(c, 'valid_path', return_value=False):
            self.assertFalse(c.matches('docs/example.md', 'docs/**'))
        self.assertTrue(c.matches('README.md', '*.md'))
        with patch.object(c.fnmatch, 'fnmatchcase', return_value=False):
            self.assertFalse(c.matches('README.md', '*.md'))


