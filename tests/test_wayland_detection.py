import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from system_keyboard.wayland_detection import (
    HyprlandLayout, SwayLayout, command, compositor, detect_layout)
from system_keyboard.windowing import choose_ui


REGISTRY = '''<xkbConfigRegistry><layoutList><layout><configItem>
<name>us</name><description>English (US)</description></configItem>
<variantList><variant><configItem><name>dvorak</name>
<description>English (Dvorak)</description></configItem></variant></variantList>
</layout><layout><configItem><name>ru</name><description>Russian</description>
</configItem></layout></layoutList></xkbConfigRegistry>'''


class WaylandDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Path(self.tmp.name) / 'evdev.xml'
        self.registry.write_text(REGISTRY)
        self.factory = self.enterContext(patch('system_keyboard.wayland_detection.Layout'))
        self.run = self.enterContext(patch('system_keyboard.wayland_detection.command'))

    def test_session_selection(self):
        for name, variable in [('sway', 'SWAYSOCK'), ('hyprland', 'HYPRLAND_INSTANCE_SIGNATURE'),
                               ('niri', 'NIRI_SOCKET')]:
            for env in ({variable: 'socket'}, {'XDG_CURRENT_DESKTOP': 'other:' + name}):
                self.assertEqual(compositor(env), name)
                self.assertEqual(choose_ui('auto', env), 'layer-shell')
                self.assertEqual(choose_ui('x11', env), 'x11')
        with self.assertRaises(RuntimeError):
            detect_layout({})

    def test_sway_refresh_variant_and_cleanup(self):
        self.run.return_value = json.dumps([{'type': 'keyboard', 'xkb_active_layout_name': 'English (US)'}])
        old, new = Mock(), Mock()
        self.factory.side_effect = [old, new]
        layout = SwayLayout(self.registry)
        layout.labels({42})
        self.factory.assert_called_once_with('us', '')
        old.labels.assert_called_once_with({42})
        self.run.return_value = json.dumps([{'type': 'keyboard', 'xkb_active_layout_name': 'English (Dvorak)'}])
        layout.labels()
        self.factory.assert_called_with('us', 'dvorak')
        old.close.assert_called_once()
        layout.close()
        layout.close()
        new.close.assert_called_once()

    def test_sway_rejects_ambiguous_or_missing_layout(self):
        for inputs in ([], [{'type': 'pointer'}], [
                {'type': 'keyboard', 'xkb_active_layout_name': 'Russian'},
                {'type': 'keyboard', 'xkb_active_layout_name': 'English (US)'}]):
            self.run.return_value = json.dumps(inputs)
            with self.assertRaises(RuntimeError):
                SwayLayout(self.registry)
        self.factory.assert_not_called()

    def test_sway_switch_checks_reply(self):
        self.run.return_value = '[{"type":"keyboard","xkb_active_layout_name":"Russian"}]'
        layout = SwayLayout(self.registry)
        self.run.return_value = '[{"success":true}]'
        layout.switch()
        self.run.assert_called_with(['swaymsg', '-r', 'input type:keyboard xkb_switch_layout next'])
        self.run.return_value = '[{"success":false,"error":"failed"}]'
        with self.assertRaises(RuntimeError):
            layout.switch()

    def test_hyprland_uses_main_keyboard_and_ipc_switch(self):
        devices = json.dumps({'keyboards': [
            {'name': 'other', 'main': False, 'active_keymap': 'Russian'},
            {'name': 'main keyboard', 'main': True, 'active_keymap': 'English (US)'}]})
        self.run.return_value = devices
        layout = HyprlandLayout(self.registry)
        self.factory.assert_called_once_with('us', '')
        self.run.side_effect = [devices, 'ok\n']
        layout.switch()
        self.run.assert_called_with(['hyprctl', 'switchxkblayout', 'main keyboard', 'next'])
        self.run.side_effect = [devices, 'error']
        with self.assertRaises(RuntimeError):
            layout.switch()

    def test_missing_main_unknown_name_and_invalid_json(self):
        for response, error in [('{"keyboards":[]}', RuntimeError),
                                ('{"keyboards":[{"main":true,"name":"k","active_keymap":"Custom"}]}', ValueError),
                                ('invalid', ValueError)]:
            self.run.return_value = response
            with self.assertRaises(error):
                HyprlandLayout(self.registry)

    def test_failed_rebuild_preserves_previous_layout(self):
        self.run.return_value = '[{"type":"keyboard","xkb_active_layout_name":"Russian"}]'
        layout = SwayLayout(self.registry)
        previous = layout.layout
        self.factory.side_effect = ValueError('bad keymap')
        self.run.return_value = '[{"type":"keyboard","xkb_active_layout_name":"English (US)"}]'
        with self.assertRaises(ValueError):
            layout.labels()
        previous.close.assert_not_called()
        self.assertEqual(layout.current, ('ru', ''))
        layout.close()

    def test_command_errors_and_timeout(self):
        with patch('system_keyboard.wayland_detection.subprocess.run') as run:
            for error in (FileNotFoundError('missing'), subprocess.TimeoutExpired('cmd', 1),
                          subprocess.CalledProcessError(1, 'cmd')):
                run.side_effect = error
                with self.assertRaises(RuntimeError):
                    command(['cmd'])
            self.assertEqual(run.call_args.kwargs['timeout'], 1)
