import unittest
from system_keyboard.keys import Keyboard, ROWS, MODIFIERS


class RecordingBackend:
    def __init__(self):
        self.events = []
        self.fail = None

    def key(self, code, pressed):
        self.events.append((code, pressed))
        if self.fail == (code, pressed):
            raise RuntimeError('input failed')


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.backend = RecordingBackend()
        self.keyboard = Keyboard(self.backend)

    def test_tap(self):
        self.keyboard.tap(30)
        self.assertEqual(self.backend.events, [(30, True), (30, False)])

    def test_sticky_shortcut(self):
        self.keyboard.tap(29)
        self.keyboard.tap(46)
        self.assertEqual(self.backend.events, [(29, True), (46, True), (46, False), (29, False)])
        self.assertFalse(self.keyboard.held)

    def test_toggle(self):
        self.keyboard.tap(42)
        self.keyboard.tap(42)
        self.assertEqual(self.backend.events, [(42, True), (42, False)])
        self.assertFalse(self.keyboard.held)

    def test_release_all(self):
        for code in MODIFIERS:
            self.keyboard.tap(code)
        self.keyboard.release()
        self.assertFalse(self.keyboard.held)
        for code in MODIFIERS:
            self.assertIn((code, False), self.backend.events)

    def test_failed_key_releases_modifier(self):
        self.keyboard.tap(29)
        self.backend.fail = (30, True)
        with self.assertRaisesRegex(RuntimeError, 'input failed'):
            self.keyboard.tap(30)
        self.assertEqual(self.backend.events[-2:], [(30, False), (29, False)])
        self.assertFalse(self.keyboard.held)

    def test_failed_release_retained_for_retry(self):
        self.keyboard.tap(29)
        self.keyboard.tap(42)
        self.backend.fail = (29, False)
        with self.assertRaises(RuntimeError):
            self.keyboard.release()
        self.assertEqual(self.keyboard.held, {29})
        self.assertIn((42, False), self.backend.events)
        self.backend.fail = None
        self.keyboard.release()
        self.assertFalse(self.keyboard.held)

    def test_failed_modifier_press_not_latched(self):
        self.backend.fail = (29, True)
        with self.assertRaises(RuntimeError):
            self.keyboard.tap(29)
        self.assertFalse(self.keyboard.held)

    def test_service_layout_key(self):
        self.keyboard.switch_layout('next-layout')
        self.assertEqual(self.backend.events, [(584, True), (584, False)])
        self.assertFalse(self.keyboard.held)

    def test_switch_releases_existing_modifiers(self):
        self.keyboard.tap(29)
        self.keyboard.switch_layout('super-space')
        self.assertEqual(self.backend.events, [(29, True), (29, False),
                         (125, True), (57, True), (57, False), (125, False)])
        self.assertFalse(self.keyboard.held)

    def test_modifier_only_layout_shortcuts(self):
        for shortcut, first in [('alt-shift', 56), ('ctrl-shift', 29)]:
            with self.subTest(shortcut=shortcut):
                self.backend.events.clear()
                self.keyboard.switch_layout(shortcut)
                self.assertEqual(self.backend.events[:2], [(first, True), (42, True)])
                self.assertCountEqual(self.backend.events[2:], [(first, False), (42, False)])
                self.assertFalse(self.keyboard.held)

    def test_switch_failure_releases_keys(self):
        self.backend.fail = (57, True)
        with self.assertRaisesRegex(RuntimeError, 'input failed'):
            self.keyboard.switch_layout('super-space')
        self.assertIn((125, False), self.backend.events)
        self.assertIn((57, False), self.backend.events)
        self.assertFalse(self.keyboard.held)

    def test_layout(self):
        codes = [code for row in ROWS for _, code in row]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(MODIFIERS.issubset(codes))
        self.assertIn(57, codes)


if __name__ == '__main__':
    unittest.main()
