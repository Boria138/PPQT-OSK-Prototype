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


def enable_drag(window, handle, ui, Gdk, layer):
    state = {'moved': False, 'origin': None}
    handle.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                      Gdk.EventMask.BUTTON_RELEASE_MASK |
                      Gdk.EventMask.POINTER_MOTION_MASK)

    def press(widget, event):
        if event.button != 1:
            return False
        if ui == 'layer-shell':
            monitor = layer.get_monitor(window)
            if monitor is None:
                monitor = Gdk.Display.get_default().get_monitor(0)
            if monitor is None:
                return False
            width = monitor.get_geometry().width
            x = (layer.get_margin(window, layer.Edge.LEFT) if state['moved']
                 else (width - window.get_size()[0]) // 2)
            y = layer.get_margin(window, layer.Edge.BOTTOM)
            layer.set_margin(window, layer.Edge.LEFT, x)
            layer.set_anchor(window, layer.Edge.LEFT, True)
            # A floating keyboard must not reserve desktop space.
            layer.set_exclusive_zone(window, 0)
        else:
            x, y = window.get_position()
        pointer = ((event.x, event.y) if ui == 'layer-shell'
                   else (event.x_root, event.y_root))
        state['origin'] = (*pointer, x, y)
        state['moved'] = True
        return True

    def motion(widget, event):
        if state['origin'] is None:
            return False
        start_x, start_y, x, y = state['origin']
        if ui == 'layer-shell':
            # Wayland has no global pointer coordinates. Local displacement
            # moves the surface until the handle is back under the pointer.
            dx, dy = round(event.x - start_x), round(event.y - start_y)
            x = layer.get_margin(window, layer.Edge.LEFT)
            y = layer.get_margin(window, layer.Edge.BOTTOM)
            layer.set_margin(window, layer.Edge.LEFT, x + dx)
            layer.set_margin(window, layer.Edge.BOTTOM, y - dy)
        else:
            dx, dy = round(event.x_root - start_x), round(event.y_root - start_y)
            window.move(x + dx, y + dy)
        return True

    def release(widget, event):
        if event.button != 1:
            return False
        state['origin'] = None
        return True

    handle.connect('button-press-event', press)
    handle.connect('motion-notify-event', motion)
    handle.connect('button-release-event', release)
    return state


def configure_window(window, ui, Gdk, layer=None, bottom_margin=0, drag_handle=None):
    drag = (enable_drag(window, drag_handle, ui, Gdk, layer)
            if drag_handle is not None else {'moved': False})
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
        # Float over windows from the first map, without reserving desktop space.
        layer.set_exclusive_zone(window, 0)
        return
    window.set_type_hint(Gdk.WindowTypeHint.DOCK)
    window.set_keep_above(True)
    window.stick()
    display = Gdk.Display.get_default()

    def position(*unused):
        if drag['moved']:
            return
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
