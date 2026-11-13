"""System input via a Linux uinput keyboard; no alternative input backends."""


class UInputBackend:
    """Access to /dev/uinput must be granted by the administrator."""
    name = 'Linux / uinput'

    def __init__(self):
        try:
            from evdev import UInput, ecodes
        except ImportError as exc:
            raise RuntimeError('Для uinput установите python-evdev (модуль evdev)') from exc
        from .keys import ROWS, KEY_KBD_LAYOUT_NEXT
        self.ecodes = ecodes
        self.device = None
        try:
            self.device = UInput(
                {ecodes.EV_KEY: sorted({code for row in ROWS for _, code in row} | {KEY_KBD_LAYOUT_NEXT})},
                name='System Keyboard', bustype=ecodes.BUS_USB)
        except (OSError, ValueError) as exc:
            raise RuntimeError('Не удалось создать /dev/uinput устройство. Нужны модуль uinput '
                               'и разрешение администратора на доступ к /dev/uinput. '
                               'Не запускайте весь GUI через sudo. Причина: ' + str(exc)) from exc

    def key(self, code, pressed):
        if self.device is None:
            raise RuntimeError('Устройство uinput закрыто')
        self.device.write(self.ecodes.EV_KEY, code, int(pressed))
        self.device.syn()

    def close(self):
        if self.device is not None:
            self.device.close()
            self.device = None
