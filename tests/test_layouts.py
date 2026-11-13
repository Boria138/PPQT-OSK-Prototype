import unittest
from system_keyboard.keys import ROWS
from system_keyboard.layouts import Layout, available_layouts


class LayoutTests(unittest.TestCase):
    def labels(self, name, modifiers=(), variant=''):
        layout = Layout(name, variant)
        try:
            return layout.labels(modifiers)
        finally:
            layout.close()

    def test_russian_and_shift(self):
        self.assertEqual(self.labels('ru')['16'], 'й')
        self.assertEqual(self.labels('ru', [42])['16'], 'Й')

    def test_french_and_german(self):
        self.assertEqual(self.labels('fr')['16'], 'a')
        self.assertEqual(self.labels('de')['21'], 'z')

    def test_altgr_and_shift_digits(self):
        self.assertEqual(self.labels('de', [100])['16'], '@')
        self.assertEqual(self.labels('us', [42])['2'], '!')

    def test_variant(self):
        self.assertEqual(self.labels('us', variant='dvorak')['16'], "'")

    def test_state_does_not_leak(self):
        layout = Layout('us')
        try:
            self.assertEqual(layout.labels([42])['30'], 'A')
            self.assertEqual(layout.labels()['30'], 'a')
        finally:
            layout.close()
            layout.close()

    def test_registry_contains_variants(self):
        self.assertIn(('ru', ''), available_layouts())
        self.assertIn(('us', 'dvorak'), available_layouts())

    def test_export_covers_keys_and_levels(self):
        layout = Layout('ru')
        try:
            data = layout.export()
        finally:
            layout.close()
        self.assertEqual(set(data), {'normal', 'shift', 'altgr', 'shift-altgr'})
        expected = {str(code) for row in ROWS for _, code in row}
        for labels in data.values():
            self.assertEqual(set(labels), expected)

