import ctypes as C
import tempfile
import unittest
from unittest.mock import Mock, patch

from system_keyboard.cosmic_detection import CosmicLayout
from system_keyboard.layouts import Layout


class CosmicTests(unittest.TestCase):
    def setUp(self):
        self.adapter = CosmicLayout.__new__(CosmicLayout)
        self.adapter.lib = Mock()
        self.adapter.context = 1
        self.adapter.device = None
        self.adapter.layout = self.adapter.mask = None
        self.adapter.lib.ei_event_get_device.return_value = 42

    def tearDown(self):
        self.adapter.close()

    def event(self, kind):
        self.adapter.lib.ei_event_get_type.return_value = kind
        self.adapter._event(100)

    def test_keymap_and_live_group_and_modifiers(self):
        source = Layout('us,ru')
        try:
            serialize = source.lib.xkb_keymap_get_as_string
            serialize.argtypes, serialize.restype = [C.c_void_p, C.c_int], C.c_void_p
            pointer = serialize(source.keymap, 1)
            try:
                text = C.string_at(pointer) + b'\0'
            finally:
                libc = C.CDLL(None)
                libc.free.argtypes = [C.c_void_p]
                libc.free(pointer)
        finally:
            source.close()
        with tempfile.TemporaryFile() as keymap:
            keymap.write(text)
            keymap.flush()
            lib = self.adapter.lib
            lib.ei_device_keyboard_get_keymap.return_value = 3
            lib.ei_keymap_get_type.return_value = 1
            lib.ei_keymap_get_size.return_value = len(text)
            lib.ei_keymap_get_fd.return_value = keymap.fileno()
            self.event(5)
        lib.ei_get_event.return_value = None
        for suffix in ('mods_depressed', 'mods_latched', 'mods_locked', 'group'):
            getattr(lib, 'ei_event_keyboard_get_xkb_' + suffix).return_value = 0
        self.event(9)
        self.assertEqual(self.adapter.labels()['30'], 'a')
        lib.ei_event_keyboard_get_xkb_group.return_value = 1
        self.event(9)
        self.assertEqual(self.adapter.labels()['30'], 'ф')
        self.assertEqual(self.adapter.labels((42,))['30'], 'Ф')
        lib.ei_event_keyboard_get_xkb_mods_locked.return_value = 2  # Caps Lock
        self.event(9)
        self.assertEqual(self.adapter.labels()['30'], 'Ф')
        self.event(6)
        with self.assertRaisesRegex(RuntimeError, 'недоступно'):
            self.adapter.labels()

    def test_seat_binds_keyboard_only(self):
        self.event(3)
        args = self.adapter.lib.ei_seat_bind_capabilities.call_args.args
        self.assertEqual([arg.value for arg in args[1:]], [4, 0])

    def test_disconnect_releases_event(self):
        self.adapter.lib.ei_get_event.return_value = 100
        self.adapter.lib.ei_event_get_type.return_value = 2
        with self.assertRaisesRegex(RuntimeError, 'закрыто'):
            self.adapter.labels()
        self.adapter.lib.ei_event_unref.assert_called_once_with(100)

    def test_initial_failure_cleans_context(self):
        lib = Mock()
        lib.ei_new_sender.return_value = 1
        with patch('system_keyboard.cosmic_detection.load_libei', return_value=lib), \
                patch('system_keyboard.cosmic_detection.sender_socket', side_effect=OSError('no bus')):
            with self.assertRaisesRegex(RuntimeError, 'no bus'):
                CosmicLayout()
        lib.ei_unref.assert_called_once_with(1)

    def test_invalid_keymap_size(self):
        self.adapter.lib.ei_keymap_get_type.return_value = 1
        self.adapter.lib.ei_keymap_get_size.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'размер'):
            self.event(5)

    def test_initial_timeout(self):
        lib = Mock()
        lib.ei_new_sender.return_value = 1
        lib.ei_setup_backend_fd.return_value = 0
        lib.ei_get_event.return_value = None
        with patch('system_keyboard.cosmic_detection.load_libei', return_value=lib), \
                patch('system_keyboard.cosmic_detection.sender_socket', return_value=99), \
                patch('system_keyboard.cosmic_detection.time.monotonic', side_effect=[0, 3]):
            with self.assertRaisesRegex(RuntimeError, 'нет карты'):
                CosmicLayout()
        lib.ei_unref.assert_called_once_with(1)
