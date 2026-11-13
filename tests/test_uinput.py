import types
import unittest
from unittest.mock import Mock, patch
from system_keyboard.backends import UInputBackend
from system_keyboard.keys import ROWS


class UInputTests(unittest.TestCase):
    def setUp(self):
        self.factory = Mock()
        self.evdev = types.SimpleNamespace(UInput=self.factory,
                                          ecodes=types.SimpleNamespace(EV_KEY=1, BUS_USB=3))
        self.modules = patch.dict('sys.modules', {'evdev': self.evdev})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_capabilities_cover_keyboard(self):
        backend = UInputBackend()
        capabilities = self.factory.call_args.args[0]
        self.assertEqual(capabilities[1], sorted({c for row in ROWS for _, c in row} | {584}))
        backend.close()

    def test_key_and_sync(self):
        backend = UInputBackend()
        backend.key(30, True)
        backend.key(30, False)
        self.assertEqual(self.factory.return_value.method_calls,
                         [('write', (1, 30, 1), {}), ('syn', (), {}),
                          ('write', (1, 30, 0), {}), ('syn', (), {})])
        backend.close()

    def test_permission_error_is_actionable(self):
        self.factory.side_effect = PermissionError('denied')
        with self.assertRaisesRegex(RuntimeError, '/dev/uinput'):
            UInputBackend()

    def test_missing_dependency(self):
        with patch.dict('sys.modules', {'evdev': None}):
            with self.assertRaisesRegex(RuntimeError, 'python-evdev'):
                UInputBackend()

    def test_close_idempotent_and_blocks_input(self):
        backend = UInputBackend()
        backend.close()
        backend.close()
        self.factory.return_value.close.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, 'закрыто'):
            backend.key(30, True)

    def test_write_failure_propagates(self):
        backend = UInputBackend()
        self.factory.return_value.write.side_effect = OSError('device lost')
        with self.assertRaisesRegex(OSError, 'device lost'):
            backend.key(30, True)
        self.factory.return_value.syn.assert_not_called()
        backend.close()
