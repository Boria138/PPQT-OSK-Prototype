"""Explicit GSettings input-source adapter (not compositor state detection)."""
from .layouts import Layout


class GSettingsLayout:
    def __init__(self):
        from gi.repository import Gio
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup('org.gnome.desktop.input-sources', True) if source else None
        if schema is None:
            raise RuntimeError('Не установлена схема org.gnome.desktop.input-sources')
        self.settings = Gio.Settings.new_full(schema, None, None)
        description = schema.get_key('current').get_description() or ''
        self.legacy_current = ('zero-based index' in description.lower()
                               and 'deprecated' not in description.lower())
        bindings_schema = source.lookup('org.gnome.desktop.wm.keybindings', True)
        if bindings_schema is None:
            raise RuntimeError('Не установлена схема org.gnome.desktop.wm.keybindings')
        self.bindings = Gio.Settings.new_full(bindings_schema, None, None)
        self.layout = None
        self.current = None
        self._update()

    def _source(self):
        sources = self.settings.get_value('sources').unpack()
        if self.settings.get_boolean('per-window'):
            raise ValueError('GSettings: определение активной раскладки для каждого окна не поддерживается')
        if not sources:
            raise ValueError('GSettings: нет источников ввода')
        recent = self.settings.get_value('mru-sources').unpack() if not self.legacy_current else []
        if self.legacy_current:
            index = self.settings.get_uint('current')
            if not 0 <= index < len(sources):
                raise ValueError('GSettings: неверный индекс current')
            selected = sources[index]
        elif len(sources) == 1:
            selected = sources[0]
        elif recent and recent[0] in sources:
            selected = recent[0]
        else:
            raise ValueError('GSettings: последний выбранный источник неизвестен')
        kind, name = selected
        if kind != 'xkb':
            raise ValueError(f'GSettings: источник {kind} не поддерживается')
        layout, separator, variant = name.partition('+')
        if not layout:
            raise ValueError('GSettings: пустое имя раскладки XKB')
        return layout, variant

    def _update(self):
        choice = self._source()
        if choice != self.current:
            replacement = Layout(*choice)
            if self.layout is not None:
                self.layout.close()
            self.layout = replacement
            self.current = choice

    def labels(self, modifiers=()):
        self._update()
        return self.layout.labels(modifiers)

    def switch_codes(self):
        """Resolve a configured GTK accelerator to Linux evdev keycodes."""
        from gi.repository import Gdk, Gtk
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        masks = [(Gdk.ModifierType.CONTROL_MASK, 29),
                 (Gdk.ModifierType.MOD1_MASK, 56),
                 (Gdk.ModifierType.SHIFT_MASK, 42),
                 (Gdk.ModifierType.SUPER_MASK, 125)]
        supported = 0
        for mask, _ in masks:
            supported |= int(mask)
        for accelerator in self.bindings.get_strv('switch-input-source'):
            keyval, modifiers = Gtk.accelerator_parse(accelerator)
            if not keyval or int(modifiers) & ~supported:
                continue
            found, entries = keymap.get_entries_for_keyval(keyval)
            if not found:
                continue
            entry = next((entry for entry in entries
                          if entry.level == 0 and 8 <= entry.keycode <= 775), None)
            if entry is not None:
                return tuple(code for mask, code in masks if modifiers & mask) + (entry.keycode - 8,)
        raise RuntimeError('GSettings: нет доступного сочетания switch-input-source')

    def close(self):
        if self.layout is not None:
            self.layout.close()
            self.layout = None
