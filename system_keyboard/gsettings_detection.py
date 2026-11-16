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
        self.layout = None
        self.current = None
        self._update()

    def _source(self):
        sources = self.settings.get_value('sources').unpack()
        index = self.settings.get_uint('current')
        if not sources or not 0 <= index < len(sources):
            raise ValueError('GSettings: нет источников ввода или неверный индекс current')
        kind, name = sources[index]
        if kind != 'xkb':
            raise ValueError(f'GSettings: источник {kind} не поддерживается')
        layout, separator, variant = name.partition('+')
        if not layout:
            raise ValueError('GSettings: пустое имя раскладки XKB')
        return (layout, variant), sources, index

    def _update(self):
        choice, _, _ = self._source()
        if choice != self.current:
            replacement = Layout(*choice)
            if self.layout is not None:
                self.layout.close()
            self.layout = replacement
            self.current = choice

    def labels(self, modifiers=()):
        self._update()
        return self.layout.labels(modifiers)

    def switch(self):
        _, sources, index = self._source()
        next_index = (index + 1) % len(sources)
        if sources[next_index][0] != 'xkb':
            raise ValueError('GSettings: следующий источник не является XKB')
        if not self.settings.set_uint('current', next_index):
            raise RuntimeError('GSettings: не удалось изменить current')
        self._update()

    def close(self):
        if self.layout is not None:
            self.layout.close()
            self.layout = None
