"""Native CardputerZero Linux Framebuffer (/dev/fb_lcd) & evdev (tca8418c) I/O backend."""
from __future__ import annotations

import os
from pathlib import Path
import select
import struct
import sys
import numpy as np
import pygame


# 64-bit Linux struct input_event: (tv_sec, tv_usec, type, code, value)
INPUT_EVENT_FMT = "<qqHHi"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FMT)
EV_KEY = 0x01

DEFAULT_FB_DEVICE = "/dev/fb_lcd"
FALLBACK_FB_DEVICE = "/dev/fb0"
DEFAULT_KBD_DEVICE = "/dev/input/by-path/platform-3f804000.i2c-event"

# Standard Linux keycodes + M5Stack /usr/share/keymaps/tca8418_keypad_m5stack_keymap.map
_ALPHA_KEYS: dict[int, tuple[str, int]] = {
    16: ("q", pygame.K_q),
    17: ("w", pygame.K_w),
    18: ("e", pygame.K_e),
    19: ("r", pygame.K_r),
    20: ("t", pygame.K_t),
    21: ("y", pygame.K_y),
    22: ("u", pygame.K_u),
    23: ("i", pygame.K_i),
    24: ("o", pygame.K_o),
    25: ("p", pygame.K_p),
    30: ("a", pygame.K_a),
    31: ("s", pygame.K_s),
    32: ("d", pygame.K_d),
    33: ("f", pygame.K_f),
    34: ("g", pygame.K_g),
    35: ("h", pygame.K_h),
    36: ("j", pygame.K_j),
    37: ("k", pygame.K_k),
    38: ("l", pygame.K_l),
    44: ("z", pygame.K_z),
    45: ("x", pygame.K_x),
    46: ("c", pygame.K_c),
    47: ("v", pygame.K_v),
    48: ("b", pygame.K_b),
    49: ("n", pygame.K_n),
    50: ("m", pygame.K_m),
}

_DIGIT_KEYS: dict[int, tuple[str, int]] = {
    2: ("1", pygame.K_1),
    3: ("2", pygame.K_2),
    4: ("3", pygame.K_3),
    5: ("4", pygame.K_4),
    6: ("5", pygame.K_5),
    7: ("6", pygame.K_6),
    8: ("7", pygame.K_7),
    9: ("8", pygame.K_8),
    10: ("9", pygame.K_9),
    11: ("0", pygame.K_0),
}

_CONTROL_KEYS: dict[int, tuple[str, int]] = {
    1: ("", pygame.K_ESCAPE),
    14: ("", pygame.K_BACKSPACE),
    15: ("", pygame.K_TAB),
    28: ("", pygame.K_RETURN),
    57: (" ", pygame.K_SPACE),
    103: ("", pygame.K_UP),
    105: ("", pygame.K_LEFT),
    106: ("", pygame.K_RIGHT),
    108: ("", pygame.K_DOWN),
    111: ("", pygame.K_BACKSPACE),  # Fn+Bksp (Delete)
}

# Verified against /usr/share/keymaps/tca8418_keypad_m5stack_keymap.map on CardputerZero
_M5_SYMBOL_KEYS: dict[int, tuple[str, int]] = {
    26: ("!", pygame.K_EXCLAIM),
    27: ("@", pygame.K_AT),
    39: ("#", pygame.K_HASH),
    40: ("$", pygame.K_DOLLAR),
    41: ("%", getattr(pygame, "K_PERCENT", pygame.K_5)),
    43: ("^", pygame.K_CARET),
    51: ("&", pygame.K_AMPERSAND),
    52: ("*", pygame.K_ASTERISK),
    53: ("(", pygame.K_LEFTPAREN),
    94: (")", pygame.K_RIGHTPAREN),
    55: ("~", pygame.K_UNKNOWN),
    69: ("`", pygame.K_BACKQUOTE),
    70: ("_", pygame.K_UNDERSCORE),
    71: ("-", pygame.K_MINUS),
    72: ("+", pygame.K_PLUS),
    73: ("=", pygame.K_EQUALS),
    74: ("[", pygame.K_LEFTBRACKET),
    75: ("]", pygame.K_RIGHTBRACKET),
    76: ("{", pygame.K_UNKNOWN),
    77: ("}", pygame.K_UNKNOWN),
    79: (";", pygame.K_SEMICOLON),
    80: (":", pygame.K_COLON),
    81: ("'", pygame.K_QUOTE),
    82: ('"', pygame.K_QUOTEDBL),
    83: ("<", pygame.K_LESS),
    85: (">", pygame.K_GREATER),
    86: ("\\", pygame.K_BACKSLASH),
    89: ("|", pygame.K_UNKNOWN),
    90: (",", pygame.K_COMMA),
    91: (".", pygame.K_PERIOD),
    92: ("/", pygame.K_SLASH),
    93: ("?", pygame.K_QUESTION),
}

_SHIFT_KEYCODES = {42, 54}
_SYM_OR_MOD_IGNORE = {29, 56, 58, 383, 389}


def should_use_fbdev(headless: bool = False) -> bool:
    """Return True when running natively on CardputerZero SPI LCD (/dev/fb_lcd)."""
    if headless or not sys.platform.startswith("linux"):
        return False
    if os.environ.get("CP0_WINDOWED") == "1":
        return False
    if os.environ.get("CP0_FORCE_FBDEV") == "1":
        return True
    if os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE") or os.environ.get("LV_LINUX_FBDEV_DEVICE"):
        return True
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return Path(DEFAULT_FB_DEVICE).exists()
    return False


def resolve_fb_device() -> str:
    """Resolve active CardputerZero framebuffer device path."""
    for env_key in ("APPLAUNCH_LINUX_FBDEV_DEVICE", "LV_LINUX_FBDEV_DEVICE"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    if Path(DEFAULT_FB_DEVICE).exists():
        return DEFAULT_FB_DEVICE
    return FALLBACK_FB_DEVICE


def resolve_kbd_device() -> str:
    """Resolve active CardputerZero hardware matrix keyboard evdev path."""
    for env_key in ("APPLAUNCH_LINUX_KEYBOARD_DEVICE", "LV_LINUX_KEYBOARD_DEVICE"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    return DEFAULT_KBD_DEVICE


def decode_evdev_key(code: int, shift: bool = False) -> tuple[int, str] | None:
    """Translate Linux evdev keycode + shift state into (pygame_key, unicode_char)."""
    if code in _CONTROL_KEYS:
        ch, pg_key = _CONTROL_KEYS[code]
        return pg_key, ch
    if code in _ALPHA_KEYS:
        ch, pg_key = _ALPHA_KEYS[code]
        return pg_key, (ch.upper() if shift else ch)
    if code in _DIGIT_KEYS:
        ch, pg_key = _DIGIT_KEYS[code]
        return pg_key, ch
    if code in _M5_SYMBOL_KEYS:
        ch, pg_key = _M5_SYMBOL_KEYS[code]
        return pg_key, ch
    return None


class FbdevBackend:
    """Direct 320x170 RGB565 /dev/fb_lcd renderer + non-blocking tca8418c evdev reader."""

    def __init__(
        self,
        width: int = 320,
        height: int = 170,
        fb_path: str | None = None,
        kbd_path: str | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fb_path = fb_path or resolve_fb_device()
        self.kbd_path = kbd_path or resolve_kbd_device()
        self.fb_fd: int | None = None
        self.kbd_fd: int | None = None
        self.shift_held = False
        self._last_frame: bytes | None = None

        self.fb_fd = os.open(self.fb_path, os.O_RDWR)
        if os.path.exists(self.kbd_path):
            self.kbd_fd = os.open(self.kbd_path, os.O_RDONLY | os.O_NONBLOCK)

    def poll_keys(self, timeout: float = 0.0) -> list[tuple[int, str]]:
        """Read all pending EV_KEY press/repeat events from the hardware keypad."""
        if self.kbd_fd is None:
            if timeout > 0:
                import time
                time.sleep(timeout)
            return []
        events: list[tuple[int, str]] = []
        ready, _, _ = select.select([self.kbd_fd], [], [], timeout)
        if not ready:
            return events

        chunks: list[bytes] = []
        while True:
            try:
                data = os.read(self.kbd_fd, INPUT_EVENT_SIZE * 16)
                if not data:
                    break
                chunks.append(data)
                if len(data) < INPUT_EVENT_SIZE * 16:
                    break
            except BlockingIOError:
                break

        raw = b"".join(chunks)
        for off in range(0, len(raw) - (len(raw) % INPUT_EVENT_SIZE), INPUT_EVENT_SIZE):
            _, _, ev_type, code, value = struct.unpack_from(INPUT_EVENT_FMT, raw, off)
            if ev_type != EV_KEY:
                continue
            if code in _SHIFT_KEYCODES:
                self.shift_held = value in (1, 2)
                continue
            if code in _SYM_OR_MOD_IGNORE:
                continue
            if value not in (1, 2):  # 1=press, 2=repeat, 0=release
                continue
            decoded = decode_evdev_key(code, shift=self.shift_held)
            if decoded is not None:
                events.append(decoded)
        return events

    @staticmethod
    def surface_to_rgb565_bytes(surface: pygame.Surface) -> bytes:
        """Convert an RGB pygame Surface into packed little-endian RGB565 bytes."""
        w, h = surface.get_size()
        raw_fn = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
        arr = np.frombuffer(raw_fn(surface, "RGB"), dtype=np.uint8).reshape((h, w, 3))
        rgb565 = (
            ((arr[:, :, 0].astype(np.uint16) & 0xF8) << 8)
            | ((arr[:, :, 1].astype(np.uint16) & 0xFC) << 3)
            | (arr[:, :, 2].astype(np.uint16) >> 3)
        )
        return rgb565.astype("<u2", copy=False).tobytes()

    def present(self, surface: pygame.Surface) -> None:
        """Convert 320x170 canvas to RGB565 and write into /dev/fb_lcd if changed."""
        if self.fb_fd is None:
            return
        buf = self.surface_to_rgb565_bytes(surface)
        if buf != self._last_frame:
            if hasattr(os, "pwrite"):
                os.pwrite(self.fb_fd, buf, 0)
            else:
                os.lseek(self.fb_fd, 0, os.SEEK_SET)
                os.write(self.fb_fd, buf)
            self._last_frame = buf

    def close(self) -> None:
        """Release framebuffer and keyboard descriptors cleanly."""
        if self.kbd_fd is not None:
            try:
                os.close(self.kbd_fd)
            except OSError:
                pass
            self.kbd_fd = None
        if self.fb_fd is not None:
            try:
                os.close(self.fb_fd)
            except OSError:
                pass
            self.fb_fd = None
