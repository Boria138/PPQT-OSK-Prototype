"""Active niri layout labels resolved against the installed XKB registry."""
import json
import subprocess
import xml.etree.ElementTree as ET

from .layouts import Layout


class NiriLayout:
    def __init__(self, registry='/usr/share/X11/xkb/rules/evdev.xml'):
        self.names = {}
        for entry in ET.parse(registry).findall('./layoutList/layout'):
            code = entry.findtext('./configItem/name')
            self.names[entry.findtext('./configItem/description')] = (code, '')
            for variant in entry.findall('./variantList/variant'):
                self.names[variant.findtext('./configItem/description')] = (
                    code, variant.findtext('./configItem/name'))
        self.layout = None
        self.current = None
        self._update()

    def _update(self):
        try:
            result = subprocess.run(
                ['niri', 'msg', '--json', 'keyboard-layouts'],
                capture_output=True, text=True, timeout=1, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f'Не удалось запросить раскладку через niri IPC: {exc}') from exc
        data = json.loads(result.stdout)
        index = data['current_idx']
        if type(index) is not int or not 0 <= index < len(data['names']):
            raise ValueError('Некорректный индекс раскладки niri')
        name = data['names'][index]
        if name not in self.names:
            raise ValueError(f'Раскладка niri отсутствует в реестре XKB: {name}')
        choice = self.names[name]
        if choice != self.current:
            replacement = Layout(*choice)
            if self.layout is not None:
                self.layout.close()
            self.layout = replacement
            self.current = choice

    def labels(self, modifiers=()):
        self._update()
        return self.layout.labels(modifiers)

    def close(self):
        if self.layout is not None:
            self.layout.close()
            self.layout = None
