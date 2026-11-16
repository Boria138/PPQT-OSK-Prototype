"""COSMIC layout notifications over Wayland, without focus or OSK ownership."""
import ctypes as C
import ctypes.util
import os
import select

from .layouts import Layout


class Message(C.Structure):
    _fields_ = [('name', C.c_char_p), ('signature', C.c_char_p),
                ('types', C.c_void_p)]


class Interface(C.Structure):
    _fields_ = [('name', C.c_char_p), ('version', C.c_int),
                ('method_count', C.c_int), ('methods', C.POINTER(Message)),
                ('event_count', C.c_int), ('events', C.POINTER(Message))]


class CosmicLayout:
    caps_lock = staticmethod(lambda: False)

    def __init__(self):
        self.display = self.layout = None
        self.group = None
        self.error = None
        self.callbacks, self.proxies = [], []
        self.keyboard = self.manager = self.tracker = None
        self.lib = C.CDLL(C.util.find_library('wayland-client') or 'libwayland-client.so.0')
        p = C.c_void_p
        for name, args, result in (
            ('wl_display_connect', [C.c_char_p], p),
            ('wl_display_disconnect', [p], None),
            ('wl_display_roundtrip', [p], C.c_int),
            ('wl_display_dispatch', [p], C.c_int),
            ('wl_display_dispatch_pending', [p], C.c_int),
            ('wl_display_get_fd', [p], C.c_int),
            ('wl_display_flush', [p], C.c_int),
            ('wl_proxy_destroy', [p], None),
            ('wl_proxy_add_listener', [p, p, p], C.c_int),
            ('wl_proxy_marshal_flags', [p, C.c_uint32, C.POINTER(Interface),
                                        C.c_uint32, C.c_uint32], p),
        ):
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result
        # Keep protocol metadata alive for the entire connection.
        self.group_requests = (Message * 2)(Message(b'set_group', b'u', None),
                                            Message(b'destroy', b'', None))
        self.group_events = (Message * 1)(Message(b'group', b'u', None))
        self.group_interface = Interface(b'zcosmic_keyboard_layout_v1', 1, 2,
                                        self.group_requests, 1, self.group_events)
        self.manager_types = (C.c_void_p * 2)(C.addressof(self.group_interface),
            C.addressof(self._interface('wl_keyboard')))
        self.manager_requests = (Message * 2)(
            Message(b'get_keyboard_layout', b'no', C.cast(self.manager_types, p)),
            Message(b'destroy', b'', None))
        self.manager_interface = Interface(b'zcosmic_keyboard_layout_manager_v1', 1,
                                          2, self.manager_requests, 0, None)
        try:
            self.display = self.lib.wl_display_connect(None)
            if not self.display:
                raise RuntimeError('не удалось подключиться к Wayland')
            registry = self._new(self.display, 1, self._interface('wl_registry'), p())
            self.registry = registry
            self._listen(registry, [
                (self._global, [C.c_uint32, C.c_char_p, C.c_uint32]),
                (lambda *args: None, [C.c_uint32])])
            for _ in range(4):
                self._check(self.lib.wl_display_roundtrip(self.display))
            if self.layout is None or self.group is None:
                raise RuntimeError('нет карты или протокола zcosmic_keyboard_layout_manager_v1')
        except Exception:
            self.close()
            raise

    def _interface(self, name):
        return Interface.in_dll(self.lib, name + '_interface')

    def _new(self, proxy, opcode, interface, *args):
        result = self.lib.wl_proxy_marshal_flags(proxy, opcode, C.byref(interface),
                                                1, 0, *args)
        if not result:
            raise RuntimeError('COSMIC: не удалось создать объект Wayland')
        self.proxies.append(result)
        return result

    def _listen(self, proxy, handlers):
        callbacks = []
        for handler, types in handlers:
            def guarded(data, obj, *args, handler=handler):
                try:
                    handler(*args)
                except Exception as exc:
                    self.error = exc
            callbacks.append(C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, *types)(guarded))
        table = (C.c_void_p * len(callbacks))(*[C.cast(fn, C.c_void_p) for fn in callbacks])
        self.callbacks.append((callbacks, table))
        if self.lib.wl_proxy_add_listener(proxy, table, None) != 0:
            raise RuntimeError('COSMIC: не удалось подписаться на события Wayland')

    def _global(self, name, interface, version):
        if interface == b'wl_seat' and not hasattr(self, 'seat'):
            self.seat = self._new(self.registry, 0, self._interface('wl_seat'),
                                 C.c_uint32(name), interface, C.c_uint32(1), C.c_void_p())
            self._listen(self.seat, [(self._capabilities, [C.c_uint32])])
        elif interface == self.manager_interface.name and self.manager is None:
            self.manager = self._new(self.registry, 0, self.manager_interface,
                                    C.c_uint32(name), interface, C.c_uint32(1), C.c_void_p())
            self._track()

    def _capabilities(self, capabilities):
        if capabilities & 2 and self.keyboard is None:
            self.keyboard = self._new(self.seat, 1, self._interface('wl_keyboard'), C.c_void_p())
            u, p = C.c_uint32, C.c_void_p
            self._listen(self.keyboard, [
                (self._keymap, [u, C.c_int, u]),
                (lambda *args: None, [u, p, p]),
                (lambda *args: None, [u, p]),
                (lambda *args: None, [u, u, u, u]),
                (lambda *args: None, [u, u, u, u, u])])
            self._track()
        elif not capabilities & 2 and self.keyboard is not None:
            self.error = RuntimeError('COSMIC: клавиатура отключена')

    def _track(self):
        if self.keyboard and self.manager and self.tracker is None:
            self.tracker = self._new(self.manager, 0, self.group_interface,
                                     C.c_void_p(), C.c_void_p(self.keyboard))
            self._listen(self.tracker, [(self._group, [C.c_uint32])])

    def _group(self, group):
        self.group = group

    def _keymap(self, format, fd, size):
        try:
            if format != 1 or not 0 < size <= 16 * 1024 * 1024:
                raise RuntimeError('COSMIC: неверная карта Wayland')
            text = os.pread(fd, size, 0)
            if len(text) != size:
                raise RuntimeError('COSMIC: неполная карта Wayland')
            replacement = Layout(keymap_text=text)
        finally:
            os.close(fd)
        if self.layout is not None:
            self.layout.close()
        self.layout = replacement

    def _check(self, result):
        if result < 0:
            raise RuntimeError('COSMIC: соединение Wayland закрыто')
        if self.error is not None:
            raise self.error

    def labels(self, modifiers=()):
        self._check(self.lib.wl_display_dispatch_pending(self.display))
        fd = self.lib.wl_display_get_fd(self.display)
        for _ in range(32):
            if not select.select([fd], [], [], 0)[0]:
                break
            self._check(self.lib.wl_display_dispatch(self.display))
        if self.layout is None or self.group is None:
            raise RuntimeError('COSMIC: раскладка недоступна')
        # Let XKB resolve Caps for this keymap (including Caps+Shift), rather
        # than assuming a fixed Lock modifier bit or uppercasing strings.
        modifiers = set(modifiers)
        if self.caps_lock():
            modifiers.add(58)
        return self.layout.labels(modifiers, mask=(0, 0, 0, self.group))

    def close(self):
        if self.layout is not None:
            self.layout.close()
            self.layout = None
        if self.display:
            for proxy in reversed(self.proxies):
                self.lib.wl_proxy_destroy(proxy)
            self.proxies.clear()
            self.lib.wl_display_disconnect(self.display)
            self.display = None
