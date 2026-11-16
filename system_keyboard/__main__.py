import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description='Системная экранная клавиатура Linux')
    parser.add_argument('--ui', choices=['auto', 'x11', 'layer-shell'], default='auto',
                        help='auto: layer-shell в COSMIC/niri/Sway/Hyprland, X11 в остальных сеансах')
    parser.add_argument('--layout', default='auto', help='auto: раскладка X11, COSMIC/Wayland или IPC niri/Sway/Hyprland; gsettings: подписи по sources/mru-sources; либо фиксированные подписи XKB: ru, us, de и др.')
    parser.add_argument('--variant', default='', help='Вариант XKB, например dvorak')
    parser.add_argument('--switch-shortcut',
                        choices=['next-layout', 'super-space', 'alt-shift', 'ctrl-shift'],
                        default='next-layout', help='Кнопка «Язык»: по умолчанию KEY_KBD_LAYOUT_NEXT')
    parser.add_argument('--bottom-margin', type=int, default=0,
                        help='Дополнительный отступ снизу в пикселях, если панель не определяется')
    args = parser.parse_args()
    if args.bottom_margin < 0:
        parser.error('--bottom-margin не может быть отрицательным')
    if args.layout in ('auto', 'gsettings') and args.variant:
        parser.error('--variant требует явного --layout, например --layout us')
    from .windowing import choose_ui, configure_window
    ui = choose_ui(args.ui, os.environ)
    os.environ['GDK_BACKEND'] = 'wayland' if ui == 'layer-shell' else 'x11'
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    from .backends import UInputBackend
    from .keys import Keyboard, ROWS

    if not Gtk.init_check()[0]:
        print('Нет доступа к графическому сеансу', file=sys.stderr)
        return 1
    switch_shortcut = args.switch_shortcut
    layer = None
    if ui == 'layer-shell':
        try:
            gi.require_version('GtkLayerShell', '0.1')
            from gi.repository import GtkLayerShell
            if GtkLayerShell.is_supported():
                layer = GtkLayerShell
        except (ValueError, ImportError):
            pass
        if layer is None:
            print('Нужны gtk-layer-shell с introspection и поддержка layer-shell в композиторе.',
                  file=sys.stderr)
            return 1

    from .layouts import Layout
    from .detection import X11Layout, is_x11_session
    manual_layout = False
    try:
        if args.layout == 'auto':
            if 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
                from .gsettings_detection import GSettingsLayout
                layout = GSettingsLayout()
            elif ui == 'layer-shell':
                from .wayland_detection import detect_layout
                from .manual_layout import ManualLayout
                try:
                    layout = detect_layout(os.environ)
                except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
                    print(f'{exc}. Используется ручной режим US/RU.', file=sys.stderr)
                    layout = ManualLayout()
                    manual_layout = True
            else:
                layout = X11Layout()
        elif args.layout == 'gsettings':
            from .gsettings_detection import GSettingsLayout
            layout = GSettingsLayout()
        else:
            layout = Layout(args.layout, args.variant)
    except Exception as exc:
        print(f'Не удалось загрузить XKB: {exc}', file=sys.stderr)
        return 1
    try:
        backend = UInputBackend()
    except Exception as exc:
        layout.close()
        print(f'Не удалось подключить ввод: {exc}', file=sys.stderr)
        return 1
    from .gsettings_detection import GSettingsLayout
    keyboard = Keyboard(backend)
    window = Gtk.Window(title='System Keyboard')
    window.set_default_size(1000, 310)
    drag_handle = Gtk.EventBox()
    drag_handle.add(Gtk.Label(label='⠿ Перетащите, чтобы переместить клавиатуру'))
    configure_window(window, ui, Gdk, layer, args.bottom_margin, drag_handle)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    root.set_border_width(8)
    window.add(root)
    root.pack_start(drag_handle, False, False, 0)
    status = Gtk.Label(label=backend.name + ' · раскладка системы · модификаторы на одно нажатие')
    if isinstance(layout, GSettingsLayout):
        status.set_text(backend.name + ' · подписи по истории GSettings, не состояние Shell')
    if manual_layout:
        status.set_text(backend.name + ' · подписи: US · ручной режим US/RU')
    root.pack_start(status, False, False, 0)
    buttons = {}

    def refresh():
        # Ctrl/Alt shortcuts must not turn printable labels into control characters.
        try:
            caps_lock = (layout.caps_lock() if isinstance(layout, X11Layout)
                         and is_x11_session(os.environ) else backend.caps_lock())
            modifiers = keyboard.held & {42, 100}
            if caps_lock:
                modifiers.add(58)
            labels = layout.labels(modifiers)
        except Exception as exc:
            status.set_text(f'Ошибка определения раскладки: {exc}')
            return True
        for code, button in buttons.items():
            active = caps_lock if code == 58 else code in keyboard.held
            text = ('● ' if active else '') + labels.get(str(code), button.original_label)
            if button.get_label() != text:
                button.set_label(text)
        return True

    def tap(button, code):
        try:
            if (code == 58 and isinstance(layout, X11Layout)
                    and is_x11_session(os.environ)):
                layout.toggle_caps_lock()
            else:
                keyboard.tap(code)
        except Exception as exc:
            status.set_text(str(exc))
        refresh()

    for row in ROWS:
        box = Gtk.Box(spacing=4, homogeneous=False)
        root.pack_start(box, True, True, 0)
        for label, code in row:
            button = Gtk.Button(label=label)
            button.original_label = label
            button.set_can_focus(False)
            button.set_size_request(48, 44)
            button.connect('clicked', tap, code)
            box.pack_start(button, True, True, 0)
            if label == 'Space':
                button.set_size_request(300, 44)
            buttons[code] = button
    footer = Gtk.Box(spacing=6)
    root.pack_start(footer, False, False, 0)
    language = Gtk.Button(label='Язык ⟳')
    language.set_can_focus(False)
    language.set_tooltip_text(
        'Переключить раскладку: сочетание из GSettings'
        if isinstance(layout, GSettingsLayout) and switch_shortcut == 'next-layout'
        else f'Переключить системную раскладку: {switch_shortcut}')

    def switch_language(*unused):
        try:
            if (isinstance(layout, X11Layout) and is_x11_session(os.environ)
                    and switch_shortcut == 'next-layout'):
                layout.switch()
            elif (not manual_layout and hasattr(layout, 'switch')
                  and not isinstance(layout, X11Layout)):
                layout.switch()
            elif isinstance(layout, GSettingsLayout) and switch_shortcut == 'next-layout':
                keyboard.switch_layout(layout.switch_codes())
            else:
                keyboard.switch_layout(switch_shortcut)
            if manual_layout:
                layout.switch()
                status.set_text(backend.name + ' · подписи: ' + layout.language.upper()
                                + ' · ручной режим, без определения системной раскладки')
        except Exception as exc:
            status.set_text(f'Не удалось переключить раскладку: {exc}')
        refresh()  # The auto-mode timer also catches asynchronous compositor changes.

    language.connect('clicked', switch_language)
    footer.pack_start(language, False, False, 0)
    reset = Gtk.Button(label='Отпустить модификаторы')
    reset.set_can_focus(False)

    def release(*unused):
        try:
            keyboard.release()
        except Exception as exc:
            status.set_text(str(exc))
        refresh()

    reset.connect('clicked', release)
    footer.pack_start(reset, True, True, 0)
    close = Gtk.Button(label='Закрыть')
    close.set_can_focus(False)
    close.connect('clicked', lambda *_: window.destroy())
    footer.pack_start(close, False, False, 0)
    window.connect('destroy', lambda *_: Gtk.main_quit())
    refresh()
    if ui == 'layer-shell':
        from .layer_drag import install
        install(window, drag_handle, layer, args.bottom_margin)
    window.show_all()
    timer = GLib.timeout_add(150, refresh) if args.layout in ('auto', 'gsettings') else None
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    finally:
        if timer is not None:
            GLib.source_remove(timer)
        try:
            keyboard.release()
        finally:
            try:
                backend.close()
            finally:
                layout.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
