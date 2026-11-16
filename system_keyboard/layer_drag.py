"""Move panel content, never the Wayland coordinate system receiving the drag."""


def panel_position(width, height, panel_width, panel_height, x, y):
    return (max(0, min(round(x), max(0, width - panel_width))),
            max(0, min(round(y), max(0, height - panel_height))))


def install(window, handle, layer, bottom_margin=0):
    import cairo
    from gi.repository import Gtk, Gdk, GLib

    content = window.get_child()
    window.remove(content)
    fixed = Gtk.Fixed()
    window.add(fixed)
    fixed.put(content, 0, 0)
    window.set_app_paintable(True)
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)
    # Draw the panel background only, not the monitor-sized input host.
    def draw(widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False
    window.connect('draw', draw)
    content.get_style_context().add_class('background')

    def draw_panel(widget, cr):
        Gtk.render_background(widget.get_style_context(), cr, 0, 0,
                              widget.get_allocated_width(), widget.get_allocated_height())
        return False

    content.connect('draw', draw_panel)
    for edge in (layer.Edge.LEFT, layer.Edge.RIGHT, layer.Edge.TOP, layer.Edge.BOTTOM):
        layer.set_anchor(window, edge, True)
        layer.set_margin(window, edge, 0)
    layer.set_exclusive_zone(window, -1)
    state = {'position': None, 'origin': None, 'moved': False}

    def size():
        width, height = fixed.get_allocated_width(), fixed.get_allocated_height()
        minimum, natural = content.get_preferred_size()
        return width, height, min(width, max(1000, minimum.width)), min(height, natural.height)

    def place(x, y):
        width, height, pw, ph = size()
        x, y = panel_position(width, height, pw, ph, x, y)
        state['position'] = (x, y)
        if content.get_size_request() != (pw, ph):
            content.set_size_request(pw, ph)
        if (fixed.child_get_property(content, 'x'),
                fixed.child_get_property(content, 'y')) != (x, y):
            fixed.move(content, x, y)
        return x, y

    def allocated(*_):
        width, height, pw, ph = size()
        if not state['moved']:
            place((width - pw) // 2, height - ph - bottom_margin)
        else:
            place(*state['position'])

    def input_region(*_):
        native = window.get_window()
        if native is not None:
            a = content.get_allocation()
            border = content.get_border_width()
            native.input_shape_combine_region(cairo.Region(
                cairo.RectangleInt(a.x - border, a.y - border,
                                   a.width + 2 * border, a.height + 2 * border)), 0, 0)

    pending = [None]

    def update_layout():
        pending[0] = None
        allocated()
        return False

    def queue_layout(*_):
        if pending[0] is None:
            pending[0] = GLib.idle_add(update_layout)

    def destroyed(*_):
        if pending[0] is not None:
            GLib.source_remove(pending[0])
            pending[0] = None

    window.connect('destroy', destroyed)
    fixed.connect('size-allocate', queue_layout)
    content.connect('size-allocate', input_region)
    handle.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                      Gdk.EventMask.BUTTON_RELEASE_MASK |
                      Gdk.EventMask.POINTER_MOTION_MASK)

    def press(widget, event):
        if event.button != 1 or state['position'] is None:
            return False
        state['moved'] = True
        state['origin'] = (*event.get_root_coords(), *state['position'])
        return True

    def motion(widget, event):
        if state['origin'] is None:
            return False
        sx, sy, x, y = state['origin']
        px, py = event.get_root_coords()
        place(x + px - sx, y + py - sy)
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
