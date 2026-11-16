import unittest
from unittest.mock import Mock, patch

from system_keyboard.gsettings_detection import GSettingsLayout


class GSettingsTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GSettingsLayout.__new__(GSettingsLayout)
        self.adapter.settings = Mock()
        self.sources = [('xkb', 'us'), ('xkb', 'ru+phonetic')]
        self.recent = list(self.sources)
        self.adapter.settings.get_value.side_effect = lambda key: Mock(
            unpack=lambda: self.sources if key == 'sources' else self.recent)
        self.adapter.settings.get_boolean.return_value = False
        self.adapter.layout = None
        self.adapter.current = None
        self.adapter.legacy_current = False

    @patch('system_keyboard.gsettings_detection.Layout')
    def test_refresh_and_variant(self, layout):
        self.adapter.labels((42,))
        layout.assert_called_once_with('us', '')
        layout.return_value.labels.assert_called_with((42,))
        self.adapter.labels()
        self.assertEqual(layout.call_count, 1)
        self.recent.reverse()
        self.adapter.labels()
        layout.assert_called_with('ru', 'phonetic')
        self.adapter.settings.get_uint.assert_not_called()
        self.adapter.close()
        self.assertIsNone(self.adapter.layout)

    def test_invalid_sources(self):
        for sources, recent in [([], []), ([('ibus', 'test')], []),
                                ([('xkb', '')], []), (self.sources, []),
                                (self.sources, [('xkb', 'de')])]:
            with self.subTest(sources=sources, recent=recent):
                self.sources, self.recent = sources, recent
                with self.assertRaises(ValueError):
                    self.adapter.labels()

    def test_per_window_rejected(self):
        self.adapter.settings.get_boolean.return_value = True
        with self.assertRaisesRegex(ValueError, 'для каждого окна'):
            self.adapter.labels()

    @patch('system_keyboard.gsettings_detection.Layout')
    def test_single_source_without_history(self, layout):
        self.sources = [('xkb', 'de')]
        self.recent = []
        self.adapter.labels()
        layout.assert_called_once_with('de', '')

    def test_switch_is_left_to_system_shortcut(self):
        self.assertFalse(hasattr(self.adapter, 'switch'))
        self.adapter.settings.set_uint.assert_not_called()

    @patch('system_keyboard.gsettings_detection.Layout')
    def test_legacy_current(self, layout):
        self.adapter.legacy_current = True
        self.adapter.settings.get_uint.return_value = 1
        self.adapter.labels()
        layout.assert_called_once_with('ru', 'phonetic')
        self.adapter.settings.get_uint.return_value = 10
        with self.assertRaises(ValueError):
            self.adapter.labels()

    def test_configured_accelerators(self):
        from types import SimpleNamespace
        masks = SimpleNamespace(CONTROL_MASK=4, MOD1_MASK=8,
                                SHIFT_MASK=1, SUPER_MASK=64)
        keymap = Mock()
        keymap.get_entries_for_keyval.return_value = (True, [
            SimpleNamespace(level=0, keycode=65)])
        gdk = Mock()
        gdk.ModifierType = masks
        gdk.Keymap.get_for_display.return_value = keymap
        gtk = Mock()
        gtk.accelerator_parse.side_effect = [(0, 0), (32, 12)]
        self.adapter.bindings = Mock()
        self.adapter.bindings.get_strv.return_value = ['', '<Control><Alt>space']
        with patch.dict('sys.modules', {'gi.repository': SimpleNamespace(Gdk=gdk, Gtk=gtk)}):
            self.assertEqual(self.adapter.switch_codes(), (29, 56, 57))
            self.adapter.bindings.get_strv.assert_called_with('switch-input-source')
            self.adapter.bindings.get_strv.return_value = []
            with self.assertRaises(RuntimeError):
                self.adapter.switch_codes()
