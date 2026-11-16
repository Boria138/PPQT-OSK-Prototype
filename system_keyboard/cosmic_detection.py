"""Read COSMIC's keymap and active XKB group via its libei sender socket.

The sender is only used for state notifications; input remains on uinput.
"""
import ctypes as C
import ctypes.util
import os
import select
import time

from .layouts import Layout


def sender_socket():
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    result, descriptors = bus.call_with_unix_fd_list_sync(
        'com.system76.CosmicComp', '/com/system76/CosmicComp/Ei',
        'com.system76.CosmicComp.Ei', 'GetSenderSocket',
        GLib.Variant('(u)', (1,)), GLib.VariantType.new('(h)'),
        Gio.DBusCallFlags.NONE, 2000, None, None)
    return descriptors.get(result.unpack()[0])


def load_libei():
    try:
        lib = C.CDLL(C.util.find_library('ei') or 'libei.so.1')
    except OSError as exc:
        raise RuntimeError('COSMIC: нужна библиотека libei (libei.so.1)') from exc
    pointer = C.c_void_p
    functions = {
        'ei_new_sender': ([pointer], pointer),
        'ei_unref': ([pointer], pointer),
        'ei_configure_name': ([pointer, C.c_char_p], None),
        'ei_setup_backend_fd': ([pointer, C.c_int], C.c_int),
        'ei_get_fd': ([pointer], C.c_int),
        'ei_dispatch': ([pointer], None),
        'ei_get_event': ([pointer], pointer),
        'ei_event_unref': ([pointer], pointer),
        'ei_event_get_type': ([pointer], C.c_int),
        'ei_event_get_seat': ([pointer], pointer),
        'ei_event_get_device': ([pointer], pointer),
        'ei_seat_bind_capabilities': ([pointer], None),  # variadic, zero sentinel
        'ei_device_keyboard_get_keymap': ([pointer], pointer),
        'ei_keymap_get_type': ([pointer], C.c_int),
        'ei_keymap_get_size': ([pointer], C.c_size_t),
        'ei_keymap_get_fd': ([pointer], C.c_int),
    }
    for suffix in ('mods_depressed', 'mods_latched', 'mods_locked', 'group'):
        functions['ei_event_keyboard_get_xkb_' + suffix] = ([pointer], C.c_uint32)
    for name, (args, result) in functions.items():
        try:
            function = getattr(lib, name)
        except AttributeError as exc:
            raise RuntimeError(f'COSMIC: libei не предоставляет {name}') from exc
        function.argtypes, function.restype = args, result
    return lib


class CosmicLayout:
    def __init__(self):
        self.context = self.layout = None
        self.device = None
        self.mask = None
        self.lib = load_libei()
        try:
            self.context = self.lib.ei_new_sender(None)
            if not self.context:
                raise RuntimeError('COSMIC: не удалось создать контекст libei')
            self.lib.ei_configure_name(self.context, b'system-keyboard')
            fd = sender_socket()
            # libei takes ownership of fd, including on failure.
            if self.lib.ei_setup_backend_fd(self.context, fd) != 0:
                raise RuntimeError('COSMIC: не удалось подключить libei')
            deadline = time.monotonic() + 2
            while self.layout is None or self.mask is None:
                self._update()
                remaining = deadline - time.monotonic()
                if self.layout is not None and self.mask is not None:
                    break
                if remaining <= 0:
                    raise RuntimeError('COSMIC: нет карты или состояния клавиатуры libei')
                select.select([self.lib.ei_get_fd(self.context)], [], [], remaining)
        except Exception as exc:
            self.close()
            raise RuntimeError(f'COSMIC: не удалось получить раскладку: {exc}') from exc

    def _event(self, event):
        kind = self.lib.ei_event_get_type(event)
        if kind == 2:  # EI_EVENT_DISCONNECT
            raise RuntimeError('COSMIC: соединение libei закрыто')
        if kind == 3:  # EI_EVENT_SEAT_ADDED
            self.lib.ei_seat_bind_capabilities(
                self.lib.ei_event_get_seat(event), C.c_int(4), C.c_int(0))
        elif kind == 5:  # EI_EVENT_DEVICE_ADDED
            device = self.lib.ei_event_get_device(event)
            keymap = self.lib.ei_device_keyboard_get_keymap(device)
            if not keymap:
                return
            if self.lib.ei_keymap_get_type(keymap) != 1:
                raise RuntimeError('COSMIC: неподдерживаемый формат карты libei')
            size = self.lib.ei_keymap_get_size(keymap)
            if not 0 < size <= 16 * 1024 * 1024:
                raise RuntimeError('COSMIC: неверный размер карты libei')
            text = os.pread(self.lib.ei_keymap_get_fd(keymap), size, 0)
            if len(text) != size:
                raise RuntimeError('COSMIC: неполная карта libei')
            replacement = Layout(keymap_text=text)
            if self.layout is not None:
                self.layout.close()
            self.layout, self.device, self.mask = replacement, device, None
        elif kind == 6 and self.lib.ei_event_get_device(event) == self.device:
            self.layout.close()
            self.layout = self.device = self.mask = None
        elif kind == 9 and self.lib.ei_event_get_device(event) == self.device:
            self.mask = tuple(getattr(self.lib, 'ei_event_keyboard_get_xkb_' + suffix)(event)
                              for suffix in ('mods_depressed', 'mods_latched', 'mods_locked', 'group'))

    def _update(self):
        self.lib.ei_dispatch(self.context)
        for _ in range(1024):
            event = self.lib.ei_get_event(self.context)
            if not event:
                return
            try:
                self._event(event)
            finally:
                self.lib.ei_event_unref(event)
        raise RuntimeError('COSMIC: слишком много событий libei')

    def labels(self, modifiers=()):
        self._update()
        if self.layout is None or self.mask is None:
            raise RuntimeError('COSMIC: состояние клавиатуры недоступно')
        return self.layout.labels(modifiers, mask=self.mask)

    def close(self):
        if self.layout is not None:
            self.layout.close()
            self.layout = None
        if self.context:
            self.lib.ei_unref(self.context)
            self.context = None
