import unittest
from unittest.mock import Mock, patch

from system_keyboard.gsettings_detection import GSettingsLayout


class GSettingsTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GSettingsLayout.__new__(GSettingsLayout)
        self.adapter.settings = Mock()
        self.adapter.settings.get_value.return_value.unpack.return_value = [
            ('xkb', 'us'), ('xkb', 'ru+phonetic')]
        self.adapter.settings.get_uint.return_value = 0
        self.adapter.layout = None
        self.adapter.current = None

    @patch('system_keyboard.gsettings_detection.Layout')
    def test_refresh_and_variant(self, layout):
        self.adapter.labels((42,))
        layout.assert_called_once_with('us', '')
        self.adapter.labels()
        self.assertEqual(layout.call_count, 1)
        self.adapter.settings.get_uint.return_value = 1
        self.adapter.labels()
        layout.assert_called_with('ru', 'phonetic')
        self.adapter.close()
        self.assertIsNone(self.adapter.layout)

    def test_invalid_sources(self):
        for sources, index in [([], 0), ([('xkb', 'us')], 2),
                               ([('ibus', 'test')], 0), ([('xkb', '')], 0)]:
            with self.subTest(sources=sources, index=index):
                self.adapter.settings.get_value.return_value.unpack.return_value = sources
                self.adapter.settings.get_uint.return_value = index
                with self.assertRaises(ValueError):
                    self.adapter.labels()

    @patch('system_keyboard.gsettings_detection.Layout')
    def test_switch_wraps_and_reports_write_failure(self, layout):
        self.adapter.settings.get_uint.return_value = 1
        self.adapter.switch()
        self.adapter.settings.set_uint.assert_called_with('current', 0)
        self.adapter.settings.set_uint.return_value = False
        with self.assertRaises(RuntimeError):
            self.adapter.switch()
