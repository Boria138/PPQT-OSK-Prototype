"""Frontend selection and bottom-edge placement."""


def choose_ui(requested, environment):
    if requested != 'auto':
        return requested
    from .wayland_detection import compositor
    return 'layer-shell' if compositor(environment) else 'x11'


def bottom_geometry(x, y, width, height, keyboard_height, bottom_margin=0):
    height = max(1, height - bottom_margin)
    keyboard_height = min(height, keyboard_height)
    keyboard_width = min(width, 1000)
    return (x + (width - keyboard_width) // 2,
            y + height - keyboard_height, keyboard_width, keyboard_height)


def configure_window(window, ui, Gdk, layer=None, bottom_margin=0):
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_accept_focus(False)
    window.set_focus_on_map(False)
    if ui == 'layer-shell':
        layer.init_for_window(window)
        layer.set_layer(window, layer.Layer.TOP)
        # With neither horizontal edge anchored, layer-shell centers the surface.
        layer.set_anchor(window, layer.Edge.BOTTOM, True)
        layer.set_anchor(window, layer.Edge.LEFT, False)
        layer.set_anchor(window, layer.Edge.RIGHT, False)
        layer.set_margin(window, layer.Edge.BOTTOM, 0)
        if bottom_margin:
            layer.set_margin(window, layer.Edge.BOTTOM, bottom_margin)
        layer.set_keyboard_mode(window, layer.KeyboardMode.NONE)
        layer.auto_exclusive_zone_enable(window)
        return
    window.set_type_hint(Gdk.WindowTypeHint.DOCK)
    window.set_keep_above(True)
    window.stick()
    display = Gdk.Display.get_default()

    def position(*unused):
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return
        rect = monitor.get_workarea()
        height = max(310, window.get_size()[1])
        x, y, width, height = bottom_geometry(
            rect.x, rect.y, rect.width, rect.height, height, bottom_margin)
        if window.get_size() != (width, height):
            window.resize(width, height)
        if window.get_position() != (x, y):
            window.move(x, y)

    window.connect('map', position)
    window.connect('size-allocate', position)
    screen = window.get_screen()
    monitor_signal = screen.connect('monitors-changed', position)
    window.connect('destroy', lambda *_: screen.disconnect(monitor_signal))
    position()
