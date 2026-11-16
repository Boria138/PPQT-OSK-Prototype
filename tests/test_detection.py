import ctypes as C
import os
import subprocess
import unittest
from unittest.mock import Mock

import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib
from system_keyboard.detection import X11Layout, XkbState


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.layout = X11Layout.__new__(X11Layout)
        self.layout.Gdk = Gdk
        self.layout.keymap = Mock()
        self.layout.keymap.translate_keyboard_state.return_value = (True, ord('a'), 0, 0, 0)
        self.layout.lib = Mock()
        self.layout.display = 123
        self.group = 1
        self.mods = 0

        def get_state(display, device, pointer):
            state = C.cast(pointer, C.POINTER(XkbState)).contents
            state.group = self.group
            state.mods = self.mods
            state.locked_mods = self.mods & 2
            return 0
        self.layout.lib.XkbGetState.side_effect = get_state

    def test_toggle_caps_lock_preserves_other_modifiers(self):
        for mods, expected in [(128, 2), (130, 0)]:
            with self.subTest(mods=mods):
                self.mods = mods
                self.layout.toggle_caps_lock()
                self.layout.lib.XkbLockModifiers.assert_called_with(123, 0x100, 2, expected)
                self.layout.lib.XSync.assert_called_with(123, False)

    def test_caps_lock_errors_propagate(self):
        self.layout.lib.XkbLockModifiers.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'Caps Lock'):
            self.layout.toggle_caps_lock()
        self.layout.lib.XSync.assert_not_called()
        self.layout.lib.XkbGetState.side_effect = None
        self.layout.lib.XkbGetState.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'Caps Lock'):
            self.layout.caps_lock()

    def test_current_group_and_evdev_offset(self):
        labels = self.layout.labels()
        self.assertEqual(labels['30'], 'a')
        self.layout.keymap.translate_keyboard_state.assert_any_call(38, Gdk.ModifierType(0), 1)

    def test_caps_shift_altgr_preserved_ctrl_excluded(self):
        self.mods = 1 | 2 | 4 | 8 | 64 | 128
        self.layout.labels()
        self.layout.keymap.translate_keyboard_state.assert_any_call(38, Gdk.ModifierType(131), 1)

    def test_sticky_shift_altgr(self):
        self.layout.labels({42, 100})
        self.layout.keymap.translate_keyboard_state.assert_any_call(38, Gdk.ModifierType(129), 1)

    def test_caps_feedback_with_shift(self):
        self.layout.labels({58, 42})
        self.layout.keymap.translate_keyboard_state.assert_any_call(38, Gdk.ModifierType(3), 1)

    def test_unicode_and_special_labels(self):
        self.layout.keymap.translate_keyboard_state.return_value = (True, Gdk.KEY_Cyrillic_ya, 0, 0, 0)
        labels = self.layout.labels()
        self.assertEqual(labels['30'], 'я')
        self.assertEqual(labels['28'], 'Enter')
        self.assertEqual(labels['42'], 'Shift')

    def test_translation_failure_uses_physical_label(self):
        self.layout.keymap.translate_keyboard_state.return_value = (False, 0, 0, 0, 0)
        self.assertEqual(self.layout.labels()['30'], 'A')

    def test_state_error_propagates(self):
        self.layout.lib.XkbGetState.side_effect = None
        self.layout.lib.XkbGetState.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'XKB'):
            self.layout.labels()

    def test_switch_locks_next_group_and_flushes(self):
        self.layout.switch()
        self.layout.lib.XkbLockGroup.assert_called_once_with(123, 0x100, 2)
        self.layout.lib.XSync.assert_called_once_with(123, False)

    def test_switch_state_error(self):
        self.layout.lib.XkbGetState.side_effect = None
        self.layout.lib.XkbGetState.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'XKB'):
            self.layout.switch()
        self.layout.lib.XkbLockGroup.assert_not_called()

    def test_switch_lock_error(self):
        self.layout.lib.XkbLockGroup.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'XKB'):
            self.layout.switch()
        self.layout.lib.XSync.assert_not_called()

    def test_native_session_not_ui_backend(self):
        from system_keyboard.detection import is_x11_session
        self.assertTrue(is_x11_session({'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0'}))
        self.assertFalse(is_x11_session({'XDG_SESSION_TYPE': 'wayland',
                                        'DISPLAY': ':0', 'GDK_BACKEND': 'x11'}))
        self.assertFalse(is_x11_session({'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}))
        self.assertTrue(is_x11_session({'DISPLAY': ':0'}))
        self.assertFalse(is_x11_session({}))

    def test_close_idempotent(self):
        self.layout.close()
        self.layout.close()
        self.layout.lib.XCloseDisplay.assert_called_once_with(123)


@unittest.skipUnless(os.environ.get('SYSTEM_KEYBOARD_TEST_X11') == '1',
                     'Requires an isolated X server; set SYSTEM_KEYBOARD_TEST_X11=1')
class LiveDetectionTests(unittest.TestCase):
    def test_group_caps_and_keymap_changes(self):
        Gdk.init([])
        subprocess.run(['setxkbmap', '-layout', 'us,ru'], check=True)
        layout = X11Layout()
        try:
            lib = layout.lib
            lib.XkbLockGroup.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
            lib.XkbLockModifiers.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint]
            lib.XSync.argtypes = [C.c_void_p, C.c_int]

            def flush():
                lib.XSync(layout.display, 0)
                context = GLib.MainContext.default()
                while context.pending():
                    context.iteration(False)

            lib.XkbLockGroup(layout.display, 0x100, 0)
            flush()
            self.assertEqual(layout.labels()['16'], 'q')
            layout.switch()
            flush()
            self.assertEqual(layout.labels()['16'], 'й')
            layout.switch()
            flush()
            self.assertEqual(layout.labels()['16'], 'q')
            lib.XkbLockGroup(layout.display, 0x100, 1)
            flush()
            self.assertEqual(layout.labels()['16'], 'й')
            self.assertEqual(layout.labels({42})['16'], 'Й')
            lib.XkbLockModifiers(layout.display, 0x100, 2, 2)
            flush()
            self.assertEqual(layout.labels()['16'], 'Й')
            lib.XkbLockModifiers(layout.display, 0x100, 2, 0)
            lib.XkbLockGroup(layout.display, 0x100, 0)
            flush()
            subprocess.run(['setxkbmap', '-layout', 'fr'], check=True)
            flush()
            self.assertEqual(layout.labels()['16'], 'a')
        finally:
            layout.close()
