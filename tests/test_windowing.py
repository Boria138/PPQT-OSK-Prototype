import types
import unittest
from unittest.mock import Mock
from system_keyboard.windowing import choose_ui, bottom_geometry, configure_window


class WindowingTests(unittest.TestCase):
    def test_niri_selection(self):
        self.assertEqual(choose_ui('auto', {'NIRI_SOCKET': '/tmp/niri.sock'}), 'layer-shell')
        self.assertEqual(choose_ui('auto', {'XDG_CURRENT_DESKTOP': 'niri:other'}), 'layer-shell')
        self.assertEqual(choose_ui('auto', {'XDG_CURRENT_DESKTOP': 'GNOME'}), 'x11')
        self.assertEqual(choose_ui('x11', {'NIRI_SOCKET': '/tmp/niri.sock'}), 'x11')

    def test_bottom_geometry(self):
        self.assertEqual(bottom_geometry(0, 0, 1920, 1080, 310), (460, 770, 1000, 310))
        self.assertEqual(bottom_geometry(-1920, 100, 1920, 1080, 310), (-1460, 870, 1000, 310))
        self.assertEqual(bottom_geometry(0, 0, 640, 240, 310), (0, 0, 640, 240))

    def test_bottom_margin_for_hidden_panel(self):
        self.assertEqual(bottom_geometry(0, 0, 1920, 1080, 310, 40),
                         (460, 730, 1000, 310))
        self.assertEqual(bottom_geometry(-1920, 100, 1920, 1080, 310, 40),
                         (-1460, 830, 1000, 310))
        self.assertEqual(bottom_geometry(0, 0, 640, 240, 310, 40),
                         (0, 0, 640, 200))

    def test_layer_bottom_margin(self):
        window, layer = Mock(), Mock()
        configure_window(window, 'layer-shell', Mock(), layer, bottom_margin=40)
        layer.set_margin.assert_any_call(window, layer.Edge.BOTTOM, 40)

    def test_layer_anchors_and_no_focus(self):
        window, layer = Mock(), Mock()
        layer.Edge = types.SimpleNamespace(BOTTOM=1, LEFT=2, RIGHT=3)
        configure_window(window, 'layer-shell', Mock(), layer)
        layer.set_anchor.assert_any_call(window, 1, True)
        layer.set_anchor.assert_any_call(window, 2, False)
        layer.set_anchor.assert_any_call(window, 3, False)
        layer.set_margin.assert_any_call(window, 1, 0)
        layer.set_keyboard_mode.assert_called_once_with(window, layer.KeyboardMode.NONE)
        layer.auto_exclusive_zone_enable.assert_called_once_with(window)
        window.set_decorated.assert_called_once_with(False)
        window.set_accept_focus.assert_called_once_with(False)

    def test_x11_dock_position(self):
        window, gdk = Mock(), Mock()
        window.get_size.return_value = (800, 310)
        window.get_position.return_value = (0, 0)
        monitor = gdk.Display.get_default.return_value.get_primary_monitor.return_value
        monitor.get_geometry.return_value = types.SimpleNamespace(x=0, y=0, width=1920, height=1080)
        # A 40px bottom panel reserves space; do not place the keyboard over it.
        monitor.get_workarea.return_value = types.SimpleNamespace(x=0, y=0, width=1920, height=1040)
        configure_window(window, 'x11', gdk)
        window.resize.assert_called_once_with(1000, 310)
        window.move.assert_called_once_with(460, 730)
        window.set_type_hint.assert_called_once_with(gdk.WindowTypeHint.DOCK)
        callbacks = {call.args[0]: call.args[1] for call in window.connect.call_args_list}
        self.assertIn('map', callbacks)
        self.assertIn('size-allocate', callbacks)
        self.assertIn('destroy', callbacks)
