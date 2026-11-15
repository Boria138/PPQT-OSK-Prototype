"""Live labels from the X server's keymap and current XKB group/state."""
import ctypes as C
import ctypes.util

from .keys import ROWS, MODIFIERS


def is_x11_session(environment):
    session = environment.get('XDG_SESSION_TYPE')
    if session:
        return session == 'x11'
    return bool(environment.get('DISPLAY')) and not environment.get('WAYLAND_DISPLAY')


class XkbState(C.Structure):
    _fields_ = [('group', C.c_ubyte), ('locked_group', C.c_ubyte),
                ('base_group', C.c_ushort), ('latched_group', C.c_ushort),
                *[(name, C.c_ubyte) for name in (
                    'mods', 'base_mods', 'latched_mods', 'locked_mods',
                    'compat_state', 'grab_mods', 'compat_grab_mods',
                    'lookup_mods', 'compat_lookup_mods')],
                ('ptr_buttons', C.c_ushort)]


class X11Layout:
    def __init__(self):
        from gi.repository import Gdk
        self.Gdk = Gdk
        self.keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        self.lib = C.CDLL(C.util.find_library('X11') or 'libX11.so.6')
        self.lib.XOpenDisplay.argtypes = [C.c_char_p]
        self.lib.XOpenDisplay.restype = C.c_void_p
        self.lib.XCloseDisplay.argtypes = [C.c_void_p]
        self.lib.XkbGetState.argtypes = [C.c_void_p, C.c_uint, C.POINTER(XkbState)]
        self.lib.XkbGetState.restype = C.c_int
        self.lib.XkbLockGroup.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        self.lib.XkbLockGroup.restype = C.c_int
        self.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        self.lib.XSync.restype = C.c_int
        self.display = self.lib.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError('Не удалось открыть X11 для определения раскладки')

    def switch(self):
        """Advance the core keyboard group; the server wraps to configured groups."""
        state = XkbState()
        if self.lib.XkbGetState(self.display, 0x0100, C.byref(state)) != 0:
            raise RuntimeError('Не удалось получить текущую раскладку XKB')
        if not self.lib.XkbLockGroup(self.display, 0x0100, (state.group + 1) % 4):
            raise RuntimeError('Не удалось переключить раскладку XKB')
        self.lib.XSync(self.display, False)

    def labels(self, modifiers=()):
        state = XkbState()
        # XkbUseCoreKbd = 0x0100; Success = 0.
        if self.lib.XkbGetState(self.display, 0x0100, C.byref(state)) != 0:
            raise RuntimeError('Не удалось получить текущую раскладку XKB')
        Gdk = self.Gdk
        # Exclude Ctrl/Alt/Super: labels should describe printable characters.
        mask = state.mods & int(Gdk.ModifierType.SHIFT_MASK |
                                Gdk.ModifierType.LOCK_MASK | Gdk.ModifierType.MOD5_MASK)
        if 42 in modifiers:
            mask |= int(Gdk.ModifierType.SHIFT_MASK)
        if 100 in modifiers:
            mask |= int(Gdk.ModifierType.MOD5_MASK)
        result = {}
        special = MODIFIERS | {1, 14, 15, 28, 58, 57, 103, 105, 106, 108, 111}
        for row in ROWS:
            for fallback, code in row:
                label = fallback
                if code not in special:
                    success, keyval, *_ = self.keymap.translate_keyboard_state(
                        code + 8, Gdk.ModifierType(mask), state.group)
                    if success:
                        unicode = Gdk.keyval_to_unicode(keyval)
                        character = chr(unicode) if unicode else ''
                        label = character if character and character.isprintable() else (
                            Gdk.keyval_name(keyval) or fallback)
                result[str(code)] = label
        return result

    def close(self):
        if self.display:
            self.lib.XCloseDisplay(self.display)
            self.display = None
