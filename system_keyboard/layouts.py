"""Generate labels from the installed XKB database, not a hand-written language list."""
import argparse
import ctypes as C
import ctypes.util
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from .keys import ROWS, MODIFIERS


class Names(C.Structure):
    _fields_ = [(name, C.c_char_p) for name in ('rules', 'model', 'layout', 'variant', 'options')]


def available_layouts(registry='/usr/share/X11/xkb/rules/evdev.xml'):
    result = []
    for layout in ET.parse(registry).findall('./layoutList/layout'):
        name = layout.findtext('./configItem/name')
        result.append((name, ''))
        for variant in layout.findall('./variantList/variant'):
            result.append((name, variant.findtext('./configItem/name')))
    return result


class Layout:
    def __init__(self, layout='us', variant='', *, keymap_text=None):
        self.context = self.keymap = None
        self.lib = C.CDLL(C.util.find_library('xkbcommon') or 'libxkbcommon.so.0')
        functions = {
            'xkb_context_new': ([C.c_int], C.c_void_p),
            'xkb_context_unref': ([C.c_void_p], None),
            'xkb_keymap_new_from_names': ([C.c_void_p, C.POINTER(Names), C.c_int], C.c_void_p),
            'xkb_keymap_new_from_string': ([C.c_void_p, C.c_char_p, C.c_int, C.c_int], C.c_void_p),
            'xkb_state_update_mask': ([C.c_void_p] + [C.c_uint] * 6, C.c_uint),
            'xkb_keymap_unref': ([C.c_void_p], None),
            'xkb_state_new': ([C.c_void_p], C.c_void_p),
            'xkb_state_unref': ([C.c_void_p], None),
            'xkb_state_update_key': ([C.c_void_p, C.c_uint, C.c_int], C.c_uint),
            'xkb_state_key_get_utf8': ([C.c_void_p, C.c_uint, C.c_void_p, C.c_size_t], C.c_int),
            'xkb_state_key_get_one_sym': ([C.c_void_p, C.c_uint], C.c_uint),
            'xkb_keysym_get_name': ([C.c_uint, C.c_void_p, C.c_size_t], C.c_int),
        }
        for name, (args, result) in functions.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.context = self.lib.xkb_context_new(0)
        if not self.context:
            raise RuntimeError('Не удалось создать контекст XKB')
        names = Names(None, b'pc105', layout.encode(), variant.encode(), b'')
        if keymap_text is None:
            self.keymap = self.lib.xkb_keymap_new_from_names(self.context, C.byref(names), 0)
        else:
            self.keymap = self.lib.xkb_keymap_new_from_string(self.context, keymap_text, 1, 0)
        if not self.keymap:
            self.close()
            raise ValueError(f'Неизвестная раскладка XKB: {layout}+{variant}')

    def labels(self, modifiers=(), *, mask=None):
        state = self.lib.xkb_state_new(self.keymap)
        if not state:
            raise RuntimeError('Не удалось создать состояние XKB')
        try:
            if mask is not None:
                depressed, latched, locked, group = mask
                self.lib.xkb_state_update_mask(state, depressed, latched, locked, 0, 0, group)
            for code in modifiers:
                self.lib.xkb_state_update_key(state, code + 8, 1)
            labels = {}
            for row in ROWS:
                for fallback, code in row:
                    if code in MODIFIERS or code in {1, 14, 15, 28, 58, 57, 103, 105, 106, 108, 111}:
                        labels[str(code)] = fallback
                        continue
                    buffer = C.create_string_buffer(128)
                    length = self.lib.xkb_state_key_get_utf8(state, code + 8, buffer, len(buffer))
                    label = buffer.value.decode() if 0 < length < len(buffer) else ''
                    if not label or not label.isprintable():
                        sym = self.lib.xkb_state_key_get_one_sym(state, code + 8)
                        self.lib.xkb_keysym_get_name(sym, buffer, len(buffer))
                        label = buffer.value.decode() or fallback
                    labels[str(code)] = label
            return labels
        finally:
            self.lib.xkb_state_unref(state)

    def export(self):
        return {name: self.labels(mods) for name, mods in
                [('normal', ()), ('shift', (42,)), ('altgr', (100,)), ('shift-altgr', (42, 100))]}

    def close(self):
        if self.keymap:
            self.lib.xkb_keymap_unref(self.keymap)
            self.keymap = None
        if self.context:
            self.lib.xkb_context_unref(self.context)
            self.context = None


def main():
    parser = argparse.ArgumentParser(description='Подписи клавиш из системной базы XKB')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--all', action='store_true', help='Экспортировать все раскладки и варианты')
    parser.add_argument('--layout', default='us', help='XKB layout, например ru, de, fr')
    parser.add_argument('--variant', default='')
    parser.add_argument('--output', type=Path, help='Файл JSON с подписями клавиш')
    args = parser.parse_args()
    if args.list:
        for name, variant in available_layouts():
            print(name + ('+' + variant if variant else ''))
        return
    choices = available_layouts() if args.all else [(args.layout, args.variant)]
    result = {}
    for name, variant in choices:
        try:
            layout = Layout(name, variant)
        except ValueError as exc:
            if not args.all:
                raise
            print(f'Пропущена недоступная запись реестра: {exc}', file=sys.stderr)
            continue
        try:
            result[name + ('+' + variant if variant else '')] = layout.export()
        finally:
            layout.close()
    text = json.dumps(result, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + '\n')
    else:
        print(text)


if __name__ == '__main__':
    main()
