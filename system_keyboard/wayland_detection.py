"""Compositor IPC adapters for layer-shell layout labels."""
import json
import subprocess

from .niri_detection import NiriLayout


def compositor(environment):
    desktop = environment.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
    for name, variable in [('hyprland', 'HYPRLAND_INSTANCE_SIGNATURE'),
                           ('sway', 'SWAYSOCK'), ('niri', 'NIRI_SOCKET')]:
        if environment.get(variable):
            return name
    return next((name for name in ('hyprland', 'sway', 'niri') if name in desktop), None)


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=1, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'Ошибка IPC ({args[0]}): {exc}') from exc


class SwayLayout(NiriLayout):
    def _query_name(self):
        inputs = json.loads(command(['swaymsg', '-t', 'get_inputs', '-r']))
        keyboards = [item for item in inputs if item.get('type') == 'keyboard'
                     and item.get('xkb_active_layout_name')]
        if not keyboards:
            raise RuntimeError('Sway не сообщил раскладку клавиатуры')
        # Never silently display one of several conflicting device layouts.
        names = {item['xkb_active_layout_name'] for item in keyboards}
        if len(names) != 1:
            raise RuntimeError('У клавиатур Sway разные раскладки; задайте --layout')
        return keyboards[0]['xkb_active_layout_name']

    def switch(self):
        result = json.loads(command(['swaymsg', '-r', 'input type:keyboard xkb_switch_layout next']))
        if not result or not all(item.get('success') for item in result):
            raise RuntimeError(f'Sway не переключил раскладку: {result}')


class HyprlandLayout(NiriLayout):
    def _query_name(self):
        data = json.loads(command(['hyprctl', '-j', 'devices']))
        keyboard = next((item for item in data['keyboards'] if item.get('main')), None)
        if keyboard is None or not keyboard.get('active_keymap'):
            raise RuntimeError('Hyprland не сообщил раскладку основной клавиатуры')
        self.keyboard = keyboard['name']
        return keyboard['active_keymap']

    def switch(self):
        self._query_name()
        result = command(['hyprctl', 'switchxkblayout', self.keyboard, 'next'])
        if result.strip() != 'ok':
            raise RuntimeError(f'Hyprland не переключил раскладку: {result.strip()}')


def detect_layout(environment):
    adapter = {'niri': NiriLayout, 'sway': SwayLayout,
               'hyprland': HyprlandLayout}.get(compositor(environment))
    if adapter is None:
        raise RuntimeError('Нет адаптера определения раскладки для этого композитора')
    return adapter()
