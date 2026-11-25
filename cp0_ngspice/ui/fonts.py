"""Font resolver aligned with cp0-dev typography guidelines (>=12px, Noto/JetBrains/DejaVu)."""
from __future__ import annotations

from pathlib import Path
import pygame


_LINUX_CJK_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-DemiLight.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)

_LINUX_MONO_CANDIDATES = (
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)

_LINUX_SANS_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

_WIN_FONT_DIR = Path(r"C:\Windows\Fonts")
_WIN_SANS_FILES = ("msyh.ttc", "segoeui.ttf", "arial.ttf")
_WIN_MONO_FILES = ("consola.ttf", "cour.ttf")


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


class FontPack:
    def __init__(self) -> None:
        self.ui_xs = self._load_sans(11, bold=False)
        self.ui_sm = self._load_sans(12, bold=False)
        self.ui_md = self._load_sans(13, bold=True)
        self.mono_sm = self._load_mono(12, bold=False)
        self.mono_xs = self._load_mono(11, bold=False)
        self._cjk_cache: dict[str, bool] = {}
        self._fit_cache: dict[tuple[int, str, int], str] = {}
        self._surf_cache: dict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = {}

    def pick(self, text: str, size: str = "xs", bold: bool = False) -> pygame.font.Font:
        """Return CJK-capable Sans font automatically whenever text contains Chinese glyphs."""
        if bold or size == "md":
            return self.ui_md
        is_cjk = self._cjk_cache.get(text)
        if is_cjk is None:
            is_cjk = has_cjk(text)
            if len(self._cjk_cache) > 1024:
                self._cjk_cache.clear()
            self._cjk_cache[text] = is_cjk
        if is_cjk:
            return self.ui_sm if size == "sm" else self.ui_xs
        if size == "sm":
            return self.mono_sm
        return self.mono_xs

    def fit_text(self, font: pygame.font.Font, text: str, max_px: int) -> str:
        key = (id(font), text, max_px)
        cached = self._fit_cache.get(key)
        if cached is not None:
            return cached
        if font.size(text)[0] <= max_px:
            res = text
        else:
            cur = text
            while len(cur) > 3 and font.size(cur + "..")[0] > max_px:
                cur = cur[:-1]
            res = cur + ".."
        if len(self._fit_cache) > 1024:
            self._fit_cache.clear()
        self._fit_cache[key] = res
        return res

    def render_cached(
        self, font: pygame.font.Font, text: str, color: tuple[int, int, int]
    ) -> pygame.Surface:
        key = (id(font), text, color)
        surf = self._surf_cache.get(key)
        if surf is not None:
            return surf
        surf = font.render(text, True, color)
        if len(self._surf_cache) > 512:
            self._surf_cache.clear()
        self._surf_cache[key] = surf
        return surf

    @staticmethod
    def _first_existing(paths: tuple[str, ...]) -> str | None:
        for p in paths:
            if Path(p).exists():
                return p
        return None

    def _load_sans(self, size: int, bold: bool) -> pygame.font.Font:
        fp = self._first_existing(_LINUX_CJK_CANDIDATES + _LINUX_SANS_CANDIDATES)
        if not fp and _WIN_FONT_DIR.exists():
            fp = self._first_existing(tuple(str(_WIN_FONT_DIR / f) for f in _WIN_SANS_FILES))
        if fp:
            font = pygame.font.Font(fp, size)
            font.set_bold(bold)
            return font
        return pygame.font.Font(None, size)

    def _load_mono(self, size: int, bold: bool) -> pygame.font.Font:
        fp = self._first_existing(_LINUX_MONO_CANDIDATES)
        if not fp and _WIN_FONT_DIR.exists():
            fp = self._first_existing(tuple(str(_WIN_FONT_DIR / f) for f in _WIN_MONO_FILES))
        if fp:
            font = pygame.font.Font(fp, size)
            font.set_bold(bold)
            return font
        return pygame.font.Font(None, size)
