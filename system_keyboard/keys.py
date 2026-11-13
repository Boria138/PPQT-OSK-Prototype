"""Linux evdev keycodes. Layout is selected by the destination desktop."""
ROWS = [
    [('Esc', 1), ('1', 2), ('2', 3), ('3', 4), ('4', 5), ('5', 6), ('6', 7), ('7', 8), ('8', 9), ('9', 10), ('0', 11), ('-', 12), ('=', 13), ('⌫', 14)],
    [('Tab', 15), ('Q', 16), ('W', 17), ('E', 18), ('R', 19), ('T', 20), ('Y', 21), ('U', 22), ('I', 23), ('O', 24), ('P', 25), ('[', 26), (']', 27), ('\\', 43)],
    [('Caps', 58), ('A', 30), ('S', 31), ('D', 32), ('F', 33), ('G', 34), ('H', 35), ('J', 36), ('K', 37), ('L', 38), (';', 39), ("'", 40), ('Enter', 28)],
    [('Shift', 42), ('Z', 44), ('X', 45), ('C', 46), ('V', 47), ('B', 48), ('N', 49), ('M', 50), (',', 51), ('.', 52), ('/', 53), ('↑', 103)],
    [('Ctrl', 29), ('Super', 125), ('Alt', 56), ('Space', 57), ('AltGr', 100), ('←', 105), ('↓', 108), ('→', 106), ('Del', 111)],
]
MODIFIERS = {42, 29, 125, 56, 100}
KEY_KBD_LAYOUT_NEXT = 584
SWITCH_SHORTCUTS = {
    'next-layout': (KEY_KBD_LAYOUT_NEXT,),
    'super-space': (125, 57),
    'alt-shift': (56, 42),
    'ctrl-shift': (29, 42),
}


class Keyboard:
    """Sticky modifiers allow mouse/touch shortcuts without holding two keys."""

    def __init__(self, backend):
        self.backend = backend
        self.held = set()

    def tap(self, code):
        if code in MODIFIERS:
            if code in self.held:
                self.backend.key(code, False)
                self.held.remove(code)
            else:
                self.backend.key(code, True)
                self.held.add(code)
            return
        try:
            self.backend.key(code, True)
        finally:
            try:
                self.backend.key(code, False)
            finally:
                self.release()

    def switch_layout(self, shortcut='next-layout'):
        """Send the configured desktop shortcut, not merely change labels."""
        codes = SWITCH_SHORTCUTS[shortcut]
        self.release()
        try:
            for code in codes:
                self.tap(code)
        finally:
            self.release()

    def release(self):
        errors = []
        for code in tuple(self.held):
            try:
                self.backend.key(code, False)
                self.held.remove(code)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
