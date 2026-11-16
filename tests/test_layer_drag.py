"""Real GTK/Wayland regression test; run with GDK_BACKEND=wayland."""
import os
import time
import unittest


@unittest.skipUnless(os.environ.get('GDK_BACKEND') == 'wayland',
                     'requires an explicit Wayland integration run')
class LayerDragTests(unittest.TestCase):
    def test_mapped_drag_has_fixed_coordinates_and_input_region(self):
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('GtkLayerShell', '0.1')
        from gi.repository import Gtk, Gdk, GtkLayerShell as layer
        from system_keyboard.windowing import configure_window
        from system_keyboard.layer_drag import install
        if not Gtk.init_check()[0] or not layer.is_supported():
            self.skipTest('no layer-shell compositor')
        window = Gtk.Window()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        handle = Gtk.EventBox()
        handle.add(Gtk.Label(label='Drag regression test'))
        content.pack_start(handle, False, False, 0)
        content.pack_start(Gtk.Button(label='Keyboard'), True, True, 0)
        content.set_size_request(1000, 310)
        window.add(content)
        configure_window(window, 'layer-shell', Gdk, layer)
        state = install(window, handle, layer, 40)

        def settle():
            end = time.monotonic() + .15
            while time.monotonic() < end:
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
                time.sleep(.005)

        def event(kind, x, y, button=None):
            ev = Gdk.Event.new(kind)
            ev.window = handle.get_window()
            ev.x_root, ev.y_root = x, y
            if button is not None:
                ev.button = button
            return ev

        try:
            window.show_all()
            settle()
            width, height = window.get_size()
            self.assertGreater(width, 1000)
            initial = state['position']
            self.assertEqual(initial, ((width - 1000) // 2, height - 310 - 40))
            allocation = content.get_allocation()
            self.assertEqual((allocation.x, allocation.y), initial)
            handle.emit('button-press-event', event(Gdk.EventType.BUTTON_PRESS, 500, 500, 1))
            for _ in range(12):
                handle.emit('motion-notify-event', event(Gdk.EventType.MOTION_NOTIFY, 550, 450))
            self.assertEqual(state['position'], (initial[0] + 50, initial[1] - 50))
            settle()
            # Same pointer position after rendering must not cause another move.
            handle.emit('motion-notify-event', event(Gdk.EventType.MOTION_NOTIFY, 550, 450))
            self.assertEqual(state['position'], (initial[0] + 50, initial[1] - 50))
            handle.emit('motion-notify-event', event(Gdk.EventType.MOTION_NOTIFY, 500, 500))
            self.assertEqual(state['position'], initial)
            handle.emit('button-release-event', event(Gdk.EventType.BUTTON_RELEASE, 500, 500, 1))
            self.assertIsNone(state['origin'])
            self.assertFalse(handle.emit('motion-notify-event', event(Gdk.EventType.MOTION_NOTIFY, 0, 0)))
            self.assertEqual(state['position'], initial)
            self.assertEqual(window.get_size(), (width, height))
            for edge in (layer.Edge.LEFT, layer.Edge.RIGHT, layer.Edge.TOP, layer.Edge.BOTTOM):
                self.assertEqual(layer.get_margin(window, edge), 0)
            settle()
            a = content.get_allocation()
            self.assertEqual((a.x, a.y), initial)
            # Save a rendered frame for visual inspection without a screenshot portal.
            import cairo
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            window.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/system-keyboard-drag-test.png')
        finally:
            window.destroy()
            settle()
