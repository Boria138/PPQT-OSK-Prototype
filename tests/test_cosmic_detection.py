import ctypes as C
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from system_keyboard.cosmic_detection import CosmicLayout
from system_keyboard.layouts import Layout


class CosmicTests(unittest.TestCase):
    def setUp(self):
        self.adapter = CosmicLayout.__new__(CosmicLayout)
        self.adapter.lib = Mock()
        self.adapter.display = None
        self.adapter.layout = None
        self.adapter.group = None
        self.adapter.error = None

    def tearDown(self):
        self.adapter.close()

    def test_keymap_and_unfocused_group(self):
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
            fd = os.dup(keymap.fileno())
            self.adapter._keymap(1, fd, len(text))
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.adapter.lib.wl_display_dispatch_pending.return_value = 0
        with patch('system_keyboard.cosmic_detection.select.select', return_value=([], [], [])):
            self.adapter._group(0)
            self.assertEqual(self.adapter.labels()['30'], 'a')
            self.adapter._group(1)
            self.assertEqual(self.adapter.labels()['30'], 'ф')
            self.assertEqual(self.adapter.labels((42,))['30'], 'Ф')
            self.adapter.caps_lock = lambda: True
            self.assertEqual(self.adapter.labels()['30'], 'Ф')
            self.assertEqual(self.adapter.labels((42,))['30'], 'ф')
            self.adapter._group(0)
            self.assertEqual(self.adapter.labels()['30'], 'A')
            self.assertEqual(self.adapter.labels()['2'], '1')
            self.assertEqual(self.adapter.labels((42,))['30'], 'a')
            self.adapter.caps_lock = lambda: False
            self.assertEqual(self.adapter.labels()['30'], 'a')

    def test_invalid_keymap_closes_fd(self):
        with tempfile.TemporaryFile() as keymap:
            fd = os.dup(keymap.fileno())
            with self.assertRaisesRegex(RuntimeError, 'неверная'):
                self.adapter._keymap(1, fd, 0)
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_short_keymap(self):
        with tempfile.TemporaryFile() as keymap:
            with self.assertRaisesRegex(RuntimeError, 'неполная'):
                self.adapter._keymap(1, os.dup(keymap.fileno()), 10)

    def test_disconnect(self):
        with self.assertRaisesRegex(RuntimeError, 'закрыто'):
            self.adapter._check(-1)

    def test_callback_error_propagates(self):
        self.adapter.error = ValueError('bad map')
        with self.assertRaisesRegex(ValueError, 'bad map'):
            self.adapter._check(0)

    def test_close_releases_proxies_before_display(self):
        self.adapter.display = 1
        self.adapter.proxies = [2, 3]
        self.adapter.close()
        self.assertEqual(self.adapter.lib.method_calls,
                         [unittest.mock.call.wl_proxy_destroy(3),
                          unittest.mock.call.wl_proxy_destroy(2),
                          unittest.mock.call.wl_display_disconnect(1)])
        self.adapter.close()
        self.assertEqual(self.adapter.lib.wl_display_disconnect.call_count, 1)

    def test_two_independent_clients_live(self):
        if not os.environ.get('WAYLAND_DISPLAY') or 'cosmic' not in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            self.skipTest('requires COSMIC session')
        first = CosmicLayout()
        try:
            second = CosmicLayout()
            try:
                self.assertEqual(first.labels(), second.labels())
            finally:
                second.close()
            self.assertTrue(first.labels())
        finally:
            first.close()
