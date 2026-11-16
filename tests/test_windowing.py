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

    def test_cosmic_selection(self):
        from system_keyboard.wayland_detection import compositor, detect_layout
        for desktop in ('COSMIC', 'cosmic', 'pop:COSMIC'):
            with self.subTest(desktop=desktop):
                environment = {'XDG_CURRENT_DESKTOP': desktop,
                               'WAYLAND_DISPLAY': 'wayland-0'}
                self.assertEqual(compositor(environment), 'cosmic')
                self.assertEqual(choose_ui('auto', environment), 'layer-shell')
                self.assertEqual(choose_ui('x11', environment), 'x11')
                from unittest.mock import patch
                with patch('system_keyboard.cosmic_detection.CosmicLayout') as adapter:
                    self.assertIs(detect_layout(environment), adapter.return_value)
                    adapter.assert_called_once_with()
        self.assertIsNone(compositor({'XDG_CURRENT_DESKTOP': 'cosmic-other'}))
        self.assertEqual(compositor({'XDG_CURRENT_DESKTOP': 'COSMIC',
                                     'NIRI_SOCKET': '/tmp/niri.sock'}), 'niri')

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
        layer.set_exclusive_zone.assert_called_once_with(window, 0)
        layer.auto_exclusive_zone_enable.assert_not_called()
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

    def test_drag_x11_stops_bottom_repositioning(self):
        window, handle, gdk = Mock(), Mock(), Mock()
        gdk.EventMask = types.SimpleNamespace(BUTTON_PRESS_MASK=1,
            BUTTON_RELEASE_MASK=2, POINTER_MOTION_MASK=4)
        window.get_size.return_value = (1000, 310)
        window.get_position.return_value = (460, 730)
        monitor = gdk.Display.get_default.return_value.get_primary_monitor.return_value
        monitor.get_workarea.return_value = types.SimpleNamespace(
            x=0, y=0, width=1920, height=1040)
        configure_window(window, 'x11', gdk, drag_handle=handle)
        events = {c.args[0]: c.args[1] for c in handle.connect.call_args_list}
        event = types.SimpleNamespace(button=1, x_root=500, y_root=740)
        events['button-press-event'](handle, event)
        event.x_root, event.y_root = 600, 640
        events['motion-notify-event'](handle, event)
        window.move.assert_called_with(560, 630)
        window.move.reset_mock()
        callbacks = {c.args[0]: c.args[1] for c in window.connect.call_args_list}
        callbacks['size-allocate']()
        window.move.assert_not_called()
        events['button-release-event'](handle, event)
        self.assertFalse(events['motion-notify-event'](handle, event))

    def test_panel_position_clamps_to_monitor(self):
        from system_keyboard.layer_drag import panel_position
        self.assertEqual(panel_position(1920, 1080, 1000, 310, 560, 630), (560, 630))
        self.assertEqual(panel_position(1920, 1080, 1000, 310, -200, 2000), (0, 770))
        self.assertEqual(panel_position(640, 240, 1000, 310, 20, 30), (0, 0))
